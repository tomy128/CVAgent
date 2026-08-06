# Current Tasks

## [In Progress] Make model compliance failures recoverable
- Status: In Progress
- Goal: Convert unsupported JD matches into growth-plan gaps and safely continue when a local model returns invalid evidence metadata.
- Acceptance: Unassigned match evidence is normalized to a gap; invalid generated claims receive one repair then original-section fallback; warnings are visible; unrecoverable service errors still fail; regressions and the failed checkpoint path pass.
