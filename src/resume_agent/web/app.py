"""FastAPI application for the local Resume Agent workbench."""

import asyncio
import json
import os
import secrets
import time
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from resume_agent.web.embedding import build_openai_embeddings
from resume_agent.web.schemas import ConnectionTestRequest, ReviewRequest, RunSettings
from resume_agent.web.service import RunManager

STATIC_DIR = Path(__file__).with_name("static")
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_TOTAL_SIZE = 20 * 1024 * 1024


def create_app(output_root: Path | None = None, testing: bool = False) -> FastAPI:
    app = FastAPI(title="NoNote Resume Workbench", docs_url=None, redoc_url=None)
    allowed_hosts = ["localhost", "127.0.0.1"]
    if testing:
        allowed_hosts.append("testserver")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.manager = RunManager(output_root or Path("output"))
    app.state.sessions = {}

    async def require_session(
        request: Request,
        x_resume_csrf: str | None = Header(default=None),
    ) -> str:
        session_id = request.cookies.get("resume_session")
        csrf = app.state.sessions.get(session_id)
        if not session_id or not csrf:
            raise HTTPException(status_code=401, detail="Local session required")
        if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(
            x_resume_csrf or "", csrf
        ):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        return session_id

    @app.get("/", include_in_schema=False)
    async def index(request: Request):
        session_id = request.cookies.get("resume_session")
        if session_id not in app.state.sessions:
            session_id = secrets.token_urlsafe(24)
            app.state.sessions[session_id] = secrets.token_urlsafe(24)
        response = FileResponse(STATIC_DIR / "index.html")
        response.set_cookie(
            "resume_session", session_id, httponly=True, samesite="strict", secure=False
        )
        return response

    @app.get("/api/bootstrap")
    async def bootstrap(session_id: str = Depends(require_session)):
        return {
            "csrf_token": app.state.sessions[session_id],
            "server_key_available": bool(os.getenv("OPENAI_API_KEY")),
        }

    @app.post("/api/connections/test")
    async def test_connection(
        payload: ConnectionTestRequest,
        _: str = Depends(require_session),
    ):
        started = time.monotonic()

        def execute() -> None:
            settings = payload.settings
            key = settings.secret(os.getenv("OPENAI_API_KEY"))
            if payload.service == "llm":
                ChatOpenAI(
                    model=settings.model,
                    api_key=key,
                    base_url=settings.base_url,
                    timeout=settings.timeout_seconds,
                    max_retries=settings.max_retries,
                    temperature=0,
                ).invoke("Reply with OK only.")
                return
            build_openai_embeddings(settings, key).embed_query("connection test")

        try:
            await asyncio.to_thread(execute)
        except Exception as error:
            message = str(error)
            lowered = message.lower()
            category = (
                "timeout" if "timeout" in lowered or "timed out" in lowered
                else "authentication" if "401" in lowered or "auth" in lowered
                else "model_not_found" if "404" in lowered or "model" in lowered and "not found" in lowered
                else "connection_refused" if "refused" in lowered or "connect" in lowered
                else "incompatible_input" if "invalid input type" in lowered
                else "unknown"
            )
            return JSONResponse(
                status_code=422,
                content={
                    "ok": False,
                    "category": category,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "message": message[:500],
                },
            )
        return {
            "ok": True,
            "category": "success",
            "duration_ms": round((time.monotonic() - started) * 1000),
        }

    @app.post("/api/runs", status_code=201)
    async def create_run(
        config: str = Form(...),
        jd: UploadFile = File(...),
        resume: UploadFile = File(...),
        sources: list[UploadFile] = File(default=[]),
        _: str = Depends(require_session),
    ):
        try:
            settings = RunSettings.model_validate_json(config)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors(include_url=False)) from error
        uploads = [jd, resume, *sources]
        contents = [await item.read(MAX_FILE_SIZE + 1) for item in uploads]
        if any(len(content) > MAX_FILE_SIZE for content in contents):
            raise HTTPException(status_code=413, detail="Each file must be 5 MB or smaller")
        if sum(map(len, contents)) > MAX_TOTAL_SIZE:
            raise HTTPException(status_code=413, detail="All files must total 20 MB or less")
        try:
            record = app.state.manager.create(
                settings,
                (jd.filename or "jd.md", contents[0]),
                (resume.filename or "resume.md", contents[1]),
                [
                    (source.filename or f"source-{index}.md", content)
                    for index, (source, content) in enumerate(
                        zip(sources, contents[2:], strict=True), start=1
                    )
                ],
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return app.state.manager.public(record)

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str, _: str = Depends(require_session)):
        try:
            return app.state.manager.public(app.state.manager.get_record(run_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(
        run_id: str,
        request: Request,
        last_event_id: str | None = Header(default=None),
        _: str = Depends(require_session),
    ):
        try:
            store = app.state.manager.get_record(run_id).event_store
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        cursor = int(last_event_id or request.query_params.get("after", "0"))

        async def generate():
            async for event in store.subscribe(cursor):
                if await request.is_disconnected():
                    break
                yield f"id: {event.id}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/api/runs/{run_id}/review")
    async def review_run(
        run_id: str,
        payload: ReviewRequest,
        _: str = Depends(require_session),
    ):
        try:
            record = await asyncio.to_thread(
                app.state.manager.review,
                run_id,
                payload.action == "approve",
                payload.resume_markdown,
            )
            return app.state.manager.public(record)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str, _: str = Depends(require_session)):
        try:
            return app.state.manager.public(app.state.manager.cancel(run_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/runs/{run_id}/resume")
    @app.post("/api/runs/{run_id}/retry")
    async def resume_run(
        run_id: str,
        settings: RunSettings,
        _: str = Depends(require_session),
    ):
        try:
            return app.state.manager.public(app.state.manager.resume(run_id, settings))
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "resume_agent.web.app:app",
        host="127.0.0.1",
        port=int(os.getenv("RESUME_AGENT_WEB_PORT", "8765")),
        reload=False,
    )
