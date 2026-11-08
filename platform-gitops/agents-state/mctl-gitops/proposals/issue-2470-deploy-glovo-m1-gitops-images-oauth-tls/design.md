# Design: issue-2470-deploy-glovo-m1-gitops-images-oauth-tls

## Current state

**How a service gets deployed.**
`platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml`
defines the `apps` ApplicationSet. Its git directory generator matches
`platform-gitops/services/*/*` (re-queued every 30 seconds). It renders every
match with `platform-gitops/helm-charts/base-service` and `<dir>/values.yaml`,
into the namespace named by the second path segment. The sync policy is
`automated: {prune: true, selfHeal: true}`. Tenants are generated the same way
from `platform-gitops/tenants/*` with `platform-gitops/helm-charts/tenant`.
Other reconciled paths include `platform-gitops/infra-components/**` (including
`infra-components/labs`), `platform-gitops/argo-workflows`, and
`platform-gitops/bootstrap`. **A file in any of these paths is live once it is
merged.** Nothing in the repo today stages a service without deploying it.

**Ingress, TLS and hostnames.** `base-service/templates/ingress.yaml` renders
`ingress.hosts`, `ingress.tls` and the optional forward-auth middleware. TLS
comes from cert-manager via `cert-manager.io/cluster-issuer: letsencrypt-prod`
(example: `platform-gitops/services/labs/mctl-telegram/values.yaml`, secret
`mctl-telegram-tls`). `infrastructure/cloudflare/zones/mctl-ai/dns.tf` holds a
proxied wildcard record `*.mctl.ai`, so a new `*.mctl.ai` host needs **no DNS
change** to become reachable. Platform hosts are guarded by the
`mctl-reserved-platform-hosts-*` ValidatingAdmissionPolicies. Their owner map
is `reservedPlatformHosts` in `platform-gitops/bootstrap/values.yaml`, for
example `tg.mctl.ai: [labs]`, `mcp.mctl.ai: []`. The runbook is
`docs/runbooks/reserved-hosts.md`. Hosts not in the map are unrestricted.
`glovo.mctl.ai` is not in the map.

**Existing MCP OAuth precedent.** `labs/mctl-telegram` serves `tg.mctl.ai/mcp`
with:
- `AUTH_MODE: local-jwt`, `AUTH_REQUIRED: "true"`
- `OAUTH_ISSUER_URL: https://tg.mctl.ai`
- the `ALLOWED_ORIGINS` and `OAUTH_ALLOWED_IMPLICIT_HOSTS` allowlists

The file warns that `mctl_deploy_service` yq rewrites strip colon-bearing env
values.

**Images.** `base-service/values.yaml` already accepts `image.tag` as semver or
an `@sha256` digest ("empty fails render"). Every labs service today pins
semver tags, not digests. `scripts/release-gate.py` is a fail-closed gate for
grouped worker Deployments ("could not observe is never observed fine"). That
is the pattern the P1 gate reuses.

**Temporal.** The shared Temporal server
(`platform-gitops/bootstrap/templates/data/temporal.yaml`) has no client auth.
`platform-gitops/infra-components/data/temporal/networkpolicy.yaml`
(`allow-temporal-ingress`) is the only boundary. Tenant Temporal namespaces are
registered by `infra-components/data/temporal/tenant-namespace-job.yaml`.
`docs/adr/0003-temporal-client-authz.md` (status Proposed) names future
`mctl-assistants:write` and `mctl-assistants-provider-<name>:write`
identities. The #2469 spike proposal
(`agents-state/mctl-gitops/proposals/issue-2469-.../`, status proposed) states
that new `mctl-assistants*` namespaces are release-blocked until client auth
is proven.

**Network isolation.** The tenant chart's `templates/networkpolicy.yaml`
provides:
- default deny of all ingress and egress
- allow intra-namespace traffic
- allow cluster egress
- allow internet egress, only when `allowInternetEgress` is true

**CI.** `.github/workflows/validate-manifests.yml` does the following:
- runs `helm lint`
- renders each `platform-gitops/services/*/*/values.yaml` with base-service
  and checks it with `kubeconform -strict`
- renders bootstrap/argocd and checks AppProject scope
- runs the `reserved-hosts` job
- has a precedent for validating overlays that are not deployed (otel eval,
  OBI spike, surface overlays)

**Deployed state checked:**
- `mctl_list_services(team=labs)`: complete=true, 21 apps, all Synced. There is
  no Glovo, glovo-mcp or assistants service. `labs-mctl-telegram` runs 0.135.0
  on `tg.mctl.ai` and `labs-mctl-telegram.mctl.ai`. `labs-kuptsi-app` is
  present (the Temporal consumer that must stay uninterrupted).
