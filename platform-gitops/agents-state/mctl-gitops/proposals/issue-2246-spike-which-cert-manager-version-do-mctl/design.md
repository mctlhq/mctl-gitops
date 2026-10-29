# Design: issue-2246-spike-which-cert-manager-version-do-mctl

## Current state

### Where cert-manager comes from

- mctl has exactly one cluster defined in code: `infrastructure/k3s-preview/`.
  `infrastructure/k3s-prod/README.md` is a TODO with no Terraform.
- cert-manager is not an ArgoCD-managed tenant service. Nothing under
  `platform-gitops/services/` or `platform-gitops/bootstrap/` deploys it.
  Instead, the `kube-hetzner/kube-hetzner/hcloud` module (version `2.19.1`)
  installs it as a k3s `HelmChart` in `kube-system`. The relevant comment is in
  `infrastructure/k3s-preview/kube.tf`: "Enabled by default
  (enable_cert_manager = true)".
- `infrastructure/k3s-preview/kube.tf`, in the `locals` block:
  - `traefik_version = "42.0.0"` and `cert_manager_version = "v1.20.3"`.
  - The comment explains that the module's default is an unpinned chart
    (`"*"`), which resolves to the newest chart whenever helm-controller
    re-runs the install job. The pin was "Pinned to the charts running on
    2026-10-22 ... Bump them here, deliberately, in their own change."
  - `local.cert_manager_version` is one element of
    `local.base_kustomization_inputs = sha1(jsonencode([...]))`. Changing it
    therefore replaces the module's `terraform_data.kustomization`, which
    re-runs `kubectl apply -k`. Because that hash also feeds
    `extra-manifests/kured.yaml.tpl` and `system-upgrade-controller.yaml.tpl`,
    those user-layer manifests re-apply after the base layer.
  - The module call passes `cert_manager_version = local.cert_manager_version`.
    The comment above it says to bump the local, "never the argument line here".
- `infrastructure/k3s-preview/extra-manifests/cert-manager-helmchartconfig.yaml.tpl`
  is a `HelmChartConfig` named `cert-manager`. It sets requests and limits for
  the controller, cainjector and webhook, and pins no version. ClusterIssuers
  live in `letsencrypt-prod.yaml.tpl`, `letsencrypt-staging.yaml.tpl` and
  `letsencrypt-http01.yaml.tpl`.
- Rollout path: `.github/workflows/terraform.yml` runs `plan` on every push to
  `main` touching `infrastructure/k3s-preview/**`. `apply` runs only on
  `workflow_dispatch` with `apply: true`, behind a reviewer on the `k3s-apply`
  environment, and refuses a plan that differs from the published one.
  `infrastructure/k3s-preview/README.md` notes that kustomization
  `terraform_data` replacements are permitted without `allow_reprovision`.
  Merging applies nothing.

### What v1.20.5 changes (cert-manager release notes, 2026-10-28)

- It removes trust in the compromised eMudhra CA.
- Its Debian 13 base images drop "emSign ECC Root CA - G3" and
  "AAA Certificate Services".
- Go 1.26.10 makes `crypto/x509` reject chains through the compromised
  intermediates (CVE-2026-111943).
- `golang.org/x/net` v0.60.0 fixes HTTP/2 CVE-2026-78669, -78659, -78660,
  -78663 and -97032, which were reachable in v1.20.4. v0.62.0 fixes
  CVE-2026-78661 and -97045.
- `x/crypto` v0.57.0 fixes CVE-2026-56855 and -78662; `go-jose/v4` v4.1.6
  fixes CVE-2026-116587; the OTLP exporters move to v1.45.0.
- Only source builds are affected by a breaking-type change: `go.mod` now
  requires Go 1.26. Released binaries keep the v1.20.4 GODEBUG defaults.
- The release notes list no CRD or values changes.

So the pinned v1.20.3 contains neither the eMudhra removal nor the HTTP/2
fixes. The issue's "do not manufacture an upgrade" branch does not apply,
unless the live cluster turns out to differ from the pin (see Open questions).

### Related proposals

- `platform-gitops/agents-state/mctl-gitops/proposals/cert-manager-dns-dos-patch/`
  targets v1.20.2. It is obsolete, because the pin is already v1.20.3.
- `.../cert-manager-acme-rbac-bypass/` says CVE-2026-62290 is fixed in 1.20.3
  and claims an unverified "1.21.2" fleet observation.

### Deployed state checked

- `infrastructure/k3s-preview/kube.tf` (clone): `cert_manager_version = "v1.20.3"`,
  commented as running on 2026-10-22. The clone has a single squashed commit, so
  git history could not show when the pin last changed.
- `mcp__mctl__mctl_list_services(team=admins)`: returned 8 tenant services
  (mctl-agents-worker*, mctl-design, mctl-docs, mctl-support, mctl-web, umami),
  `complete: true`. cert-manager is not among them, which is expected: it lives
  in `kube-system`, outside any tenant. This tool cannot see the cert-manager
  version.
- `$MCTL_GITOPS_ROOT/services` and `tenants`: these hold tenant services only.
  No cert-manager entry exists there, and none was expected.
