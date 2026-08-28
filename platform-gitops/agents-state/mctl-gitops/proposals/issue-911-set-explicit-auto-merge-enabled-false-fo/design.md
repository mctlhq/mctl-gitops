# Design: issue-911-set-explicit-auto-merge-enabled-false-fo

## Current state

The `admins-mctl-agent` ArgoCD `Application` is defined entirely in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml` (a raw
manifest under the App-of-Apps bootstrap tree, not a templated Helm
chart itself — it *sources* the `base-service` chart via
`spec.source.helm.values`).

Relevant excerpt (lines 32-93), the inline `env:` map passed to the
`base-service` chart:

```yaml
env:
  PORT: "8080"
  MCTL_API_URL: "http://mctl-api.mctl-api.svc:8080"
  GITHUB_OWNER: mctlhq
  GITHUB_REPO: mctl-gitops
  GITHUB_TOKEN_FILE: /var/run/secrets/github/GITHUB_TOKEN
  POLL_INTERVAL: "5m"
  ALERT_FLAP_COOLDOWN: "12h"
  DRY_RUN: "false"
  WEBHOOK_ENABLED: "true"
  ...
  OPTIMIZER_ENABLED: "true"
  OPTIMIZER_DRY_RUN: "true"
  OPTIMIZER_TENANT_ALLOWLIST: "labs"
  DATABASE_URL: "postgresql://..."
```

`AUTO_MERGE_ENABLED` is absent from this map. Per the issue, the
mctl-agent binary defaults this to `true` when unset, so with
`DRY_RUN: "false"` already live, the agent is currently permitted (at the
code-default level) to auto-merge PRs it opens against `mctl-gitops`.

This `env` map is consumed by
`platform-gitops/helm-charts/base-service/templates/deployment.yaml:121-127`:

```yaml
{{- if .Values.env }}
env:
  {{- range $key, $value := .Values.env }}
  - name: {{ $key }}
    value: {{ $value | quote }}
  {{- end }}
{{- end }}
```

Every entry in the map becomes one Deployment container env var, quoted
as a string regardless of the YAML scalar's original type — which is why
existing boolean-shaped flags in this file (`DRY_RUN`, `WEBHOOK_ENABLED`,
`DISABLE_LLM_DIAGNOSIS`, `AM_RECONCILE_ENABLED`, `OPTIMIZER_ENABLED`,
`OPTIMIZER_DRY_RUN`) are all already written as quoted strings
(`"false"` / `"true"`) in this file, not bare YAML booleans. This is the
established local convention this change must follow.

The Application has `syncPolicy.automated` with `prune: true` and
`selfHeal: true`, so once this file is merged to `main` and ArgoCD
reconciles (root-app watches `mctl-gitops` `main`), the change rolls out
without a manual sync trigger. `strategy.type: Recreate` means the single
mctl-agent pod is replaced (old terminated, new created), so the new env
set is guaranteed to be in the very next pod's spec — there is no rolling
overlap where an old-env pod could linger and merge a PR under the stale
default.

## Proposed solution

Add one new key to the existing `env` map in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`,
directly under `DRY_RUN: "false"` (the two flags are conceptually paired —
DRY_RUN gates whether the agent writes at all, AUTO_MERGE_ENABLED gates
whether what it writes lands without review — so co-locating them keeps
that relationship legible to the next reader):

```yaml
DRY_RUN: "false"
# Explicit fail-closed override: mctl-agent's code default for this flag
# is true, which combined with DRY_RUN=false would let agent-authored
# PRs to this repo auto-merge without review. Pin it here regardless of
# the code-side default (companion mctl-agent issue: flip the default to
# false) so the deployment's intent doesn't silently depend on whatever
# a future image tag ships as its compiled-in default.
AUTO_MERGE_ENABLED: "false"
```

The comment follows this file's established convention (every non-obvious
flag in this file — `GITHUB_TOKEN_FILE`, `ALERT_FLAP_COOLDOWN`,
`DISABLE_LLM_DIAGNOSIS`, `MAX_ANALYZING_AGE`, `AM_RECONCILE_ENABLED`,
`OPTIMIZER_ENABLED`/`OPTIMIZER_DRY_RUN`) carries a comment explaining
*why*, per this repo's `CLAUDE.md` convention: "Comments explain
non-obvious configuration, not what the YAML does."

