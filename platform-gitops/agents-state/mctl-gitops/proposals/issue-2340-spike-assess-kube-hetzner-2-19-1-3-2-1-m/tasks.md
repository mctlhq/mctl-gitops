# Tasks: issue-2340-spike-assess-kube-hetzner-2-19-1-3-2-1-m

- [ ] 1. Re-read current `main` (`infrastructure/k3s-preview/kube.tf`, `.github/workflows/terraform.yml`, `.github/scripts/k3s-plan-guard.sh`) and record the source SHA. Fetch the pinned v3.2.1 `MIGRATION.md`, `docs/v2-to-v3-migration.md`, `variables.tf`, `versions.tf` and the 2.19.1 `variables.tf`. — DoD: SHAs and upstream tag recorded in `MIGRATION-v3.md`.
- [ ] 2. Inventory every input passed to `module "kube-hetzner"` and every file in `extra-manifests/` (depends on 1). — DoD: a table in `MIGRATION-v3.md` with columns v2 name / v3 name / v2 effective value / v3 default / candidate value. It includes the unset-but-defaulted inputs that v3 re-defaults: `dns_servers`, `automatically_upgrade_os`, `automatically_upgrade_kubernetes`, `k3s_channel`, `load_balancer_location`, `network_subnet_mode`, `os`, `selinux`, `enable_kured`, `enable_system_upgrade_controller`, `ssh_authorized_keys_exclusive`, and the add-on versions. The existence of `ssh_additional_public_keys` in v3.2.1 is confirmed or refuted.
- [ ] 3. Create the draft-PR branch and edit `kube.tf` (depends on 2):
  - `version = "3.2.1"`;
  - renames: `install_k3s_version` -> `k3s_version`, `sys_upgrade_controller_version` -> `system_upgrade_controller_version`;
  - remove `hetzner_ccm_use_helm`;
  - replace `extra_kustomize_parameters` with `user_kustomizations["1"]` (`source_folder = "extra-manifests"`, same parameters);
  - set explicit values for every changed default.

  Keep the locals names. — DoD: the diff changes only module inputs and the version, and every explicit pin cites its row in the map.
- [ ] 4. Adjust provider constraints only as v3.2.1 requires: hcloud `>= 1.62.0`, plus `assert` if it is declared (depends on 3). Run `tofu init -backend=false -upgrade` and record the provider selections before and after. — DoD: a separate commit; kubernetes, helm and kubectl constraints are unchanged; the lockfile policy question is noted in the PR.
- [ ] 5. Update `tests/test_k3s_kured_single_owner.py` so its K3 check reads `user_kustomizations["1"].kustomize_parameters` instead of `extra_kustomize_parameters` (depends on 3). — DoD: the test passes on the candidate and still fails if a parameter is dropped.
- [ ] 6. Static validation, for baseline and candidate (depends on 3-5):
  - `tofu fmt -check -recursive`;
  - `tofu init -backend=false`;
  - `tofu validate`;
  - upstream `scripts/v2_to_v3_migration_assistant.py --root .`, with every match resolved;
  - `pytest tests/test_k3s_*`.

  — DoD: outputs are recorded in `MIGRATION-v3.md` under "Static evidence", and are explicitly labelled "not a migration plan".
- [ ] 7. Add `scripts/k3s-plan-action-report.sh`, which reads a plan JSON and prints only `address | actions | class` plus the `PLAN_PROJECTION` digest copied verbatim from `terraform.yml`. — DoD: it emits no attribute values; unit cases use synthetic plan JSON.
- [ ] 8. Get baseline and candidate plans against the same state serial through an authorized plan-only path: an operator local plan with `tfenv.sh` and `-lock=false`, or an owner-approved plan-only dispatch (depends on 3, 7). — DoD: the sanitized action reports, source SHAs, state serial and digests are recorded, and the raw files are deleted. If no path is authorized, the section reads `BLOCKED` and names the missing prerequisite (the non-main plan path, or operator credentials).
- [ ] 9. Classify every candidate action:
  - destroy/replace
  - reprovision
  - `hcloud_server_network` delete
  - in-place `network`/`public_net`
  - `server_type` or cost change
  - firewall/LB
  - kustomization re-apply
  - SSH key reconciliation
  - bookkeeping
  - unknown

  Also run upstream `--plan-json --strict` and the protected-resource gate (depends on 8). — DoD: every address has exactly one class, and unknowns are listed as blockers.
- [ ] 10. Guard audit and proposal: add an `inplace-risk` class to `.github/scripts/k3s-plan-guard.sh`. It covers `hcloud_server` updates that change or leave unknown `server_type`/`network`/`public_net`, `hcloud_load_balancer` type changes, and `hcloud_server_network` create/delete, behind a new `allow_inplace_risk` dispatch input. Extend the routine kustomization regex with the v3 address seen in task 8. Add test cases to `tests/test_k3s_plan_guard.py`. — DoD: the tests show today's guard passing an in-place rescale and the new guard refusing it.
- [ ] 11. Reconcile the snapshot docs: change the README cluster-spec row to "every 12h ... 28 kept = 14 days" and update the 6h / 56 text at `docs/runbooks/restore.md` line 159. — DoD: `grep -rn "56 kept\|retention 56"` returns nothing for k3s-preview.
- [ ] 12. Write the report section of `MIGRATION-v3.md` (depends on 6-11):
  - recovery prerequisites (state pull, fresh etcd snapshot to R2, CNPG backup check, deploy key SSH, Hetzner console);
  - single-CP outage implications;
  - a staged rollout proposal (state backup -> plan digest review -> apply with the narrowest `allow_*` -> verify nodes, system pods, storage classes, LB, OIDC login, audit log -> post-apply plan shows no changes);
  - verdict GO / CONDITIONAL / NO-GO with evidence.

  — DoD: the draft PR is opened, not merged, and its description links #2340 and states "no apply performed".

## Tests
- [ ] T1. `tofu fmt -check`, `tofu init -backend=false` and `tofu validate` pass on the candidate.
- [ ] T2. `pytest tests/test_k3s_kured_single_owner.py tests/test_k3s_plan_guard.py` passes, including the new in-place rescale, network-change and `hcloud_server_network` cases.
- [ ] T3. Upstream migration assistant `--root .` reports no unresolved v2 names.
- [ ] T4. If plans were obtained: the candidate action report has no destroy/replace of hcloud resources, no `server_type`/LB-type change, no `hcloud_server_network` delete, no changed or unknown `network`/`public_net`, and no unknown class. Otherwise T4 is recorded as BLOCKED.
- [ ] T5. A grep of the PR diff and report finds no secret, raw plan or state content: no `private_key`, no token values, no `etcd-s3-secret-key` value.

## Rollback
Nothing is applied, so there is no infrastructure to roll back. To abandon the spike, close the draft PR and delete its branch. The docs-only reconciliation (task 11) can be split into its own PR and reverted with `git revert`. If a guard change is later merged and proves too strict, revert that commit; the existing `allow_destroy`/`allow_reprovision` behaviour is unchanged. Any later rollout has its own rollback in the report: restore the state from the `tofu state pull` backup (`docs/runbooks/opentofu-state-restore.md`), pin the module back to 2.19.1, and restore etcd from the pre-rollout R2 snapshot (`docs/runbooks/restore.md`).
