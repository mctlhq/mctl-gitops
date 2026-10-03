# Dispatcher: a kind-neutral engine-ref refusal, and the last stale `dev-loop-xr_` wording

## Context

Issue #488 collects the two P3 follow-ups that review round 3 of #487
deliberately left out of the #461 option A landing. Neither is a live defect;
both are contract hygiene that #487 could not fix without reaching outside
`mctl-agents`.

The first is a vocabulary mismatch in `orchestrator/temporal/dispatcher.py`.
`_dispatch` mints the engine ref `<loop>#<request id>`
(`issue_ref.request_engine_ref`) for **every** request kind since option A, and
guards it against mctl-api's 256-byte `MaxEngineRefBytes`
(`issue_ref.MAX_ENGINE_REF_BYTES`) because a fulfil that trips that limit comes
back as an untyped 400, which `TERMINAL_FULFIL_CODES` deliberately defers — so
the request would be re-claimed every lease period for ever. The guard is
correct; its refusal reason is not. It rejects with
`f"{xr.RESUME_REFUSED}:engine-ref-too-long"`, so a `start` is answered in the
`resume_refused:` vocabulary that `execution_requests.RESUME_REFUSAL_REASONS`
documents as "the `resume` signal's rules". A surface that branches on the
reason (which is exactly what the closed vocabulary exists for, per
`execution_requests.py` lines 52-98) is told a `start` was refused as a resume.
It is narrow: the ref is 40 bytes (`#` plus `xr_` plus a 36-char UUID) plus the
loop id `dev-loop-mctlhq-<repo>-<n>`, so the repo name and issue number would
have to exceed ~199 characters together, and GitHub caps repo names at 100. The
guard is defensive, and the wrong label is the only thing anyone will ever see
of it. Fixing it properly needs a kind-neutral reason, which means an mctl-api
vocabulary addition — the reason #487 postponed it.

The second is stale `dev-loop-xr_<id>` wording in two files outside this repo.
Every in-repo mention is load-bearing (`dispatcher.PRE_ISSUE_KEYED_DISPATCH_PREFIX`,
`execution_requests.ENGINE_RUN_ENDED`, the replay fixtures) because pre-option-A
executions are still reconciled. The two outside ones are not: mctl-gitops'
`cwft-mctl-agents-investigate.yaml` carries a comment on `temporal_workflow_id`
describing an id shape nothing mints any more (the parameter itself is still
needed, per `issue_ref.loop_workflow_id`), and mctl-api's
`handlers_write_devloop_params_test.go` uses `dev-loop-xr_0000` as a sample
value. Both are comments and fixtures; neither is functional.

## User stories

- AS a surface (Telegram, the portal) consuming execution-request rejections
  I WANT the reason for an over-long engine ref to be kind-neutral
  SO THAT I do not have to read a `start` refusal out of the `resume_refused:`
  vocabulary, and my exhaustive branch on resume reasons stays honest.
- AS an operator reading `EXECUTION_REQUEST_DISPATCH` audit lines
  I WANT the reject reason to name what actually happened
  SO THAT `resume_refused:` in a log line always means a resume was refused.
- AS a platform engineer reading `cwft-mctl-agents-investigate.yaml` or
  `handlers_write_devloop_params_test.go`
  I WANT no reference to a workflow-id shape the platform no longer mints
  SO THAT I do not go looking for a `dev-loop-xr_*` loop that cannot exist.
- AS a reviewer of ADR 011
  I WANT the documented refusal vocabulary to match the code
  SO THAT the contract stays the single source of truth after this change.

## Acceptance criteria (EARS)

- WHEN `Dispatcher._dispatch` finds `len(request_engine_ref(loop, request_id).encode("utf-8"))`
  greater than `MAX_ENGINE_REF_BYTES` THE SYSTEM SHALL reject the request with
  the kind-neutral reason `engine_ref_too_long`, for `start` and `resume` alike.
- WHEN the dispatcher rejects for an over-long engine ref THE SYSTEM SHALL do so
  before any delivery to the loop and before any fulfil, so that no `we_`
  execution is minted and no DevLoop run is started for the request.
- WHILE the refusal reason is kind-neutral THE SYSTEM SHALL NOT emit
  `resume_refused:engine-ref-too-long` from any code path.
