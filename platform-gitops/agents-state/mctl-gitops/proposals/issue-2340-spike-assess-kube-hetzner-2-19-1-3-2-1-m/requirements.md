# Spike: assess kube-hetzner 2.19.1 -> 3.2.1 migration for k3s-preview (no apply)

## Context
Issue mctlhq/mctl-gitops#2340 asks for an assessment of whether the
`infrastructure/k3s-preview` OpenTofu root can move from the kube-hetzner module
2.19.1 to 3.2.1. The move must keep the existing infrastructure, the effective
cluster configuration and the cost exactly as they are. The deliverable is
evidence: a draft migration PR with an explicit old -> new input map, static
validation output, and state-backed baseline/candidate plan evidence or a
recorded BLOCKED reason. It ends in a GO / CONDITIONAL / NO-GO report and a
separate rollout proposal. Nothing is applied. Lifecycle stays `proposed`.

This matters because `kube.tf` carries a lot of hard-won configuration:
- pinned add-on versions;
- the `base_kustomization_inputs` hash that keeps kured and
  system-upgrade-controller re-applying;
- audit and OIDC apiserver args;
- the etcd S3 snapshot map;
- the trailing-newline SSH key.

v3 renames, removes and re-defaults several of these inputs and changes who owns
the network attachments. Any of these changes can silently restart k3s on the
single control plane, power-cycle nodes or move add-on versions. Because there
is only one control plane, a mistake here takes the API server down.

## User stories
- AS a platform owner I WANT a reviewed old -> new input map for every input, template and default the root uses SO THAT I can decide on the upgrade without inheriting v3 defaults by accident.
- AS a platform owner I WANT a baseline plan and a candidate plan against the same state, published as a sanitized action report SO THAT I can see every destroy, replace, reprovision, in-place network change and restart before any apply is authorized.
- AS an operator I WANT the plan guard to refuse in-place rescales and network-attachment changes SO THAT a later apply cannot pass a dangerous plan just because it contains no replacement.
- AS an operator I WANT the README and the restore runbook to state the real etcd snapshot schedule SO THAT recovery planning uses correct numbers.

## Acceptance criteria (EARS)
- WHEN the draft migration PR is opened THE SYSTEM SHALL contain a migration map (`infrastructure/k3s-preview/MIGRATION-v3.md`) listing every module input used by `kube.tf` with its v2 name, v3 name, v2 effective value, v3 default and chosen v3 value, plus every local template under `extra-manifests/` and how v3 consumes it.
- WHEN a v3 default differs from the current effective value THE SYSTEM SHALL set the input explicitly to the current effective value rather than inherit the default. This covers at least:
  - `dns_servers`
  - `automatically_upgrade_os`
  - `automatically_upgrade_kubernetes`
  - `k3s_channel`
  - per-nodepool `os` and `selinux`
  - `load_balancer_location`
  - `network_subnet_mode`
  - `enable_kured`
  - `enable_system_upgrade_controller`
  - `ssh_authorized_keys_exclusive`
  - the add-on versions
- WHILE the candidate configuration is in review THE SYSTEM SHALL keep the following unchanged:
  - K3s `v1.34.12+k3s1`;
  - CCM `v1.33.0`, CSI `v2.21.2`, kured `1.21.0`, system-upgrade-controller `v0.18.0`, Traefik `42.0.0`, cert-manager `v1.20.5`;
  - MicroOS;
  - 1 x cx33 control plane and 3 x cx43 workers in fsn1;
  - lb11 in fsn1;
  - the network, subnet and IP assignments;
  - SSH keys;
  - the audit and OIDC apiserver args;
  - the etcd snapshot settings (12h / 28);
  - `automatically_upgrade_os = false`.
