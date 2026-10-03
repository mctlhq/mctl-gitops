# Tasks: issue-1431-fix-tenants-move-per-tenant-argo-cd-rbac

All of tasks 1-6 must land in ONE commit/PR: `argo-cd.configs.rbac.create: false`
without the new template would leave `argocd-rbac-cm` unmanaged.

- [ ] 1. Capture the pre-change baseline. Run `helm template test
  platform-gitops/argocd -f platform-gitops/argocd/values.yaml`, extract the
  `argocd-rbac-cm` `data["policy.csv"]`, normalize (drop comments and blank lines,
  sort) and save it as `tests/fixtures/argocd-rbac-policy.baseline.csv`.
  DoD: the baseline file is committed and contains the 5 tenant blocks plus the base
  policy; it is the reference every later task diffs against.

- [ ] 2. Add the per-tenant fragments
  `platform-gitops/argocd/rbac/tenants/{labs,ovk,karabu}.csv`, each holding the
  canonical header comment plus the six lines copied verbatim from
  `platform-gitops/argocd/values.yaml` (lines 205-211, 227-233, 235-241).
  DoD: `diff <(cat fragments) <(sed -n '205,241p' values.yaml)` accounts for every
  migrated line; no fragment is created for the orphans `yyy` / `xxxx`.

- [ ] 3. Add `platform-gitops/argocd/templates/argocd-rbac-cm.yaml` that renders
  `argocd-rbac-cm` from `index .Values "argo-cd" "configs" "rbac"` plus
  `.Files.Glob "rbac/tenants/*.csv"` (sorted, concatenated into the single
  `policy.csv` key), with the in-file comment explaining why the subchart no longer
  owns the ConfigMap (depends on 2).
  The template must carry over every `configs.rbac` key except `create` and
  `annotations`, as the subchart does, and must not hard-code
  `policy.default`/`scopes` (reviewer amendment 2026-09-27).
  DoD: `helm template test platform-gitops/argocd -f
  platform-gitops/argocd/values.yaml` emits exactly one `argocd-rbac-cm`, and
  `helm lint platform-gitops/argocd` passes. A scratch render with an extra
  `configs.rbac` key (e.g. `policy.matchMode: glob`) shows that key in the
  ConfigMap.

- [ ] 4. In `platform-gitops/argocd/values.yaml`: set `argo-cd.configs.rbac.create:
  false` with a comment pointing at `rbac/tenants/`, delete the five tenant blocks
  (lines 205-241) and keep `policy.default`, `scopes`, the base policy and the SOC F4
  "no tenant exec" comment (depends on 3).
  DoD: `grep -c 'role:team-' platform-gitops/argocd/values.yaml` is 0; the normalized
  render differs from task 1's baseline only by the 12 `yyy` / `xxxx` lines.

- [ ] 5. Rework `platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml`:
  replace the "Append ArgoCD RBAC entries" `awk` section with a `cat >` of
  `platform-gitops/argocd/rbac/tenants/${TENANT}.csv` guarded by `[ -f ... ]`,
  remove `platform-gitops/argocd/values.yaml` from the `git add` list, add the
  fragment path, and update the commit message body (depends on 4).
  DoD: the step's script contains no reference to `platform-gitops/argocd/values.yaml`;
  re-running the workflow for an existing tenant is still a no-op.

- [ ] 6. Rework `wft-delete-tenant.yaml` (lines 212-218) and
  `wft-delete-tenant-safe.yaml` (lines 555-561): replace the four `sed -i` calls with
  a `git rm` of the fragment inside the existing `apply_changes()` function, keeping
  the `CHANGED=true` bookkeeping, and update the commit-message lines (depends on 5).
  DoD: neither template references `platform-gitops/argocd/values.yaml`; a delete run
  leaves no `# Tenant:` comment or blank-line squeeze anywhere.

- [ ] 7. Add `scripts/validate-tenant-workflow-shared-writes.py` with `--selftest`,
  following the style of `scripts/validate-shell-param-interpolation.py`: every path
  written/staged/removed by the three tenant workflow templates must contain the
  tenant name or sit in a commented `WAIVERS` table (initially the three
  `platform-gitops/infra-components/data/cnpg/shared/*.yaml` files, with the
  out-of-scope note from the issue) (depends on 6).
  DoD: `--selftest` proves the detector fires on the restored `awk` insertion and
  stays silent on the post-change templates; the real run is green.

- [ ] 8. Add `scripts/validate-argocd-tenant-rbac.py` with `--selftest`: 1:1 between
  `platform-gitops/tenants/*/` and `platform-gitops/argocd/rbac/tenants/*.csv`
  (`admins` exempt via a commented `EXEMPT_TENANTS` set; a fragment for an exempt
  tenant is itself a failure; reviewer amendment 2026-09-27), each
  fragment byte-equal to the canonical six lines for its tenant, and no `role:team-`
  line left in `platform-gitops/argocd/values.yaml` (depends on 4).
  DoD: `--selftest` fires on each of: an added `exec` rule, a widened `*` object glob,
  a tenant dir with no fragment, a fragment with no tenant dir, and an
  `admins.csv` fragment. It stays silent on the real tree, where `admins` has no
  fragment.

