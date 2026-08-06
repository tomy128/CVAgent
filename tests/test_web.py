import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from resume_agent.chains.common import build_chat_model
from resume_agent.web.app import create_app
from resume_agent.web.events import EventStore
from resume_agent.web.embedding import build_openai_embeddings
from resume_agent.web.schemas import EmbeddingSettings, ModelSettings, RunSettings
from resume_agent.web.service import RunManager, RunRecord, classify_error
from resume_agent.graph import SafetyGateError


def demo_settings() -> RunSettings:
    return RunSettings(
        demo=True,
        llm=ModelSettings(model="demo-llm"),
        embedding=EmbeddingSettings(model="demo-embedding"),
    )


def local_client(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(tmp_path / "output", testing=True))
    assert client.get("/").status_code == 200
    bootstrap = client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    return client, {"X-Resume-CSRF": bootstrap.json()["csrf_token"]}


def wait_for_status(client: TestClient, run_id: str, expected: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["status"] == expected:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Run did not reach {expected}")


def create_demo_run(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/runs",
        headers=headers,
        data={"config": demo_settings().model_dump_json()},
        files={
            "jd": ("jd.md", b"- Python\n- LangGraph", "text/markdown"),
            "resume": ("resume.md", b"# Resume\n\nPython engineer", "text/markdown"),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_api_requires_local_session_and_csrf(tmp_path: Path) -> None:
    app = create_app(tmp_path / "output", testing=True)
    anonymous = TestClient(app)
    assert anonymous.get("/api/bootstrap").status_code == 401

    client, _ = local_client(tmp_path)
    response = client.post(
        "/api/runs",
        data={"config": demo_settings().model_dump_json()},
        files={
            "jd": ("jd.md", b"Python", "text/markdown"),
            "resume": ("resume.md", b"Python", "text/markdown"),
        },
    )
    assert response.status_code == 403


def test_settings_redact_secrets() -> None:
    settings = RunSettings(
        llm=ModelSettings(model="chat", api_key="llm-secret"),
        embedding=EmbeddingSettings(model="embed", api_key="embed-secret"),
    )

    serialized = json.dumps(settings.redacted())

    assert "llm-secret" not in serialized
    assert "embed-secret" not in serialized
    assert settings.redacted()["llm"]["has_api_key"] is True
    assert settings.redacted()["llm"]["context_window"] is None


def test_demo_run_reaches_review_and_can_be_approved(tmp_path: Path) -> None:
    client, headers = local_client(tmp_path)
    created = create_demo_run(client, headers)
    run = wait_for_status(client, created["id"], "waiting_review")

    assert "application-resume.md" in run["results"]
    assert "semantic" in run["results"]["run.json"]
    assert any(
        event["type"] == "node_progress"
        and event["details"].get("batch_total") == 1
        for event in run["events"]
    )
    approval = client.post(
        f"/api/runs/{created['id']}/review",
        headers=headers,
        json={
            "action": "approve",
            "resume_markdown": run["results"]["application-resume.md"],
        },
    )

    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "approved"


def test_edited_demo_resume_requires_evidence(tmp_path: Path) -> None:
    client, headers = local_client(tmp_path)
    created = create_demo_run(client, headers)
    wait_for_status(client, created["id"], "waiting_review")

    response = client.post(
        f"/api/runs/{created['id']}/review",
        headers=headers,
        json={"action": "approve", "resume_markdown": "Invented production result"},
    )

    assert response.status_code == 409
    assert "unsupported" in response.json()["detail"].lower()
    assert client.get(f"/api/runs/{created['id']}").json()["status"] == "waiting_review"


def test_event_store_replays_after_event_id(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.sqlite", "run-1")
    first = store.append("run_started", "running", "Started")
    second = store.append("node_started", "running", "Parsing", "extract_requirements")

    replay = store.after(first.id)

    assert [item.id for item in replay] == [second.id]
    assert replay[0].node == "extract_requirements"


def test_upload_rejects_unsupported_file_type(tmp_path: Path) -> None:
    client, headers = local_client(tmp_path)
    response = client.post(
        "/api/runs",
        headers=headers,
        data={"config": demo_settings().model_dump_json()},
        files={
            "jd": ("jd.pdf", b"pdf", "application/pdf"),
            "resume": ("resume.md", b"Python", "text/markdown"),
        },
    )

    assert response.status_code == 409
    assert "unsupported" in response.json()["detail"].lower()


def test_markdown_preview_disables_html_and_sanitizes(tmp_path: Path) -> None:
    source = (Path(__file__).parents[1] / "src/resume_agent/web/static/app.js").read_text(
        encoding="utf-8"
    )

    assert "html: false" in source
    assert "DOMPurify.sanitize" in source


def test_timeout_error_is_actionable_and_redacted(tmp_path: Path) -> None:
    settings = RunSettings(
        llm=ModelSettings(model="chat", api_key="llm-secret"),
        embedding=EmbeddingSettings(
            model="local-embed",
            api_key="embed-secret",
            base_url="http://localhost:11434/v1",
            timeout_seconds=300,
        ),
    )
    record = RunRecord("run-1", tmp_path, settings, "now", "now")
    record.current_node = "retrieve_evidence"

    error = classify_error(TimeoutError("embedding request timed out"), record)
    serialized = json.dumps(error)

    assert error["category"] == "timeout"
    assert error["service"] == "embedding"
    assert error["timeout_seconds"] == 300
    assert "embed-secret" not in serialized
    assert "llm-secret" not in serialized


def test_embedding_client_sends_raw_text_to_compatible_endpoint() -> None:
    settings = EmbeddingSettings(
        model="qwen3-embedding:0.6b",
        api_key="ollama",
        base_url="http://localhost:11434/v1",
        timeout_seconds=300,
    )

    embeddings = build_openai_embeddings(settings)

    assert embeddings.check_embedding_ctx_length is False
    assert embeddings.model == "qwen3-embedding:0.6b"
    assert str(embeddings.openai_api_base) == "http://localhost:11434/v1"


def test_invalid_embedding_input_is_classified(tmp_path: Path) -> None:
    record = RunRecord("run-1", tmp_path, demo_settings(), "now", "now")
    record.current_node = "retrieve_evidence"

    error = classify_error(ValueError("invalid input type"), record)

    assert error["category"] == "incompatible_input"
    assert error["service"] == "embedding"


def test_length_finish_reason_is_an_llm_context_failure(tmp_path: Path) -> None:
    class LengthFinishReasonError(RuntimeError):
        pass

    record = RunRecord("run-1", tmp_path, demo_settings(), "now", "now")
    record.current_node = "retrieve_evidence"
    record.current_phase = "llm_evidence_mapping"

    error = classify_error(
        LengthFinishReasonError("Could not parse response as the length limit was reached"),
        record,
    )

    assert error["category"] == "context_length"
    assert error["service"] == "llm"


def test_chat_model_applies_reasoning_and_output_limits() -> None:
    model = build_chat_model(
        "qwen3.5:4b", "ollama", "http://localhost:11434/v1",
        reasoning_effort="none", max_output_tokens=4096,
    )

    assert model.reasoning_effort == "none"
    assert model.max_tokens == 4096


def test_llm_connection_test_uses_structured_output(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    class FakeModel:
        def with_structured_output(self, schema):
            calls.append(schema.__name__)
            return self

        def invoke(self, prompt):
            calls.append(prompt)

    monkeypatch.setattr(
        "resume_agent.web.app.build_chat_model", lambda *args, **kwargs: FakeModel()
    )
    client, headers = local_client(tmp_path)
    response = client.post(
        "/api/connections/test",
        headers=headers,
        json={
            "service": "llm",
            "settings": {
                "model": "qwen3.5:4b",
                "api_key": "ollama",
                "reasoning_effort": "none",
                "max_output_tokens": 4096,
            },
        },
    )

    assert response.status_code == 200
    assert calls[0] == "ConnectionProbe"


def test_safety_failure_is_actionable_without_model_context(tmp_path: Path) -> None:
    record = RunRecord("run-1", tmp_path, demo_settings(), "now", "now")
    record.current_node = "safety_gate"
    error = classify_error(
        SafetyGateError([{"claim": "Invented scale", "reason": "No evidence"}]),
        record,
    )

    assert error["category"] == "safety_gate"
    assert error["service"] == "workflow"
    assert error["issues"] == [{"claim": "Invented scale", "reason": "No evidence"}]


def test_safety_failure_ui_hides_checkpoint_retry() -> None:
    source = (Path(__file__).parents[1] / "src/resume_agent/web/static/app.js").read_text(
        encoding="utf-8"
    )

    assert 'safetyFailure || !["failed", "interrupted"]' in source
    assert '"failure-report.md": "失败报告"' in source


def test_all_model_configuration_persists_in_local_storage() -> None:
    source = (Path(__file__).parents[1] / "src/resume_agent/web/static/app.js").read_text(
        encoding="utf-8"
    )

    assert 'localStorage.setItem("resume-workbench-config", JSON.stringify(config()))' in source
    assert "delete saved.llm.api_key" not in source
    assert 'saved[service]?.api_key' in source
    assert 'input:not([type="file"])' in source
    assert "sessionStorage" not in source


def test_result_viewer_initializes_content_before_rendering() -> None:
    source = (Path(__file__).parents[1] / "src/resume_agent/web/static/app.js").read_text(
        encoding="utf-8"
    )

    assignment = source.index('$("#markdown-source").value = source;')
    render = source.index('renderTabs(); setReviewMode("render");', assignment)
    assert assignment < render
    assert '$("#review-actions").classList.toggle("hidden", !actionable)' in source
    assert '$("#markdown-source").readOnly = !actionable' in source
    assert "✕ 事实安全未通过" in source
    assert 'name === "target-resume.md"' in source
    assert "⚠ 目标版本不可直接投递" in source


def test_persisted_base_urls_use_explicit_dom_mapping() -> None:
    source = (Path(__file__).parents[1] / "src/resume_agent/web/static/app.js").read_text(
        encoding="utf-8"
    )

    assert 'base_url: "base-url"' in source
    assert 'timeout_seconds: "timeout"' in source
    assert 'max_retries: "retries"' in source
    assert 'field.replace("_seconds", "")' not in source


def test_event_stream_uses_cursor_and_terminal_disconnect() -> None:
    source = (Path(__file__).parents[1] / "src/resume_agent/web/static/app.js").read_text(
        encoding="utf-8"
    )

    assert "events?after=${state.lastEventId}" in source
    assert "event.id <= state.lastEventId" in source
    assert '["running", "preparing", "cancelling"]' in source
    assert 'state.actionPending || !["preparing", "running", "waiting_review"]' in source


def test_production_worker_can_be_terminated(tmp_path: Path) -> None:
    manager = RunManager(tmp_path / "output", process_runs=True)
    record = manager.create(
        demo_settings(),
        ("jd.md", b"- Python"),
        ("resume.md", b"Python engineer"),
        [],
    )

    cancelled = manager.cancel(record.id)

    assert cancelled.status == "cancelled"
    assert cancelled.process is not None
    assert not cancelled.process.is_alive()
    events = cancelled.event_store.after(0)
    assert len([event for event in events if event.type == "run_cancelled"]) == 1


def test_context_window_uses_explicit_dom_mapping() -> None:
    source = (Path(__file__).parents[1] / "src/resume_agent/web/static/app.js").read_text(
        encoding="utf-8"
    )

    assert 'settings.context_window = numberValue("#llm-context-window") || null' in source
    assert '$("#llm-context-window").value = saved.llm.context_window' in source
