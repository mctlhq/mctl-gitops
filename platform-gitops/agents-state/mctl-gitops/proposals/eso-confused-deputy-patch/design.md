# Design: eso-confused-deputy-patch

## Current state
ESO is deployed on the platform via its own Helm chart (separate from the `base-service` Helm chart used by most services). The active chart version targets ESO in the range affected by CVE-2026-42876 (0.1.0–2.4.0). The related proposal `eso-cross-namespace-bypass-patch` set the target at helm-chart-2.4.1, which is still within the vulnerable range.

The ClusterSecretStore `vault-backend` bridges Vault (`secrets.mctl.ai`) to all tenant namespaces. ExternalSecret manifests are stored under `platform-gitops/argo-workflows/secrets/` and are reconciled by the ESO controller, which runs with cluster-scoped privileges. Because of this elevated trust, a confused-deputy exploit allows a low-privileged tenant user to have the controller mint long-lived Service Account tokens on their behalf, bypassing least-privilege.

No CRD schema changes exist between the current deployed version and v2.5.0. The upgrade path is therefore a pure image/chart bump.

## Proposed solution

Bump the ESO Helm chart to the release that packages ESO v2.5.0 in the platform GitOps repository. The single change is the chart version (and the resulting image tag) in the ESO Helm values or `Application` manifest under `platform-gitops/apps/` (or the equivalent services path for the ESO deployment). ArgoCD detects the diff on the next sync cycle and performs a rolling update of the ESO controller pod.

Key points:

1. **Version target:** ESO v2.5.0 / corresponding Helm chart release. This is the first release that patches CVE-2026-42876 and supersedes the v2.4.1 target set by `eso-cross-namespace-bypass-patch`.
2. **No CRD migrations required:** v2.5.0 ships no CRD schema changes; existing ExternalSecret and ClusterSecretStore objects remain valid.
3. **Liveness probe:** v2.5.0 adds a `/healthz` endpoint on the controller. The Helm values should enable `livenessProbe` pointing at `/healthz` to improve controller observability. This is a low-risk configuration addition included in the same commit.
4. **GitOps discipline:** the change is committed to `platform-gitops/` (the ArgoCD-watched path). No out-of-band `kubectl` operations are used.
5. **Consistency with related proposals:** `eso-dns-exfil-patch` targeted v2.2.1+; v2.5.0 satisfies that constraint. The version target of `eso-cross-namespace-bypass-patch` (v2.4.1) is rendered moot — v2.5.0 is strictly newer and fixes all three known ESO CVEs present in the proposals backlog.

## Alternatives

### A. Stay at v2.4.1 (target of eso-cross-namespace-bypass-patch)
v2.4.1 closes the cross-namespace bypass but does NOT fix CVE-2026-42876. A tenant could still exploit the confused-deputy vector. Rejected: leaves a known high-impact privilege-escalation open.

### B. Apply an admission webhook policy (e.g., Kyverno/OPA) to block malicious ExternalSecret shapes
A policy could reject ExternalSecret manifests that reference Service Account token types. This is a compensating control, not a fix. It adds policy complexity, may break legitimate use cases, and does not address the root defect in the controller. Rejected as a standalone solution; may be considered as defence-in-depth later.

### C. Upgrade directly to the next minor/major beyond v2.5.0
No higher stable release is available at the time of writing that has been validated for the platform. Jumping to an unvalidated release introduces unknown risk. Rejected: minimum viable fix version (v2.5.0) is the appropriate target.

## Platform impact

### Migrations
None. ESO v2.5.0 introduces no CRD schema changes. No `kubectl` migration commands are needed before or after the Helm upgrade.

### Backward compatibility
Existing ExternalSecret and ClusterSecretStore manifests in `platform-gitops/argo-workflows/secrets/` are fully compatible with v2.5.0. The `vault-backend` ClusterSecretStore configuration requires no changes.

### Resource impact (labs tenant)
ESO v2.5.0 does not increase the controller's baseline memory or CPU requirements compared to v2.4.x. The liveness probe addition adds negligible overhead (a single HTTP handler on an existing port). No increase in `labs` namespace resource consumption is expected. This proposal is therefore not flagged as risky for `labs`. However, the upgrade should be validated in a staging pass before the `labs` namespace is affected.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| ESO controller fails to start after image bump | Low | ArgoCD sync-failure alert fires; rollback via git revert restores previous chart version within one sync cycle. |
| A subset of ExternalSecret objects fails to reconcile post-upgrade | Low | Pre-upgrade: snapshot list of all ExternalSecret `.status.conditions`. Post-upgrade: automated check confirms all conditions return to `Ready=True` within 5 minutes. |
| Liveness probe misconfiguration causes controller CrashLoopBackOff | Low | Probe is only enabled if the `/healthz` path responds; set `initialDelaySeconds` conservatively (30 s). Rollback path identical to above. |
| labs memory limit breach | Negligible | No new sidecar or init container is introduced. Memory delta is expected to be zero. |
