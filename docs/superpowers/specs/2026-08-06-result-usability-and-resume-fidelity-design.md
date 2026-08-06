# Result Usability and Resume Fidelity Design

## User Goal

Turn a completed Run into a genuinely usable, JD-targeted resume. The user must understand why Graph stages ran or were skipped and know exactly how to complete human review. Resume artifacts retain the master resume's language, while JD-analysis artifacts follow the JD's language. The application resume should improve prioritization and formatting without replacing concrete personal writing with generic AI prose.

## Product Decisions

- The master resume's dominant language controls `application-resume.md` and `target-resume.md`. The JD's dominant language controls `match-report.md`, `growth-plan.md`, and `interview-prep.md`. Each ambiguous input falls back to the other input's detected language and records that fallback in Run details.
- Use structured editing: the model selects, reorders, or minimally rewrites source entries; deterministic Python renders Markdown.
- Preserve clear, specific, JD-relevant source sentences verbatim. Editing exists to improve relevance, order, clarity, and consistency—not to manufacture a new voice.
- `partial`, `transferable`, and `gap` requirements all produce growth guidance. Aspirational content remains excluded from the application resume.
- Growth and target resume generation happens before human review. A branch that is unnecessary must be explicitly marked skipped.

## Structured Resume Editing

Parse the master resume into a `ResumeDocument` containing ordered `ResumeSection` and `ResumeEntry` values. A bullet is the smallest editable entry. Parent records retain company or project ownership, role, dates, and links; moving a bullet moves only within its parent unless the complete parent record moves. Parsing remains dependency-light and supports the Markdown conventions already accepted by the product. IDs derive deterministically from the source path and position. Missing, duplicate, or unknown IDs invalidate only the affected decision.

If a block cannot be parsed safely, store its source as an opaque entry. The renderer strips active Markdown structure from that value and emits escaped plain text under its original section; it never passes model-produced Markdown through. Fallback uses this normalized source text in the resume's original language.

The resume chain returns typed edit decisions instead of unrestricted final Markdown:

- `keep`: preserve source text and position unless its enclosing section moves.
- `move`: preserve text while changing section or entry priority.
- `rewrite`: return revised text with source entry ID, evidence IDs, and a concise reason.
- `omit`: hide irrelevant content from this output without changing the uploaded source.

Unknown source IDs, unsupported additions, changed ownership, and ungrounded facts are invalid. Only the affected decision is sent for one repair; accepted decisions remain byte-for-byte stable. A second compliance failure restores the normalized source entry in the resume's language and records a warning. Existing section-level context and service-error recovery remain available.

## Language Policy

A deterministic detector runs independently over the JD and master resume. It normalizes Unicode, removes URLs, email addresses, fenced/inline code, and numbers, then counts Han characters and Latin alphabetic characters; technology names remain ordinary language-bearing text. At least 20 language-bearing characters are required. A Han share of at least 30% selects `zh`; a lower share selects `en`. If one input is short or empty, it falls back to the other input's detected language; if both are ambiguous, use `zh` when either contains Han text and otherwise `en`. Exact counts, threshold, selected language, and source are stored as `analysis_language` (JD) and `resume_language` (resume) in Graph state and `run.json`.

Every LangChain task receives its artifact language explicitly. Resume generation, verification, Markdown headings, and target-resume warnings use `resume_language`. Requirement explanations, match rationales, growth tasks, report headings, and interview questions use `analysis_language`. Evidence identifiers and proper nouns are never translated automatically. The first MVP offers no manual language selector and no simultaneous bilingual output.

## Natural Writing Guardrails

Prompts require concise, concrete language and preservation of useful source wording. They prohibit unsupported numbers, technologies, ownership, outcomes, and generic self-promotion. Chinese output additionally treats expressions such as “赋能”, “深耕”, “卓越”, “全面提升”, and “显著推动” as suspicious when they were absent from the source and unsupported by evidence.

Python validation compares each rewrite with its source and assigned evidence. New numbers, technology terms, strong outcome language, or promotional phrases trigger one bounded repair. If repair remains unsafe or generic, the resume output restores the original-language source and records a warning. This is a conservative warning system, not a broad claim that every occurrence of a word is invalid.

## Deterministic Markdown Rendering

The renderer owns formatting. It emits one top-level resume heading, second-level section headings, consistent blank lines, and stable unordered lists. Company or project, role, and dates retain their relationships and receive a compact consistent hierarchy. Existing contact details, links, proper nouns, and concrete business context survive.

The model may prioritize sections and entries according to JD relevance, but cannot produce Markdown syntax or decorative slogans. The renderer does not add a generic professional summary, self-rating, visual ornaments, tables, PDF layout, or theme system. Unparseable source blocks emit normalized, Markdown-escaped source text and cannot inject active headings, lists, or tables.

## Graph and Growth Semantics

Gap analysis treats every non-`strong` status as actionable:

- `partial`: include only source-backed facts from the supported portion and create a task for the missing portion.
- `transferable`: include only source-backed transferable facts and create a targeted task.
- `gap`: omit unsupported claims and create a task.

Every actionable requirement must map to a growth task, using deterministic fallback tasks when the model omits one. Requirement wording, growth tasks, and target aspirations are never evidence for application-resume claims. Target-resume aspirations remain visibly non-submittable and link to those tasks.

