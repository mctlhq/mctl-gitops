# Controlled work item for the #443 live session (no implementation)

## Context
Issue #737 is a controlled test fixture, not a change request. It exists so the
owner can run the #443 live session end to end: `/mctl link`, then
`/mctl work https://github.com/mctlhq/mctl-telegram/issues/737` from Telegram
Saved Messages, `/mctl work status` until the `start` execution request is
fulfilled, and the same WorkItem opened in the portal at `/work-items/<id>`
(mctlhq/mctl-portal#126). That flow also produces the REST evidence for
mctlhq/mctl-api#341.

The DevLoop investigation that produced this proposal is the execution being
observed. The issue says plainly that the proposal must not be approved and that
nothing should be implemented. The issue is already CLOSED. This proposal
therefore records the investigation as evidence and changes no code.

## User stories
- AS the platform owner I WANT the `/mctl work` start request to run a real DevLoop investigation on a harmless issue SO THAT I can observe the WorkItem lifecycle across Telegram, mctl-api and the portal.
- AS a reviewer I WANT the proposal to say plainly that nothing is to be built SO THAT nobody approves it by accident and the implementer is not triggered.

## Acceptance criteria (EARS)
- WHEN the investigation for #737 finishes THE SYSTEM SHALL leave a proposal that names zero code, config or gitops changes.
- WHILE this proposal exists THE SYSTEM SHALL stay at status `proposed`, and no reviewer SHALL approve it.
- IF the proposal is approved by mistake THEN the implementer SHALL find no task that changes the repository (every task in tasks.md is a non-code verification or closure step).
- WHEN the session evidence is recorded on #443 THE SYSTEM SHALL have the proposal abandoned or rejected rather than merged.

## Out of scope
- Any change to `internal/agent/control/work.go`, `internal/workctx/`, `internal/db/work_item_bindings.go` or any other source file.
- Any change to `services/labs/mctl-telegram/values.yaml` or other gitops config.
- Recording the evidence on #443 or mctlhq/mctl-api#341. The owner does that by hand.
- Fixing any defect seen during the session. A defect gets its own issue.

## Open questions
- None that block this proposal. If the live session shows a defect in `/mctl work` or `/mctl work status`, it should be filed as a separate issue and not folded into this one.
