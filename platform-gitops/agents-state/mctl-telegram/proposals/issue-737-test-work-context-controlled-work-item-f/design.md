# Design: issue-737-test-work-context-controlled-work-item-f

## Current state
The path the live session exercises already exists and needs no change:

- `internal/agent/control/work.go`: `WorkHandler.Handle` dispatches `/mctl link`, `/mctl work <url>`, `/mctl work status`, `/mctl work note` and `/mctl work resume`.
  - `handleOpen` calls `workctx.CanonicalIssueURL`, resolves the linked actor (`resolveActor`), checks the thread binding (`Store.GetWorkItemBinding`), then calls `Client.CreateWorkItem` with a deterministic `IdempotencyKey(chat, msg, "open", 0)`. It persists the binding (`Store.UpsertWorkItemBinding`), registers the thread (`Client.AddSurfaceRef`), and submits `Client.RequestExecution` with `ExecutionKindStart` and key `IdempotencyKey(chat, msg, "start", 0)`. Finally it stores the request id (`Store.SetWorkItemBindingRequest`).
  - `handleWorkStatus` reads `Store.LatestWorkItemBinding` and calls `Client.GetWorkItem`, then refreshes the local mirror with `Store.TouchWorkItemBindingState`. It renders the request through `renderRequestLine` and `formatRequestState`, which covers the states `pending`, `claimed`, `fulfilled` (with execution id) and `rejected`.
- `internal/workctx/target.go`: `CanonicalIssueURL` accepts only `https://github.com/mctlhq/<repo>/issues/<n>`. The URL `https://github.com/mctlhq/mctl-telegram/issues/737` is therefore a valid target with a stable `external_key`.
- `internal/workctx/client.go`: the allowlisted REST relay to mctl-api (`CreateWorkItem`, `GetWorkItem`, `RequestExecution`, `GetExecutionRequest`, `ListExecutionRequests`, `AddSurfaceRef`). These calls are the REST evidence that mctl-api#341 needs.
- `internal/db/work_item_bindings.go`: the per-thread binding store.
- `docs/work-context.md`: "Manual cross-surface verification" already describes the session steps (link, work, status until `fulfilled`, open the same `work_item_id` on a second surface). "Rollback" describes `WORK_CONTEXT_ENABLED=false`.

## Proposed solution
No change to the repository. Issue #737 is a fixture. The investigation that produced this proposal is itself the `start` execution the session observes. The design therefore has three parts:

1. **Run the session using the procedure in `docs/work-context.md`**, with issue #737 as the target and the portal (`/work-items/<id>`, mctl-portal#126) as the second surface.
2. **Record the evidence on #443.** Include the work item id, the start request id and its `pending` -> `claimed` -> `fulfilled` progression as rendered by `formatRequestState`, the execution id, and confirmation that the portal shows the same WorkItem, execution and snapshot pointer. Include the matching mctl-api REST observations for #341.
3. **Neutralise the DevLoop.** Do not approve this proposal (do not call `mctl_approve_dev_loop` or `mctl_trigger_approve`). Leave the DevLoop parked, or cancel it. Then close #737.

Shipping nothing is the only design consistent with the issue's explicit instruction ("nothing here should be implemented").

## Alternatives
- **Add an automated end-to-end test for `/mctl work` against a stub mctl-api.** Dropped. Unit coverage already exists in `internal/agent/control/work_test.go` and `internal/workctx/client_test.go`, and the issue asks for live evidence, not new tests.
- **Extend `docs/work-context.md` with a "session evidence" section.** Dropped. Evidence belongs on #443, where acceptance is judged. Committing run-specific ids to a public repo adds noise and could expose account-linked data.
- **Treat the issue as a feature request and harden something found along the way.** Dropped. That would directly contradict the issue, and the approval gate would then have to be trusted not to act on it.

## Platform impact
- Migrations: none. Backward compatibility: unaffected. Resources: one DevLoop investigation (already incurred) plus a handful of mctl-api relay calls from the live session.
- Risk: someone approves this proposal and the implementer opens a meaningless PR. Mitigation: the proposal states do-not-approve in every file, and `tasks.md` contains no implementer-actionable code task. If a PR appears anyway, close it unmerged.
- Risk: a dangling DevLoop stays parked on the approve signal indefinitely. Mitigation: the owner cancels it, or accepts it as parked, once the evidence is recorded.
- Risk: the evidence leaks private data. Mitigation: post only platform ids and states. Post no Telegram user ids, handles or message bodies, consistent with the repo's safety rules in `.claude/CLAUDE.md`.
