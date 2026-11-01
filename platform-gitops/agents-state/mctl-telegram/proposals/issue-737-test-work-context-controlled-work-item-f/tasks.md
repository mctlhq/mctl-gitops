# Tasks: issue-737-test-work-context-controlled-work-item-f

This proposal intentionally contains no implementation tasks (see requirements.md). Do not approve it.

- [ ] 1. Owner records the live-session evidence (the WorkItem id, the start request reaching `fulfilled` in `/mctl work status`, and the portal `/work-items/<id>` view) on mctlhq/mctl-telegram#443 and mctlhq/mctl-api#341. This is manual and outside this repository. DoD: evidence comment posted.
- [ ] 2. (depends on 1) Owner abandons the DevLoop `dev-loop-mctlhq-mctl-telegram-737` without approving it. DoD: the loop status is not Running, and no PR exists for this proposal.

## Tests
- [ ] T1. Confirm no branch `feat/agents-issue-737-*` and no PR were created in mctlhq/mctl-telegram.

## Rollback
Nothing to roll back: no code, config or gitops change is proposed. If the proposal was approved by mistake, close any resulting PR unmerged.