When all requirements are `strong`, gap analysis emits durable `node_skipped` events for both growth-plan and target-resume stages before continuing. Each event contains `node`, `status: skipped`, and a stable `reason_code: no_actionable_gap`; no other current path skips these nodes because deterministic fallback guarantees a task for every actionable requirement. Events are persisted and replayed like completion events, including after refresh and process restart. A resumed Run retains prior skipped events and does not re-emit them. The Web distinguishes pending, running, complete, skipped, waiting, and failed states. Skipped nodes say why they were skipped instead of remaining white.

## Human Review Experience

`waiting_review` is a successful checkpointed pause, not a warning or failure. The workspace displays “生成已完成，请审核可投递简历” and a primary “审核可投递简历” action near the current step. Both that action and the human-review Graph node call the existing client-side `openReview("application-resume.md")` route. The SVG node has `role="button"`, `tabindex="0"`, an accessible label, visible focus, pointer activation, and Enter/Space activation. Refresh and restored Runs reconstruct the waiting node from persisted `review_required`; focus remains on the workspace action rather than auto-opening a modal.

The review view keeps rendered Markdown as the default and source editing as an option. Approving an unchanged resume completes the Run. Edited content still passes the existing evidence verification before approval. Rejecting records a terminal `rejected` checkpoint and event after an explicit message that rejection will not regenerate automatically.

## Error Handling

- Ambiguous JD or resume language detection falls back to the other input's language and records a warning.
- Unsafe parsing emits normalized, Markdown-escaped source text as an opaque entry; it never preserves active source or model Markdown syntax.
- Invalid model decisions repair once, then restore only the affected source entry.
- Promotional or unsupported rewrites repair once, then restore source wording.
- Actual timeout, authentication, connection, and response-parsing failures remain Run failures eligible for checkpoint recovery.
- State gains a schema version. Before resuming an older checkpoint, a state upgrader derives missing `analysis_language` and `resume_language` metadata from retained JD/resume text and reconstructs node state only from persisted events. Legacy `GeneratedSection` values remain generated candidates and never become source or evidence. They may continue through verification only when their retained claims reference existing evidence; otherwise the affected section restores the corresponding master-resume section with a warning. The upgrader never marks a node skipped without a `node_skipped` event and never reruns an already checkpointed stage. Old completed Runs remain read-only without artifact migration.

## MVP Boundaries

The MVP includes language consistency, structured editing, deterministic Markdown, natural-writing validation, actionable partial matches, explicit skipped/waiting Graph states, and a discoverable review action. It does not include Word/PDF export, themes, drag-and-drop layout, user-defined phrase dictionaries, bilingual output, cover letters, portraits, or personal-brand slogans.

## Verification

- Exact artifact snapshots cover Chinese/Chinese and English-JD/Chinese-resume fixtures. In the mixed fixture, both resume artifacts remain Chinese while match, growth, and interview artifacts are English; headings, blank lines, and lists remain stable.
- Detector boundary fixtures cover 19 and 20 language-bearing characters, exactly 30% Han, stripped URLs/code/numbers, technology-name counting, cross-input fallback, and the final `zh`/`en` default.
- A preservation fixture asserts unchanged output for already-clear same-language bullets.
- Move fixtures assert that company, project, role, date, links, and bullet ownership IDs are unchanged; duplicate, missing, and unknown IDs exercise localized fallback.
- Prohibited-token fixtures add unsupported numbers, technologies, outcome verbs, and promotional phrases and assert either a grounded repaired decision or exact restoration of the normalized source entry; unsafe generated text must be absent from the application resume.
- Parametrized `partial`, `transferable`, and `gap` fixtures assert one growth task per requirement and no aspirational leakage into the application resume.
- A no-gap event fixture asserts both persisted `node_skipped` payloads and their replayed Web states.
- Browser-source tests assert the review CTA, `openReview` route, node role/tabindex, Enter/Space behavior, visible waiting copy, and terminal rejection event.
- Legacy checkpoint fixtures cover missing schema/language/edit fields without rerunning completed stages; existing edited-resume verification and classified service-error tests continue to pass.

## Tradeoff and Evolution

Structured editing is less visually dramatic than free-form generation, but it is safer, more personal, easier to understand, and suitable for an actual application. Later iterations may add selectable templates or document export on top of the typed resume model without giving the model ownership of facts or layout.

## Implementation Outline

1. Add dependency-free language detection and localized message catalogs. Persist `analysis_language`, `resume_language`, detector metadata, and schema version in Graph state and Run summaries.
2. Extend domain contracts with resume entries and typed edit decisions. Replace free-form section generation with source-ID decisions, localized repair, source fallback, and a deterministic Markdown renderer while retaining a legacy generated-section adapter for resumable checkpoints.
3. Treat all non-`strong` matches as actionable. Emit durable skipped events for growth and target stages when no actionable requirement exists, and expose their reason through Web event serialization.
4. Add the waiting-review CTA and make only the human-review SVG node accessible by pointer, Enter, and Space while waiting. Render skipped and waiting as distinct states and preserve them across refresh.
5. Add detector boundaries, bilingual artifact snapshots, source-fidelity and prohibited-language fixtures, growth coverage, skipped-event replay, review accessibility, and legacy checkpoint regressions. Run the complete Python and JavaScript validation suite before the functional commit.

Primary implementation files are `domain.py`, new focused language/resume-rendering modules, `chains/*.py`, `graph/{state,nodes,routes}.py`, `output.py`, `web/{service,static/*}`, and the corresponding test files. No new runtime dependency or frontend framework is required.