- [ ] 9. Wire both scripts into `.github/workflows/validate-manifests.yml` as two
  steps next to the existing interpolation checks, `--selftest` first, each with the
  short "why this gate exists" comment the job's other steps carry (depends on 7, 8).
  DoD: both steps run and pass in CI on the PR.

- [ ] 10. Update docs: `docs/soc2/access-review.md` step 4 (tenant `exec` review now
  reads `platform-gitops/argocd/rbac/tenants/` and is machine-checked by
  `validate-argocd-tenant-rbac.py`), and add the `rbac/tenants/` layout plus "add a
  tenant" note to `CLAUDE.md` / the argocd README if one covers RBAC.
  DoD: no doc still tells a reader that tenant RBAC lives in
  `platform-gitops/argocd/values.yaml`.

- [ ] 11. Before merge, grep `mctlhq/mctl-api` (and `mctl-portal`) for `role:team-`
  and `argocd/values.yaml` to confirm no out-of-repo reader parses the tenant blocks
  (open question in `requirements.md`).
  DoD: result recorded in the PR body; if a reader exists, this proposal is paused and
  the reader is migrated first.

## Tests

- [ ] T1. Rendered-policy equivalence: `tests/test_argocd_rbac_policy_render.py`
  renders `platform-gitops/argocd`, extracts and normalizes `policy.csv`, and asserts
  it equals `tests/fixtures/argocd-rbac-policy.baseline.csv` minus exactly the `yyy`
  and `xxxx` lines. Also asserts one `argocd-rbac-cm` document is present and that
  `policy.default` / `scopes` survived the move.
- [ ] T2. `scripts/validate-tenant-workflow-shared-writes.py --selftest` — the
  regression test the issue asks for: it must FAIL with the old `awk` insertion into
  `platform-gitops/argocd/values.yaml` put back.
- [ ] T3. `scripts/validate-argocd-tenant-rbac.py --selftest` — fires on `exec`, on a
  widened glob, on a missing fragment and on an orphan fragment.
- [ ] T4. Empty-glob render: `helm template` the chart with `rbac/tenants/` emptied
  (via a scratch copy) and assert a schema-valid `argocd-rbac-cm` containing only the
  base policy — covers the very first tenant-less state and a bad `.helmignore`.
- [ ] T5. Concurrency proof in a scratch clone: two branches off the same base commit,
  each adding a different `rbac/tenants/<t>.csv` and `tenants/<t>/`, then
  `git fetch` + `git rebase origin/main` + push on the second — must succeed with no
  conflict. The same script against the pre-change code must reproduce `CONFLICT
  (content): Merge conflict in platform-gitops/argocd/values.yaml`.
- [ ] T6. Post-merge live verification (after `argocd-self-managed` syncs): for each of
  `labs`, `ovk`, `karabu`, `argocd admin settings rbac can <t> get applications
  apps/<t>-*` → allowed for get/list/sync/override and `logs get`; `argocd admin
  settings rbac can <t> create exec apps/<t>-*` → denied; the same probe on another
  tenant's prefix → denied.
- [ ] T7. End-to-end: create a throwaway tenant (`mctl_create_tenant`), confirm the
  workflow succeeds, that the commit touches only per-tenant paths, and that the new
  group can see only its own apps; then delete it and confirm the fragment is gone and
  `values.yaml` is untouched.
- [ ] T8. Existing gates stay green: `helm lint platform-gitops/argocd`, the
  `helm template ... | kubeconform` step, and the raw-manifest kubeconform sweep over
  `platform-gitops/argo-workflows` (the reworked templates must still validate).

## Rollback

`argocd-rbac-cm` is the single point of failure, so roll back at the git level:

1. `git revert <merge commit>` on `main`. That restores
   `argo-cd.configs.rbac.create: true` (subchart owns the ConfigMap again) and the
   five tenant blocks in `platform-gitops/argocd/values.yaml` in one step, and removes
   the fragments, the template and the gates together — no intermediate state where
   `create: false` is live without the template.
2. **Before pushing the revert**, re-add by hand the six policy lines of any tenant
   created *after* the migration: its fragment is deleted by the revert and its block
   was never in `values.yaml`, so it would silently lose Argo CD access.
3. Wait for `argocd-self-managed` to sync (`prune: false`, `selfHeal: true`;
   `argocd app sync argocd-self-managed` to force it) and re-run the T6 probes.
4. If the UI is inaccessible in the meantime, break-glass is `argocd --core` against
   the cluster kubeconfig (documented in `platform-gitops/argocd/values.yaml` lines
   28-32); `kubectl -n argocd edit cm argocd-rbac-cm` restores policy immediately and
   `selfHeal` will overwrite it on the next sync, so the git revert is still required.
5. Tenant workflow rollback is implied by the same revert: `wft-create-tenant` and both
   delete templates return to editing `values.yaml`, so the conflict returns — accept
   it as the known pre-fix behaviour and serialize tenant operations until a fix
   re-lands. Note that Argo Workflows snapshots ClusterWorkflowTemplates at submit
   time, so allow ~3 min for ArgoCD to sync the reverted templates before submitting.
