# Design System

## Direction

Quiet Instrument: a precise, calm professional workbench with optional AI-laboratory depth. The interface uses familiar product patterns and state-driven feedback. It avoids chatbot layouts, decorative cards, glowing gradients, and unnecessary motion.

## Color

Use OKLCH tokens throughout:

```css
--color-bg: oklch(1 0 0);
--color-surface: oklch(0.975 0.006 200);
--color-surface-strong: oklch(0.945 0.012 200);
--color-ink: oklch(0.24 0.025 200);
--color-muted: oklch(0.48 0.022 200);
--color-border: oklch(0.88 0.014 200);
--color-primary: oklch(0.52 0.105 200);
--color-primary-soft: oklch(0.94 0.035 200);
--color-success: oklch(0.54 0.13 155);
--color-warning: oklch(0.62 0.14 65);
--color-danger: oklch(0.54 0.18 28);
```

Primary color marks current selection and primary actions only. Success, warning, and danger communicate runtime state and always include text or icons. Body text must meet WCAG AA contrast.

## Typography

Use `Inter`, `ui-sans-serif`, `system-ui`, and platform fallbacks. Use one family across the application. The scale is compact: 12px metadata, 14px body and controls, 16–18px section headings, and 22px page titles. Use tabular numbers for durations and counts and a system monospace stack for Markdown source and technical values.

## Layout

The desktop shell has a 280–320px configuration sidebar and a flexible execution workspace. The workspace contains run identity, Graph state, current-node details, and result summaries. Result documents open in a full-viewport review surface rather than a small panel.

Below 900px the sidebar collapses above the workspace. The Graph scrolls horizontally. The result viewer separates document content and review metadata into tabs on narrow screens.

## Components

- Configuration groups use plain sections and dividers, not nested cards.
- Buttons share one height, radius, focus ring, and loading vocabulary.
- File inputs expose filename, size, validation state, and removal.
- Graph nodes display pending, running, complete, waiting, failed, skipped, and retry states using icon, label, and color.
- Node details appear in an adjacent inspector, never as a blocking modal.
- Markdown results provide rendered and source modes. Source mode is editable.
- Errors include a concise explanation, technical details disclosure, and a relevant recovery action.

## Motion

Use 150–220ms ease-out transitions for panel disclosure, status changes, and focus movement. A running Graph edge may use restrained progress motion. Under `prefers-reduced-motion`, replace movement with immediate state and subtle color changes. No decorative page-load animation.

## Accessibility

Target WCAG AA. Preserve visible focus, semantic headings, associated errors, keyboard access, reduced motion, readable status announcements, and non-color state cues. The Graph exposes an ordered textual execution list alongside its SVG representation.
