# Design: issue-2668-spike-assess-argo-rollouts-for-evidence

## Current state

### Argo Rollouts is already declared, but unused
- `platform-gitops/bootstrap/templates/core-infra/argo-rollouts.yaml` is an ArgoCD `Application` in project `default` for chart `argo-rollouts` `2.39.0` from `https://argoproj.github.io/argo-helm`, namespace `argo-rollouts`. It sets `installCRDs: true`, `dashboard.enabled: true` (ClusterIP), automated sync with `prune: true` and `selfHeal: true`, `ServerSideApply=true`, and an `ignoreDifferences` on CRD `/spec/preserveUnknownFields`. Controller requests are 50m/64Mi (limits 250m/256Mi). Dashboard requests are 25m/32Mi.
- `platform-gitops/bootstrap/templates/projects/project-default.yaml:68` names `argo-rollouts` in the default project.
- `platform-gitops/helm-charts/base-service/templates/rollout.yaml` renders `kind: Rollout` (argoproj.io/v1alpha1) when `.Values.blueGreen.enabled` is true. `templates/deployment.yaml` renders the `Deployment` only when it is false. The strategy is `blueGreen` with `activeService: <fullname>` and `previewService: <fullname>-preview` (`templates/service-preview.yaml`). `autoPromotionEnabled` comes from values. A comment at rollout.yaml around line 112 says plainly that there is no pre-promotion analysis. The template carries `argocd.argoproj.io/sync-options: PruneLast=true` so that switching back to a Deployment does not drop endpoints.
- `platform-gitops/helm-charts/base-service/values.yaml` defines `blueGreen.enabled: false` and `blueGreen.autoPromotionEnabled: true`. That default promotes as soon as the preview pod passes readiness. The values comment also says the template is incompatible with RWO PVCs.
- No `services/*/*/values.yaml` sets `blueGreen` (grep over `$MCTL_GITOPS_ROOT/services` returned no match). No canary strategy, `AnalysisTemplate` or `TraefikService` exists anywhere in the chart.

