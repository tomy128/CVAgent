"""Single-user Run lifecycle service shared by the Web routes."""

import json
import os
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_openai import OpenAIEmbeddings
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from resume_agent.backends import HeuristicBackend, LangChainBackend
from resume_agent.evidence import load_evidence, read_text_file
from resume_agent.output import write_artifacts
from resume_agent.retrieval import DeterministicHashEmbeddings, HybridRetriever
from resume_agent.web.events import EventStore
from resume_agent.web.schemas import RunPublic, RunSettings
from resume_agent.workflow import build_graph

ACTIVE_STATUSES = {"preparing", "running", "waiting_review", "cancelling"}
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_error(error: Exception, record: "RunRecord") -> dict[str, object]:
    """Return a redacted, actionable failure description for the workbench."""
    message = str(error)
    lowered = message.lower()
    if "timeout" in lowered or "timed out" in lowered:
        category = "timeout"
    elif any(token in lowered for token in ("unauthorized", "authentication", "api key", "401")):
        category = "authentication"
    elif any(token in lowered for token in ("model not found", "unknown model", "404")):
        category = "model_not_found"
    elif any(token in lowered for token in ("connection refused", "failed to connect")):
        category = "connection_refused"
    elif record.cancel_requested:
        category = "cancelled"
    else:
        category = "workflow"

    service = (
        "embedding"
        if record.current_node in {"build_evidence_index", "retrieve_evidence"}
        else "llm"
    )
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
    error: dict[str, object] | None = None
    cancel_requested: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def event_store(self) -> EventStore:
        return EventStore(self.directory / "events.sqlite", self.id)


class RunManager:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.runs: dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        self._load_existing()

    def _load_existing(self) -> None:
        for metadata_path in self.output_root.glob("*/web-run.json"):
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                settings = RunSettings.model_validate(data["config_for_resume"])
                status = data["status"]
                if status in ACTIVE_STATUSES:
                    status = "interrupted"
                self.runs[data["id"]] = RunRecord(
                    id=data["id"], directory=metadata_path.parent, settings=settings,
                    created_at=data["created_at"], updated_at=utc_now(), status=status,
                    current_node=data.get("current_node"), error=data.get("error"),
                )
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

    def _emit(self, record: RunRecord, event: dict[str, Any]) -> None:
        node = event.get("node")
        if isinstance(node, str):
            record.current_node = node
        record.updated_at = utc_now()
        record.event_store.append(
            event_type=str(event.get("type", "progress")),
            status=str(event.get("status", "running")),
            summary=self._event_summary(event),
            node=node if isinstance(node, str) else None,
            details={
                key: value
                for key, value in event.items()
                if key in {"error_type", "category"}
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
            thread = threading.Thread(
                target=self._execute,
                args=(record, jd_path, resume_path, sources_dir if sources else None),
                daemon=True,
                name=f"resume-run-{run_id}",
            )
            thread.start()
            return record

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
        )
        embedding_options: dict[str, Any] = {
            "model": settings.embedding.model,
            "api_key": embedding_key,
            "base_url": settings.embedding.base_url,
            "request_timeout": settings.embedding.timeout_seconds,
            "max_retries": settings.embedding.max_retries,
        }
        if settings.embedding.dimensions:
            embedding_options["dimensions"] = settings.embedding.dimensions
        return backend, HybridRetriever(OpenAIEmbeddings(**embedding_options))

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
                    config={"configurable": {"thread_id": record.id}},
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
                record.event_store.append(
                    "run_failed", record.status, "Run cancelled" if record.cancel_requested else "Run failed",
                    record.current_node,
                    {
                        "error_type": record.error["type"],
                        "category": record.error["category"],
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
        if record.status not in ACTIVE_STATUSES:
            raise ValueError("Run is not active")
        record.cancel_requested = True
        if record.status == "waiting_review":
            record.status = "cancelled"
            record.event_store.append("run_cancelled", "cancelled", "Run cancelled")
        else:
            record.status = "cancelling"
            record.event_store.append("cancel_requested", "cancelling", "Cancellation requested")
        self._persist(record)
        return record

    def resume(self, run_id: str, settings: RunSettings) -> RunRecord:
        record = self.get_record(run_id)
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
            try:
                backend, retriever = self._components(record.settings)
                graph = build_graph(
                    backend, SqliteSaver(connection), retriever,
                    event_sink=lambda event: self._emit(record, event),
                )
                state = graph.invoke(
                    None,
                    config={"configurable": {"thread_id": record.id}},
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
                record.event_store.append(
                    "run_failed", record.status, "Resumed Run failed", record.current_node,
                    {
                        "error_type": record.error["type"],
                        "category": record.error["category"],
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
        results = {}
        for name in (
            "tailored-resume.md", "requirement-map.md", "evidence-report.md",
            "interview-questions.md", "run.json",
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
