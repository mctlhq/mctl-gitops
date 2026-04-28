# Design: helm-security-patch

## Current state
According to `context/architecture.md`, the platform uses Helm charts (base-service, openclaw,
custom), an ArgoCD ApplicationSet for App generation, and `helm-charts/base-service` as the
generic chart. The Helm binary lives in several places:
1. Inside the ArgoCD image (used to render Helm-based Applications).
2. In CI/CD pipelines (Argo Workflow steps, Backstage scaffolder).
3. Locally on platform engineers' machines (out of scope for this proposal — manual updates).

Current versions v4.0.0–v4.1.3 are exposed to GHSA-vmx8-mqv2-9gmg, GHSA-hr2v-4r36-88hr,
GHSA-q5jf-9vfq-h4h7.

## Proposed solution
Update Helm to v4.1.4 across all platform usage points.

**Step 1: ArgoCD**
ArgoCD bundles Helm as part of its official image. Determine which ArgoCD version contains
Helm v4.1.4 and update the ArgoCD image tag in `platform-gitops/apps/`. If the current
ArgoCD version has already shipped a patch with Helm v4.1.4 — updating the tag suffices. If
not — wait for the upstream ArgoCD patch or use a custom init-container with patched Helm
(undesirable).

**Step 2: Argo Workflow steps**
Workflow steps that invoke the `helm` CLI (e.g. build/package steps) must use an image with
Helm v4.1.4. Update the image references in the corresponding ClusterWorkflowTemplate in
`platform-gitops/argo-workflows/cluster-templates/`.

**Step 3: Backstage scaffolder templates**
If the scaffolder uses helm CLI in skeleton actions — update the image or pinned version in
`platform-gitops/backstage-templates/`.

All changes are captured as a git commit in mctl-gitops; ArgoCD applies via App-of-Apps.
ADR-0001 (App-of-Apps pattern) is preserved.

## Alternatives

### 1. Block chart extraction via OPA/Gatekeeper admission webhook
Introduce a policy that validates chart names before applying. Does not close the vulnerability
in Helm itself (extraction happens before admission), does not close the plugin vulnerabilities.
Dropped: incomplete coverage.

### 2. Disable Helm plugins at the configuration level
Disable plugin installation in CI and the ArgoCD environment. Partially reduces the risk of
GHSA-vmx8-mqv2-9gmg and GHSA-q5jf-9vfq-h4h7, but does not close path traversal in chart
extraction. Dropped: not a complete fix, plugins may be needed.

### 3. Update only ArgoCD, skip the CI images
Minimise scope — update Helm only in ArgoCD. Path traversal during chart extraction stays
possible in CI workflow steps. Dropped: incomplete attack-surface coverage.

## Platform impact

### Migration
No data migration. The patch release (v4.1.4) is declared as having no breaking changes.
Existing `values.yaml` files and chart structures remain unchanged.

### Backward compatibility
v4.1.4 is fully backward compatible with v4.1.x. All existing Helm charts (`base-service`
and custom ones) continue to render unchanged.

### Resource impact
Updating the Helm binary does not affect runtime CPU/memory consumption. ArgoCD and workflow
step images may change in size slightly. The `labs` tenant is not affected directly:
ArgoCD and Argo Workflows run in the `admins` tenant. Deploys into the `labs` tenant via
ArgoCD continue normally.

### Risks and mitigations
- **Risk:** The ArgoCD version deployed on the platform has not yet shipped a patch with
  Helm v4.1.4.
  **Mitigation:** Check the ArgoCD ↔ Helm compatibility matrix; if necessary, wait for the
  next ArgoCD patch release or use a temporary workaround with a custom image.
- **Risk:** Workflow steps use pinned images not managed via central values.
  **Mitigation:** Grep `cluster-templates/` for all Helm-related image references.
- **Risk:** Regression in Helm chart rendering after the upgrade.
  **Mitigation:** ArgoCD dry-run sync before applying; rollback available via git revert.
