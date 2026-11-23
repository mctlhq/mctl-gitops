# Reconcile staged Glovo M1 GitOps package drift before the Direct Production Canary

## Context

Issue mctlhq/mctl-gitops#2567 is P0 preparation for the Direct Production Canary plan (#2457). The inert
staged package `deploy/staged/glovo-m1/` was written for #2470 when the provider was still a Temporal
worker. Since then mctl-telegram#1262 (provider becomes an HTTP bridge client with no Temporal
credential) and mctl-telegram#1235 (facade frozen identifiers and `GLOVO_MCP_*` config) merged as
proposals, and mctl-api#957/#985/#989 fixed the DB role model (`glovo_runtime`/`glovo_migrator`,
explicit `GLOVO_DB_URL`/`WORK_ITEMS_DB_URL`, no `AUDIT_DB_URL` fallback). The staged package and
`CROSSWALK.md` still describe the old shape: the README lists the drift as M14-M16 but nothing fixes it,
and the validator `scripts/validate-glovo-m1-staging.py` actively *requires* some of the obsolete values
(for example `GLOVO_TEAM_FALLBACK == "false"` and the provider `TEMPORAL_NAMESPACE`).

The work is a staged-only, render-only reconciliation: correct the staged values, network policies,
secrets map, compatibility and provenance files; rewrite the validator so it enforces the corrected
contract (and fails on the current tree); version the crosswalk with evidence. Nothing is applied,
no reconciled path changes, and the DB roles/migration staging owned by open PR #2563 (A15) is not
duplicated.

## User stories

- AS the #2457 canary owner I WANT the staged package to match the merged/proposed contracts SO THAT a
  later P1/P2 activation PR copies correct manifests instead of re-discovering drift.
- AS a security reviewer I WANT CI to fail when a staged manifest grants the provider Temporal access,
  lets the facade reach the control worker or Temporal, or re-introduces an implicit tenant fallback SO
  THAT drift cannot return silently.
- AS an operator I WANT a versioned crosswalk listing, for every staged value, its canonical source,
  the old value, the corrected value and the owner SO THAT P1/P2 gates are auditable.

## Acceptance criteria (EARS)

- WHEN the validator runs against the pre-fix tree (HEAD `628471c`) THE SYSTEM SHALL exit 6 (REFUSED)
  for each new drift check (the D-rows in design.md that carry a validator check), demonstrated by
  selftest fixtures built from the pre-fix content.
- WHEN the validator runs against the post-fix tree THE SYSTEM SHALL exit 0 for `--selftest` and the
  default mode, including helm render and kubeconform of every staged values file and NetworkPolicy.
- THE SYSTEM SHALL refuse any staged file, env key or value naming `GLOVO_TEAM_FALLBACK`, or any other
  `*_FALLBACK` / default-tenant key, in facade, provider or control values and in `compatibility.yaml` /
  `budgets.yaml`.
- THE SYSTEM SHALL require the facade staged image repository to equal the #1235 frozen identifier
  `ghcr.io/mctlhq/mctl-glovo-mcp`, its env keys to be a subset of the #1235 `GLOVO_MCP_*` table, and
  `GLOVO_MCP_ENABLED` to be `"false"`.
- THE SYSTEM SHALL refuse any `TEMPORAL_*` env key, Temporal ExternalSecret, or Temporal namespace in
  the provider worker staged values, and SHALL require `MCTL_API_BASE_URL`,
  `MCTL_BRIDGE_CREDENTIAL_FILE` (a file path, never an env-valued credential) and
  `BRIDGE_WORKER_IDENTITY` matching `^provider:[a-z0-9-]{1,32}$`.
- THE SYSTEM SHALL require the provider tenant to keep `allowInternetEgress: false` and
  `allowClusterEgress: false`, and SHALL require a staged provider egress NetworkPolicy whose only
  non-DNS peer is namespace `mctl-api` with pod label `app.kubernetes.io/name: mctl-api`, with no peer in
  namespace `temporal`.
- THE SYSTEM SHALL require a staged facade egress NetworkPolicy whose only non-DNS peer is mctl-api,
  and SHALL refuse any staged policy that admits facade traffic to the control worker or to Temporal.
