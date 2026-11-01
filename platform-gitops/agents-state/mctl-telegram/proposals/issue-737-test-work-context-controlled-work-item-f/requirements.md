# Controlled work item for the #443 live session (no code change)

## Context
Issue mctlhq/mctl-telegram#737 is a deliberately controlled test work item. It exists only so the owner can run the #443 live session end to end: `/mctl link`, then `/mctl work https://github.com/mctlhq/mctl-telegram/issues/737` from Telegram Saved Messages, `/mctl work status` until the `start` execution request is fulfilled, and the same WorkItem opened in the portal at `/work-items/<id>` (mctlhq/mctl-portal#126). That session also supplies REST evidence for mctlhq/mctl-api#341.

The DevLoop investigation that produced this proposal is itself the execution the session observes. The issue states explicitly that the proposal must not be approved and that nothing is to be implemented; the issue is already CLOSED. This proposal therefore specifies no repository change. It records the expected observable behaviour of the already-shipped work-context adapter (`internal/agent/control/work.go`, `internal/workctx/`) so the reviewer can check the session evidence against it, and it is meant to be left unapproved (or rejected).

## User stories
- AS the platform owner I WANT a throwaway issue whose DevLoop run I can observe from Telegram and the portal SO THAT I can record end-to-end evidence for #443 and mctl-api#341 without changing any code.
- AS a reviewer I WANT the proposal to state plainly that it contains no implementation work SO THAT nobody approves it and sends it to the implementer by mistake.

## Acceptance criteria (EARS)
- WHEN the owner sends `/mctl work https://github.com/mctlhq/mctl-telegram/issues/737` in Saved Messages from a linked account THE SYSTEM SHALL create (or reuse) one WorkItem with external key equal to the issue URL, bind it, and submit exactly one `start` execution request (existing behaviour of `WorkHandler.handleOpen`).
- WHEN the owner sends `/mctl work status` THE SYSTEM SHALL reply with the WorkItem id, issue URL, state, and the request line from `formatRequestState` (`pending`, `claimed`, `fulfilled, execution <id>`, or `failed: <reason>`).
- WHILE this proposal exists THE SYSTEM SHALL NOT receive any code, configuration, schema or gitops change attributable to it.
- IF this proposal is approved THEN the reviewer SHALL treat that as an error and reject or abandon the DevLoop, because the issue forbids approval and implementation.
- WHEN the session evidence (WorkItem id, request id, execution id, portal URL) is recorded on #443 THE SYSTEM SHALL require no further action on #737 (it is already closed).

## Out of scope
- Any change to `mctl-telegram` code, tests, migrations, Helm values or docs.
- Fixing any defect the live session might surface; such findings go into new issues.
- Approving this proposal or running the Tier 2 implementer for it.

## Open questions
- None blocking. If the session surfaced a defect, it is not captured in this issue and needs its own issue.