### Native Deployment path
- `base-service/values.yaml`: `replicaCount: 1`, `strategy: {}` (the Kubernetes default is RollingUpdate 25%/25%), readiness `/readyz` and liveness `/healthz`, and `preStopSleepSeconds: 5` to avoid Traefik 502s during endpoint removal (gitops#1946). The sleep is not rendered under `Recreate`.
- `labs/mctl-telegram/values.yaml:8-9` uses `strategy.type: Recreate`. The issue excludes it (mctl-telegram#1115), and this proposal keeps it excluded.
- mctl-api is not a base-service service. `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` renders the chart from the mctl-api repo, pinned to commit `9895c76f`, with `replicaCount: 2`, a Traefik sticky cookie, a hostname topology spread and image tag `4.159.0`. `mctl-api-pdb.yaml` sets `minAvailable: 1` and notes that PDBs do not gate rolling updates.

### Release gates and approvals
- `platform-gitops/release-gates.yaml:38-44` has `version_holds`, including `mctl-api-bootstrap` with `held_from: "4.155.0"`. The enforcement points are listed in `docs/runbooks/mctl-api-release-hold.md`: `release-gate.py check` and `verify` in `release-deploy.yaml` and `gitops-bump.yaml`, `validate-manifests.yml`, and `release-gate-watch.yml`. Write path P5b (deploy key bypass) is BLOCKING-UNKNOWN until #2543.
- These gates act on GitOps desired state (the image tag written to git), before ArgoCD sync. An Argo Rollouts analysis would act after sync, on live pods. The two layers are therefore orthogonal. A Rollout can only progress or abort a revision that the gates already admitted. It cannot widen what the gates admit, unless someone hands it the power to write git, which this design forbids.

### Observability and traffic
- Metrics: `platform-gitops/bootstrap/templates/observability/monitoring.yaml:12-13` deploys `victoria-metrics-k8s-stack` `0.72.5`. The PromQL-compatible query endpoint (vmsingle/vmselect service) was not resolved from the repo. `mctl-api-monitor.yaml` and others provide service scrapes.
- Traffic: Traefik comes from the kube-hetzner module, `traefik_version = "42.0.0"` (`infrastructure/k3s-preview/kube.tf:125`), which is a v3-era chart. Argo Rollouts traffic splitting with Traefik needs a `TraefikService` weighted object and the rollouts Traefik plugin, and none exists in the repo. Without traffic routing, a canary's traffic weight equals its replica ratio. At mctl-api's 2 replicas the only achievable steps are 0%, 50% and 100%. At 1 replica (mctl-web, mctl-docs) a canary degenerates into blue-green.
- mctl-api's sticky cookie means existing sessions stay pinned. A canary's measured traffic would therefore skew toward new sessions, so the sample is biased.

Deployed state checked:
- `mctl_list_services(team=admins)`: argocd ok, complete. mctl-web 7.22.0, mctl-docs 0.1.67, mctl-design, mctl-support (has DB), umami (has DB), and the agents workers. All are `base-service`. mctl-api is not in the catalogue (it is a platform Application), as expected.
- `mctl_get_service_config(admins, mctl-web)`: image 7.22.0, port 80, no database. Replica count and strategy are not returned.
- `$MCTL_GITOPS_ROOT/services/admins/{mctl-web,mctl-docs}/values.yaml`: no `replicaCount`, `strategy` or `blueGreen` keys, so the chart defaults apply (1 replica, RollingUpdate).
- `$MCTL_GITOPS_ROOT/services` grep for `blueGreen` / `argoproj.io/v1alpha1`: no match.
- Live health of the `argo-rollouts` Application and its CRDs was not observed. The read-only tools available cover tenant services, not core-infra Applications. Treat it as unknown, not absent.
- The live mctl-api replica count, strategy and SLIs were not observed, and SLO definitions were not found in the repo.

## Proposed solution

Deliver a research-only decision record. It changes no manifests. The implementer writes:

1. `docs/spikes/argo-rollouts-progressive-delivery.md`, the decision document, with these sections:
   - **Evidence ledger.** Every claim is tagged verified-repo, live-observed, simulated, estimate or unknown, with a path, commit or tool call.
   - **Candidate selection.** mctl-api is the primary paper candidate, since it is the one workload with 2 replicas, a PDB and real traffic. `admins/mctl-docs` is the control, since it is stateless, static and has 1 replica. Each gets a baseline: strategy, replicas, probes, metrics source, known failure modes (the 2026-10-09 five-hour unready outage noted in `mctl-api.yaml`, and the gitops#1946 502s), and a proposed SLO marked as an estimate.
   - **Decision matrix.** Rows are native RollingUpdate + readiness/startup probes + release gates, Rollouts blue-green (the existing chart path), and Rollouts canary with replica-ratio or Traefik weights. Columns are detection time, rollback time, blast radius, p95/5xx effect, metric sample sufficiency at the real replica count, operator burden, controller/CRD overhead (already paid: the controller is declared), ArgoCD drift and sync interaction, capacity surge (blue-green doubles pods against tenant quota), and recovery when the controller is down.
   - **Scenario model.** Four frozen scenarios, run offline: success, elevated 5xx/p95, low sample/inconclusive, provider unavailable. Each states the expected Rollout phase and the expected native behaviour.
   - **Authority boundary.** See below.
   - **Security negatives table.** Unauthorized promotion (dashboard or `kubectl argo rollouts promote`, and the `autoPromotionEnabled: true` default), missing approval or release binding, wrong digest (the Rollout pod template is whatever ArgoCD synced, so digest binding stays the gates' and GitOps' job), stale or empty query, zero traffic, broken provider, ArgoCD selfHeal vs Rollout-managed ReplicaSets and Service selectors, and multi-tenant spillover (a cluster-wide controller and dashboard).
   - **Verdict** and an **existing-issue reuse map** covering #2523, #2580, #2601, mctl-telegram#1108/#1115, mctl-agents#1007 and .github#55.
   - **Pinned sources.** Argo Rollouts docs URLs for analysis, blue-green, canary and the Traefik plugin at the version matching chart 2.39.0.
2. `docs/spikes/fixtures/argo-rollouts/`: offline-only YAML fixtures. An `AnalysisTemplate` with a Prometheus provider against a placeholder address, using `successCondition` with an explicit `len(result) > 0` guard, `failureLimit: 0`, `inconclusiveLimit: 0` and `consecutiveErrorLimit: 1`, so that inconclusive or error results abort. A canary `Rollout` sketch with `pause: {}` (indefinite, human resume) before any step above 0%. A README stating that these files must never be applied. The fixtures sit outside every ArgoCD-watched path (`platform-gitops/`), so the ApplicationSet cannot pick them up.
3. A recorded finding with a proposed follow-up issue: the base-service `blueGreen.autoPromotionEnabled: true` default allows evidence-free promotion. The fix (default to `false`, or remove the template) is a separate, owner-approved change.

### Authority boundary (normative text for the document)
- Input: only a revision already admitted by `release-gates.yaml` checks, merged to `main` and synced by ArgoCD, pinned by digest.
- The Rollout may only pause, abort (scale the new ReplicaSet to 0 and keep stable), or continue to the next step if the delegated policy expressly allows auto-progress for that step.
- It may not approve, write git, publish images, call mctl-api or DevLoop signals, or change release gates. Abort is not a rollback in GitOps. Git still declares the new tag, so ArgoCD shows Degraded until a human reverts through the normal PR or `wft-rollback-service`.
- Inconclusive, empty, stale or provider-error results lead to pause or abort, never to promotion.

### Expected verdict (to be confirmed by the document)
`DEFER_UNTIL_RELEASE_GATES_READY` for mctl-api, because hold P5b is open, the chart is external and 2 replicas give only coarse traffic steps. For base-service workloads, the expected answer is `KEEP_NATIVE_DEPLOYMENTS` plus probe and strategy hardening. A `BOUNDED_ROLLOUTS_PILOT` contract is drafted but not recommended until the gates are closed. The implementer must let the evidence override this expectation, and say so if it does.

## Alternatives
- **Install-and-try (live canary on mctl-docs).** Dropped. The issue forbids live tests and promotion, and a 1-replica static site produces no meaningful metric sample.
- **Harden native Deployments only, no Rollouts analysis.** This is kept as a matrix row rather than as the whole answer. The issue explicitly asks for the comparison, and the existing installed-but-ungated controller needs a decision either way.
- **Remove the controller and the blueGreen template now.** Dropped from this spike, because it is an implementation change that needs owner approval. It is recorded as a possible follow-up if the verdict is KEEP_NATIVE.

## Platform impact
- Migrations: none. Only docs and offline fixtures outside `platform-gitops/` are added.
- Backward compatibility: no rendered manifest changes. `helm template` output for every service stays identical.
- Resources: none at runtime.
- Risks and mitigations:
  - A fixture is applied by mistake. Mitigation: it lives outside ArgoCD paths, its README forbids use, and it uses a placeholder metrics address.
  - The verdict is read as a deployment grant. Mitigation: the document header restates RESEARCH ONLY, and any pilot needs a separate owner decision.
  - Unknown live state is treated as fact. Mitigation: the evidence ledger, with unknowns listed explicitly.
