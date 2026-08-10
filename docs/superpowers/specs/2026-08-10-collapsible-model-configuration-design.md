# Collapsible Model Configuration Design

## User goal

An individual job seeker should be able to reclaim vertical space after configuring model services while keeping each service's identity and connection status visible. The workbench brand should read “CV Agent” instead of “NoNote Resume.”

## Core tradeoff

Use native `details` and `summary` elements for each model service. This gives the browser ownership of expansion, keyboard behavior, and accessibility state while removing custom JavaScript that can fail independently of the markup. The native disclosure marker will be styled to match the existing compact sidebar, but the interaction remains familiar and dependency-free.

## MVP scope

- Change the visible header brand to `CV Agent` and the document title to `CV Agent Workbench`.
- Make each LLM and Embedding configuration a native `details` section with the `open` attribute on initial markup.
- Make the complete `summary` row clickable, containing a valid service heading, disclosure indicator, and connection state.
- Keep both sections expanded on every page load; do not persist disclosure state.
- When collapsed, keep the service title, disclosure indicator, and connection state visible while hiding fields and the connection-test action.
- Support pointer and keyboard activation through native `summary` behavior without custom state synchronization.
- Leave material uploads, configuration persistence, service testing, and backend behavior unchanged.

## Technical path

Replace each model service's outer `section` with `details open`. Its `summary` contains the existing eyebrow, a valid `h2`, the connection state, and a small directional indicator. Existing fields and the connection-test action remain ordinary content below the summary.

No disclosure-specific JavaScript is used. A fresh page load recreates the static markup with `open`, so both sections default expanded without reading or writing disclosure state in `localStorage`.

CSS will remove the browser's default marker, preserve a clearly clickable full-width summary row, retain visible focus, and rotate the indicator based on the native `[open]` state. The existing reduced-motion rule covers the indicator transition.

## Verification

- Add a static Web regression that checks the new titles and disclosure semantics for both services.
- Add structural regression coverage for two independent `details open` elements, their summary and heading semantics, and the absence of disclosure-specific JavaScript. Native browser disclosure behavior itself does not need to be reimplemented or unit-tested.
- Run the repository test suite.

## Risks and evolution

The main risk is over-styling `summary` until it no longer looks interactive. The disclosure indicator, pointer cursor, hover color, and visible focus state will preserve the affordance. Persisting disclosure state or adding a global “collapse all” control is deliberately deferred until user behavior shows a need.
