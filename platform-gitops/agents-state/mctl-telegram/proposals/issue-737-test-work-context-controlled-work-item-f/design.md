# Design: issue-737-test-work-context-controlled-work-item-f

## Current state
The Telegram work-context adapter that the #443 session exercises already ships:
- `internal/agent/control/work.go`:
  - `WorkHandler.handleOpen` canonicalises the issue URL (`workctx.CanonicalIssueURL`) and
    resolves the linked actor (`resolveActor`).
  - It then creates or opens the WorkItem through `workctx.Client.CreateWorkItem`, using the
    issue URL as `ExternalKey` and a deterministic `workctx.IdempotencyKey`.
  - It records the thread binding (`Store.UpsertWorkItemBinding`), registers the surface ref
    (`AddSurfaceRef`) and submits the `start` execution request (`RequestExecution`,
    `ExecutionKindStart`). This request is what started the investigation producing this proposal.
- `WorkHandler.handleWorkStatus` shows the WorkItem's state, latest execution, pending approval
  and snapshot, plus the last request's state (`renderRequestLine`, `formatRequestState`).
- `internal/workctx/client.go` holds the mctl-api relay client (create, get, intents, execution
  requests, surface refs). `internal/db/work_item_bindings.go` stores the bindings.
- `docs/work-context.md` "Manual cross-surface verification" is the procedure the live session follows.

Deployed state checked:
- `mctl_get_service_status(team=labs, service=mctl-telegram)`: ArgoCD `Healthy`/`Synced`,
  image `0.123.2`, host `tg.mctl.ai`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:
  - `workContext.enabled: true`, `featureEnabled: true`, `tenant: mctl`, token from
    `platform/mctl-api/surface-tokens` / `telegram-token`.
  - `HUMAN_INPUT_ENABLED: "true"`.
  - The `/mctl work` path is live in production.
  - The comment in that block mentions tenant "admins", but the value is `mctl`. See Open questions.
- I did not observe the WorkItem id, the execution request or the portal view for #737. They are
  produced by the owner's session and are outside this run's reach.

## Proposed solution
No code change. The issue is a controlled fixture: the DevLoop investigation it triggers is the
observed artifact. The proposal is deliberately empty of implementation work so that:
1. The DevLoop parks at the approval gate. That is the expected end state for the session.
2. The owner records the WorkItem id, request id, execution id and portal screenshot or REST
   response on #443 (and on mctlhq/mctl-api#341 for the REST evidence).
3. The owner then ends the loop with `mctl_abandon_dev_loop` on
   `dev-loop-mctlhq-mctl-telegram-737`, giving a reason that cites #443. The proposal is
   never approved.

## Alternatives
- Invent a small change to make the proposal "useful": rejected. The issue explicitly forbids
  implementation, and a fabricated change would risk being approved and merged.
- File a clarification question instead: rejected. The issue is unambiguous about its intent,
  so nothing is blocking.
- Leave the DevLoop parked forever: possible, but it keeps a live workflow and its ownership
  row indefinitely. Abandoning after the evidence is recorded is cleaner.

## Platform impact
- No migrations, no config change, no resource impact.
- Risk: an operator approves the proposal by habit. Mitigation: the title and every file say
  "no implementation". If it does get approved, close any resulting PR unmerged.
