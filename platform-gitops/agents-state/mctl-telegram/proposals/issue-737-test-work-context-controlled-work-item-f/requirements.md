# Controlled work item for the #443 live session (no implementation)

## Context
Issue mctlhq/mctl-telegram#737 is a controlled fixture, not a change request. It exists so the
owner can run the #443 work-context live session end to end: `/mctl link`, then
`/mctl work https://github.com/mctlhq/mctl-telegram/issues/737` from Telegram Saved Messages,
`/mctl work status` until the `start` execution request is `fulfilled`, and the same WorkItem
opened in the portal at `/work-items/<id>` (mctlhq/mctl-portal#126). The session also supplies
REST evidence for mctlhq/mctl-api#341.

`/mctl work` submits a `start` execution request, which runs this DevLoop investigation. The
issue states plainly that the resulting proposal must not be approved and nothing must be
implemented. The issue is already CLOSED. This proposal therefore records that intent and
defines no code change. The run producing it is the evidence. It is not a deliverable.

## User stories
- AS the platform owner I WANT the `/mctl work` start request on #737 to produce a real
  DevLoop execution SO THAT the #443 session can observe `pending -> claimed -> fulfilled`
  across Telegram, REST and the portal.
- AS a reviewer I WANT this proposal to say explicitly that nothing should be built SO THAT
  nobody approves it and the implementer opens no PR.

## Acceptance criteria (EARS)
- WHEN this proposal is reviewed THE SYSTEM SHALL require no repository change in
  mctlhq/mctl-telegram (tasks.md contains only verification and recording steps).
- WHILE this proposal is in status `proposed` THE SYSTEM SHALL leave the DevLoop parked at the
  approval gate. No approval signal is sent and no implementer run happens.
- IF the session evidence is recorded on mctlhq/mctl-telegram#443 THEN THE SYSTEM SHALL let
  the owner end the parked DevLoop with an abandon (not an approve), recording a reason that
  cites #443.
- IF someone approves this proposal by mistake THEN the implementer SHALL find no code task,
  and any PR it opens SHALL be closed unmerged.

## Out of scope
- Any change to `internal/agent/control/work.go`, `internal/workctx/`, `internal/db/work_item_bindings.go`
  or any other code, docs or config in this repository.
- Any change to the deployed `labs/mctl-telegram` configuration in mctl-gitops.
- Fixing defects the live session finds. Each one gets its own issue.

## Open questions
- Whether the parked DevLoop for this issue should be ended with an abandon after the evidence
  is recorded, or left parked. Recommendation: abandon it, citing #443.
- The gitops comment in `services/labs/mctl-telegram/values.yaml` says "tenant admins", but
  `workContext.tenant` is `mctl`. The live session will reveal which tenant the WorkItem was
  created in. That is worth noting on #443, but this proposal does not resolve it.