- IF mctl-api answers the reject with a definite 4xx (`xr.REFUSED`) because it
  does not yet know `engine_ref_too_long` THEN THE SYSTEM SHALL retry the reject
  exactly once with the legacy `resume_refused:engine-ref-too-long`, and audit
  both attempts, so that a version-skewed deployment cannot strand the request
  in the claim-and-lapse loop the guard exists to prevent.
- WHILE old rows rejected by earlier builds still carry
  `resume_refused:engine-ref-too-long` THE SYSTEM SHALL keep
  `"engine-ref-too-long"` inside `execution_requests.RESUME_REFUSAL_REASONS`
  as read-side vocabulary, so those rows never normalise to `unspecified`.
- WHEN a loop's `accept_execution_request` validator refuses a delivery
  THE SYSTEM SHALL keep answering in the `resume_refused:<reason>` vocabulary
  unchanged — this proposal touches only the reason the dispatcher mints itself.
- WHEN the change lands THE SYSTEM SHALL have `docs/adr/011-work-item-resume-contract.md`
  (the sentence "The dispatcher adds `engine-ref-too-long` itself", around line
  322) and the `execution_requests.py` reason docstrings describing the new
  kind-neutral reason and the retained read-side alias.
- WHEN the mctl-gitops companion change lands THE SYSTEM SHALL have the
  `temporal_workflow_id` comment in
  `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`
  describe the issue-keyed `dev-loop-<owner>-<repo>-<n>` shape, with the
  parameter itself unchanged.
- WHEN the mctl-api companion change lands THE SYSTEM SHALL have
  `internal/api/handlers_write_devloop_params_test.go` use an issue-keyed sample
  value instead of `dev-loop-xr_0000`, with no assertion semantics changed.
- IF the mctl-api vocabulary addition has not merged THEN THE SYSTEM SHALL NOT
  merge the mctl-agents change that emits the new reason.

## Out of scope

- Any change to the loop-side refusal vocabulary
  (`malformed-delivery`, `work-item-mismatch`, `resume-already-pending`,
  `surface-or-actor-missing`, `surface-or-actor-unrecognised`) or to
  `DevLoopWorkflow.accept_execution_request`.
- Removing `PRE_ISSUE_KEYED_DISPATCH_PREFIX`, `ENGINE_RUN_ENDED`, or the
  pre-option-A reconciliation path — those `dev-loop-xr_` mentions are
  load-bearing and stay.
- Re-recording `tests/fixtures/histories/dev_loop_resumed.json` or
  `dev_loop_issue_keyed.json`; they are kept as the in-flight shape on purpose.
- Bounding repo-name or issue-number length in `issue_ref.parse_issue_url`,
  or raising/lowering `MAX_ENGINE_REF_BYTES`.
- Changing which fulfil codes are terminal (`TERMINAL_FULFIL_CODES`).
- Any surface-side (Telegram, portal) rendering of the new reason beyond
  whatever already handles an unrecognised top-level reason.

## Open questions

- **Exact spelling of the new reason.** This proposal picks
  `engine_ref_too_long`, matching the snake_case of every other top-level
  reason (`no_runnable_target`, `unsupported_kind`, `loop_active`,
  `engine_run_ended`). mctl-api owns the vocabulary and may prefer another
  spelling; if so, the constant's value changes and nothing else does.
- **Does mctl-api validate the reject reason server-side at all?** The client
  (`work_context/client.py::reject_execution_request`) posts the string as-is,
  and nothing in this repo proves a closed server-side list. #488 asserts a
  vocabulary addition is needed, so this proposal assumes it is validated. The
  one-shot legacy fallback makes the assumption safe either way: if mctl-api
  never validated it, the fallback simply never fires.
- **Whether the mctl-api and mctl-gitops edits become their own PRs.** They are
  in different repositories, so the implementer cannot land them on this
  proposal's `feat/agents-<slug>` branch. Treated here as two companion tasks
  with their own PRs; the mctl-api vocabulary addition is a hard prerequisite
  for merging the mctl-agents change, the two cosmetic edits are not.
- **Whether any surface exhaustively switches on the top-level reason.** Not
  visible from this repo. If one does, it needs the new arm before this merges;
  the fallback does not protect against a surface that crashes on an unknown
  reason, only against an mctl-api that refuses the write.
