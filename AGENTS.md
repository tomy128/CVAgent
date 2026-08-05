# Repository Guidelines

## Scope

This repository contains the standalone Resume Agent. Keep it independent from sibling repositories. Read `tasks/current.md` before changes and keep design decisions under `docs/`.

## Development

- Use Python 3.13 and `uv`.
- Keep the CLI usable without a web frontend.
- Prefer typed, testable workflow nodes over hidden prompt chains.
- Never invent resume evidence. Generated claims must reference source evidence.
- Input files are read-only; write generated artifacts only under the selected output directory.

## Commands

```bash
uv sync --group dev
uv run pytest
uv run resume-agent tailor --help
```

Use four-space Python indentation, type annotations, and focused modules. Add regression tests for workflow, evidence, or safety changes. Use Conventional Commit prefixes such as `feat:`, `fix:`, `test:`, and `docs:`.

## Commit Boundaries

Product planning and functional implementation must be committed separately. Treat changes under `docs/`, `tasks/`, `plans/`, and similar product-decision or planning paths as planning work. Commit those files independently with a documentation-oriented message, for example `docs: define resume review workflow`.

When one task changes several planning artifacts, consolidate them into one coherent docs commit before implementation. Prefer one primary design document that includes the implementation outline; do not create consecutive commits merely to separate design, plan, approval, and task-state updates. Governance changes such as `AGENTS.md` and the task entry should accompany that same docs commit when they belong to the task. Archive-only changes may wait for the next related docs commit unless the archive itself needs independent review.

Do not include source code, tests, dependency changes, or generated assets in a planning commit. Commit implementation afterward with an appropriate prefix such as `feat:`, `fix:`, or `test:`. When one task requires both planning and implementation, use at least two commits:

1. Consolidated planning, governance, and task documentation.
2. Functional code, tests, and implementation-specific configuration.

Before each commit, inspect the staged file list with `git diff --cached --name-only` and unstage files that cross the intended boundary. Changes limited to repository governance files such as `AGENTS.md` may accompany the related planning/task documentation, but never a functional implementation commit.
