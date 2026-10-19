# Design: issue-721-governance-harden-action-approval-contra

## Current state

Files read in the clone (HEAD `ba97de4`, merge of #720):

**Governance rules: `internal/governance/governance.go`**
- `Policies` (a `PolicySet`) registers one rule: `DevLoopPolicyRule =
  "dev-loop.human-approval"` at `v1`.
- `PolicySet.Check` returns `PolicyUnregistered` (not an error) for an unknown
  rule and `ErrPolicyDrift` for a version mismatch.
- `Revalidate` checks, in order: F6 digest (skipped when
  `DecidedContextDigest == ""`), F4 `FreshUntil` against `live.Now`, F3
  decider principal and admin membership, then F9 policy. An unregistered rule
  fails only when `live.StrictPolicy` is set. `Revalidate` does **not** check
  `DecisionContextOf(...).ContextComplete`, so an approved legacy row with an
  empty `risk_level` (unregistered action kind) is spendable.
- `FillCreateContext` derives `risk_level` from the operation registry and
  fills the other fields from the registered policy. `CreateContext.Missing`
  lists what is still empty.

**Handlers: `internal/api/handlers_action_approvals.go`, `handlers_approval_governance.go`, `handlers_approval_grant.go`**
- `CreateActionApproval` order: service-principal gate (403), body decode with
  a 16 KiB limit (400), header/body idempotency key mismatch (400),
  `requireOpenExecution` for `mctl-agents-approve` (400/409/503),
  `FillCreateContext` (400 `approval_context_invalid`), `Missing()` (422
  `approval_context_incomplete`), and only then
  `WorkItems.CreateActionApproval`. Inside the store come field
  length/format/enum checks and `scanSecrets` (`ActionApprovalInput.validate`,
  400), then the idempotency lookup (200 replay or 409 conflict).
  Consequences:
  - an overlong `target` or a secret in a field, sent together with a missing
    `side_effect`, gets 422 instead of 400;
  - a retry of an already-stored request is re-run through completeness and
    open-execution checks first, so a retry after the DevLoop execution
    finished gets `409 approval_execution_not_open` instead of its replay.
  This is handler order, not a documented contract.
- `ConsumeActionApproval` and `spendApprovalGrant` both run
  `workitems.ConsumeStateRefusal` before `revalidateApproval`. That precedence
  is documented and tested (`TestF3_ConsumeStateRefusalPrecedesRevalidation`,
  `TestF6_ContextGateDoesNotMaskTerminalRefusal`).
- `guardDecision` gates only an approve, on completeness and the optional
  `context_digest`. Policy registration is not checked at decide time.
- `approvalNow()` returns `h.opts.Clock()` or falls back to `time.Now()`.
  `cmd/api/main.go` does not set `Clock`, so production uses `time.Now`.
- `actionApprovalRefusals` maps errors to status, code and `reapproval`.
  `ErrContextIncomplete` maps to 422 with `reapproval=false`.

**Store: `internal/workitems/action_approvals.go`, `store.go`**
- `Store.now` is `func() time.Time { return time.Now().UTC() }`, set in
  `NewStore`. Only package tests can replace it.
- `s.now()` drives: the create expiry check, `scanActionApproval` lazy expiry
  (`effectiveState`), `DecideActionApproval` (`decided_at`, `fresh_until =
  LEAST(expires_at, now+FreshFor)`, expiry refusal), and
  `ConsumeActionApproval`'s compare-and-set (`expires_at > $3 AND (fresh_until
  IS NULL OR fresh_until > $3)`). The handler's revalidation uses a
  different clock source.
- `actionApprovalSchema` runs on every boot and ends in an unconditional
  backfill: `UPDATE ... SET side_effect/policy_decision/policy_reasons
  (['legacy.pre-governance'])/intent_source ... WHERE intent_source = '' AND
  decided_context_digest = ''`. It does not filter on state or expiry, so it
  rewrites terminal rows. It never touches `risk_level`, logs no counts, and
  has no postcondition check. It is idempotent: backfilled rows get an
  `intent_source`.

**Config: `cmd/api/main.go`, `helm/values.yaml`**
- `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` is parsed by
  `config.requireRegisteredPolicy()` through `killSwitchOn` and passed as
  `Options.RequireRegisteredPolicy`. Helm default `""` (off).
- `ACTION_APPROVAL_MAX_DECISION_AGE` defaults to 24h.

**Docs: `docs/decision-context-contract.md`, `internal/openapi/openapi.yaml`**
- The doc covers create- and approve-time completeness, consume state
  precedence and the five-step revalidation order. It does not say where 400
  sits relative to 422, how replay interacts with validation, that create
  accepts unregistered rules even in strict mode, or that spend-time
  completeness is unchecked.

**Tests**
- `internal/api/handlers_approval_governance_test.go`: the F4 "stale" case only
  moves `h.opts.Clock` forward 2h. The store keeps real time, so the refusal
  comes from `Revalidate`, and the store's own `fresh_until` CAS path is never
  exercised through the handler.
- `internal/api/handlers_action_approvals_test.go` `approvalBody` uses the
  unregistered rule `merge-needs-human` v3 and the unregistered action kind
  `github.merge_pr`. These are Postgres-backed `workItemsEnv` tests.

**Producers inferred from code:** the DevLoop grant path
(`handlers_approval_grant.go`, `bindApprovalGrant`) recomputes the intent hash
under `h.devLoopPolicy()` (`dev-loop.human-approval`, registered version), so
mctl-agents' `mctl-agents-approve` approvals must use the registered rule. No
other in-repo producer exists. Commerce (`handlers_commerce.go`) only reads
approvals by id.

Deployed state checked:
- `mctl_list_services(team=admins)`: lists mctl-agents-worker{,-exec,-implement}
  at 1.86.0, mctl-design, mctl-docs, mctl-web and umami. **mctl-api is not a
  catalogue service**, so its deployed env (including
  `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY`) could not be observed.
- `$MCTL_GITOPS_ROOT/services/*/*/values.yaml`, grep for `ACTION_APPROVAL`,
  `human-approval` and `policy_rule`: no matches. mctl-api's deployment values
  are not in this checkout. Not observed, which is not the same as unset.
- `services/admins/mctl-agents-worker/values.yaml`: mentions calling mctl-api
  with the mctl-agent service principal. That confirms mctl-agents is a
  producer but does not show which policy rules it sends.

## Proposed solution

Five slices in the issue's implementation order. Each reuses the existing
`governance` / `workitems` primitives.

### 1. Freeze the precedence contract (create, decide, spend)

Make create precedence explicit in `CreateActionApproval`:

1. authentication / service-principal gate: 401/403;
2. decode, size and header/body key mismatch: 400;
3. **structural validation** (new): call
   `workitems.ValidateActionApprovalInput(in)`, the exported form of
   `ActionApprovalInput.validate` (lengths, prefixes, enums, `scanSecrets`,
   `expires_at` present, `intent_hash` equals the computed hash): 400
   `invalid` / `intent_hash_mismatch`. The `ActionApprovalInput` is built
   from the body before the governance fill, with the client-sent context
   fields, so a bad enum or secret is a 400 first;
4. **idempotent replay** (new, explicit): `WorkItems.FindActionApprovalByKey(ctx,
   requestedBy, key)`. If found and the intent hash is equal, return 200. If
   the hash differs, return 409 `approval_idempotency_conflict`. Stored
   requests are answered as they are, so completeness, strict-policy and
   open-execution checks, which judge a new request, are skipped. This
   matches the store's existing rule ("a retry of one already stored is
   answered with it, expired or not");
5. `requireOpenExecution` for `mctl-agents-approve`: 400/409/503;
6. `FillCreateContext`: 400 `approval_context_invalid`;
7. strict policy (slice 2): 422 `approval_policy_unregistered` / 409
   `approval_policy_drift`;
8. `Missing()`: 422 `approval_context_incomplete`;
9. `Store.CreateActionApproval`. Its own locked lookup stays the race
   backstop: a concurrent create that loses step 4 still replays or
   conflicts inside the transaction.

Decide: 403, then 400 decode, then not-found 404, then state refusal
(`approval_already_decided` / `approval_expired`), then for approve only:
completeness 422, strict policy, digest 409. `guardDecision` gains the
strict-policy check but keeps its existing position after the store's state
read. The current order loads `cur` first, which is kept.

Spend (consume and grant): state refusal, then `Revalidate`, then store
compare-and-set. `Revalidate` gains a step 0, **context completeness**: an
approved row whose `DecisionContextOf` is incomplete is refused with a new
sentinel `governance.ErrContextIncompleteAtSpend` (wraps
`ErrContextIncomplete`). It is mapped in `actionApprovalRefusals`, ahead of
`ErrContextIncomplete`, to `409 approval_context_incomplete,
reapproval_required=true`. The code stays canonical while the status and flag
reflect that nothing the client sends can repair a decided row.

No refusal path writes to the store before the compare-and-set. Tests assert
that the row is byte-identical (`state`, `consumed_at`, `fresh_until`,
`decided_at`) after each refusal.

All of this goes into one table-driven test file,
`internal/api/handlers_approval_precedence_test.go`, and into a new
"Precedence" section of `docs/decision-context-contract.md` that mirrors the
table. OpenAPI create/decide/consume responses list the same codes.

### 2. Strict registered policy: inventory, observability, enforcement

- **Observability first (flag off).** `governance.PolicySet` gets
  `Status(ruleID, version) (status string, err error)`, which reuses `Check`.
  `CreateActionApproval`, `DecideActionApproval` and `revalidateApproval`
  record `policy_status` (`ok` / `unregistered` / `drift`) as an audit
  parameter (`auditActionApproval` extra map; consume already has
  `Result.PolicyStatus`). Each `unregistered` sighting also gets a
  `slog.Warn("action approval under unregistered policy", ...)` with
  action_kind, policy_rule_id, policy_version and requested_by. Refusals keep
  `auditActionApprovalRefusal` with the typed code. At startup `main.go` logs
  `strict_policy` and the registered rule:version list.
- **Inventory.** A store method `ActionApprovalPolicyInventory(ctx, since)`
  returns distinct `(requested_by, action_kind, policy_rule_id,
  policy_version, state)` with counts. It is exposed only as a startup log
  line at boot and through tests, not as a new route. Together with the audit
  `policy_status` that gives a producer inventory without new surfaces. The
  operator runbook in the doc: run with observability for at least one
  `ACTION_APPROVAL_MAX_DECISION_AGE` window; any unregistered producer is
  either registered in `governance.Policies` (code change) or retired.
- **Enforcement.** With `RequireRegisteredPolicy` set:
  - create: unregistered rule gives 422 `approval_policy_unregistered` (new
    code, `reapproval=false`, nothing stored). A registered rule at the wrong
    version gives 409 `approval_policy_drift`;
  - approve: same checks in `guardDecision`; the request stays pending;
  - spend: unchanged `Revalidate` step 5.

  A version change of a registered rule keeps producing 409
  `approval_policy_drift, reapproval_required=true` in every mode.
- **Production flip.** Set `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: "true"`
  in `helm/values.yaml` once the inventory shows no unregistered live
  producer. Rollback is setting it back to `""`/`"false"`, with no data
  change. The api test env (`workItemsEnv`) keeps strict off by default.
  Strict-mode tests opt in, and a new test proves that an unregistered rule
  cannot be created, approved or spent with strict on.

### 3. Bounded legacy migration

Move the backfill out of the `actionApprovalSchema` string into
`(*Store).migrateLegacyGovernance(ctx)`, called by `NewStore` after the
schema:

1. **Observe:** `SELECT state, count(*) ... WHERE intent_source = '' AND
   decided_context_digest = '' GROUP BY state`, logged as
   `legacy_governance_pending{state=...}`.
2. **Mutate live rows only:** the same `SET` as today, with `AND state IN
   ('pending','approved') AND expires_at > $1` (`$1 = s.now()`). Terminal rows
   are not touched. Rows already rewritten by #700 stay as they are, which is
   documented.
3. **risk_level:** never written. `DecisionContextOf` already derives it for
   a registered action kind. For an unregistered kind the row stays
   incomplete: approve gives 422, and spend gives 409
   `approval_context_incomplete` (slice 1 step 0).
4. **Postcondition:** `(*Store).LiveIncompleteGovernanceCount(ctx)` counts
   live rows (`pending`/`approved`, unexpired) with an empty `side_effect`,
   `policy_decision`, `intent_source` or `policy_reasons`, logged after
   migration. Executability does not depend on that count: spend-time
   completeness makes an incomplete row non-executable whatever the count.
5. **Idempotence:** the WHERE clause matches nothing on a second run (tested).

A dry run is the step-1 count, which is logged before every mutation. Env
`ACTION_APPROVAL_LEGACY_BACKFILL=count` (default `apply`) logs and skips the
mutation, so an operator can observe before the first apply.

### 4. One clock

- `workitems.NewStore(ctx, conn, opts ...StoreOption)` with
  `WithClock(func() time.Time)`. The default stays `time.Now().UTC()`. The
  variadic keeps existing callers compiling.
- `cmd/api/main.go` builds `approvalClock := func() time.Time { return
  time.Now().UTC() }` once and passes it to `workitems.NewStore(...,
  workitems.WithClock(approvalClock))` and `api.Options{Clock: approvalClock}`.
- `approvalNow()` keeps its nil fallback for unit tests that build
  `Handlers` directly, with a comment that production always sets it. A
  `main_test.go` check asserts that the wired options carry a non-nil `Clock`.
- `workItemsEnv` gains a shared controllable clock installed in both the
  store (`WithClock`) and `h.opts.Clock`. F4 stale and expired cases advance
  that one clock. A new case covers decide-then-advance, where the refusal
  must come from both `Revalidate` and the store CAS (asserted by calling the
  store directly with the same clock).
- `governance` already takes `Now` as input. A grep-based test
  (`TestNoTimeNowInApprovalLifecycle`) fails if `time.Now(` appears in
  `internal/governance/*.go` or `handlers_approval_governance.go` outside the
  documented fallback.

### 5. Documentation

`docs/decision-context-contract.md` gains three sections: Precedence (the
create/decide/spend tables above), Registered policy (strict-mode semantics at
create/approve/spend, the rollout runbook and rollback), and Legacy rows
(bounded backfill, no `risk_level` reconstruction, postcondition). The
refusal-code table gains `approval_policy_unregistered` and the spend-time
`approval_context_incomplete` row. `internal/openapi/openapi.yaml`: the
`ActionApprovalError.code` enum gains `approval_policy_unregistered`, and the
create/decide/consume response descriptions list the new codes and the replay
rule.

## Alternatives

1. **Only flip the default of `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY`.**
   Dropped: the issue explicitly rejects a bare config flip. Without inventory
   and observability an unknown producer would break silently, and create and
   approve would still accept requests that can never be spent.
2. **Validate the retried body fully before replay (keep today's order and
   document it).** Dropped: a client retrying after a network failure, or
   after its execution finished, would get a refusal for a request that
   already exists. That contradicts the store's "a retry of one already
   stored is answered with it" rule and makes retries non-idempotent across
   config changes such as the strict flip.
3. **A database-backed policy registry or a migration framework.** Dropped
   as out of scope: the issue forbids a new policy engine, and a one-function
   Go migration with counts gives the bounded postcondition without new
   infrastructure.
4. **Reconstruct `risk_level` as `high` for unregistered legacy kinds.**
   Dropped: that invents governance truth a human never saw. Refusing, so the
   row needs reapproval, is fail-closed.

## Platform impact

- **Schema:** no new columns. The backfill `UPDATE` moves from the schema
  string into Go and narrows to live rows. Terminal rows rewritten by #700
  are left as they are.
- **API compatibility:**
  - new code `approval_policy_unregistered`, only with strict on;
  - create 400 can now win over 422 when both apply;
  - a replay can now succeed where it used to get 422/409 execution-not-open;
  - spend of an incomplete approved row is now refused with 409.
  Clients keyed on `reapproval_required` behave correctly. mctl-agents
  should be checked for handling `approval_policy_unregistered` (it gets it
  only if it sends an unregistered rule).
- **Interfaces:** the `WorkItems` interface in `internal/api/interfaces.go`
  gains `FindActionApprovalByKey`, and fakes must be updated.
- **Resources:** one indexed lookup per create (UNIQUE `(requested_by,
  idempotency_key)` exists), plus three cheap count queries at boot.
- **Risks and mitigations:**
  - strict flip refuses a legitimate unregistered producer: observability
    window and inventory first, one-variable rollback, and spend refusals
    never consume the approval;
  - the clock change alters test timing: one shared controllable clock, and
    the production clock is the same `time.Now().UTC()` as before;
  - replay-before-governance could return a request that is now invalid:
    it is returned as stored. Spend-time revalidation still guards
    execution, so replay never grants anything new.
