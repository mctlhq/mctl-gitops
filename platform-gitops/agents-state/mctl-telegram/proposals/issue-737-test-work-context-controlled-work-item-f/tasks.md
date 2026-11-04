# Tasks: issue-737-test-work-context-controlled-work-item-f

No code tasks. Do NOT approve this proposal, and do not run the implementer for it.

- [ ] 1. Owner records the session evidence on mctlhq/mctl-telegram#443 (and the REST evidence on
  mctlhq/mctl-api#341): WorkItem id, start request id and its `fulfilled` state, execution id,
  and the portal `/work-items/<id>` view. DoD: comment posted on #443.
- [ ] 2. (depends on 1) Owner ends the parked DevLoop `dev-loop-mctlhq-mctl-telegram-737` with an
  abandon, not an approve, with a reason citing #443. DoD: `mctl_get_dev_loop` reports a
  terminal status, and the proposal remains unapproved.

## Tests
- [ ] T1. `/mctl work status` in the bound Saved Messages thread shows the request as
  `fulfilled -> <execution id>`, matching the execution the portal shows for the same WorkItem.
- [ ] T2. No `feat/agents-issue-737-*` branch or PR exists in mctlhq/mctl-telegram.

## Rollback
Nothing to roll back: no code or config changes. If the proposal was approved by mistake,
close any implementer PR unmerged and abandon the DevLoop.
