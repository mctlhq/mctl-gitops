# Design: issue-2246-spike-which-cert-manager-version-do-mctl

## Current state

mctl has one cluster defined in code under `infrastructure/k3s-preview/`; `infrastructure/k3s-prod/` is still a TODO. cert-manager is installed by the kube-hetzner module as a k3s `HelmChart` in `kube-system`, not as a tenant ArgoCD Application.

`infrastructure/k3s-preview/kube.tf` pins `cert_manager_version = "v1.20.3"`. The adjacent comment says the pin reflects charts running on 2026-10-22 and should be deliberately bumped in its own change. `local.cert_manager_version` already participates in `local.base_kustomization_inputs`, so changing the pin causes the expected kustomization re-render path without editing the module argument.

v1.20.5 removes trust in the compromised eMudhra CA and carries dependency security fixes including reachable HTTP/2 fixes. The release notes do not describe a CRD or values migration for this patch-level move.

The investigator could not observe `kube-system`, so the live HelmChart version and image tags remain unknown. A separate older proposal targets v1.20.2 and is stale if the v1.20.3 pin is accurate. Another proposal contains an unverified 1.21.2 observation, so a live readback is mandatory before any pin change.

## Proposed solution

Treat this as **audit + PR preparation**, not as deployment authorization.

1. **Re-observe live state.** With read-only cluster access, capture the `kube-system/cert-manager` HelmChart version, controller/cainjector/webhook image tags, Certificate Ready count and ClusterIssuer status. If that access is unavailable, record the gap explicitly and do not invent a live version.
2. **Choose the no-downgrade branch.** If live is already v1.20.5+ or a newer line containing the same fixes, do not prepare a v1.20.5 downgrade. Either align the pin to the observed live version in a separate reviewable change or report that no change is needed.
3. **Prepare the one-file patch when warranted.** If live evidence is compatible with the v1.20.3 baseline, change only `local.cert_manager_version` to `"v1.20.5"` and add a short comment citing #2246, the eMudhra trust removal and the HTTP/2 fixes. Leave the module argument and HelmChartConfig untouched.
4. **Use the PR plan as the safety gate.** The Terraform plan may show the expected kustomization/user-manifest re-rendering, but any server, network, SSH-key or node-provisioner replacement blocks the change.
5. **Stop and hand off.** The spike ends with the PR + plan evidence + live-version audit + post-apply verification checklist + rollback instructions. It does **not** dispatch `terraform.yml` with `apply: true` and does not approve `k3s-apply`.
6. **Production apply is a separate operator action.** After the PR is merged and reviewed through the normal gate, an operator may choose to dispatch/apply. That action is outside this proposal and requires its own explicit production approval.

## Why this boundary

The spike answers whether the upgrade is warranted and prepares the safest minimal change. Approval of an investigation should not implicitly authorize a live cluster mutation. The existing `k3s-apply` reviewer gate remains the authoritative production boundary.

## Alternatives

- **Apply as part of the spike.** Rejected: it conflates research/implementation approval with production deployment approval.
- **Do nothing until the next k3s upgrade.** Rejected if v1.20.3 is live, because the chart is pinned and will not move automatically.
- **Unpin to `*` or jump to 1.21.x.** Rejected: this is an urgent patch-level security change, not a minor-line migration.
- **Move cert-manager to ArgoCD.** Rejected as unrelated re-platforming.

## Platform impact

- The proposal may produce a one-file Terraform PR; no live resource is changed by the DevLoop.
- No CRD, ClusterIssuer or HelmChartConfig change is expected.
- The PR plan is the main safety evidence before any later production action.
- Rollback for a later operator-applied rollout is to revert the pin change and re-run the same normal gated apply path; that rollback is documented here but not executed by this spike.

## Open questions

- What is the actual live HelmChart/image version?
- Does the unverified 1.21.2 observation reflect current reality?
- Does the rendered/plan delta stay limited to the expected kustomization path?
- Once the baseline is confirmed, should the older v1.20.2 proposal be marked superseded?