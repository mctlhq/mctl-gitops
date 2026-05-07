# Tasks: cert-manager-dns-dos-patch

- [ ] 1. Identify current cert-manager chart version in both tenants — check
  `platform-gitops/services/admins/` and `platform-gitops/services/labs/` for the
  cert-manager Helm chart version currently pinned.
  DoD: current version is documented in the PR description; confirmed that both tenants are
  below v1.20.2.

- [ ] 2. Update Helm chart version to v1.20.2 in `labs` (depends on 1) — change the
  cert-manager chart version in `platform-gitops/services/labs/<cert-manager-svc>/` to
  v1.20.2 and open a PR.
  DoD: ArgoCD syncs the `labs` cert-manager Deployment to v1.20.2; controller restarts
  cleanly (no CrashLoopBackOff); ESO and ArgoCD logs show no cert-related errors.

- [ ] 3. Verify `labs` Certificate resources remain healthy (depends on 2) — after the
  controller restart, confirm all Certificate objects in the `labs` namespace are `Ready`
  and no renewal failures appear in cert-manager controller logs within 15 minutes.
  DoD: `kubectl get certificates -n labs` shows all resources in `Ready=True` state;
  cert-manager logs contain no `panic` or `Error` lines related to certificate processing.

- [ ] 4. Verify webhook YAML correctness in `labs` (depends on 2) — if
  `webhook.config` and `webhook.volumes` are both set in the `labs` Helm values, render
  the webhook configuration and confirm it is valid YAML.
  DoD: `helm template` output for the cert-manager chart parses without YAML errors;
  the webhook pod starts and passes its readiness probe.

- [ ] 5. Update Helm chart version to v1.20.2 in `admins` (depends on 3, 4) — change the
  cert-manager chart version in `platform-gitops/services/admins/<cert-manager-svc>/` to
  v1.20.2 and open a PR.
  DoD: ArgoCD syncs the `admins` cert-manager Deployment to v1.20.2; all Certificate
  resources in `admins` remain `Ready`; no renewal failures in logs within 15 minutes of
  rollout; GHSA-gx3x-vq4p-mhhv is confirmed closed for both tenants.

## Tests

- [ ] T1. Panic regression test — after upgrade to v1.20.2 in `labs`, simulate a malformed
  DNS response by temporarily pointing cert-manager's DNS resolver at a test server that
  returns a crafted truncated response. Confirm the cert-manager controller does not panic
  and continues processing other certificate requests. If a live DNS test environment is
  unavailable, verify the fix by confirming the cert-manager v1.20.2 changelog entry for
  GHSA-gx3x-vq4p-mhhv and the Go patch level (1.26.2).

- [ ] T2. Certificate continuity test — list all Certificate resources in both tenants
  before and after the upgrade; confirm that no certificate transitions from `Ready=True`
  to any non-Ready state as a result of the upgrade itself (as opposed to a legitimate
  renewal or expiry event).

- [ ] T3. Webhook YAML validity test — run `helm template cert-manager <chart> -f values.yaml`
  with `webhook.config` and `webhook.volumes` both populated; pipe through a YAML linter
  (e.g., `yq .`) and confirm zero parsing errors.

## Rollback

If the cert-manager upgrade causes controller instability or certificate sync failures:

1. Revert the Helm chart version change via `git revert` on the relevant commit in
   `platform-gitops/services/<tenant>/<cert-manager-svc>/`.
2. Merge and push the revert; ArgoCD reconciles the controller back to the previous image.
3. Verify the controller restarts cleanly and all Certificate resources return to `Ready`.
4. Investigate the failure (check controller logs for the specific panic or error) before
   re-attempting the upgrade.

Issued certificates stored as Kubernetes Secrets are not affected by rolling back the
controller version — they remain valid until their natural expiry.
