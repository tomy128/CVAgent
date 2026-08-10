# Collapsible Model Configuration Implementation

## Outcome

Rename the local Web workbench to CV Agent and let users independently collapse the LLM and Embedding configuration after setup, with both sections expanded on each page load.

## Commit boundary

This implementation plan is a planning-only commit. HTML, CSS, JavaScript, and tests belong to a later functional commit. Final task archival is a separate documentation commit.

## Implementation

1. Update the document and visible brand titles.
2. Preserve each model service as a semantic section with an `h2`; place a native disclosure button inside the heading and keep connection status adjacent.
3. Wrap each service form body in a controlled panel that can be removed from layout and keyboard navigation with `hidden`.
4. Add a small dependency-free disclosure module that always initializes both panels expanded and independently synchronizes `hidden` with `aria-expanded` on activation.
5. Reuse existing tokens for hover, focus, and a short indicator rotation; disable the transition for reduced-motion preferences.

## Verification

1. Use Node's built-in test runner with minimal fake DOM controls to verify fresh initialization, independent toggling, and synchronized accessibility state without adding a frontend dependency.
2. Invoke that frontend test from pytest so the repository's standard suite exercises the interaction.
3. Run `uv run pytest` and inspect the rendered page structure at desktop and narrow widths when a browser is available.

## Scope controls

- Do not persist disclosure state.
- Do not change model settings, connection testing, uploads, local storage configuration, or backend APIs.
- Do not add a frontend framework or package manager.
