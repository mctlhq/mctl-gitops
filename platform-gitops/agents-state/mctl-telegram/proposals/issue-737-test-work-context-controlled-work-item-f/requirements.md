# Controlled work item for the #443 live session (no-op proposal)

## Context
Issue #737 is not a feature or bug request. It is a controlled GitHub issue the
owner created as the target of a live end-to-end session for the work-context
surface adapter (issue #443, documented in `docs/work-context.md`). The session
runs `/mctl link`, then `/mctl work https://github.com/mctlhq/mctl-telegram/issues/737`
from Telegram Saved Messages, polls `/mctl work status` until the `start`
execution request is `fulfilled`, and opens the same WorkItem in the portal at
`/work-items/<id>` (mctlhq/mctl-portal#126). The evidence also feeds
mctlhq/mctl-api#341.

The `start` request created by `/mctl work` is what launches this DevLoop
investigation, so this proposal is itself the execution the session observes.
The issue states explicitly that the proposal must not be approved and that
nothing should be implemented. This proposal therefore records an intentional
no-op: zero code, config, or documentation changes to `mctl-telegram`. The issue
is already CLOSED.

## User stories
- AS the platform owner running the #443 live session I WANT the DevLoop
  investigation on #737 to complete and produce a proposal SO THAT the WorkItem's
  `start` request reaches `fulfilled` with a real execution id I can observe in
  Telegram and the portal.
- AS a reviewer I WANT the proposal to declare plainly that no implementation is
  intended SO THAT nobody approves it by mistake and no PR is opened.

## Acceptance criteria (EARS)
- WHEN the investigator runs on issue #737 THE SYSTEM SHALL write a proposal
  (requirements.md, design.md, tasks.md) that contains no implementation tasks
  against the `mctl-telegram` code base.
- WHILE this proposal exists THE SYSTEM SHALL leave every file in
  `mctlhq/mctl-telegram` unchanged (no branch `feat/agents-issue-737-*`, no PR).
- IF this proposal is ever approved THEN THE SYSTEM SHALL treat it as an
  operator error: the implementer has no task to perform and the operator should
  move the proposal to `rejected` (or abandon its DevLoop) instead of letting it
  produce a commit.
- WHEN the owner reads `/mctl work status` after this investigation finishes THE
  SYSTEM SHALL (via the existing code path `WorkHandler.handleWorkStatus` in
  `internal/agent/control/work.go`) show the start request as `fulfilled` with
  the execution id - no new behaviour is required for this.

## Out of scope
- Any change to `internal/agent/control/work.go`, `internal/workctx/`,
  `internal/db/work_item_bindings.go`, `docs/work-context.md` or any other file.
- Approving this proposal or running the Tier 2 implementer on it.
- Recording the session evidence on #443 and closing #737 (owner-run, manual).
- Changes in mctl-api (#341) or mctl-portal (#126).

## Open questions
- None blocking. Reviewer note: the DevLoop for this issue will park at the
  approval gate indefinitely; once the #443 evidence is recorded, the owner may
  want to end it with `mctl_abandon_dev_loop` (reason: "controlled test item for
  #443, not to be implemented") so it does not linger.
