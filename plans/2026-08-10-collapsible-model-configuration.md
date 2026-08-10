# Collapsible Model Configuration Implementation

## Outcome

Rename the local Web workbench to CV Agent and let users independently collapse the LLM and Embedding configuration after setup, with both sections expanded on each page load.

## Commit boundary

This implementation plan is a planning-only commit. HTML, CSS, JavaScript, and tests belong to a later functional commit. Final task archival is a separate documentation commit.

## Implementation

1. Update the document and visible brand titles.
2. Represent each model service with native `details open` and a full-width `summary` containing its heading, connection status, and disclosure indicator.
3. Keep each service form body as ordinary details content and remove the custom disclosure JavaScript module and initializer.
4. Reuse existing tokens for hover, focus, and a short indicator rotation driven by the native `[open]` state; disable the transition for reduced-motion preferences.

## Verification

1. Add structural regression coverage for two independent `details open` elements, valid summary headings, and removal of disclosure-specific JavaScript.
2. Run `uv run pytest` and inspect the rendered page structure at desktop and narrow widths when a browser is available.

## Scope controls

- Do not persist disclosure state.
- Do not change model settings, connection testing, uploads, local storage configuration, or backend APIs.
- Do not add a frontend framework or package manager.
