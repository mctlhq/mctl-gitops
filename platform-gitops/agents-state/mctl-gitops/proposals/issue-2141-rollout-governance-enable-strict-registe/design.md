# Design: issue-2141-rollout-governance-enable-strict-registe

## Current state

Production mctl-api is not a tenant service under `platform-gitops/services/`.
It is the Argo CD Application `admins-mctl-api` (project `platform`), declared in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`. Its first
source is the mctl-api repo's `helm/` chart at `targetRevision: main`, with
inline `helm.values`. The second source is
`platform-gitops/infra-components/mctl-platform/mctl-api` from this repo.
Relevant values:

- `image.tag: "4.122.0"`, `replicaCount: 2`.
- `env:` holds the governance switches, each with a comment giving the reason,
  the evidence and the rollback: `TENANT_AUTHZ_MODE: "principal"`,
  `MCTL_AGENTS_APPROVE_LEGACY_APPROVER: "false"`,
  `MCTL_AGENT_RECEIPT_GATE: "enforce"` (gitops#1980, the closest precedent: an
  observe window, then enforce, with rollback by line).
- Neither `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` nor
  `ACTION_APPROVAL_MAX_DECISION_AGE` is set anywhere in this repo (grep over
  `platform-gitops/`). The only hits are the #700/#721 proposals under
  `platform-gitops/agents-state/mctl-api/proposals/`.

mctl-api side (read from mctlhq/mctl-api `main` via `gh api`, read-only):

- `helm/values.yaml`: `ACTION_APPROVAL_MAX_DECISION_AGE: ""` (empty is 24h) and
  `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: ""` (empty is off).
- `cmd/api/main.go`: `requireRegisteredPolicy()` uses `killSwitchOn`, which
  treats any value other than `""/false/f/0/no/off` as on. So `"true"` enables
  strict mode, and removing the line disables it. `parseApprovalMaxDecisionAge`
  refuses boot on an invalid duration and defaults to
  `governance.DefaultMaxDecisionAge`. `logApprovalPolicy` emits
  `slog.Info("action approval policy", "require_registered_policy", <bool>, "registered_rules", [...])`
  at boot (line ~111). That line is the startup evidence.
- `internal/governance/governance.go`: `Policies` registers exactly one rule,
  `dev-loop.human-approval` (`DevLoopPolicyRule`) at `v1`, with
  `require_approval` and side effect `write`. `PolicySet.Admit(rule, version, strict)`
  returns `ErrPolicyUnregistered` for an unregistered rule in strict mode,
  `ErrPolicyUnavailable` for an empty set, and refuses drift in both modes.
- `internal/api/handlers_approval_governance.go`: `guardDecision` calls `Admit`
  at decide, and `revalidateApproval` passes the policies to spend-time
  revalidation. Both attach `policy_status` to refusals. Create applies the
  same rule in `handlers_action_approvals.go`.
- `docs/decision-context-contract.md`: `approval_policy_unregistered` is 422 at
  create, and 409 with `reapproval_required=true` at decide and spend.
  `approval_policy_unavailable` is 503.

Deployed state checked:

- `mctl_get_service_status admins/mctl-api`: Argo `admins-mctl-api` is Healthy
  and Synced, updatedAt 2026-10-25T14:59:02Z. The `service` block is null
  (not a catalogue service), and the revision field is empty.
- `gh pr view 766 -R mctlhq/mctl-api`: merged 2026-10-23T08:28:27Z, merge
  commit `329f17c6c238494947bfe3bcb59a9b5702760a93`.
- `gh api repos/mctlhq/mctl-api/compare/329f17c...4.122.0`: status `ahead`.
  The deployed tag 4.122.0 (released 2026-10-25T13:54Z) contains #721. The
  first release after the merge is 4.117.0 (2026-10-23T09:43Z). When it
  reached production was not checked.
- `gh release list -R mctlhq/mctl-api`: 4.117.0 through 4.122.0 released
  between 2026-10-23 and 2026-10-25. So at least about 2 days of #721-capable
  releases exist, which is more than one 24h window if production followed
  within hours.
- Repo clone `mctl-api.yaml` at mctl-gitops `b80c27fe` (2026-10-25T14:53Z): the
  strict flag and the max-age are both absent. The effective max-age is 24h
  unless another env source overrides it (not observed).
- `mctl_get_service_logs admins/mctl-api` (since 6h, 1000 lines): returned
  `count: 0`. This is treated as could-not-observe, not as "no logs". The
  current boot line (`require_registered_policy=false`) and any
  `policy_status` audit signal were therefore not observed.
- Action-approval inventory (rows by `policy_rule_id`/`policy_version`/
  `policy_status`/state): no read-only MCP tool exposes it, so it was not
  observed. This is the main gate gap (see requirements Open questions).
- `$MCTL_GITOPS_ROOT` services/tenants checkout: no mctl-api entry. That is
  expected, because mctl-api lives in bootstrap.

## Proposed solution

A three-phase operator rollout. Only phase 2 changes the repo.

Phase 1, evidence gate (read-only; it can stop the rollout):

1. Pin the revisions: the mctl-gitops `main` SHA, the `image.tag` from
   `mctl-api.yaml`, the mctl-api commit of that tag, and the chart revision Argo
   currently renders (`main`, so record the SHA).
2. Confirm that #721 is in the image (compare with `329f17c`, as above), and
   that `admins-mctl-api` is Healthy/Synced.
3. Read the live pod env (`kubectl -n mctl-api get deploy mctl-api -o yaml`,
   or `kubectl exec ... env`) for `ACTION_APPROVAL_*`, so that the effective
   max-age reflects every env source, not only the gitops file. Read the
   current boot line on both replicas (`kubectl logs`), which should show
   `require_registered_policy=false`, `registered_rules=[dev-loop.human-approval@v1]`.
   Determine when the first #721-capable pod started (the Argo history, or
   the ReplicaSet creation time of a 4.117.0+ image). Record the window as
   `[first_721_pod_start, now]`, and require it to be at least the max-age.
4. Inventory query against the work-items action-approval store (read-only
   SQL against the `mctl-api` database on `shared-pg-rw`, or an admin
   listing endpoint if one exists). Group by `policy_rule_id, policy_version`,
   then by state, for rows created or updated within the window plus every
   row still `pending`, or `approved` with `fresh_until > now()`. Classify each
   group with the same rule as `PolicySet.Check`. Also count live rows with
   incomplete mandatory context (missing `decided_context_digest`,
   `policy_decision`, `side_effect`, and so on, according to the #721 contract).
5. Decide:
   - all groups `ok`, or non-executable, and zero live incomplete rows: go;
   - any executable unregistered/drift group, or any live incomplete row:
     no-go, record it, and open a follow-up in mctl-api;
   - any step unavailable: no-go, a blocker on #2141.

Phase 2, the flip (the only repo change). A PR that edits only
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`. It inserts
the entry next to the other approval switches (after
`MCTL_AGENT_RECEIPT_GATE`):