- Live HelmChart `kube-system/cert-manager` `.spec.version` and the controller
  image tags: NOT OBSERVED. No read-only tool in this run reaches
  kube-system. This is a gap, not evidence of absence.
- Repo grep for `trust-manager`, `emudhra` and `emsign` outside agents-state:
  no matches. No trust-manager is deployed from this repo.

## Proposed solution

This is a single, deliberate, patch-level version bump. The `kube.tf` comment
asks for exactly this.

1. Re-observe the live state, as the issue's boundary requires. Before merging,
   an operator with cluster access records the following in the PR
   description:
   - `kubectl -n kube-system get helmchart cert-manager -o jsonpath='{.spec.version}'`
   - the images of the `cert-manager`, `cert-manager-cainjector` and
     `cert-manager-webhook` Deployments
   - `kubectl get certificates -A` with its Ready count

   Then act on the live version:
   - Live is v1.20.3 (expected): proceed.
   - Live is v1.20.5 or later, or a newer line carrying the same fixes: do not
     downgrade. Change the pin to the live value instead, or, if pin and live
     already match a fixed version, close #2246 with the audit.
2. In `infrastructure/k3s-preview/kube.tf`, change only
   `cert_manager_version = "v1.20.3"` to `"v1.20.5"` in the `locals` block, and
   append one comment line, for example: "v1.20.5 (2026-10-28): drops eMudhra
   CA trust, fixes reachable x/net HTTP/2 CVEs (#2246)". Leave the module
   argument line untouched. `base_kustomization_inputs` already covers the
   local.
3. Review the `terraform.yml` plan. Expect a replacement of
   `module.kube-hetzner.terraform_data.kustomization`, plus the user-layer
   kured and system-upgrade-controller manifests re-rendering through
   `base_kustomization_inputs`. Expect nothing else. Any server, network,
   `hcloud_ssh_key` or node-provisioner change blocks the merge.
4. Apply with `workflow_dispatch apply: true` and approve on `k3s-apply`.
   helm-controller re-runs the `helm-install-cert-manager` job against chart
   `v1.20.5`. The `HelmChartConfig` resource values are merged unchanged.
5. Audit and close: post the post-apply versions, the Certificate Ready count,
   ClusterIssuer status and a summary of the v1.20.5 trust changes on #2246.
   Mark `cert-manager-dns-dos-patch` as superseded.

The pin approach is chosen because it is the established, reviewed mechanism
for cluster add-ons in this repo. Updating the local rather than the argument
keeps the kured/system-upgrade-controller re-apply coupling intact.

## Alternatives

- **Do nothing and wait for the next k3s upgrade.** Rejected. The chart is
  pinned, so no k3s upgrade moves it. Before the pin, it would have jumped to an
  unreviewed `*`.
- **Unpin (`"*"`), or jump to the newest 1.21.x.** Rejected. That is the
  uncontrolled upgrade the 2026-10-22 pin was added to stop, and a minor-line
  jump brings CRD and behaviour changes that this urgent security patch should
  not carry. A 1.21 move can be its own change.
- **Move cert-manager to an ArgoCD Application in `platform-gitops/`.**
  Rejected for this issue. It is a larger re-platforming with ownership
  overlap: the k3s HelmChart would also need disabling via
  `enable_cert_manager = false`. Not needed to ship the fix.

## Platform impact

- **Migrations / compatibility:** none expected. It is a patch release with no
  CRD or values changes in the release notes. Existing Certificates, Secrets and
  ClusterIssuers are untouched.
- **Resource impact:** none. The `HelmChartConfig` requests and limits are
  unchanged. Debian 13 images may differ slightly in size, which only affects
  the pull.
- **Behaviour change:** cert-manager will refuse outbound TLS chains through
  eMudhra/emSign roots or the compromised intermediates. ACME talks to Let's
  Encrypt, which does not chain to those roots, so issuance is unaffected. A
  user-configured issuer endpoint chaining to eMudhra would break, and that is
  intended.
- **Risks and mitigations:**
  - Brief webhook unavailability during the rollout may reject cert-manager
    resource writes. Mitigation: apply off-peak; ArgoCD retries syncs.
  - The live version may differ from the pin. Mitigation: step 1
    re-observation, with the no-downgrade rule.
  - The kustomization re-apply also re-applies the module's base kured and
    system-upgrade-controller manifests. Mitigation: this is the designed path,
    and the user-layer templates re-apply after them, as in prior bumps
    (#2035 history in the `kube.tf` comment).
- **Rollback:** revert the one-line change to `"v1.20.3"`, then plan and apply
  through the same workflow.

## Open questions

- The live cert-manager version could not be observed from this run. See
  "Deployed state checked" above.
- The "1.21.2" claim in `cert-manager-acme-rbac-bypass` is unverified and
  conflicts with the pin.
- Whether kube-hetzner 2.19.1 sets `crds.enabled` / `installCRDs`. Verify it in
  the helm-install job log.
- A broader trust-store audit of node OS CA bundles and of workload images
  outside cert-manager is out of scope. Should it become a separate spike?
