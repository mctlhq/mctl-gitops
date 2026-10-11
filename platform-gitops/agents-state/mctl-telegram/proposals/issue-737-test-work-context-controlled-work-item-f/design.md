# Design: issue-737-test-work-context-controlled-work-item-f

## Current state
The work-context surface adapter from #443 already exists in this repo:
- `internal/agent/control/work.go` - `WorkHandler` with `handleLink`,
  `handleOpen` (creates/opens the canonical WorkItem via mctl-api and submits a
  `start` execution request keyed by `workctx.IdempotencyKey(..., "start", 0)`),
  `handleWorkStatus` / `renderRequestLine` / `formatRequestState` (renders
  `pending`, `claimed`, `fulfilled`, `failed: <reason>`), `handleNote` and
  `handleResume`.
- `internal/workctx/client.go` - mctl-api client (`RedeemLink`,
  `CreateWorkItem`, `GetWorkItem`, `RequestExecution`, `GetExecutionRequest`,
  `ListExecutionRequests`, `AddSurfaceRef`).
- `internal/db/work_item_bindings.go` - thread-to-WorkItem bindings
  (`UpsertWorkItemBinding`, `LatestWorkItemBinding`,
  `SetWorkItemBindingRequest`, `TouchWorkItemBindingState`).
- `docs/work-context.md` - documents the exact session the issue describes
  under "Manual cross-surface verification", and
  `docs/contracts/mctl-api-work-context.md` the mctl-api routes.

Issue #737 is the target issue used to exercise that flow end to end. The
platform's fulfilment of the `start` request is the DevLoop investigation that
produced this proposal.

## Proposed solution
Do nothing to the code base. The deliverable of this run is the proposal
itself: its existence lets the `start` execution request on the #737 WorkItem
reach `fulfilled`, which is the observation the #443 session needs. The
proposal deliberately contains no implementation tasks, so even an accidental
approval gives the implementer nothing to build. The owner records the session
evidence on #443 manually and ends the parked DevLoop.

## Alternatives
1. Propose a small real change (e.g. a doc tweak in `docs/work-context.md`
   noting the live session result). Dropped: the issue explicitly says nothing
   should be implemented, and any task would invite an approval and a PR.
2. Propose automated test coverage for the live flow (e.g. an integration test
   around `WorkHandler.handleOpen` + `handleWorkStatus`). Dropped: out of the
   issue's scope; `internal/agent/control/work_test.go` already covers the
   handler, and a cross-service live test belongs to a separate issue.
3. Refuse to write a proposal. Dropped: the session needs the investigation to
   complete normally so the request is observed as `fulfilled`.

## Platform impact
- Migrations: none. Backward compatibility: unaffected. Resources: none beyond
  the already-spent investigation run.
- Risk: the proposal is approved by mistake and the implementer runs.
  Mitigation: no tasks exist; the title and requirements state "no-op" and "do
  not approve"; the owner should abandon the DevLoop after evidence capture.
- Risk: the DevLoop stays parked at the approval gate forever. Mitigation:
  `mctl_abandon_dev_loop` once #443 evidence is recorded.
