# Tasks: issue-737-test-work-context-controlled-work-item-f

There are no implementation tasks. This proposal must NOT be approved.

- [ ] 1. (Owner, manual, outside the implementer) Confirm `/mctl work status`
  shows the #737 start request as `fulfilled` with this investigation's
  execution id, and that the portal `/work-items/<id>` shows the same execution
  and snapshot pointer — DoD: evidence recorded on mctlhq/mctl-telegram#443 and
  mctlhq/mctl-api#341.
- [ ] 2. (Owner, manual, depends on 1) End the parked DevLoop for #737 without
  approving it (e.g. `mctl_abandon_dev_loop`, reason "controlled test item for
  #443") and leave the proposal un-accepted — DoD: no `feat/agents-issue-737-*`
  branch or PR exists in `mctlhq/mctl-telegram`.

## Tests
- [ ] T1. `git log` / PR list on `mctlhq/mctl-telegram` shows no change
  attributable to issue #737.
- [ ] T2. `/mctl work status` in Saved Messages renders the request line via
  `formatRequestState` in `internal/agent/control/work.go` as `fulfilled`.

## Rollback
Nothing to roll back: no code, config or docs change is made. If the proposal
was approved by mistake, abandon the DevLoop, close any resulting PR unmerged,
and mark the proposal `rejected`.