- `$MCTL_GITOPS_ROOT/services/labs/` (`/workdir/mctl-gitops/platform-gitops/services/labs`):
  no `glovo*` directory.
- `platform-gitops/bootstrap/values.yaml` `reservedPlatformHosts` in the clone:
  no `glovo.mctl.ai` entry.
- Clone-wide grep for `glovo` outside `agents-state/`: no matches. There are
  related proposals for mctl-api#953/#954, mctl-agents#1043 and
  mctl-telegram#1184/#1225/#1227.
- Not observed: the live Temporal namespace list, the live Cloudflare DNS
  records (only the Terraform source was read), and GHCR packages for the
  three images (they do not exist yet, per the issue). See Open questions in
  requirements.md.

## Proposed solution

### 1. Staging area outside every reconciled path

Add a top-level directory, `deploy/staged/glovo-m1/`. It sits outside
`platform-gitops/`, so no ApplicationSet, Application or `manifest-generate-paths`
can match it.

```
deploy/staged/glovo-m1/
  README.md                       # phase map P0/P1/P2/P3, who approves what
  gate.yaml                       # phase state machine: p0=approved, p1=blocked, p2=blocked
  provenance.yaml                 # per image: ghcr repo, digest, source repo+commit, SBOM ref, build run
  compatibility.yaml              # facade x provider x control x mctl-api versions that may run together
  target-paths.yaml               # where each file goes when its phase is activated
  facade/values.yaml              # base-service values, target: services/labs/glovo-mcp
  control-worker/values.yaml      # target decided in P1 (assumed admins)
  provider-worker/values.yaml     # target: tenant/namespace mctl-assistants-provider-glovo
  provider-tenant/values.yaml     # tenant chart values, allowInternetEgress: false
  temporal-namespaces.patch.md    # lines P1 would add to tenant-namespace-job.yaml (text, not YAML)
  netpol/                         # extra NetworkPolicies P1 would apply (facade->control, control->temporal)
  secrets-map.md                  # Vault paths + ExternalSecret names per component, no values
  budgets.yaml                    # rate/cost budgets, canary size, kill-switch keys
docs/runbooks/glovo-m1.md         # enablement checklists P1/P2, smoke, rollback, kill switch
```

### 2. Facade values (staged)

The facade is a base-service deployment of the `mctl-telegram` Glovo facade
image:
- `image.tag` is an `@sha256:` digest from `provenance.yaml`.
- `ingress.hosts` is `[glovo.mctl.ai]`, with `path: /mcp` and the
  `/.well-known/oauth-protected-resource` metadata path only.
- TLS uses `letsencrypt-prod` with secret `glovo-mcp-tls`.
- `ingress.enabled: false` in the staged file. P2 flips it.

Env, following the `tg.mctl.ai` precedent but pointing at the MCTL issuer:
- `OAUTH_ISSUER_URL` = the mctl-api issuer, `OAUTH_RESOURCE` /
  audience = `https://glovo.mctl.ai/mcp`
- `AUTH_REQUIRED: "true"`
- `GLOVO_ENABLED: "false"` (kill switch)
- `GLOVO_ALLOWLIST: ""` (empty means deny all)
- `GLOVO_TEAM_FALLBACK: "false"`

The env key names are placeholders until the mctl-telegram facade issue fixes
them. Recorded in compatibility.yaml. Personal scope is unsupported, and the
facade requires an explicit team tenant. Colon-bearing values are documented
with the existing yq caveat. Security context and resources copy the hardened
`mctl-telegram` block (non-root, read-only root filesystem, small requests).

### 3. Provider and control worker values (staged)

The provider worker:
- has `ingress.enabled: false` and no Service port exposure. The render guard
  forbids Ingress, LoadBalancer and NodePort.
- runs in its own tenant namespace with default-deny from the tenant chart and
  `allowInternetEgress: false`.
- gets egress only to the Temporal frontend (P1 adds a matching rule to
  `allow-temporal-ingress`) and its Temporal identity
  `mctl-assistants-provider-glovo:write`.

The control worker gets `mctl-assistants:write`. It never gets a DevLoop
namespace role, so the provider is denied control/DevLoop by construction
(ADR 0003 mapping). Existing `mctl-agents` and kuptsi namespaces and the
existing NetworkPolicy peers are not modified in P0. P1 may only append to
them.

### 4. CI guard (the only live change in P0, and it is CI-only)

Add a `glovo-m1` job to `validate-manifests.yml` that runs a new script,
`scripts/validate-glovo-m1-staging.py` (with `--selftest`, like
`release-gate.py`). The script does the following:
1. Renders each staged `*/values.yaml` with base-service (and the tenant
   chart for `provider-tenant`), runs `kubeconform -strict`, and runs a
   second render with `ingress.enabled=true` to check the P2 shape. Then it
   runs `scripts/test-reserved-hosts-policy.sh`-style host checks and
   `validate-argocd-project-scope.py` against the hypothetical target
   namespaces.
