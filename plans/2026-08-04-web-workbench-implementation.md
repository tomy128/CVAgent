# Web Workbench Implementation Plan

## Outcome

Deliver a local, single-user FastAPI application with a framework-free Web interface for model configuration, document upload, Graph observability, failure recovery, and full-screen Markdown review while preserving the existing CLI.

## Commit boundary

This plan and task state are a planning-only commit. FastAPI code, static assets, tests, dependencies, README, and ignore rules belong to a later functional commit. Final task archival is a separate documentation commit.

## Phase 1: Shared runtime contracts

1. Add typed independent LLM and Embedding configuration with timeout, retries, dimensions, secret presence, and redacted serialization.
2. Extend backend/retriever construction to consume typed configuration without changing the user's dirty CLI configuration.
3. Add Web-oriented Graph event hooks and edited-resume verification while preserving existing workflow defaults and tests.

## Phase 2: Durable Run service

1. Add FastAPI, Uvicorn, and multipart dependencies.
2. Implement safe Run directories, upload validation, filename normalization, checkpoint connection ownership, one-active-Run enforcement, and atomic artifact snapshots.
3. Persist ordered allowlisted events in per-Run SQLite and implement replay plus live subscriptions.
4. Implement background execution, review resume, cancellation flags, retry/resume with re-supplied credentials, and interrupted-state recovery.
5. Enforce loopback hosts, same-origin session cookies, CSRF headers, secret omission, and safe error serialization.

## Phase 3: Native Web interface

1. Build a semantic single-page HTML shell with split workbench, configuration sidebar, uploads, Graph SVG plus textual equivalent, node inspector, recent events, and result summaries.
2. Implement API client, SSE reconnect, Run state transitions, connection tests, timeout recovery, cancellation, refresh restoration, and keyboard-accessible controls using native JavaScript modules.
3. Build the full-viewport review surface with result tabs, Markdown rendered/source modes, edited approval, evidence markers, and responsive metadata tabs.
4. Vendor pinned Markdown rendering, sanitization, and code-highlighting assets locally; do not add a frontend build system.
5. Apply DESIGN.md tokens, responsive behavior, reduced motion, focus states, loading skeletons, empty states, and typed error UI.

## Phase 4: Verification and documentation

1. Add API and service tests for configuration, uploads, one-active-Run, event replay, review, cancellation, retry/resume, restart interruption, security, and secret omission.
2. Add Graph regression tests for events and edited-resume verification.
3. Add Node built-in tests for pure frontend state/formatting modules where practical.
4. Run all Python tests, compile checks, CLI demo, Web API integration, browser workflow, responsive inspection, keyboard flow, and Markdown XSS checks.
5. Update README inline with Web setup and usage without linking planning documents.

## Scope controls

- No React, Vue, HTMX, npm build, accounts, cloud deployment, multi-user concurrency, run-history browser, PDF/Word upload, persistent vector index, or LLM token streaming.
- Do not stage or modify the user's current changes to `src/resume_agent/cli.py` or `examples/`.
- Prefer a coherent vertical slice over speculative abstractions; retry/resume supports only states exercised by the current Graph and tests.