No chart change is needed: the `base-service` `env` range loop already
handles arbitrary new keys generically. No image tag bump, no RBAC,
secrets, or ApplicationSet change. This is the minimal, single-file,
single-key diff the issue asks for.

Verification (per acceptance criteria, "check the pod env, not just
Synced"):
1. `helm template admins-mctl-agent platform-gitops/helm-charts/base-service -f <(extract the inline values block)` — or more directly, `argocd app diff admins-mctl-agent` after the PR merges — to confirm the rendered Deployment carries `AUTO_MERGE_ENABLED: "false"`.
2. After ArgoCD syncs (automated, no manual trigger needed given
   `syncPolicy.automated`), `kubectl -n admins exec <mctl-agent pod> -- env | grep AUTO_MERGE_ENABLED` (or equivalent `kubectl get pod -o jsonpath` on `spec.containers[0].env`) to confirm the *live* pod, not just the ArgoCD-reported sync state, carries the value. This is the fail-closed check the issue explicitly calls out — ArgoCD `Synced`/`Healthy` only proves git-vs-live parity for fields ArgoCD tracks, not that the process actually read and honored the new env var (e.g. an old cached pod from before `Recreate` finished).

## Alternatives

1. **Set it via `update-config` (mctl_deploy_service action=update-config)
   instead of editing the file directly.** Rejected: this repo's own
   convention (`CLAUDE.md` "Common Operations") treats
   `platform-gitops/services/<team>/<service>/values.yaml` edits and the
   `mctl_deploy_service` tool as equivalent paths to the same GitOps
   commit for *service* deployments, but `admins-mctl-agent` lives in
   `bootstrap/templates/mctl-platform/`, not
   `platform-gitops/services/admins/mctl-agent/` — it is bootstrap-owned,
   not a per-tenant service onboarded through the normal service flow. A
   direct file edit + PR is the correct, and only, path for this
   Application.

2. **Fix it in the mctl-agent code instead (flip the compiled-in default
   to `false`).** Rejected as the sole fix, though it is the companion
   issue and eventually desirable: the issue explicitly asks for the
   *deployment* to be explicit "regardless of the code-side default
   flip," because relying solely on a code default leaves every other
   deployment of mctl-agent (if any exist or are added later) silently
   exposed until they happen to run an image tag with the new default.
   Explicit config is the fail-closed layer; the code default is
   defense-in-depth on top of it. This proposal is deployment-only and
   leaves the code change to the linked mctl-agent issue.

3. **Set `AUTO_MERGE_ENABLED: "false"` globally at the `base-service`
   chart level (a chart default) instead of per-Application.** Rejected:
   `base-service` is shared by every service on the platform, most of
   which have no concept of "auto-merge" at all (it's an mctl-agent
   business-logic env var, not a chart-level concern), so adding it to
   the chart's `values.yaml` defaults would be a category error — it
   would silently inject an unused env var into unrelated services and
   obscure that this is an mctl-agent-specific fail-closed decision.
   Scoping it to the one Application that needs it keeps the blast radius
   correct.

## Platform impact
- **Migrations**: none. Pure env-var addition.
- **Backward compatibility**: fully backward compatible. On mctl-agent
  `1.16.2` (current tag in this file) and any tag that already reads
  `AUTO_MERGE_ENABLED`, behavior becomes explicit-false. On any
  hypothetical older tag that doesn't read this key, the entry is inert
  (same precedent as `GITHUB_TOKEN_FILE` documented in this file) — no
  regression either way.
- **Resource impact**: none — one additional string env var on an
  existing container.
- **Risk**: very low. The only behavior change is that mctl-agent-authored
  PRs to `mctl-gitops` will require manual merge instead of potentially
  auto-merging, which is the intended, more conservative direction. The
  risk of *not* doing this (silent auto-merge of agent PRs with
  `DRY_RUN=false`) is materially higher and is exactly what this issue is
  closing.
- **Mitigation**: `strategy.type: Recreate` on this Application (already
  in place, unrelated to this change) means there is no window where old-
  and new-env pods run concurrently — a straightforward sync fully
  replaces the pod before it resumes work, so there's no ambiguity about
  which env set is live once `Synced`/`Healthy` and pod-env verification
  both pass.
