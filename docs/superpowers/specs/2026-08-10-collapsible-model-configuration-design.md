# Collapsible Model Configuration Design

## User goal

An individual job seeker should be able to reclaim vertical space after configuring model services while keeping each service's identity and connection status visible. The workbench brand should read “CV Agent” instead of “NoNote Resume.”

## Core tradeoff

Use a small explicit disclosure control rather than native `details`. A button gives the existing heading and connection-status layout precise control and exposes `aria-expanded` and `aria-controls` clearly. It costs a few lines of JavaScript but avoids a browser-dependent marker and keeps the interaction consistent with the current interface.

## MVP scope

- Change the visible header brand to `CV Agent` and the document title to `CV Agent Workbench`.
- Give each LLM and Embedding heading a native disclosure button while preserving a valid `h2` heading for heading navigation; the adjacent connection state remains visible and outside the button.
- Keep both sections expanded on every page load; do not persist disclosure state.
- When collapsed, keep the service title, disclosure indicator, and connection state visible while hiding fields and the connection-test action.
- Support pointer, Enter, and Space activation through native button behavior.
- Update `aria-expanded` and connect each trigger to its panel with `aria-controls`.
- Leave material uploads, configuration persistence, service testing, and backend behavior unchanged.

## Technical path

Wrap each service's existing fields and test button in a named content container. Keep a valid `h2` heading and place a native disclosure button inside it, with the title and directional icon in the button; keep the connection state beside the heading rather than nested in the button. A shared JavaScript initializer toggles `hidden`, `aria-expanded`, and a collapsed class for either section without duplicating service-specific logic.

On every script initialization, the initializer explicitly sets both content panels to visible and both triggers to `aria-expanded="true"`. It does not read or write disclosure state in `localStorage`, so a fresh page load always resets both sections to expanded.

CSS will preserve the current sidebar visual language, provide hover and focus states, and rotate the disclosure icon during the existing fast state transition. Reduced-motion preferences disable the rotation transition. Hiding content uses the native `hidden` attribute so collapsed controls leave the accessibility tree and tab order.

## Verification

- Add a static Web regression that checks the new titles and disclosure semantics for both services.
- Add automated JavaScript behavior coverage for default expansion, independent LLM and Embedding toggling, synchronized `hidden` and `aria-expanded` values, and reset to expanded on fresh initialization. Extend the smallest existing Web test harness that can exercise the static script; do not substitute source assertions for the core interaction.
- Run the repository test suite.

## Risks and evolution

The main risk is turning the heading into a button without neutralizing default button styling or preserving visible focus. Existing design tokens and `:focus-visible` behavior will be reused. Persisting disclosure state or adding a global “collapse all” control is deliberately deferred until user behavior shows a need.
