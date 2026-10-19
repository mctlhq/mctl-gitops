# Design: issue-700-governance-define-authority-and-decision

## Current state

**Action approvals** (`internal/workitems/action_approvals.go`):

- `ActionApprovalRequest` (`aar_`, schema `actionapproval/v1`) is single use. States go `pending -> approved | denied`, then `approved -> consumed`. `expired` is never stored; `effectiveState` derives it lazily from `expires_at`.
- `IntentHash(ActionIntent)` is the exact-action hash: sha256 over `mctl-action-intent/v1` with length-prefixed `execution_id, action_kind, target, args_digest, policy_rule_id, policy_version, artifact_hash, work_item_id`. The doc comment says clients reproduce this encoding, so it must not change.
- Canonical principals are dual-written (#373): `requested_by_principal_id`, `via_principal_id`, `decided_by_principal_id`, `decided_via_principal_id`. Actor and subject (#376 D2) are `actor_kind`, `actor_name`, `subject_principal_id`, `subject_kind`, `agent_run_id`.
- Schema evolution is done with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` inside `actionApprovalSchema`.
- `CreateActionApproval` validates bounds and runs `scanSecrets` on every field. It caps `expires_at` at `MaxApprovalTTL = 7 * 24h`.
- `DecideActionApproval` refuses self-decision and any request that is not pending or has expired. It records the decider, `decided_at` and the reason. It does not check context completeness and records no authority basis.
- `ConsumeActionApproval` is one CAS: `WHERE id=$1 AND state='approved' AND intent_hash=$2 AND expires_at > $3`. Refusals are typed: `ErrApprovalConsumed`, `ErrApprovalDenied`, `ErrApprovalExpired`, `ErrApprovalNotApproved` and `ErrApprovalIntentMismatch`.
- There is no risk or side-effect classification, no intent-source reference, and no policy decision or reasons on the row. A reviewer reading `GET /api/v1/action-approvals/{id}` sees the target, `args_digest` and the policy rule id/version, and nothing that says what kind of side effect is being approved or why the policy asked for approval. This is the #182 F6 gap.

**HTTP layer**:

- `internal/api/handlers_action_approvals.go`:
  - `actionApprovalBody` holds the create fields. `isDirectService` gates create and consume; `isHumanAdmin` gates decide.
  - `actionApprovalRefusals` maps sentinels to `aarCode*` codes, and `writeActionApprovalError` writes them through `writeErrorCode(w, status, code, msg, details)` (`internal/api/handlers_read.go:932`). Today `details` is always nil.
  - `auditActionApproval` records ids and hashes only, "never args or the reason text". It hard-codes `operations.RiskLow` on create and `RiskMedium` on decide. `auditActionApprovalRefusal` records the code and ids.
  - `writeActionApproval` emits `{"schema_version", "approval"}`.
- `internal/api/handlers_approval_grant.go` implements the agent-run grant path for `mctl-agents-approve` (`X-MCTL-On-Behalf-Of: aar_...`):
  - `prepareApprovalGrant` runs the kind check and `approverName(a.DecidedBy)`.
  - `bindApprovalGrant` rebuilds the intent with the constants `devLoopApprovalPolicyRule = "dev-loop.human-approval"` and `devLoopApprovalPolicyVersion = "v1"`.
  - `spendApprovalGrant` calls `WorkItems.ConsumeActionApproval` and runs last, right before `Executor.Submit` in `ExecuteOperation` (`handlers_write.go`).
  - None of these checks the decider's current authority.
- `internal/api/handlers_dev_loop.go` (~line 634-660) decides the newest pending `mctl-agents-approve` `aar_` for a DevLoop approve signal, through `DecideActionApproval` with the caller's principal ids.
- `internal/api/handlers_surface_identity.go:349` `checkHumanPrincipal(ctx, auth.PrincipalResolver, prn)` already type-asserts `auth.HumanPrincipalChecker`. It maps `auth.ErrPrincipalDisabled` and `auth.ErrIdentityRefused` to typed codes, and maps any other error (including the store being unable to check) to "store could not answer", which becomes a 503. This proposal reuses that helper's shape.
- `internal/api/handlers_commerce.go` exposes `{policy_rule_id, policy_version}` of an `aar_` as `commerce.PolicyDecisionRef`. It notes "Approvals carry no tenant yet (mctl-api#489)".

**Identity, authz and policy**:

- `internal/auth/principal_authz.go`: in principal mode, a platform admin is a principal listed in `ADMIN_PRINCIPALS`. `api.Options.AdminPrincipals map[string]bool` and `TenantAuthzMode` (`internal/api/router.go:144-154`) are parsed at boot in `cmd/api/main.go`, from env `TENANT_AUTHZ_MODE` and `ADMIN_PRINCIPALS`.
- `internal/principals/resolver.go:199` `CheckHumanPrincipal` returns:
  - `auth.ErrPrincipalDisabled` for a disabled or merged principal or a customer deletion;
  - `auth.ErrIdentityRefused` for a missing principal or one that is not human;
  - `ErrUnresolved` for a failed read.
  Answers are cached.
- `internal/operations/registry.go`: `RiskLevel` (`low|medium|high`) per operation. `mctl-agents-approve` is `RiskMedium` (line ~941). `Registry.Get(name)` looks an operation up.
- `docs/tenant-roles.md`: decisions on action approvals are made by human platform admins only.

**Deployed state checked**:

- `mcp__mctl__mctl_get_service_config(team=admins, service=mctl-api)` returned an error: "service not found: admins/mctl-api". mctl-api is not a catalogue service under `admins`, so its deployed config could not be observed through this tool.
- `$MCTL_GITOPS_ROOT/services/`: has `admins/`, `karabu/` and `labs/`. No `mctl-api/values.yaml` exists there. `grep -rl mctl-api services` matches only consumers (`mctl-agents-worker*`, `mctl-telegram`, and others), not mctl-api's own deployment.
- `helm/values.yaml` in the clone has chart defaults `TENANT_AUTHZ_MODE: ""` and `ADMIN_PRINCIPALS: ""`. These are defaults, not deployed values.
- Conclusion: the deployed `TENANT_AUTHZ_MODE`, `ADMIN_PRINCIPALS` and replica count were **not observed**. The design does not depend on them. The admin-membership check runs only in principal mode and records `skipped_legacy_mode` otherwise. The claim that principal mode is current comes from `docs/tenant-roles.md`, not from deployed state. This gap is recorded under Open questions in requirements.md.

## Proposed solution

Add a small `internal/governance` package that composes the existing primitives. It is a contract plus a check, not a new authorization model. Authority is still `ADMIN_PRINCIPALS` plus `auth.HumanPrincipalChecker`, and policy identity is still `policy_rule_id`/`policy_version`.

### 1. Policy registry with context defaults

```go
type Policy struct {
    Version    string   // current version
    Decision   string   // "require_approval"
    Reasons    []string // reason codes, e.g. "human-gate:dev-loop"
    SideEffect string   // none|read|write|destructive|external
}
var Policies = map[string]Policy{
    "dev-loop.human-approval": {Version: "v1", Decision: "require_approval",
        Reasons: []string{"dev-loop.proposal-acceptance"}, SideEffect: "write"},
}
func (p PolicySet) Check(ruleID, version string) (status string, err error) // ok | unregistered | ErrPolicyDrift
```

`handlers_approval_grant.go` reads `devLoopApprovalPolicyRule`/`Version` from this map, so there is one source of truth. Tests inject a `PolicySet` through `api.Options.Policies`, which defaults to `governance.Policies`. This is how the F9 v1 -> v2 drift is exercised.

### 2. Mandatory decision context (F6)

New columns on `action_approval_requests`, all `ADD COLUMN IF NOT EXISTS`, default `''`/NULL:

| Column | Notes |
|---|---|
| `risk_level` | Server-derived from `operations.Registry` when `action_kind` is a registered operation; otherwise client-sent. |
| `side_effect` | Client-sent, or the registry default for the policy. |
| `intent_source` | `<kind>:<ref>`. Defaults to `work_item:<wi_>`, else `execution:<we_>`. |
| `policy_decision` | Client-sent or registry default. |
| `policy_reasons` | `TEXT[]`, at most 8 codes of at most 128 bytes, `[a-z0-9._:-]`. Client-sent or registry default. |
| `decided_context_digest` | Written at decision time. |
| `authority_basis` | Written at decision time. |
| `authz_mode` | Written at decision time. |
| `fresh_until` | `TIMESTAMPTZ`, written at decision time. |

`actionApprovalBody` and `ActionApprovalInput` gain the five context fields. `validate()` applies `checkText` and `scanSecrets` to them as it does to every other field. A `risk_level` that contradicts the registry is refused with 400 `approval_context_invalid`, so a client cannot downgrade the risk of a known operation.

`governance.DecisionContext` (schema `decisioncontext/v1`) is a read-side projection:

```
mandatory:  target, args_digest, intent_hash, artifact_hash?,
            risk_level, side_effect, intent_source, execution_id,
            policy{rule_id, version, decision, reasons}
actor:      actor_kind, actor_name, requested_by_principal_id, via_principal_id
subject:    subject_principal_id, subject_kind
tenant:     ""   (reserved, mctl-api#489)
authority:  decided_by_principal_id, decided_via_principal_id,
            basis (platform_admin | unrecorded), authz_mode
time:       created_at, decided_at, expires_at, fresh_until
context_digest, decided_context_digest, context_complete, missing_fields[]
```

`ContextDigest(ctx)` is sha256 over `mctl-decision-context/v1\n` followed by `<field>:<len>:<value>\n` lines, in a fixed order: `intent_hash, target, args_digest, artifact_hash, risk_level, side_effect, intent_source, policy_rule_id, policy_version, policy_decision, policy_reasons (joined by ',')`. This is the same length-prefixed style as `IntentHash`, so any client can reproduce it. The intent hash itself is unchanged.

`writeActionApproval` adds `decision_context` next to `approval`. The change is additive JSON, with no new route and no MCP change.

**Decide** (`handlers_action_approvals.DecideActionApproval` and `handlers_dev_loop.go` ~648): before the store call, build the context from the row plus live registry values.

- An `approve` with `!context_complete` returns 422 `approval_context_incomplete` with `details.missing_fields`, and no grant is created.
- An optional `context_digest` in `actionDecisionBody` that differs from the current digest returns 409 `approval_context_changed`. This proves the reviewer approved what they were shown.
- On success, `ActionDecisionInput` carries `ContextDigest`, `AuthorityBasis = "platform_admin"`, `AuthzMode` and `FreshFor`. The store writes `decided_context_digest`, `authority_basis`, `authz_mode` and `fresh_until = LEAST(expires_at, now + FreshFor)` in the same `UPDATE ... WHERE state='pending'`.
- A `deny` skips the completeness check.

### 3. Execution-time revalidation

```go
type LiveAuthority struct {
    Mode     string                 // h.opts.TenantAuthzMode
    Admins   map[string]bool        // h.opts.AdminPrincipals
    Checker  auth.PrincipalResolver // h.opts.Principals; asserted to HumanPrincipalChecker
    Policies PolicySet
    Registry *operations.Registry
    Now      time.Time              // h.now(), injectable
}
func Revalidate(ctx context.Context, a *workitems.ActionApprovalRequest, live LiveAuthority) (Result, error)
```

The checks run in this order, and the first failure wins:

1. **Context (F6c):** if `decided_context_digest != ""` and the recomputed digest differs, return `ErrContextChanged`.
2. **Freshness (F4):** if `fresh_until != nil && !fresh_until.After(now)`, return `ErrApprovalStale`. `expires_at` stays with the store CAS (`ErrApprovalExpired`).
3. **Decider (F3):** an empty `decided_by_principal_id` returns `ErrAuthorityRevoked`. Otherwise `checkHumanPrincipal` is called. `ErrPrincipalDisabled` or `ErrIdentityRefused` returns `ErrDeciderDisabled`. A missing checker or an unresolved read returns `ErrAuthorityUnavailable` (503, fail closed).
4. **Admin membership (F3):** in principal mode, `!Admins[prn]` returns `ErrAuthorityRevoked`. In other modes the result records `skipped_legacy_mode`.
5. **Policy (F9):** `Policies.Check` returns `ErrPolicyDrift` on a version mismatch. An unregistered rule is recorded, and fails only in strict mode.

**Call sites:**

- `handlers_action_approvals.ConsumeActionApproval`: after `visibleActionApproval`, before `WorkItems.ConsumeActionApproval`.
- `handlers_approval_grant.spendApprovalGrant`: before `WorkItems.ConsumeActionApproval`. This keeps the "spend last" ordering in `ExecuteOperation`, so a refusal never reaches `Executor.Submit`.

**Store CAS:** the CAS gains `AND (fresh_until IS NULL OR fresh_until > $3)`, and its read-back maps a row that is approved but stale to `ErrApprovalStale`. Freshness is therefore enforced atomically. Authority and policy are checked milliseconds before the CAS, against facts that need a redeploy (`ADMIN_PRINCIPALS`, `Policies`) or a principal-store transaction to change. The residual TOCTOU is documented as bounded.

### 4. Typed refusals

New entries go in `actionApprovalRefusals`. `writeActionApprovalError` gains a per-entry `reapproval bool`, and when it is set, writes `details: {"reapproval_required": true}`:

| Code | HTTP | reapproval_required | #182 |
|---|---|---|---|
| `approval_context_incomplete` (decide) | 422 | n/a (no grant made) | F6 |
| `approval_context_invalid` (create) | 400 | n/a | F6 |
| `approval_context_changed` | 409 | true | F6 |
| `approval_stale` | 409 | true | F4 |
| `approval_expired` (existing; detail added) | 409 | true | F4 |
| `approval_authority_revoked` | 409 | true | F3 |
| `approval_decider_disabled` | 409 | true | F3 |
| `approval_authority_unavailable` | 503 | false (retry; approval not spent) | F3 |
| `approval_policy_drift` | 409 | true | F9 |

mctl-agents matches codes by substring. Callers should key on `details.reapproval_required` instead, and the contract document says so.

Every refusal is audited through `auditActionApprovalRefusal` (code and ids only). The success audit gains `revalidation`, `policy_version`, `authority_basis`, `context_digest` and `fresh_until`. `auditActionApproval` uses the stored `risk_level` instead of the hard-coded `RiskLow`/`RiskMedium` when the row has one.

### 5. Contract document

`docs/decision-context-contract.md` covers the mandatory field list, captured versus revalidated facts, the table above, freshness semantics (`expires_at` is the requester's hard bound; `fresh_until` is the decision-age bound; both are checked at consume), the privacy rule (references, digests, enums and reason codes only; never args or reason text), and the #182 mapping table exactly as in the issue. It is linked from `docs/tenant-roles.md`. The OpenAPI spec (`internal/openapi/openapi.yaml`) gains the new body fields, the `decision_context` object and the error codes.

## Alternatives

1. **Revoke outstanding approvals eagerly** when an admin is removed or a policy is bumped, with a sweeper that marks rows revoked. Dropped. Admin removal is a boot-time env change, and principal disable happens on several paths (`internal/principals/link.go`, customer deletion). Each of those would need a hook, and a missed hook is a silent pass. Lazy revalidation at the single spend point covers every cause by construction.
2. **Fold context and authority into `IntentHash`.** Dropped. It changes `mctl-action-intent/v1`, which clients reproduce, and an unrelated admin-set change would invalidate every approval. A separate `context_digest` binds the reviewer-visible context without breaking the action hash.
3. **Store a full decision snapshot (payload, reason, args) as JSON.** Dropped on privacy grounds. It contradicts the existing audit stance and the issue's reference/redaction requirement. The context can be reconstructed from ids and digests that point at the work item, execution and evidence stores.

## Platform impact

- **Migration:** nine additive columns via `ADD COLUMN IF NOT EXISTS`, following the #373/#376 pattern. No backfill. Legacy rows read as `authority_basis: "unrecorded"`, `fresh_until: null` and `decided_context_digest: ""`, so the consume-time digest check is skipped for them.
- **Backward compatibility:**
  - Responses are additive. New refusal codes appear on decide and consume only.
  - The DevLoop gate keeps working without an mctl-agents change. `risk_level` comes from the registry (`mctl-agents-approve` = medium), `side_effect`, `policy_decision` and `policy_reasons` come from `governance.Policies`, and `intent_source` defaults to `work_item:`/`execution:`.
  - **Behaviour changes:**
    - an approved but unconsumed `aar_` whose decider has left `ADMIN_PRINCIPALS`, or whose decider's principal is disabled, becomes unspendable on deploy (the intended fix);
    - a pending request under an unregistered policy that lacks context cannot be approved;
    - DevLoop approvals decided more than 24h before the implementer runs need reapproval. Set `ACTION_APPROVAL_MAX_DECISION_AGE=168h` to keep today's horizon.
  - A follow-up issue on mctl-agents should switch re-grant logic to `details.reapproval_required`.
- **Resource impact:** one cached `CheckHumanPrincipal` lookup and one sha256 per consume and decide. Volume is one per side effect, which is negligible.
- **Risks and mitigations:**
  - A principal-store outage blocks consumes with 503. This is deliberate fail-closed behaviour; the approval is not spent, and a retry succeeds.
  - A registry risk change (for example, an operation raised to `high`) changes the context digest and forces reapproval of outstanding grants for that operation. This is intended, and documented.
  - Policy constants drifting from `bindApprovalGrant` is prevented by reading both from `governance.Policies`.
  - Import cycles are avoided because `governance` imports `workitems`, `auth` and `operations`, and none of those imports it.
