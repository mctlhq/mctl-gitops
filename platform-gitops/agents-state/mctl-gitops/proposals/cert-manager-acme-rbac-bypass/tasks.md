# Tasks: cert-manager-acme-rbac-bypass

- [ ] 1. Confirm cert-manager version pinned in both tenants — check
  `platform-gitops/services/admins/<cert-manager-svc>/` and
  `platform-gitops/services/labs/<cert-manager-svc>/`.
  DoD: documented in PR description whether each tenant is inside the vulnerable range
  (1.18.0-1.19.5, 1.20.0-1.20.2) or already at/above the fixed versions (1.19.6, 1.20.3, or
  1.21.x+).

- [ ] 2. Bump version in any tenant found vulnerable in task 1 (depends on 1) — apply the
  same labs-first rolling-update sequence as `cert-manager-dns-dos-patch`.
  DoD: both tenants confirmed at a fixed or later version; Certificate resources remain
  `Ready` post-bump.

- [ ] 3. Audit for any direct user-facing Challenge/Order creation in existing templates
  (depends on 1) — search `platform-gitops/argo-workflows/service-templates/`,
  `backstage-templates/`, and `platform-gitops/services/*/*` for any manifest that creates
  `acme.cert-manager.io` Challenge/Order objects directly.
  DoD: confirmed no legitimate workflow depends on direct Challenge/Order creation, or any
  found dependency is documented and addressed before task 4.

- [ ] 4. Draft the RBAC restriction (depends on 3) — either enable the cert-manager Helm
  chart's built-in option to disable `edit`/`view` ClusterRole aggregation for ACME
  resources (preferred if available on the pinned chart version), or add an explicit
  ClusterRole patch removing `create`/`update` verbs on `challenges.acme.cert-manager.io`
  and `orders.acme.cert-manager.io` from the aggregated role.
  DoD: patch manifest committed under the relevant
  `platform-gitops/services/<tenant>/<cert-manager-svc>/` or a shared cert-manager overlay;
  `helm template` renders without errors.

- [ ] 5. Apply the RBAC patch to `labs` first, verify, then `admins` (depends on 4).
  DoD: `kubectl auth can-i create challenges.acme.cert-manager.io --as=<test-edit-user> -n
  <test-namespace>` returns `no` in both tenants; existing Certificate issuance in a
  smoke-test namespace still succeeds end-to-end.

## Tests
- [ ] T1. Version confirmation test — `kubectl get deployment cert-manager -o
  jsonpath='{.spec.template.spec.containers[0].image}'` in both tenants reports a version
  at/above the fixed release.
- [ ] T2. RBAC negative test — as a user holding only the namespace `edit` role, attempt
  `kubectl create -f <test-challenge>.yaml`; confirm it is denied with a Forbidden error, in
  both `admins` and `labs`.
- [ ] T3. Certificate issuance regression test — create a test Certificate referencing an
  existing Issuer in a non-production namespace; confirm cert-manager's own controller (not
  the test user) creates the resulting Order/Challenge and the Certificate reaches
  `Ready=True`.
- [ ] T4. Visibility regression test — confirm the test `edit` user can still
  `kubectl get`/`describe` existing Challenge/Order objects for debugging (i.e., only write
  verbs were removed, not read verbs).

## Rollback
If the RBAC patch blocks a legitimate workflow discovered after rollout:
1. Revert the ClusterRole patch commit via `git revert` in the relevant
   `platform-gitops/services/<tenant>/<cert-manager-svc>/` path (or re-enable chart-level
   aggregation if that route was used).
2. Push the revert; ArgoCD reconciles the ClusterRole back to its previous (broader) state.
3. Re-run T3 to confirm certificate issuance is unaffected by the rollback.
4. Investigate the specific workflow that depended on direct Challenge/Order creation and
   design a scoped exception (e.g. a dedicated ServiceAccount with the narrow permission)
   before re-attempting the restriction.

If the version bump (task 2) caused instability, follow the same rollback procedure
documented in `cert-manager-dns-dos-patch/tasks.md` (git revert the chart version pin).
