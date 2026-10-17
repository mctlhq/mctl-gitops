# Document approval of a DevLoop run through a bound approval grant

version-status: unverified, see commit SHA (mctl-api 4.88.0-4.90.0 per gitops bump 4163272)

## Context
Between 2026-10-13 and 2026-10-16, `mctl-api` and `mctl-agents` changed how a DevLoop run is approved: a run can be approved by its human's `aar_` approval grant bound to the run's `we_` WorkItem execution (55f168c, d2f2c71, agents 61eb4c6). Denied, spent, expired or wrong-kind grants are refused and the newest grant decides (dab23f3, 74f397a, 6311b05). The legacy approver relay is audited and gated (4df8488) and disabled in production by mctl-gitops 653572f. The existing proposal `platform-operations-approval-flow` describes only the signal and `.status.yaml` paths.

## User stories
- AS a platform admin I WANT to understand which approval paths are valid SO THAT I approve DevLoop runs correctly.
- AS a reviewer I WANT to know why an approval was refused SO THAT I can issue a fresh grant.

## Acceptance criteria (EARS)
- WHEN a reader opens the approval section THE SYSTEM SHALL list the grant-based path alongside signal and `.status.yaml` paths.
- IF a grant is denied, spent, expired or of another kind THEN THE SYSTEM SHALL state that approval is refused.
- WHEN several grants exist THE SYSTEM SHALL state the newest decides.
- WHEN a reader asks about the legacy approver relay THE SYSTEM SHALL state it is disabled in production.

## Out of scope
- Grant issuance UI, WorkItem model internals, customer principals (in flight).
