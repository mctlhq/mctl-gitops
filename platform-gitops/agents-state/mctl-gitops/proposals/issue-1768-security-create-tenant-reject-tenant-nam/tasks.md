# Tasks: issue-1768-security-create-tenant-reject-tenant-nam

- [ ] 1. Add ClusterRole and ClusterRoleBinding `argo-workflow-namespace-read`
  (`namespaces`: `get`, `list`) for `argo-workflows/argo-workflow-sa` in
  `platform-gitops/argo-workflows/config/sa-and-rbac.yaml`, with a comment explaining why.
  - DoD: manifests validate in `validate-manifests.yml`, and no other verbs or resources are granted.
- [ ] 2. Write the shared `# BEGIN tenant-ns-guard` / `# END tenant-ns-guard` sh block
  (`tenant_name_reserved`, `tenant_ns_owner_state`) as specified in design.md section 1.
  - DoD: the block is POSIX sh. A lookup error returns non-zero and is never reported as `absent`.
- [ ] 3. In `wft-create-tenant.yaml` (depends on 2):
  - replace the reserved-name loop in `validate-tenant-name` with the block;
  - add the template `check-namespace-collision` (`alpine/k8s:1.33.12`, env-bound
    `tenant_name`/`reprovision`, format re-check, denylist, and a check of `N` and
    `N-preview` that rejects `foreign` or a lookup error);
  - add DAG task `check-namespace` alongside `validate`;
  - make `create-vault-policy` depend on `[validate, check-namespace]`;
  - update the template description annotation.
  - DoD: nothing writes to Vault or git unless both checks pass.
- [ ] 4. In `wft-delete-tenant-safe.yaml` (depends on 2):
  - `validate-tenant-exists`: switch to `alpine/k8s:1.33.12`, bind `tenant_name` through
    `env`, check the format, keep the protected list (including `admins`), and add the
    block plus an ownership check of `N` and `N-preview`;
  - `delete-k8s-resources`: switch to `alpine/k8s:1.33.12` (drop the curl download of
    kubectl), bind `tenant_name` through `env`, and re-check ownership right before each
    `kubectl delete ns`;
  - make the wait loop fail on lookup errors instead of counting them as "gone".
  - DoD: a `foreign` namespace or a lookup error fails the workflow before any delete;
    an `absent` namespace is still skipped.
- [ ] 5. Add the same ownership guard before `kubectl delete ns` in the legacy
  `wft-delete-tenant.yaml` (depends on 2).
  - DoD: the legacy path cannot delete an unlabelled namespace.
- [ ] 6. Update `scripts/validate-shell-param-interpolation.py` BASELINE: remove any
  entries for the template/parameter pairs fixed in tasks 3-5.
  - DoD: the script passes, and the baseline shrank or stayed the same.
- [ ] 7. Add `scripts/validate-tenant-ns-guard.py` with `--selftest` (depends on 3-5).
  It must:
  - check that the block is identical across the three templates;
  - check the reject and accept name sets (accept includes every
    `platform-gitops/tenants/*` directory);
  - drive `tenant_ns_owner_state` against a fake `kubectl` covering absent, owned,
    foreign-unlabelled, foreign-other-tenant and error;
  - run the bootstrap-namespace freshness check.
  Wire it into `.github/workflows/validate-manifests.yml` next to the other
  `validate-*.py` steps.
  - DoD: CI passes on the branch, and the selftest proves the checker fails on a
    weakened block.
- [ ] 8. Pre-merge cluster checks, recorded in the PR description:
  - `kubectl auth can-i {get,list,delete} namespaces --as=system:serviceaccount:argo-workflows:argo-workflow-sa`;
  - `kubectl get ns -l mctl.me/tenant --show-labels`, confirming every tenant in
    `platform-gitops/tenants/` has a labelled namespace.
  - DoD: results are pasted in the PR, and any unlabelled tenant namespace or missing
    `delete` right is called out (see Open questions).

## Tests

- [ ] T1. CI: `scripts/validate-tenant-ns-guard.py --selftest` and a plain run pass in
  `validate-manifests.yml`.
- [ ] T2. CI: `scripts/validate-shell-param-interpolation.py` passes.
- [ ] T3. CI: manifest validation and yamllint pass on the changed templates and RBAC.
- [ ] T4. Live, after merge and ArgoCD sync: run
  `argo submit -n argo-workflows --from clusterworkflowtemplate/create-tenant --entrypoint check-namespace-collision -p tenant_name=temporal`.
  - Expected: Failed, with an error naming namespace `temporal` without `mctl.me/tenant=temporal`.
- [ ] T5. Live: run the same command with `-p tenant_name=zz-ns-guard-probe` (no such namespace).
  - Expected: Succeeded. There are no side effects, because only the check template runs.
- [ ] T6. Live: run the same command with `-p tenant_name=labs -p reprovision=true`.
  - Expected: Succeeded (`owned`).
- [ ] T7. Live: run
  `argo submit -n argo-workflows --from clusterworkflowtemplate/delete-tenant-safe --entrypoint validate-tenant-exists -p tenant_name=temporal`.
  - Expected: Failed (reserved or foreign). Nothing is deleted, because only validate runs.
- [ ] T8. Record the T4-T7 workflow names and their outcomes in the PR.

## Rollback

- Revert the PR. ArgoCD restores the previous ClusterWorkflowTemplates and prunes the
  `argo-workflow-namespace-read` ClusterRole and ClusterRoleBinding. Nothing is migrated.
- If only the delete-path fail-closed behaviour blocks a legitimate deletion (for
  example, a tenant namespace missing its label), do not revert. Instead, sync
  `tenant-<name>` so the chart applies `mctl.me/tenant`, then re-run the deletion.
