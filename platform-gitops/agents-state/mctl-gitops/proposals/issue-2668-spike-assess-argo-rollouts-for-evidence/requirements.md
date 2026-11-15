# Spike: assess Argo Rollouts for evidence-gated progressive delivery without bypassing DevLoop

## Context
Issue mctlhq/mctl-gitops#2668 asks for a decision: would Argo Rollouts make releases safer for one stateless MCTL service than the native Kubernetes Deployment + ArgoCD + release gates we use now? It has to do so without letting metric-based promotion or rollback get around governed approvals, and without making deployment failures worse. The issue allows research only. It does not authorize a controller install, a cluster experiment, a rollout, a promotion, a merge or an approval. The deliverable is a decision document with one verdict from the fixed set: `KEEP_NATIVE_DEPLOYMENTS | BOUNDED_ROLLOUTS_PILOT | ADOPT_GATED_PROGRESSIVE_DELIVERY | DEFER_UNTIL_RELEASE_GATES_READY`.

This matters because the repo already contains part of what the issue treats as a hypothetical. `platform-gitops/bootstrap/templates/core-infra/argo-rollouts.yaml` declares the Argo Rollouts controller (chart 2.39.0, dashboard enabled, `installCRDs: true`). `platform-gitops/helm-charts/base-service/templates/rollout.yaml` renders a blue-green `Rollout` when `blueGreen.enabled` is true, with `autoPromotionEnabled: true` by default and no analysis. No service values file opts in today. So the spike has to answer two questions: whether to use Rollouts at all, and what to do with an already-installed, unused, ungated capability whose default auto-promotes on readiness alone.

## User stories
- AS a platform owner I WANT a decision matrix comparing native RollingUpdate + release gates with Argo Rollouts canary/blue-green for one named stateless candidate SO THAT I can pick a verdict on evidence rather than on what a CNCF project can do.
- AS a release-gate maintainer I WANT a written authority boundary SO THAT no rollout analysis result can approve a release, override `platform-gitops/release-gates.yaml`, publish an image or edit GitOps desired state.
- AS an operator I WANT stop conditions and a rollback plan for a possible bounded pilot SO THAT any later pilot request starts from a reviewed contract.
- AS a security reviewer I WANT the negative cases (unauthorized promotion, wrong digest, stale or zero-traffic metrics, broken provider, ArgoCD sync conflict, multi-tenant spillover) analyzed explicitly SO THAT fail-open paths are known before any adoption.

## Acceptance criteria (EARS)
- WHEN the spike document is delivered THE SYSTEM SHALL contain exactly one verdict from the four Outcomes, with a rationale that cites the decision matrix.
- WHEN the document states a fact about the platform THE SYSTEM SHALL label it with one evidence class: verified-repo (file path and commit), live-observed (tool call named), simulated (offline fixture), estimate, or unknown.
- WHEN a live fact could not be observed THE SYSTEM SHALL record it as unknown and SHALL NOT present it as absent.
- WHEN a candidate workload is selected THE SYSTEM SHALL record why it is stateless, its current replica count, strategy, readiness probes, metrics source and baseline failure modes, and SHALL exclude `labs/mctl-telegram`.
- WHEN the four synthetic scenarios (success, elevated 5xx/p95, low sample volume / inconclusive, metrics provider unavailable) are modelled THE SYSTEM SHALL show that the inconclusive and unavailable scenarios end in pause or abort, never in promotion.
- WHEN an offline fixture `AnalysisTemplate` is written THE SYSTEM SHALL set its failure, inconclusive and error handling so that a missing or empty result cannot count as success. The fixture must not be applied to any cluster.
- WHILE the issue's authority stays RESEARCH ONLY THE SYSTEM SHALL change no file under `platform-gitops/bootstrap/`, `platform-gitops/helm-charts/` or `platform-gitops/services/`, and SHALL start no controller, rollout or promotion.
- IF the document recommends any pilot THEN THE SYSTEM SHALL bind it to a digest-pinned image that has already passed release gates. It SHALL list measurable entry and exit criteria, stop conditions and a rollback sequence, and require a separate owner decision before execution.
- IF the analysis finds that the existing `blueGreen.autoPromotionEnabled: true` default lets a Rollout promote without evidence THEN THE SYSTEM SHALL record it as a finding with a follow-up issue reference, and SHALL NOT fix it inside this spike.
- IF the Traefik traffic-splitting path or the VictoriaMetrics query path cannot be confirmed from repo or authorized live evidence THEN THE SYSTEM SHALL mark canary traffic weighting as unknown and SHALL NOT design weights on top of it.

## Out of scope
- Installing, upgrading, removing or configuring the Argo Rollouts controller, CRDs or dashboard.
- Enabling `blueGreen` or adding any `Rollout`, `AnalysisTemplate` or `TraefikService` object to a live service.
- Any live test, canary promotion, release, merge or approval, and any DevLoop implementation child.
- Changing `platform-gitops/release-gates.yaml`, the bump workflows or the mctl-api chart.
- mctl-telegram session ownership or fencing (mctl-telegram#1115).
- Opening a new epic.

## Open questions
- Which candidate does the owner prefer? The issue suggests mctl-api, but it is under an active release hold (`release-gates.yaml` hold `mctl-api-bootstrap`, `docs/runbooks/mctl-api-release-hold.md`, P5b BLOCKING-UNKNOWN until #2543), and its chart lives in the mctl-api repo, not in base-service. This proposal analyzes mctl-api on paper as the primary candidate and `admins/mctl-docs` (a base-service static site) as the low-risk control. The final pick is left to the owner.
- Is the `argo-rollouts` Application actually Synced and Healthy in the cluster? The read-only MCP tools reached during investigation only cover tenant services, so this is unknown.
- Was the base-service `blueGreen` template ever used, and is anyone relying on it? No service values file sets it today. The history of who added it and why was not traced.
- What exact Traefik version does chart 42.0.0 ship (`infrastructure/k3s-preview/kube.tf:125`)? Is the Argo Rollouts Traefik traffic-router plugin acceptable under the platform's plugin-download and egress policy?
- Do SLOs exist for any candidate? None were found in the repo. Baseline SLOs may need to be proposed as estimates.
