# Tasks: issue-737-test-work-context-controlled-work-item-f

No implementation tasks. This proposal must not be approved (issue #737 forbids it).

- [ ] 1. Owner confirms `/mctl work status` shows the start request as `fulfilled, execution <id>` — DoD: request id and execution id captured.
- [ ] 2. Owner opens the same WorkItem in the portal at `/work-items/<id>` (depends on 1) — DoD: portal shows the same WorkItem id and execution.
- [ ] 3. Owner records the evidence on #443 and the REST evidence for mctlhq/mctl-api#341 (depends on 2) — DoD: comment posted.
- [ ] 4. Reject this proposal / abandon its DevLoop (depends on 3) — DoD: no PR opened against mctl-telegram; #737 stays closed.

## Tests
- [ ] T1. None to add. Existing `internal/agent/control/work_test.go` and `internal/workctx/client_test.go` already cover the exercised paths; the live session itself is the manual end-to-end check.

## Rollback
Nothing to roll back: no code, config or gitops change is made. If the proposal was approved by mistake, abandon the DevLoop and close any resulting PR unmerged.