- THE SYSTEM SHALL require the control worker values to keep `TEMPORAL_NAMESPACE: mctl-assistants`,
  its own ExternalSecret, no Ingress, a staged deny-all ingress policy (the control worker receives no
  inbound workload traffic in M1; the old `netpol/facade-to-control.yaml` is removed), and a staged
  egress policy allowing only DNS, Temporal frontend 7233 and mctl-api.
- WHILE any image digest is `<digest-pending>` THE SYSTEM SHALL keep image `tag` as `"0.0.0"` and mark
  the image `deployable: false` in `provenance.yaml`; IF a staged image has a non-placeholder tag or
  digest without a matching provenance `commit` THEN THE SYSTEM SHALL refuse.
- THE SYSTEM SHALL keep the existing leak guard over `platform-gitops/**` unchanged in strength and
  SHALL show via `git diff --stat` that no file outside `deploy/staged/glovo-m1/`,
  `scripts/validate-glovo-m1-staging.py`, `docs/runbooks/glovo-m1.md` is changed.
- WHEN a detail cannot be observed from a pinned source THE SYSTEM SHALL record it as `UNKNOWN` in the
  crosswalk, never as a corrected value.
- THE SYSTEM SHALL publish `CROSSWALK.md` version `v2` with a pinned-source table (repo, revision,
  path, sha256 of the cited file) and one row per staged mismatch: canonical source, staged value,
  corrected value, owner, status.
- THE SYSTEM SHALL record P1 and P2 human gates and downstream activation PR boundaries in the
  crosswalk and the runbook, and SHALL state that this change grants no deploy or activation right.

## Out of scope

- Any Argo apply, DNS, TLS, namespace creation, Vault write, Temporal namespace or authorizer change,
  image build or release.
- The DB roles, ExternalSecrets for `glovo_runtime`/`glovo_migrator`, migration job and mctl-api env
  patch staged by PR #2563 (files under `deploy/staged/glovo-m1/db/`). This proposal only cross-references
  them and checks their names in the crosswalk.
- Changes to mctl-api, mctl-telegram or mctl-agents code or proposals (contract AMENDs M1-M13 stay with
  their owners).
- Changes to live service manifests (`platform-gitops/services/**`, `platform-gitops/tenants/**`).
- Real Glovo provider (P3), login, session, payment.

## Open questions

- Control worker image name: #1044 leaves open `ghcr.io/mctlhq/mctl-agents-assistants-control` vs a
  build-only image. Assumed: stage `ghcr.io/mctlhq/mctl-agents-assistants-control`, marked
  `UNKNOWN`/not deployable until #1044 decides.
- Provider image name: #1262 adds `Dockerfile.glovo-provider-worker` but the read design names no
  registry path. Assumed: keep `ghcr.io/mctlhq/glovo-provider-worker` as `UNKNOWN` pending mctl-telegram.
- Facade workload credential for `GLOVO_MCP_API_CREDENTIAL_FILE`: the issuer is gated on #2506/#2540; the
  Vault path is proposed plan-only (`teams/labs/glovo-mcp/mctl-api-credential`) and marked UNKNOWN.
- mctl-api egress peer: namespace `mctl-api` and label `app.kubernetes.io/name: mctl-api` are taken
  from `platform-gitops/argo-workflows/config/networkpolicy.yaml` and
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-monitor.yaml`. The container port was not
  observed in this run; it is staged as UNKNOWN until the implementer reads it from the mctl-api chart.
  Whether the facade and provider reach mctl-api in-cluster or via the public `api.mctl.ai` (Traefik)
  path is also unresolved; the latter would need a peer on the ingress controller, not mctl-api.
- Ordering with #2563: whichever merges second rebases; this proposal assumes #2563 merges first and
  adds its `db/` files to the crosswalk. If #2563 is still open, the crosswalk cites its head
  `6464978` as UNMERGED.
- Kill-switch naming: mctl-api uses `GLOVO_ENABLED`/`GLOVO_JOIN_ENABLED`/`GLOVO_CONTROL_START_ENABLED`;
  the facade uses `GLOVO_MCP_ENABLED`. The staged `budgets.yaml` `killSwitch.keys` is restructured per
  component; the reviewer should confirm that split.
