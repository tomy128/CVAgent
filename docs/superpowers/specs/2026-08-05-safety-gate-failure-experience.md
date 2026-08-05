# Safety Gate Failure Experience

## Decision

The evidence safety gate remains a hard boundary. A user cannot manually approve unsupported resume claims. The existing one-time retrieval and verification retry remains automatic; if the second verification still fails, the Run ends in a dedicated safety-failure state.

## Failure Contract

Raise a typed safety error containing individual issues rather than one opaque string. Persist those issues in redacted Run metadata and durable events. On failure, recover the latest checkpoint state and write available draft, verification, retrieval, and a concise `failure-report.md`; these are diagnostic artifacts, not approved output.

The server logs the captured exception with Run and node context. Other workflow errors retain their existing behavior.

## Web Experience

Render “事实安全未通过,” list every unsupported or unclassified claim, and explain that the automatic evidence retry was exhausted. Offer the failure report and instruct the user to add supporting Sources or remove/weaken the claims before starting a new Run. Do not show checkpoint retry for safety failures because it deterministically repeats the same gate. Do not add manual override or inline remediation in this iteration.

## Implementation and Verification

Introduce a typed safety exception, enrich failure classification, snapshot recoverable checkpoint state, and add a dedicated failure panel using the existing native Web stack. Add workflow, service, API, and UI regression coverage; run the full Python suite and JavaScript validation.