- WHEN `extra_kustomize_parameters` is ported THE SYSTEM SHALL express it as `user_kustomizations` entry `"1"`, with `source_folder = "extra-manifests"` and the same three `kustomize_parameters`. It SHALL keep the kured / system-upgrade-controller wiring that `tests/test_k3s_kured_single_owner.py` checks, adapted to the new input.
- WHEN provider constraints change THE SYSTEM SHALL change only what v3.2.1 requires: hcloud `>= 1.62.0`, any newly required provider such as `assert`, and OpenTofu `>= 1.10.1`, which is already satisfied by `~> 1.13.0`. The change SHALL be recorded separately from the module bump.
- WHEN static checks run THE SYSTEM SHALL record the output of `tofu fmt -check`, `tofu init -backend=false` and `tofu validate` for both the baseline and the candidate, plus the upstream `scripts/v2_to_v3_migration_assistant.py --root .` scan.
- IF no authorized plan-only path can plan a non-main revision against the live state THEN THE SYSTEM SHALL mark the plan criterion BLOCKED and name the missing prerequisite. Today `.github/workflows/terraform.yml` runs `plan` on `refs/heads/main` only. The report SHALL NOT describe static checks as a safe migration plan.
- WHEN baseline and candidate plans exist THE SYSTEM SHALL publish only a sanitized action report: address, action, the classification below, the source SHA and the plan digest computed with the `PLAN_PROJECTION` of `terraform.yml`. Raw plan and state files SHALL never be committed, attached or printed.
- WHEN a plan action is classified THE SYSTEM SHALL assign it exactly one class:
  - destroy/replace
  - terraform_data reprovision (SSH command / k3s restart)
  - network attachment delete
  - in-place `network`/`public_net` update
  - `server_type` change (rescale and cost change)
  - firewall / LB change
  - kustomization re-apply
  - benign bookkeeping
  - unknown

  An `unknown` classification SHALL be a blocker.
- IF any plan action is a destroy/replace of a real resource, a `hcloud_server_network` delete, a changed or unknown `network`/`public_net`, a `server_type` change, or a reprovision of `control_plane_config`/`agent_config` THEN THE SYSTEM SHALL conclude NO-GO or CONDITIONAL. It SHALL NOT conclude GO.
- WHEN the guard audit completes THE SYSTEM SHALL record whether `.github/scripts/k3s-plan-guard.sh` refuses in-place `server_type` updates, in-place `network`/`public_net` updates and `hcloud_server_network` deletes. For each one not refused, it SHALL propose a guard change with a test case in `tests/test_k3s_plan_guard.py`.
- WHEN the report is written THE SYSTEM SHALL state:
  - the recovery prerequisites (state pull backup, a fresh etcd snapshot, `docs/runbooks/opentofu-state-restore.md`, `docs/runbooks/restore.md`);
  - the single-control-plane outage implications;
  - a staged rollout proposal that requires a separate owner decision.
- WHEN documentation is reconciled THE SYSTEM SHALL change the README cluster-spec row and `docs/runbooks/restore.md` section text from "6h / 56" to the code value "12h / 28 (14 days)".
- WHILE this spike is open THE SYSTEM SHALL NOT perform:
  - a tofu apply;
  - a refresh-only apply;
  - any state mutation, import or `state rm`;
  - a merge of the draft PR;
  - any node or OS change.

## Out of scope
- Any `tofu apply`, refresh-only apply, `state mv/rm/import`, or merge of the draft migration PR.
- Node changes, new VMs, rescale, autoscaling, OS upgrades (MicroOS -> Leap Micro), K3s or add-on version bumps, CNI changes, and enabling NAT or the `shared` subnet mode.
- Moving kured or system-upgrade-controller to single ownership. That is the separate follow-up named in the issue. This phase retains the current dual layer (module base + `extra-manifests` override).
- `infrastructure/k3s-prod` (a TODO README only).
- Executing the rollout. Only a proposal is produced.

## Open questions
- Authorized plan-only path for a non-main revision: `terraform.yml` refuses any ref other than `main` (`wrong-ref` job, and the `k3s-plan` environment branch policy is `main`). A candidate plan therefore needs one of these:
  - an operator running a local `tofu plan -lock=false` with Keychain credentials;
  - a new dispatch input that plans a given SHA on `main` without the apply job.

  The owner must choose. Until then the plan criterion is BLOCKED.
- `.terraform.lock.hcl` is git-ignored (`infrastructure/k3s-preview/.gitignore`), while the README "Updating the kube-hetzner module" says to commit it. Provider versions are therefore not pinned in Git, and CI resolves the newest version within the constraints on each run. Should the migration PR start committing the lockfile? The proposal records the before/after provider selections without changing this policy.
- Whether the v3 resource addresses for the user kustomization (v2 `terraform_data.kustomization_user`) and for the moved network attachments are covered by upstream `moved` blocks. The upstream docs fetched for this proposal do not say; the plan must show it. The guard's `routine_data` regex only knows the v2 names.
- Upstream says v3 keeps unknown `authorized_keys` lines and "revokes removed module-managed keys". Whether the first v3 apply runs an SSH command on every node to reconcile keys has not been verified. That would be a restart/SSH class effect to classify.
- Upstream docs fetched here did not confirm that `ssh_additional_public_keys` exists in v3.2.1 (it was outside the visible excerpt). The implementer must check it against the pinned `variables.tf`.
- Live values (node count, server types, private IPs, live add-on versions) were not observed in this run. Every value in this proposal is a configured value from `kube.tf`.