2. Asserts the following:
   - the provider render has no Ingress, LoadBalancer or NodePort
   - the facade render routes only `glovo.mctl.ai` with `/mcp` and the
     metadata path
   - the kill switch defaults off, the allowlist is empty and team fallback
     is false
   - no secret value appears (ExternalSecret references only)
3. Checks provenance. P0 mode allows `<digest-pending>`. P1 mode (when
   `gate.yaml` says `p1: approved`) requires a `sha256:` digest, a source
   commit and an SBOM reference for each image.
4. Runs a **leak guard** that scans all reconciled paths (`platform-gitops/**`
   excluding `agents-state/`) for `glovo.mctl.ai`, `mctl-assistants` and
   `mctl-assistants-provider-glovo`. It fails unless `gate.yaml` marks the
   matching phase approved with an approval issue URL. Changing `gate.yaml`
   is itself a reviewed PR, which makes the gate auditable.

Exit codes follow `release-gate.py`: 0 pass, 6 refused, 7 could not observe.
Anything unreadable is a refusal.

### 5. Runbook

`docs/runbooks/glovo-m1.md` includes the following:
- The P1 checklist: #2469 evidence filled, JWT/TLS/authorizer slices merged
  and verified, mctl-agents#1043 bridge verified, digests and SBOMs present,
  kuptsi/DevLoop canary green.
- The P2 checklist: a reserved host entry `glovo.mctl.ai: [labs]` added in the
  same PR as the Ingress, per `reserved-hosts.md`; whether an MCP portal entry
  is wanted; the pilot allowlist and team tenant named explicitly.
- The negative test matrix from the issue, assigned to the phase that can run
  it.
- A smoke test with a real MCP client.
- OTel logs and metrics expectations (the `otel` block of base-service).
- Rate and cost budgets.
- A kill switch procedure: flip `GLOVO_ENABLED=false`, or set
  `ingress.enabled=false`.
- A rollback procedure: revert the activation PR, and Argo CD prunes.
- Canary limits: one team, N users.

## Alternatives

- **Put staged values under `platform-gitops/services/labs/glovo-mcp/` with
  `replicaCount: 0` and `ingress.enabled: false`.** Rejected. The ApplicationSet
  still creates an Argo CD Application, ServiceAccount, Service and
  ExternalSecrets (ESO would try Vault paths that do not exist). One flipped
  value then deploys with no separate approval. This violates "no apply path
  in P0".
- **A dedicated ApplicationSet or Application with `syncPolicy` manual or
  disabled.** Rejected for P0. It is still a live Argo object, editable from
  the UI, and a "Sync" click by any admin activates it. It mixes P0 and P1
  approvals.
- **Docs only, no manifests.** Rejected. The acceptance criteria require
  manifests that pass render/helm/ArgoCD validation. Prose cannot be validated
  and drifts from the chart.
- **Reuse `labs/mctl-telegram` on `tg.mctl.ai` as the Glovo endpoint.**
  Rejected by the issue. It also couples Glovo OAuth audiences and session
  risk to the production Telegram MCP.

## Platform impact

- **No migration and no runtime change in P0.** The only behavioural change is
  a new CI job. Resource impact is zero until P1. In P1, roughly 3 pods with
  small requests. Labs quota headroom is in `platform-gitops/tenants/labs/values.yaml`
  (requests.cpu 4 / limits.cpu 20) and must be checked at P1 time. The provider
  tenant gets its own quota.
- **Risk: wildcard DNS makes any Ingress live.** Mitigation: the leak guard
  blocks `glovo.mctl.ai` in reconciled paths before P2, plus optional task 7,
  which reserves `glovo.mctl.ai: []` so admission refuses it cluster-wide
  until P2 changes the owner to `[labs]`.
- **Risk: the CI guard is bypassed by renaming hosts or namespaces.**
  Mitigation: the guard also refuses any reconciled `values.yaml` whose image
  repository matches the provenance repos, and the claude-review/human review
  remains required for non-bump changes (CLAUDE.md branch-protection section).
- **Risk: false positives on the existing `mctl-assistants` mentions in
  `docs/adr/0003` and the runbooks.** Mitigation: the guard scans
  `platform-gitops/**` only and excludes `agents-state/`.
- **Risk: placeholder env key names do not match the facade implementation.**
  Mitigation: compatibility.yaml pins the facade version that defines them,
  and the P1 gate refuses a mismatch.
- **Backward compatibility:** existing services, the Temporal server, kuptsi
  and mctl-agents DevLoop are untouched. `validate-manifests.yml` gains a job
  and changes no existing step.
