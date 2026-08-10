# Collapsible Model Configuration Design

## User goal

An individual job seeker should be able to reclaim vertical space after configuring model services while keeping each service's identity and connection status visible. The workbench brand should read “CV Agent” instead of “NoNote Resume.”

## Core tradeoff

Use a small explicit disclosure control rather than native `details`. A button gives the existing heading and connection-status layout precise control and exposes `aria-expanded` and `aria-controls` clearly. It costs a few lines of JavaScript but avoids a browser-dependent marker and keeps the interaction consistent with the current interface.

## MVP scope

- Change the visible header brand to `CV Agent` and the document title to `CV Agent Workbench`.
- Make the complete LLM and Embedding heading rows independently clickable disclosure buttons.
- Keep both sections expanded on every page load; do not persist disclosure state.
- When collapsed, keep the service title, disclosure indicator, and connection state visible while hiding fields and the connection-test action.
- Support pointer, Enter, and Space activation through native button behavior.
- Update `aria-expanded` and connect each trigger to its panel with `aria-controls`.
- Leave material uploads, configuration persistence, service testing, and backend behavior unchanged.

## Technical path

Wrap each service's existing fields and test button in a named content container. Replace its static heading wrapper with a full-width button containing the existing heading and connection state plus a directional disclosure icon. A shared JavaScript initializer toggles `hidden`, `aria-expanded`, and a collapsed class for either section without duplicating service-specific logic.

CSS will preserve the current sidebar visual language, provide hover and focus states, and rotate the disclosure icon during the existing fast state transition. Reduced-motion preferences disable the rotation transition. Hiding content uses the native `hidden` attribute so collapsed controls leave the accessibility tree and tab order.

## Verification

- Add a static Web regression that checks the new titles and disclosure semantics for both services.
- Add JavaScript regression coverage for default expanded state and independent toggling if the existing test harness supports DOM execution; otherwise keep the toggle initializer small and validate it through source assertions plus a browser smoke check.
- Run the repository test suite.

## Risks and evolution

The main risk is turning the heading into a button without neutralizing default button styling or preserving visible focus. Existing design tokens and `:focus-visible` behavior will be reused. Persisting disclosure state or adding a global “collapse all” control is deliberately deferred until user behavior shows a need.
