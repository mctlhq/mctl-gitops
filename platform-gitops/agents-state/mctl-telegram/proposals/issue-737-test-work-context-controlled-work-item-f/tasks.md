# Tasks: issue-737-test-work-context-controlled-work-item-f

DO NOT APPROVE. These are owner or operator actions, not implementer tasks. No commit to `mctl-telegram` is expected.

- [ ] 1. Owner runs `/mctl link <code>` and then `/mctl work https://github.com/mctlhq/mctl-telegram/issues/737` from Telegram Saved Messages. DoD: the reply from `WorkHandler.handleOpen` shows "Bound to work item <id>" and a start request id.
- [ ] 2. (depends on 1) Owner repeats `/mctl work status` until the request line reads `fulfilled, execution <id>`. DoD: `pending`/`claimed`/`fulfilled` transitions observed and the execution id noted.
- [ ] 3. (depends on 2) Owner opens `/work-items/<id>` in the portal (mctl-portal#126). DoD: the portal shows the same WorkItem, execution id and snapshot pointer as `/mctl work status`.
- [ ] 4. (depends on 3) Record the evidence on #443, plus the REST observations for mctl-api#341. DoD: a comment on #443 lists ids and states only, with no Telegram identifiers or message content.
- [ ] 5. (depends on 4) Leave this proposal unapproved, and cancel or abandon the DevLoop `dev-loop-mctlhq-mctl-telegram-737`. DoD: no implementer run and no `feat/agents-*` PR exists for this issue.
- [ ] 6. (depends on 4) Close issue #737. DoD: issue state is CLOSED.

## Tests
- [ ] T1. No new tests. The existing suites `go test ./internal/agent/control/... ./internal/workctx/... ./internal/db/...` remain green on main (sanity check only, no change).
- [ ] T2. Manual: the cross-surface check in steps 1-3 above, following `docs/work-context.md` "Manual cross-surface verification".

## Rollback
Nothing ships, so there is nothing to roll back in `mctl-telegram`. If an implementer PR is opened by mistake, close it unmerged and delete its branch. If the live session misbehaves, set `WORK_CONTEXT_ENABLED=false` and restart, as `docs/work-context.md` "Rollback" describes. Work items that were already created remain valid state in mctl-api.
