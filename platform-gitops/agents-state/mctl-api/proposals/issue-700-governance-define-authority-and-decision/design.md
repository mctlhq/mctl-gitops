# Design: issue-700-governance-define-authority-and-decision

## Current state

Action approvals (`internal/workitems/action_approvals.go`):

- `ActionApprovalRequest` (`aar_`) is single use: `pending -> approved | denied`, then `approved -> consumed`. `expired` is never stored; `effectiveState` derives it lazily from `expires_at`.
- `IntentHash(ActionIntent)` is a sha256 hash over `mctl-action-intent/v1`, with length-prefixed `execution_id, action_kind, target, args_digest, policy_rule_id, policy_version, artifact_hash, work_item_id`. This is the exact-action hash.
- Canonical principals are dual-written: `requested_by_principal_id`, `via_principal_id`, `decided_by_principal_id`, `decided_via_principal_id`. Actor and subject come from #376 D2: `actor_kind`, `actor_name`, `subject_principal_id`, `subject_kind`, `agent_run_id`.
- `CreateActionApproval` caps `expires_at` at `MaxApprovalTTL = 7 * 24h`. The requester chooses the TTL.
- `DecideActionApproval` refuses self-decision and anything that is not pending or that has expired. It records the decider, `decided_at` and the reason. It records no authority basis.
- `ConsumeActionApproval` is one CAS: `WHERE id=$1 AND state='approved' AND intent_hash=$2 AND expires_at > $3`. Typed refusals are `ErrApprovalConsumed`, `Denied`, `Expired`, `NotApproved` and `IntentMismatch`.

HTTP layer:

- `internal/api/handlers_action_approvals.go`: `isHumanAdmin` gates decisions. `isDirectService` gates create and consume. `actionApprovalRefusals` maps store errors to codes (`approval_expired`, `approval_intent_mismatch`, ...). `auditActionApproval` records ids and hashes only, never args or the reason text. The privacy stance this proposal keeps comes from here.
- `internal/api/handlers_approval_grant.go`: an agent run presenting `X-MCTL-On-Behalf-Of: aar_...` on `mctl-agents-approve` is authorized by the grant instead of the admin gate. The path is `prepareApprovalGrant` (kind check, `approverName(a.DecidedBy)`, content digest required), then `bindApprovalGrant` (target must belong to the execution's DevLoop; it rebuilds the intent with the constants `devLoopApprovalPolicyRule="dev-loop.human-approval"` and `devLoopApprovalPolicyVersion="v1"`), then `spendApprovalGrant`. `spendApprovalGrant` is called last in `ExecuteOperation` (`internal/api/handlers_write.go` around line 452), right before `Executor.Submit`. **The decider's current authority is never checked.** The approval carries the authority of a decision that may be days old.
- `internal/api/handlers_dev_loop.go` (around line 648) decides the newest pending `aar_` for a DevLoop approve signal.
- `internal/api/handlers_commerce.go`: `policyDecisionOf` already exposes `{policy_rule_id, policy_version}` of an `aar_` as a `commerce.PolicyDecisionRef` on receipts. `checkApprovalOwner` notes "Approvals carry no tenant yet (mctl-api#489)".

Identity and authz:

- `internal/auth/principal_authz.go`: `PrincipalAuthz.Apply` sets `platformAdmin = Admins[prn] && actingPrincipal == ""` from `ADMIN_PRINCIPALS`. `api.Options.AdminPrincipals map[string]bool` (`internal/api/router.go:154`) is the same set. It is parsed at boot in `cmd/api/main.go` (`cfg.adminPrincipals()`), so removing an admin takes a redeploy, and after that the set is authoritative.
- `internal/principals/resolver.go`: `Resolver.CheckHumanPrincipal(ctx, prn)` returns `auth.ErrPrincipalDisabled` for a disabled or merged principal, `auth.ErrIdentityRefused` for one that is missing or not human, and `ErrUnresolved` for a failed read. Answers are cached, and `Forget` drops them on merge or unlink. `principals.StatusDisabled` is set by link/merge/customer deletion (`internal/principals/link.go`).
- `internal/operations/registry.go`: `RiskLevel` is `low|medium|high` per operation. This is the existing risk/side-effect classification.
- `docs/tenant-roles.md`: principal mode is current. Action-approval decisions are human platform admin only, and tenant owners cannot approve.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/`: holds only `admins/`, `karabu/` and `labs/` directories. `admins/` lists `mctl-agents-worker*` and `mctl-design`. **No `mctl-api` values.yaml was found in this checkout**, so the deployed `TENANT_AUTHZ_MODE`, `ADMIN_PRINCIPALS` and replica count were not observed. `grep -r TENANT_AUTHZ_MODE services tenants` returned nothing. This means the value could not be observed; it does not mean the variable is unset.
- mctl MCP tools: not called. The design does not depend on a live tenant, hostname or service config. The claim that principal mode is in force is taken from `docs/tenant-roles.md` ("`TENANT_AUTHZ_MODE=principal` is the current mode"), not from deployed state.

## Proposed solution

Add a small `internal/governance` package that composes the existing primitives. It is a contract and a check, not a new authorization model.

### 1. Decision context (references only)

`governance.DecisionContext` (schema `decisioncontext/v1`) is a read-side projection of an `ActionApprovalRequest` plus new authority evidence:

```
intent:     execution_id, work_item_id, agent_run_id, action_kind
actor:      actor_kind, actor_name, requested_by_principal_id, via_principal_id
subject:    subject_principal_id, subject_kind
tenant:     ""                                   (reserved for mctl-api#489)
target, args_digest, artifact_hash, intent_hash
policy:     rule_id, version, decision (approve|deny), revalidation (registered|unregistered)
risk_level: operations.RiskLevel of action_kind if it names a registered operation, else ""
authority:  decided_by_principal_id, decided_via_principal_id,
            basis ("platform_admin" | "unrecorded"), authz_mode
time:       created_at, decided_at, expires_at, fresh_until
```

The context reuses only stored ids, hashes and enums. The reason text and args are excluded. `writeActionApproval` adds it as `decision_context` to the existing JSON (additive). There is no new route and no MCP tool change.

### 2. Authority evidence at decision time

New nullable/defaulted columns go on `action_approval_requests`, added with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `actionApprovalSchema`, matching the existing migration style:

- `authority_basis TEXT NOT NULL DEFAULT ''` (`platform_admin`; empty means recorded before this change, read as `unrecorded`)
- `authz_mode TEXT NOT NULL DEFAULT ''`
- `risk_level TEXT NOT NULL DEFAULT ''`
- `fresh_until TIMESTAMPTZ` (NULL for legacy rows)

`ActionDecisionInput` gains `AuthorityBasis`, `AuthzMode` and `FreshFor time.Duration`. `DecideActionApproval` writes `fresh_until = LEAST(expires_at, now + FreshFor)` for approvals. Denials store it too, which does no harm. `risk_level` is set at create from `Registry.Get(action_kind)` when found. The callers that fill these are `handlers_action_approvals.DecideActionApproval` and `handlers_dev_loop` (line ~648), both of which already pass `isHumanAdmin`. Authority basis is always `platform_admin` because no other decider exists.

### 3. Policy registry

`governance.Policies` is a static map from `policy_rule_id` to the current version, seeded with `dev-loop.human-approval: v1`. `handlers_approval_grant.go` reads its constants from this map, so there is one source. `Policies.Check(ruleID, version)` returns `ok`, `ErrPolicyDrift`, or `unregistered`. `unregistered` fails closed only when `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY=true`. Bumping a policy version in code makes every outstanding approval under the old version refuse with `approval_policy_drift`.

### 4. Execution-time revalidation

```go
type LiveAuthority struct {
    Mode      string                      // h.opts.TenantAuthzMode
    Admins    map[string]bool             // h.opts.AdminPrincipals
    Principal auth.HumanPrincipalChecker  // h.opts.Principals (Resolver), may be nil
    Policies  Policies
    Now       time.Time
}
func Revalidate(ctx context.Context, a *workitems.ActionApprovalRequest, live LiveAuthority) (Result, error)
```

The checks run in order, and the first failure wins:

1. Freshness: if `fresh_until` is set and `!fresh_until.After(now)`, return `ErrApprovalStale`. (`expires_at` is still enforced by the store.)
2. Decider principal: if `decided_by_principal_id` is empty, return `ErrAuthorityRevoked` (409 `approval_authority_revoked`). A decision recorded with no canonical principal cannot be revalidated, and a 503 retry would never succeed, so it fails closed and asks for reapproval. `CheckHumanPrincipal` then maps `ErrPrincipalDisabled` and `ErrIdentityRefused` to `ErrDeciderDisabled`, and `ErrUnresolved` or a nil checker to `ErrAuthorityUnavailable` (503).
3. Admin membership: in principal mode, `!Admins[decided_by_principal_id]` returns `ErrAuthorityRevoked`. In other modes the result records `skipped_legacy_mode`.
4. Policy: `Policies.Check`.

Call sites:

- `handlers_action_approvals.ConsumeActionApproval`: after `visibleActionApproval` and before `WorkItems.ConsumeActionApproval`.
- `handlers_approval_grant.spendApprovalGrant`: before `WorkItems.ConsumeActionApproval`. This keeps the existing "spend last, after every check that could still refuse" ordering in `ExecuteOperation`.

Both map errors through new entries in `actionApprovalRefusals` (`approval_authority_revoked`, `approval_decider_disabled`, `approval_policy_drift`, `approval_stale` at 409, and `approval_authority_unavailable` at 503). `writeErrorCode` details carry `{"reapproval_required": true}`, except for the 503. Each refusal is audited through `auditActionApprovalRefusal` (code and ids only).

The store CAS gains `AND (fresh_until IS NULL OR fresh_until > $3)`, and the refusal read-back maps a stale row to the new `ErrApprovalStale` sentinel. Freshness is therefore atomic, while authority and policy are checked immediately before the CAS. The window between the two is milliseconds against authority changes that need a redeploy (`ADMIN_PRINCIPALS`) or a merge/disable transaction. The residual TOCTOU is documented as bounded, not eliminated.

### 5. Contract document

`docs/decision-context-contract.md` covers the field list, which facts are captured versus revalidated, the drift-to-outcome table, freshness semantics, the privacy rule, and the mapping to #182 F3/F4/F6/F9. It is linked from `docs/tenant-roles.md`.

Drift-to-outcome table:

| Fact | Captured at decision | Revalidated at execution | Drift outcome |
|---|---|---|---|
| intent (exact action) | intent_hash | yes, by the CAS (existing) | 409 approval_intent_mismatch |
| expiry | expires_at | yes, by the CAS (existing) | 409 approval_expired |
| decision freshness | fresh_until | yes, by the CAS (new) | 409 approval_stale, reapprove |
| decider is admin | authority_basis, decided_by_principal_id | yes (principal mode) | 409 approval_authority_revoked, reapprove |
| decider principal active/human | decided_by_principal_id | yes | 409 approval_decider_disabled, reapprove |
| policy version | policy_rule_id/version | yes (registered rules) | 409 approval_policy_drift, reapprove |
| live fact unreadable | n/a | n/a | 503 approval_authority_unavailable, retry |
| risk level | risk_level | no (evidence only) | n/a |
| tenant | reserved | no (until #489) | n/a |

## Alternatives

1. **Revoke outstanding approvals eagerly when an admin is removed or a policy is bumped** (a sweeper that marks rows denied or revoked). Dropped because admin removal is a boot-time env change and principal disable happens in several transactions (`link.go`, customer deletion), so every one of those paths would need a hook, and a missed one is a silent pass. Lazy revalidation at the single spend point covers every cause by construction.
2. **Embed authority and policy facts in the intent hash** (for example, hash the admin-set digest). Dropped because that changes `mctl-action-intent/v1`, which clients reproduce (the IntentHash doc), and an unrelated admin addition would invalidate every approval. Revalidation must ask whether this decider still holds authority, not whether the world is byte-identical.
3. **Store a full decision snapshot (payload, reason, args) as JSON.** Dropped on privacy grounds: it contradicts the existing audit stance ("never args or the reason text") and the issue's reference/redaction requirement. The context is fully reconstructable from ids and digests that point at the work item, execution and evidence stores.

## Platform impact

- **Migration**: four additive columns via `ADD COLUMN IF NOT EXISTS`, which follows the existing #373/#376 pattern in `actionApprovalSchema`. No backfill. Legacy rows read as `authority_basis: "unrecorded"`, `fresh_until: null`.
- **Backward compatibility**: the JSON responses are additive (`decision_context`). New refusal codes appear only on consume. **Behaviour change**: an approved but unconsumed `aar_` whose decider has since been removed from `ADMIN_PRINCIPALS`, or whose principal is disabled, becomes unspendable on deploy. That is the intended fix. mctl-agents callers that already handle `approval_expired` by requesting a new approval must handle the new codes the same way (see the `reapproval_required` detail). A follow-up issue should be filed on mctl-agents.
- **Freshness default**: 24h is shorter than the 7d TTL, so DevLoop approvals decided more than 24h before the implementer runs will need reapproval. Set `ACTION_APPROVAL_MAX_DECISION_AGE=168h` to keep today's behaviour if this proves disruptive.
- **Resource impact**: one cached `CheckHumanPrincipal` lookup per consume. The resolver cache absorbs it. Consume volume is low (one per side effect).
- **Risks and mitigations**: (a) A principal-store outage blocks consumes with 503. This is deliberate fail-closed behaviour, consistent with `ErrPrincipalAuthzUnavailable`, and the approval is not spent, so a retry works. (b) Legacy rows with an empty `decided_by_principal_id` become unspendable. They are at most 7 days old, and the release note says so. (c) A shared policy constant drifting from `bindApprovalGrant` is avoided by reading both from `governance.Policies`.
