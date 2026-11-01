# Controlled work item for the #443 live session: no code change

## Context
Issue #737 is not a feature request or a bug. It is a controlled GitHub issue the
owner created as the target of a live session that closes mctlhq/mctl-telegram#443
(the Telegram work-context adapter) and supplies REST evidence for
mctlhq/mctl-api#341. In that session the owner runs `/mctl link`, then
`/mctl work https://github.com/mctlhq/mctl-telegram/issues/737` from Telegram Saved
Messages, polls `/mctl work status` until the `start` execution request is
fulfilled, and opens the same WorkItem in the portal at `/work-items/<id>`
(mctlhq/mctl-portal#126).

The `start` request is what started this DevLoop investigation. The issue says
plainly that the proposal must not be approved and nothing must be implemented.
The issue is already CLOSED. This proposal therefore records that this run
happened and specifies no change to the repository. It exists so the session can
observe a fulfilled execution with a sealed proposal.

## User stories
- AS the platform owner I WANT the DevLoop started by `/mctl work` to finish with a proposal SO THAT the live session can observe a fulfilled start request end to end.
- AS a reviewer I WANT the proposal to state that no implementation is intended SO THAT nobody approves it by mistake and no PR is opened.

## Acceptance criteria (EARS)
- WHEN this proposal is reviewed THE SYSTEM SHALL present no code, config or gitops change to implement.
- WHILE issue #737 is a controlled test item THE SYSTEM SHALL leave the proposal unapproved (status remains `proposed`, or the DevLoop is abandoned by the owner).
- IF someone approves this proposal THEN the implementer SHALL find no tasks that change files, and SHALL open no pull request.
- WHEN the session evidence is recorded on #443 THE SYSTEM SHALL need no follow-up from this proposal.

## Out of scope
- Any change to `internal/agent/control/work.go`, `internal/workctx/`, `internal/db/work_item_bindings.go` or other repository code.
- Any change to `services/labs/mctl-telegram/values.yaml` in mctl-gitops.
- Recording the session evidence on #443 or mctl-api#341. The owner does this by hand.
- Approving, implementing or merging anything for #737.

## Open questions
- Should the owner abandon this DevLoop (`mctl_abandon_dev_loop` on `dev-loop-mctlhq-mctl-telegram-737`) once the evidence is recorded, rather than leaving it parked at the approval gate? Leaving it parked is harmless, but an abandoned loop releases its lifecycle-ownership row. This proposal recommends abandoning it.
- The gitops comment above `workContext` says the tenant step was done with "tenant admins", but the deployed value is `tenant: mctl`. That does not affect this proposal; it is noted so the owner can confirm which tenant the WorkItem was created in when collecting evidence.
