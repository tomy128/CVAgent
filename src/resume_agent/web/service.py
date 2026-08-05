"""Single-user Run lifecycle service shared by the Web routes."""

import json
import logging
import multiprocessing
import os
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from resume_agent.backends import HeuristicBackend, LangChainBackend
from resume_agent.evidence import load_evidence, read_text_file
from resume_agent.output import write_artifacts, write_failure_artifacts
from resume_agent.retrieval import DeterministicHashEmbeddings, HybridRetriever
from resume_agent.web.embedding import build_openai_embeddings
from resume_agent.web.events import EventStore
from resume_agent.web.schemas import RunPublic, RunSettings
from resume_agent.workflow import SafetyGateError, build_graph

ACTIVE_STATUSES = {"preparing", "running", "waiting_review", "cancelling"}
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
LOGGER = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_error(error: Exception, record: "RunRecord") -> dict[str, object]:
    """Return a redacted, actionable failure description for the workbench."""
    message = str(error)
    lowered = message.lower()
    if isinstance(error, SafetyGateError):
        return {
            "type": type(error).__name__,
            "category": "safety_gate",
            "message": "Evidence safety checks rejected the generated draft.",
            "service": "workflow",
            "issues": error.issues,
        }
    if type(error).__name__ == "LengthFinishReasonError" or any(
        token in lowered for token in ("length limit", "context length", "maximum context")
    ):
        category = "context_length"
    elif "timeout" in lowered or "timed out" in lowered:
        category = "timeout"
    elif any(token in lowered for token in ("unauthorized", "authentication", "api key", "401")):
        category = "authentication"
    elif any(token in lowered for token in ("model not found", "unknown model", "404")):
        category = "model_not_found"
    elif any(token in lowered for token in ("connection refused", "failed to connect")):
        category = "connection_refused"
    elif "invalid input type" in lowered:
        category = "incompatible_input"
    elif record.cancel_requested:
        category = "cancelled"
    else:
        category = "workflow"

    if category == "context_length" or record.current_phase == "llm_evidence_mapping":
        service = "llm"
    elif (
        record.current_phase == "embedding_retrieval"
        or record.current_node == "build_evidence_index"
        or (record.current_node == "retrieve_evidence" and record.current_phase is None)
    ):
        service = "embedding"
    else:
        service = "llm"
    settings = getattr(record.settings, service)
    return {
        "type": type(error).__name__,
        "category": category,
        "message": message[:500],
        "service": service,
        "model": settings.model,
        "base_url": settings.base_url,
        "timeout_seconds": settings.timeout_seconds,
    }


@dataclass
class RunRecord:
    id: str
    directory: Path
    settings: RunSettings
    created_at: str
    updated_at: str
    status: str = "preparing"
    current_node: str | None = None
    current_phase: str | None = None
    error: dict[str, object] | None = None
    cancel_requested: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    event_lock: threading.Lock = field(default_factory=threading.Lock)
    process: Any = field(default=None, repr=False, compare=False)

    @property
    def event_store(self) -> EventStore:
        return EventStore(self.directory / "events.sqlite", self.id)


