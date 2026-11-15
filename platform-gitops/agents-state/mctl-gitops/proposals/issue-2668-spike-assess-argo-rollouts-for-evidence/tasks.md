# Tasks: issue-2668-spike-assess-argo-rollouts-for-evidence

- [ ] 1. Build the evidence ledger in `docs/spikes/argo-rollouts-progressive-delivery.md`: the current state of `core-infra/argo-rollouts.yaml`, `base-service/templates/rollout.yaml`, `templates/deployment.yaml`, `values.yaml` (`strategy`, `blueGreen`, probes, `preStopSleepSeconds`), `mctl-platform/mctl-api.yaml`, `mctl-api-pdb.yaml`, `release-gates.yaml`, `observability/monitoring.yaml`, and `infrastructure/k3s-preview/kube.tf` (Traefik). — DoD: every claim tagged verified-repo, live-observed, simulated, estimate or unknown, with a path and commit SHA. Live controller health is recorded as unknown unless separately observed.
- [ ] 2. Candidate selection and baseline (depends on 1). — DoD: mctl-api (primary, paper-only) and admins/mctl-docs (control) documented with replicas, strategy, probes, metrics source, known failure modes and estimated SLOs. mctl-telegram exclusion stated, with mctl-telegram#1115 cited.
- [ ] 3. Decision matrix (depends on 2). — DoD: rows are native RollingUpdate + gates, Rollouts blue-green (existing chart path) and Rollouts canary (replica-ratio and Traefik-weighted). All columns listed in design.md are filled. Achievable traffic steps at the actual replica counts are stated.
- [ ] 4. Offline fixtures in `docs/spikes/fixtures/argo-rollouts/` (depends on 3): an `AnalysisTemplate` with empty-result guard, `failureLimit: 0`, `inconclusiveLimit: 0` and `consecutiveErrorLimit: 1`, a canary `Rollout` sketch with an indefinite `pause: {}`, a README forbidding use, and four frozen metric-result inputs (success, 5xx/p95 breach, low-sample, provider error). — DoD: the files exist outside `platform-gitops/`, use placeholder addresses, and are not referenced by any ArgoCD Application.
- [ ] 5. Scenario model (depends on 4). — DoD: for each of the four scenarios, the document records the expected Rollout phase and the native behaviour. Inconclusive and unavailable both end in pause or abort.
- [ ] 6. Authority boundary and security negatives table (depends on 3). — DoD: the normative boundary text from design.md is included, and each of the eight negatives in the issue has a row giving the control, the residual risk and the evidence class.
- [ ] 7. Finding on the `blueGreen.autoPromotionEnabled: true` default (depends on 1). — DoD: written up with the exact path and line, and a proposed follow-up issue drafted in the doc. No chart change made.
- [ ] 8. Verdict, reuse map, pinned sources and draft pilot contract (depends on 3, 5, 6). — DoD: one Outcome chosen with its rationale. Reuse map covers #2523, #2580, #2601, mctl-telegram#1108/#1115, mctl-agents#1007 and .github#55. Rollouts documentation links are pinned to the version matching chart 2.39.0. The pilot contract, if included, has entry and exit criteria, stop conditions and a rollback sequence, and is marked as requiring an owner decision.
- [ ] 9. Open a docs-only PR and request owner review. — DoD: the PR touches only `docs/spikes/**`, CI passes, and the body restates RESEARCH ONLY.

## Tests
- [ ] T1. `git diff --name-only origin/main` lists only paths under `docs/spikes/`.
- [ ] T2. `helm template` of `platform-gitops/helm-charts/base-service` with `services/admins/mctl-docs/values.yaml` is byte-identical before and after the change.
- [ ] T3. `kubeconform` or a YAML lint (offline, with Argo Rollouts CRD schemas if available) parses the fixtures. No `kubectl` call to any cluster is made.
- [ ] T4. A reviewer can find, for each of the four scenarios, a fixture input and an expected outcome. Neither the inconclusive nor the error scenario maps to "Successful/Promoted".
- [ ] T5. grep confirms that no `platform-gitops/**` file references `docs/spikes/fixtures`.

## Rollback
Revert the docs-only PR. Nothing is deployed, synced or installed, so no cluster action is needed.
