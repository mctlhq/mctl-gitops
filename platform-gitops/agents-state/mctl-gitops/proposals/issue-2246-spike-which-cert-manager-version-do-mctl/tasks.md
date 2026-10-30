# Tasks: issue-2246-spike-which-cert-manager-version-do-mctl

- [ ] 1. Re-observe live cert-manager state with read-only access: HelmChart `.spec.version`, controller/cainjector/webhook image tags, Certificate Ready count and ClusterIssuer status. Record unavailable facts as `unknown (not observed)`. — DoD: live/pinned version matrix is in the PR or spike report.
- [ ] 2. Apply the no-downgrade rule. If live is already v1.20.5+ or a newer line carrying the same fixes, do not create a v1.20.5 downgrade. Either prepare a pin-alignment change to the observed live version or conclude no change is required. — DoD: chosen branch is explicit and evidence-backed.
- [ ] 3. If v1.20.5 is warranted, change only `local.cert_manager_version = "v1.20.3"` to `"v1.20.5"` in `infrastructure/k3s-preview/kube.tf` and add a one-line security rationale comment. Do not touch the module argument, ClusterIssuers, CRDs or `cert-manager-helmchartconfig.yaml.tpl`. — DoD: one-file PR, `terraform fmt` clean.
- [ ] 4. Review the PR's Terraform plan. — DoD: expected kustomization/user-manifest re-rendering only; any server, network, SSH-key or node-provisioner replacement blocks the PR.
- [ ] 5. Write the production handoff in the PR/issue: observed and pinned versions, security rationale, plan summary, post-apply verification commands/checks, and rollback steps. Mark the obsolete v1.20.2 proposal as superseded once the baseline is confirmed. — DoD: handoff is complete enough for a separate operator to execute safely.
- [ ] 6. STOP before production. Do not dispatch `terraform.yml` with `apply: true`, do not approve the `k3s-apply` environment, and do not mutate the live cluster. — DoD: the DevLoop ends with audit + PR/plan evidence only.

## Tests

- [ ] T1. `terraform fmt` passes for the changed file.
- [ ] T2. The PR plan contains no server, network, SSH-key or node-provisioner replacement.
- [ ] T3. The diff touches only `infrastructure/k3s-preview/kube.tf` when an upgrade PR is required.
- [ ] T4. The handoff lists post-apply verification for HelmChart version, cert-manager pod images/availability, ClusterIssuer Ready status, Certificate Ready count and a server-side dry-run webhook smoke test.
- [ ] T5. No workflow dispatch/apply event is performed by this proposal.

## Production handoff (outside this spike)

After the PR is merged and an operator explicitly approves production deployment, the normal `terraform.yml` + `k3s-apply` gate may be used. Post-apply verification should confirm the intended HelmChart/image version, Ready issuers/certificates and webhook admission. If that later rollout fails, revert the pin and use the same normal gated apply path. None of these live actions are part of this DevLoop.