```yaml
            # Strict registered-policy enforcement for action approvals
            # (mctlhq/mctl-api#721, rollout mctlhq/mctl-gitops#2141). An
            # approval whose policy rule is not in governance.Policies is
            # refused at create (422), decide and spend (409
            # approval_policy_unregistered, reapproval_required). Observation
            # window and producer inventory: <evidence comment link>.
            # Rollback: remove this line (empty = off) and let Argo resync.
            ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: "true"
```

The PR does not bump `ROLLOUT_MARKER` or the image. A Deployment env change
already rolls the pods, and mixing in another change would blur the evidence.
`helm template` with the inline values must render the new env var. The
existing `validate-manifests.yml` and `claude-review.yml` run as usual.

Phase 3, verify and close:

- Argo: `admins-mctl-api` Healthy/Synced on the merge SHA and the same image
  tag, with both replicas ready.
- Boot: `kubectl logs` on every new pod shows `action approval policy`,
  `require_registered_policy=true`,
  `registered_rules=[dev-loop.human-approval@v1]`.
- Negative proof: as platform admin, one create-action-approval request with
  `policy_rule_id` set to an obviously unregistered id (for example
  `rollout-2141.unregistered-probe`) and otherwise complete context. Expect
  422 `approval_policy_unregistered`. The request fails at create, so no row
  is stored, nothing can be decided or spent, and no workflow runs. If the
  probe is not acceptable, fall back to the mctl-api unit tests for `Admit`
  plus the boot line (see Open questions).
- Positive check: the next governed DevLoop approval (`mctl_approve_dev_loop`
  on a real proposal, done by a human in the normal course of work) succeeds
  and is spent. A deliberate test approval is not created for this.
- Post the evidence bundle on #2141, link it to mctl-api#721, and close the
  issue.

## Alternatives

- Flip now on the basis of elapsed time alone. The issue explicitly forbids
  this: more than 24h having passed proves nothing about producers. Dropped.
- Set the flag in the mctl-api chart default (`helm/values.yaml`). That is an
  mctl-api runtime-semantics change, it affects every deployment including
  previews, and it moves the rollback out of GitOps. Dropped.
- Stage it as a shadow or observe mode first. mctl-api has no observe mode for
  this flag; `policy_status` in the audit trail already is the observation
  signal. Adding a mode is new code, which is out of scope. Dropped.
- Use Loki as the inventory source. Loki returned zero rows for this service,
  and the issue states that zero rows is not evidence. Loki is acceptable only
  as a supplement, after authoritative store evidence.

## Platform impact

- Migrations: none. No schema or data change. Legacy rows are untouched;
  strict mode only adds refusals for unregistered rules.
- Backward compatibility: every producer using `dev-loop.human-approval@v1`
  is unaffected. Any producer with another rule id starts getting 422 at
  create. Already-approved rows with such a rule get 409 at spend
  (`reapproval_required=true`). That is why the inventory gate exists.
- Resource impact: one rolling restart of 2 replicas. The topology spread and
  sticky cookies are unchanged. In-flight identity-link challenges on the
  restarted pods are lost ("start again"), as in any mctl-api rollout.
- Risks and mitigations:
  - Hidden producer refused after the flip. Mitigation: the inventory gate,
    the positive DevLoop check, and a one-line rollback.
  - The registered set ends up empty in some build: that gives 503
    `approval_policy_unavailable` for all approvals. Mitigation: the boot line
    must list `dev-loop.human-approval@v1` before closure. Roll back if it
    does not.
  - The chart tracks `main`, so a chart change may land in the same sync.
    Mitigation: pin and record the chart SHA in phase 1, and diff the rendered
    manifest in the Argo app before and after.
  - The evidence surface is unavailable (the current state for the inventory
    and Loki). Mitigation: a hard stop. Report a blocker and do not flip.