class RunManager:
    def __init__(
        self,
        output_root: Path,
        process_runs: bool = True,
        mark_interrupted: bool = True,
    ) -> None:
        self.output_root = output_root.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.runs: dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        self.process_runs = process_runs
        self._process_context = multiprocessing.get_context("spawn")
        self._load_existing(mark_interrupted)

    def _load_existing(self, mark_interrupted: bool) -> None:
        for metadata_path in self.output_root.glob("*/web-run.json"):
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                settings = RunSettings.model_validate(data["config_for_resume"])
                status = data["status"]
                interrupted = mark_interrupted and status in ACTIVE_STATUSES
                if interrupted:
                    status = "interrupted"
                self.runs[data["id"]] = RunRecord(
                    id=data["id"], directory=metadata_path.parent, settings=settings,
                    created_at=data["created_at"],
                    updated_at=utc_now() if interrupted else data["updated_at"], status=status,
                    current_node=data.get("current_node"),
                    current_phase=data.get("current_phase"), error=data.get("error"),
                )
                if interrupted:
                    self._persist(self.runs[data["id"]])
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue

    def _persist(self, record: RunRecord) -> None:
        data = {
            "id": record.id,
            "status": record.status,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "current_node": record.current_node,
            "current_phase": record.current_phase,
            "error": record.error,
            "config": record.settings.redacted(),
            "config_for_resume": self._settings_without_secrets(record.settings),
        }
        target = record.directory / "web-run.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    @staticmethod
    def _settings_without_secrets(settings: RunSettings) -> dict[str, object]:
        data = settings.model_dump(mode="json", exclude={"llm": {"api_key"}, "embedding": {"api_key"}})
        return data

    def _refresh(self, record: RunRecord) -> None:
        metadata_path = record.directory / "web-run.json"
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        record.status = data.get("status", record.status)
        record.updated_at = data.get("updated_at", record.updated_at)
        record.current_node = data.get("current_node")
        record.current_phase = data.get("current_phase")
        record.error = data.get("error")

    def _emit(self, record: RunRecord, event: dict[str, Any]) -> None:
        with record.event_lock:
            node = event.get("node")
            if isinstance(node, str):
                record.current_node = node
            if event.get("type") == "node_started":
                record.current_phase = None
            phase = event.get("phase")
            if isinstance(phase, str):
                record.current_phase = phase
            record.updated_at = utc_now()
            record.event_store.append(
                event_type=str(event.get("type", "progress")),
                status=str(event.get("status", "running")),
                summary=self._event_summary(event),
                node=node if isinstance(node, str) else None,
                details={
                    key: value
                    for key, value in event.items()
                    if key in {
                        "error_type", "category", "elapsed_seconds", "duration_seconds",
                        "phase",
                    }
                },
            )
            self._persist(record)
        if record.cancel_requested and event.get("type") == "node_completed":
            raise RuntimeError("Run cancelled by user")

    @staticmethod
    def _event_summary(event: dict[str, Any]) -> str:
        node = str(event.get("node", "workflow")).replace("_", " ")
        labels = {
            "node_started": f"Started {node}",
            "node_completed": f"Completed {node}",
            "node_failed": f"Failed {node}",
            "node_heartbeat": (
                f"{node} is still running · {event.get('elapsed_seconds', 0)}s elapsed"
            ),
            "node_progress": {
                "embedding_retrieval": "Retrieving semantic evidence",
                "llm_evidence_mapping": "Mapping evidence with LLM",
            }.get(str(event.get("phase")), node),
            "review_required": "Waiting for resume review",
        }
        return labels.get(str(event.get("type")), node)

    def create(
        self,
        settings: RunSettings,
        jd: tuple[str, bytes],
        resume: tuple[str, bytes],
        sources: list[tuple[str, bytes]],
    ) -> RunRecord:
        with self._lock:
            for item in self.runs.values():
                self._refresh(item)
            if any(item.status in ACTIVE_STATUSES for item in self.runs.values()):
                raise ValueError("Another Run is active")
            run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
            directory = self.output_root / run_id
            inputs = directory / "inputs"
            sources_dir = inputs / "sources"
            sources_dir.mkdir(parents=True)
            jd_path = self._write_upload(inputs, "jd", jd)
            resume_path = self._write_upload(inputs, "resume", resume)
            for index, source in enumerate(sources, start=1):
                self._write_upload(sources_dir, f"source-{index}", source)
            now = utc_now()
            record = RunRecord(run_id, directory, settings, now, now)
            self.runs[run_id] = record
            self._persist(record)
            record.event_store.append("run_created", "preparing", "Run created")
            source_path = sources_dir if sources else None
            if self.process_runs:
                self._start_process(
                    record, _execute_process, jd_path, resume_path, source_path
                )
            else:
                threading.Thread(
                    target=self._execute,
                    args=(record, jd_path, resume_path, source_path),
                    daemon=True,
                    name=f"resume-run-{run_id}",
                ).start()
            return record

    def _start_process(self, record: RunRecord, target, *args: object) -> None:
        process = self._process_context.Process(
            target=target,
            args=(self.output_root, record.id, record.settings, *args),
            daemon=True,
            name=f"resume-worker-{record.id}",
        )
        record.process = process
        process.start()
        threading.Thread(
            target=self._monitor_process,
            args=(record, process),
            daemon=True,
            name=f"resume-monitor-{record.id}",
        ).start()

    def _monitor_process(self, record: RunRecord, process: Any) -> None:
        process.join()
        if record.cancel_requested:
            return
        self._refresh(record)
        if process.exitcode and record.status in ACTIVE_STATUSES:
            record.status = "failed"
            record.error = {
                "type": "WorkerProcessError",
                "category": "workflow",
                "message": f"Run worker exited with code {process.exitcode}.",
                "service": "workflow",
            }
            record.updated_at = utc_now()
            record.event_store.append(
                "run_failed", "failed", "Run worker stopped unexpectedly",
                record.current_node, {"exit_code": process.exitcode},
            )
            self._persist(record)

    @staticmethod
    def _write_upload(directory: Path, fallback: str, upload: tuple[str, bytes]) -> Path:
        filename, content = upload
        suffix = Path(filename).suffix.lower()
        if suffix not in {".md", ".txt"}:
            raise ValueError(f"Unsupported file type: {suffix or '<none>'}")
        safe_stem = SAFE_NAME.sub("-", fallback).strip(".-") or "upload"
        path = directory / f"{safe_stem}{suffix}"
        counter = 2
        while path.exists():
            path = directory / f"{safe_stem}-{counter}{suffix}"
            counter += 1
        path.write_bytes(content)
        return path

    def _components(self, settings: RunSettings):
        if settings.demo:
            return HeuristicBackend(), HybridRetriever(DeterministicHashEmbeddings(size=64))
        server_key = os.getenv("OPENAI_API_KEY")
        llm_key = settings.llm.secret(server_key)
        embedding_key = settings.embedding.secret(server_key)
        backend = LangChainBackend(
            model=settings.llm.model,
            api_key=llm_key,
            base_url=settings.llm.base_url,
            timeout=settings.llm.timeout_seconds,
            max_retries=settings.llm.max_retries,
            reasoning_effort=settings.llm.reasoning_effort,
            max_output_tokens=settings.llm.max_output_tokens,
        )
        embeddings = build_openai_embeddings(settings.embedding, embedding_key)
        return backend, HybridRetriever(embeddings)

    def _execute(
        self,
        record: RunRecord,
        jd_path: Path,
        resume_path: Path,
        sources_dir: Path | None,
    ) -> None:
        with record.lock:
            record.status = "running"
            record.updated_at = utc_now()
            self._persist(record)
            record.event_store.append("run_started", "running", "Run started")
            connection = sqlite3.connect(record.directory / "checkpoints.sqlite", check_same_thread=False)
            graph = None
            config = {"configurable": {"thread_id": record.id}}
            try:
                backend, retriever = self._components(record.settings)
                graph = build_graph(
                    backend, SqliteSaver(connection), retriever,
                    event_sink=lambda event: self._emit(record, event),
                )
                state = graph.invoke(
                    {
                        "jd_text": read_text_file(jd_path),
                        "master_resume": read_text_file(resume_path),
                        "evidence_chunks": [
                            chunk.model_dump() for chunk in load_evidence(resume_path, sources_dir)
                        ],
                    },
                    config=config,
                )
                interrupts = state.get("__interrupt__", [])
                if not interrupts:
                    raise RuntimeError("Workflow finished without review")
                record.status = "waiting_review"
                state["final_resume"] = interrupts[0].value.get("resume_markdown", "")
                state["review_status"] = "waiting_review"
                write_artifacts(record.directory, state)
                record.event_store.append("review_required", "waiting", "Review required", "human_review")
            except Exception as error:
                record.status = "cancelled" if record.cancel_requested else "failed"
                record.error = classify_error(error, record)
                if isinstance(error, SafetyGateError) and graph is not None:
                    try:
                        checkpoint_state = dict(graph.get_state(config).values)
                        write_failure_artifacts(record.directory, checkpoint_state, error.issues)
                    except Exception:
                        LOGGER.exception("Could not write failure artifacts for Run %s", record.id)
                LOGGER.exception(
                    "Run %s failed at node %s", record.id, record.current_node
                )
                record.event_store.append(
                    "run_failed", record.status, "Run cancelled" if record.cancel_requested else "Run failed",
                    record.current_node,
                    {
                        "error_type": record.error["type"],
                        "category": record.error["category"],
                        "issues": record.error.get("issues", []),
                    },
                )
            finally:
                connection.close()
                record.updated_at = utc_now()
                self._persist(record)

    def review(self, run_id: str, approved: bool, resume_markdown: str | None) -> RunRecord:
        record = self.get_record(run_id)
        if record.status != "waiting_review":
            raise ValueError("Run is not waiting for review")
        with record.lock:
            connection = sqlite3.connect(record.directory / "checkpoints.sqlite", check_same_thread=False)
            try:
                backend, retriever = self._components(record.settings)
                graph = build_graph(
                    backend, SqliteSaver(connection), retriever,
                    event_sink=lambda event: self._emit(record, event),
                )
                current = (record.directory / "tailored-resume.md").read_text(encoding="utf-8")
                edited = resume_markdown if resume_markdown is not None else current
                if approved and edited != current:
                    record.event_store.append(
                        "node_started", "running", "Verifying edited resume", "verify_edited_resume"
                    )
                    inputs = record.directory / "inputs"
                    resume_files = sorted(inputs.glob("resume.*"))
                    if not resume_files:
                        raise ValueError("Master resume input is missing")
                    sources_dir = inputs / "sources"
                    chunks = load_evidence(
                        resume_files[0], sources_dir if sources_dir.is_dir() else None
                    )
                    verification = backend.verify_edited_resume(current, edited, chunks)
                    valid_ids = {item.id for item in chunks}
                    invalid = [
                        claim.text
                        for claim in verification.supported_claims
                        if not claim.evidence_ids or any(item not in valid_ids for item in claim.evidence_ids)
                    ]
                    if verification.unsupported_claims or invalid:
                        record.event_store.append(
                            "node_failed", "failed", "Edited resume contains unsupported claims",
                            "verify_edited_resume",
                            {"unsupported_count": len(verification.unsupported_claims) + len(invalid)},
                        )
                        raise ValueError("Edited resume contains unsupported factual claims")
                    if verification.corrected_resume_markdown != edited:
                        raise ValueError(
                            "Edited resume verification changed the draft; review it again"
                        )
                    record.event_store.append(
                        "node_completed", "complete", "Edited resume verified", "verify_edited_resume"
                    )
                state = graph.invoke(
                    Command(resume={"approved": approved, "resume_markdown": edited}),
                    config={"configurable": {"thread_id": record.id}},
                )
                write_artifacts(record.directory, state)
                record.status = "approved" if approved else "rejected"
                record.event_store.append(
                    "run_completed", record.status,
                    "Resume approved" if approved else "Resume rejected", "human_review",
                )
            finally:
                connection.close()
                record.updated_at = utc_now()
                self._persist(record)
        return record

    def cancel(self, run_id: str) -> RunRecord:
        record = self.get_record(run_id)
        self._refresh(record)
        if record.status == "cancelling" or record.cancel_requested:
            return record
        if record.status not in ACTIVE_STATUSES:
            raise ValueError("Run is not active")
        record.cancel_requested = True
        if record.status == "waiting_review":
            record.status = "cancelled"
            record.event_store.append("run_cancelled", "cancelled", "Run cancelled")
        elif record.process is not None and record.process.is_alive():
            record.process.terminate()
            record.process.join(timeout=2)
            if record.process.is_alive():
                record.process.kill()
                record.process.join(timeout=2)
            record.status = "cancelled"
            record.updated_at = utc_now()
            record.event_store.append(
                "run_cancelled", "cancelled", "Run worker terminated",
                record.current_node,
            )
        else:
            record.status = "cancelling"
            record.event_store.append("cancel_requested", "cancelling", "Cancellation requested")
        self._persist(record)
        return record

    def resume(self, run_id: str, settings: RunSettings) -> RunRecord:
        record = self.get_record(run_id)
        self._refresh(record)
        if record.status not in {"failed", "interrupted"}:
            raise ValueError("Only failed or interrupted Runs can resume")
        if not self._same_identity(record.settings, settings):
            raise ValueError("Model and endpoint must match the original Run")
        record.settings = settings
        record.cancel_requested = False
        record.error = None
        record.status = "running"
        record.updated_at = utc_now()
        self._persist(record)
        record.event_store.append("run_resumed", "running", "Run resumed from checkpoint")
        if self.process_runs:
            self._start_process(record, _resume_process)
        else:
            threading.Thread(
                target=self._resume_execute,
                args=(record,),
                daemon=True,
                name=f"resume-retry-{run_id}",
            ).start()
        return record

    @staticmethod
    def _same_identity(original: RunSettings, current: RunSettings) -> bool:
        if original.demo != current.demo:
            return False
        return all(
            getattr(original, service).model == getattr(current, service).model
            and getattr(original, service).base_url == getattr(current, service).base_url
            for service in ("llm", "embedding")
        )

    def _resume_execute(self, record: RunRecord) -> None:
        with record.lock:
            connection = sqlite3.connect(record.directory / "checkpoints.sqlite", check_same_thread=False)
            graph = None
            config = {"configurable": {"thread_id": record.id}}
            try:
                backend, retriever = self._components(record.settings)
                graph = build_graph(
                    backend, SqliteSaver(connection), retriever,
                    event_sink=lambda event: self._emit(record, event),
                )
                state = graph.invoke(
                    None,
                    config=config,
                )
                interrupts = state.get("__interrupt__", [])
                if interrupts:
                    record.status = "waiting_review"
                    state["final_resume"] = interrupts[0].value.get("resume_markdown", "")
                    state["review_status"] = "waiting_review"
                    write_artifacts(record.directory, state)
                    record.event_store.append(
                        "review_required", "waiting", "Review required", "human_review"
                    )
                else:
                    raise RuntimeError("Resumed workflow finished without review")
            except Exception as error:
                record.status = "cancelled" if record.cancel_requested else "failed"
                record.error = classify_error(error, record)
                if isinstance(error, SafetyGateError) and graph is not None:
                    try:
                        checkpoint_state = dict(graph.get_state(config).values)
                        write_failure_artifacts(record.directory, checkpoint_state, error.issues)
                    except Exception:
                        LOGGER.exception("Could not write failure artifacts for Run %s", record.id)
                LOGGER.exception(
                    "Resumed Run %s failed at node %s", record.id, record.current_node
                )
                record.event_store.append(
                    "run_failed", record.status, "Resumed Run failed", record.current_node,
                    {
                        "error_type": record.error["type"],
                        "category": record.error["category"],
                        "issues": record.error.get("issues", []),
                    },
                )
            finally:
                connection.close()
                record.updated_at = utc_now()
                self._persist(record)

    def get_record(self, run_id: str) -> RunRecord:
        try:
            return self.runs[run_id]
        except KeyError as error:
            raise KeyError("Run not found") from error

    def public(self, record: RunRecord) -> RunPublic:
        self._refresh(record)
        results = {}
        for name in (
            "tailored-resume.md", "requirement-map.md", "evidence-report.md",
            "interview-questions.md", "run.json", "failure-report.md", "unsafe-draft.md",
        ):
            path = record.directory / name
            if path.is_file():
                results[name] = path.read_text(encoding="utf-8")
        return RunPublic(
            id=record.id, status=record.status, created_at=record.created_at,
            updated_at=record.updated_at, current_node=record.current_node,
            error=record.error, config=record.settings.redacted(), results=results,
            events=record.event_store.after(0),
        )


def _worker_manager(
    output_root: Path,
    run_id: str,
    settings: RunSettings,
) -> tuple[RunManager, RunRecord]:
    manager = RunManager(output_root, process_runs=False, mark_interrupted=False)
    record = manager.get_record(run_id)
    record.settings = settings
    record.cancel_requested = False
    return manager, record


def _execute_process(
    output_root: Path,
    run_id: str,
    settings: RunSettings,
    jd_path: Path,
    resume_path: Path,
    sources_dir: Path | None,
) -> None:
    manager, record = _worker_manager(output_root, run_id, settings)
    manager._execute(record, jd_path, resume_path, sources_dir)


def _resume_process(
    output_root: Path,
    run_id: str,
    settings: RunSettings,
) -> None:
    manager, record = _worker_manager(output_root, run_id, settings)
    record.status = "running"
    manager._resume_execute(record)
