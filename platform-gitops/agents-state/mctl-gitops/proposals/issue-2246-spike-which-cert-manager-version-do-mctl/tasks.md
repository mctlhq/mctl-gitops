# Tasks: issue-2246-spike-which-cert-manager-version-do-mctl

- [ ] 1. Re-observe the live cert-manager version. Read the
  `kube-system/cert-manager` HelmChart `.spec.version`, the images of the
  controller, cainjector and webhook Deployments, and the Ready count from
  `kubectl get certificates -A`. Record all of it in the PR description. — DoD:
  live version recorded. If it is >= v1.20.5, or a newer line with the same
  fixes, do not downgrade: skip to task 5 and align the pin or close with
  evidence.
- [ ] 2. (depends on 1) In `infrastructure/k3s-preview/kube.tf`, change
  `cert_manager_version = "v1.20.3"` to `"v1.20.5"` in the `locals` block, and
  add a one-line comment citing v1.20.5, the eMudhra trust removal, the x/net
  HTTP/2 CVEs and #2246. Do not touch the module argument line or
  `cert-manager-helmchartconfig.yaml.tpl`. — DoD: a one-file PR on a feature
  branch with `terraform fmt`-clean output.
- [ ] 3. (depends on 2) Review the `terraform.yml` plan on the merged commit.
  — DoD: the plan replaces only `terraform_data.kustomization` and re-renders
  the kured and system-upgrade-controller user manifests. It has no
  server, network, SSH-key or node-provisioner changes, and needs neither
  `allow_destroy` nor `allow_reprovision`.
- [ ] 4. (depends on 3) Dispatch `terraform.yml` with `apply: true` and
  approve on `k3s-apply`. — DoD: the HelmChart is at `v1.20.5`, all three
  Deployments run `v1.20.5` images and are Available, and the
  `helm-install-cert-manager` job succeeded.
- [ ] 5. (depends on 4, or on 1 for the no-upgrade branch) Post the trust and
  version audit on #2246:
  - pinned and live versions before and after
  - the Certificate Ready count before and after
  - ClusterIssuer Ready status
  - a summary of the v1.20.5 trust changes (eMudhra removed, emSign ECC
    Root CA - G3 and AAA Certificate Services dropped, CVE-2026-111943
    rejection)

  Mark `cert-manager-dns-dos-patch` as superseded. — DoD: the comment is posted
  and the issue is closed.

## Tests

- [ ] T1. Before apply, the `terraform.yml` plan output matches task 3's
  expected resource set exactly.
- [ ] T2. After apply,
  `kubectl -n kube-system get helmchart cert-manager -o jsonpath='{.spec.version}'`
  returns `v1.20.5`. All cert-manager pods are Running with 0 restarts after
  5 minutes.
- [ ] T3. `kubectl get clusterissuer` shows `letsencrypt-prod`,
  `letsencrypt-staging` and `letsencrypt-http01` Ready=True.
  `kubectl get certificates -A` shows the same Ready count as before.
- [ ] T4. Webhook smoke test: a server-side dry-run create of a Certificate
  against `letsencrypt-staging` (`kubectl apply --dry-run=server`) is admitted
  without a webhook error.
- [ ] T5. Resources: the controller, cainjector and webhook pods carry the
  requests and limits from `cert-manager-helmchartconfig.yaml.tpl`.

## Rollback

Revert the PR, setting `cert_manager_version` back to `"v1.20.3"`. Let the
`terraform.yml` plan show the same kustomization-only replacement, then
dispatch `apply: true` and approve on `k3s-apply`. helm-controller then
reinstalls chart v1.20.3. A same-line patch downgrade has no CRD changes.
Existing Certificates and Secrets are not touched, so serving TLS is
unaffected during either direction.
