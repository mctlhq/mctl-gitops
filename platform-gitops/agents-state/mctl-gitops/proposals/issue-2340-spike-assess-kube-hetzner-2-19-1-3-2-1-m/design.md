# Design: issue-2340-spike-assess-kube-hetzner-2-19-1-3-2-1-m

## Current state

### Root module (`infrastructure/k3s-preview/kube.tf`)
- Module `kube-hetzner` comes from `kube-hetzner/kube-hetzner/hcloud`, `version = "2.19.1"`.
- `required_version = "~> 1.13.0"` (OpenTofu; CI pins 1.13.1).
- Providers: hcloud `~> 1.60`, kubernetes `~> 3.0`, helm `~> 3.1`, kubectl (alekc) `~> 2.1`.

Inputs passed to the module today. These are configured values, not live observations.

| v2 input | Configured value |
| --- | --- |
| `hcloud_token` | `var.hcloud_csi_token`, the in-cluster CCM/CSI token (#1140). Changing it replaces `terraform_data.kube_system_secrets`. |
| `ssh_public_key` | `format("%s\n", trimspace(var.ssh_public_key))` or `file("~/.ssh/id_ed25519.pub")`. The trailing newline is load-bearing (#1534). |
| `ssh_private_key` | `file("~/.ssh/id_ed25519")` |
| `ssh_additional_public_keys` | the `k3s-preview-ci-deploy` key |
| `extra_firewall_rules` | 3 outbound rules: SMTP 2465, and Cloudflare Tunnel 7844 over UDP and TCP |
| `network_region` | `eu-central` |
| `cluster_name` | `mctl-preprod` |
| `control_plane_nodepools` | `control-plane-fsn1`, cx33, fsn1, count 1, no `os` attribute (v2 is MicroOS) |
| `agent_nodepools` | `worker-cx43-fsn1`, cx43, fsn1, count 3 |
| `load_balancer_type` / `load_balancer_location` | `lb11` / `fsn1` |
| `enable_longhorn` | `false` |
| `etcd_s3_backup` | R2 endpoint, bucket `mctl-etcd-snapshots`, folder `k3s-preview`, `etcd-snapshot-schedule-cron = "0 */12 * * *"`, `etcd-snapshot-retention = "28"`. An empty access key yields `{}`, which per the README replaces `control_plane_config`. |
| `dns_servers` | `1.1.1.1`, `8.8.8.8`, `2606:4700:4700::1111` |
| `hetzner_ccm_use_helm` | `true` |
| Add-on versions | from locals: `hetzner_ccm_version v1.33.0`, `hetzner_csi_version v2.21.2`, `kured_version 1.21.0`, `sys_upgrade_controller_version v0.18.0`, `traefik_version 42.0.0`, `cert_manager_version v1.20.5` |
| `hetzner_ccm_merge_values`, `hetzner_csi_values` | the resource heredocs. The CSI values copy the 2.19.1 node affinity verbatim. |
| `automatically_upgrade_os` | `false` (single CP) |
| `system_upgrade_use_drain` | `true` |
| `install_k3s_version` | `v1.34.12+k3s1` |
| `extra_kustomize_parameters` | `{ base_kustomization_inputs, kured_version, sys_upgrade_controller_version }` |
| `preinstall_exec` | writes `/var/lib/rancher/k3s/server/audit.yaml` from `audit-policy.yaml` |
| `control_planes_custom_config.kube-apiserver-arg` | audit args and OIDC args (`auth.mctl.ai`, client `395107286768486101`) |
| `create_kubeconfig`, `create_kustomization` | `false` |
| `firewall_ssh_source`, `firewall_kube_api_source` | left at the default |
| `automatically_upgrade_k3s` | not set, so the v2 default applies |

`locals.base_kustomization_inputs` is a sha1 over the version pins and values. It is fed into `extra-manifests/kured.yaml.tpl` (line 72) and `system-upgrade-controller.yaml.tpl` (line 25) as an annotation, so the user layer re-applies whenever the module base kustomization is replaced (#2036). `tests/test_k3s_kured_single_owner.py` checks this wiring by parsing the `extra_kustomize_parameters` block (line 110).

### Extra manifests
`extra-manifests/kustomization.yaml.tpl` lists these resources:
- the letsencrypt prod and staging issuers;
- the cert-manager and Traefik HelmChartConfigs;
- the Cloudflare origin allowlist;
- kured;
- the metrics-server patch;
- system-upgrade-controller.

`letsencrypt-http01.yaml.tpl` exists but is not listed.

### CI and guard
`.github/workflows/terraform.yml` has two jobs:
- `plan` runs only on `refs/heads/main`, on environment `k3s-plan`. It runs `tofu init`, `validate` and `plan -lock=false`, publishes the "#" lines and a `PLAN_PROJECTION` sha256 digest to the public run summary, and runs the guard.
- `apply` runs on dispatch with `apply: true`, on environment `k3s-apply`.

`.github/scripts/k3s-plan-guard.sh` refuses:
- any action containing `delete` on a non-`terraform_data`, non-local resource (needs `ALLOW_DESTROY`);
- any `delete` of a `terraform_data` other than `kustomization|kustomization_user|kustomization_user_deploy` (needs `ALLOW_REPROVISION`).

It does NOT refuse pure `update` actions. That means it lets through:
- an in-place `hcloud_server.server_type` change (a rescale with downtime and a cost change);
- an in-place `network`/`public_net` change on `hcloud_server`.

A `hcloud_server_network` delete IS refused, because it is a non-`terraform_data` delete. The guard also does not know the v3 kustomization resource names, so a v3 user kustomization replace would be flagged as a reprovision. That fails safe, but the result is noisy.

### Other
- `.gitignore` ignores `.terraform.lock.hcl`, and `git ls-files` shows no lockfile. The README's "Updating the kube-hetzner module" section says to commit it.
- The README cluster spec says "every 6h ... 56 kept". `kube.tf` (lines 375-413) says 12h / 28. `docs/runbooks/restore.md` line 14 says 12h / 28, but line 159 still says 6h / retention 56.

### Upstream v3.2.1
Sources fetched from GitHub at tag `v3.2.1`: `docs/v2-to-v3-migration.md`, `MIGRATION.md` and `variables.tf`.

Renamed, removed or replaced inputs:
- `install_k3s_version` -> `k3s_version`.
- `sys_upgrade_controller_version` -> `system_upgrade_controller_version` (default `v0.18.0`).
- `hetzner_ccm_use_helm` is removed. The CCM is always a HelmChart.
- `extra_kustomize_*` -> `user_kustomizations` (`map(object)`, numeric-string keys). Fields: `source_folder`, `kustomize_parameters`, `pre_commands`, `post_commands`, `apply_options`, `allow_empty`. The default is key `"1"` with `source_folder = "extra-manifests"`.
- `automatically_upgrade_k3s` -> `automatically_upgrade_kubernetes`, default `true`.
- `initial_k3s_channel` -> `k3s_channel`, default changed from `v1.33` to `stable`.

New inputs:
- `enable_kured` (default `true`) and `enable_system_upgrade_controller` (default `true`).
- `ssh_authorized_keys_exclusive` (default `false`). v3 reconciles root `authorized_keys`.
- `network_subnet_mode`, default `per_nodepool`. That matches v2; `shared` can replace subnets.
- Per-nodepool `os` (`microos` | `leapmicro`; new pools default to Leap Micro) and per-nodepool `selinux` (default `true`).

Changed defaults:
- `dns_servers` defaults to the Hetzner resolvers.
- `load_balancer_location` defaults to `nbg1`.
- `automatically_upgrade_os` defaults to `true`.
- The add-on versions default to `null`, which means the module's reviewed matrix.

Tooling and stop conditions:
- Requires OpenTofu/Terraform `>= 1.10.1` and hcloud `>= 1.62.0`.
- `variables.tf` uses `provider::assert::` functions, which implies a new `assert` provider requirement.
- Upstream stop conditions: any `hcloud_server_network` delete, and any changed or unknown `network`/`public_net` on a server. Public-net updates can power-cycle nodes without replacing them.
- Upstream ships `scripts/v2_to_v3_migration_assistant.py` with `--root` and `--plan-json --strict` modes.

Not confirmed from the fetched excerpts: the existence of `ssh_additional_public_keys` in v3.2.1, and whether `moved` blocks exist.

### Deployed state checked
- Gitops path `infrastructure/k3s-preview/kube.tf` in the clone: the configured values listed above. These are configuration, not observations of the live cluster.
- `$MCTL_GITOPS_ROOT` / `platform-gitops/services` and `tenants`: not relevant. The Hetzner nodes, network and LB are not tenant services, and these paths describe tenant workloads only.
- mctl MCP tools: none called. No read-only mctl tool exposes Hetzner server state, OpenTofu state or the `terraform.yml` run summaries. Live server types, private IPs, live add-on versions and the current main plan digest were NOT observed. This is a gap, not an absence (see Open questions).

## Proposed solution

The spike produces one draft PR on a feature branch, labelled draft and never merged in this phase. It contains four parts.

### 1. Candidate configuration (`kube.tf`)
- `version = "3.2.1"`.
- Provider constraints: only what v3.2.1 requires (hcloud `~> 1.62`, plus `assert` if the module declares it). Kubernetes, helm and kubectl constraints stay untouched.
- Every value is pinned explicitly to the current effective value:
  - `k3s_version = local.install_k3s_version`. The local name is kept so the hash inputs and tests stay stable.
  - `automatically_upgrade_kubernetes`: set to the v2 effective value of `automatically_upgrade_k3s`. That value must be read from the 2.19.1 `variables.tf`; v2's default was `true`, and with the k3s version pinned the system-upgrade Plans render `version:`. The aim is to keep today's behaviour.
  - `automatically_upgrade_os = false`.
  - `system_upgrade_use_drain = true`.
  - `system_upgrade_controller_version = local.sys_upgrade_controller_version`.
  - All add-on versions from locals, as today.
  - `dns_servers` explicit, as today.
  - `load_balancer_location = "fsn1"` explicit, as today.
  - `network_subnet_mode = "per_nodepool"`.
  - `os = "microos"` and `selinux` set to the v2 effective value on both nodepools.
  - `enable_kured = true` and `enable_system_upgrade_controller = true`. This retains current ownership.
  - `ssh_authorized_keys_exclusive = false`. That keeps the hand-appended deploy key line and does not remove keys.
  - `hetzner_ccm_use_helm` removed. It is a no-op because v3 always uses Helm.
- `extra_kustomize_parameters` is replaced by:
  ```hcl
  user_kustomizations = {
    "1" = {
      source_folder        = "extra-manifests"
      kustomize_parameters = { base_kustomization_inputs = ..., kured_version = ..., sys_upgrade_controller_version = ... }
    }
  }
  ```
- `base_kustomization_inputs` gets new inputs only if v3 adds triggers to its base kustomization. The implementer reads the v3 trigger list.
- `extra-manifests/*.tpl` stay byte-identical unless v3's template rendering differs. Check whether `$${}` escaping and the `.tpl` suffix convention are still used.

### 2. Migration map (`infrastructure/k3s-preview/MIGRATION-v3.md`)
- One table row per input. Columns: v2 name, v3 name, v2 effective value, v3 default, candidate value, source line.
- One row per template.
- One row per provider and lockfile change.
- The upstream assistant scan output.
- Static validation output.
- The guard audit.
- Recovery prerequisites, the single-CP outage analysis, and the staged rollout proposal.
- A final verdict of GO / CONDITIONAL / NO-GO.

### 3. Plan evidence (sanitized)
- The baseline plan is current `main` (2.19.1) against live state. The candidate plan is the PR head against the same state serial.
- The preferred path is an operator-run local `tofu plan -lock=false -out` with `tfenv.sh` credentials, using `TF_VAR_ssh_public_key` the same way as CI.
- Both are reduced with the exact `PLAN_PROJECTION` jq from `terraform.yml` to a digest. A script `scripts/k3s-plan-action-report.sh plan.json` emits only `address | actions | class`, using the classes in requirements.md. The raw `plan.json` and `tfplan` are scrubbed, never committed and never uploaded.
- If no authorized path exists, the evidence section reads `BLOCKED: no plan-only path for non-main revisions` and names the options.

### 4. Guard hardening proposal
This is a diff in the draft PR. It is reviewed but not merged in this phase. `k3s-plan-guard.sh` gets a third class, `inplace-risk`:
- an `update` on `hcloud_server` where `before.server_type != after.server_type`, or `network`/`public_net` differ or are unknown (`after_unknown`);
- an `update` on `hcloud_load_balancer.load_balancer_type`;
- any `create`/`delete` of `hcloud_server_network`.

This class needs a new `ALLOW_INPLACE_RISK` input. The routine regex is extended with the v3 user kustomization address once it is known from the plan. Cases are added to `tests/test_k3s_plan_guard.py`.

### 5. Documentation
- The README cluster spec row and the restore.md text at line 159 are changed to 12h / 28 kept (14 days).
- The README module-upgrade section is corrected about the lockfile, or the open question is flagged.

Verdict rules:
- GO requires that the candidate plan exists and is clean beyond kustomization re-applies.
- CONDITIONAL applies when the only remaining items are reprovisions with an explicit, accepted restart window.
- NO-GO applies to any network detach, rescale, replacement, unknown, or a BLOCKED plan.

The expected outcome when the plan path is unavailable is: static: pass; plan: BLOCKED; verdict: CONDITIONAL at best, pending plan evidence.

## Alternatives
- **Blue/green: build a new v3 cluster and move workloads.** Upstream recommends it when a plan is hard to explain. It was dropped for this phase because it doubles cost temporarily, adds new VMs, and requires an etcd/ArgoCD rebuild, all of which the issue's hard boundaries exclude. It is kept as the fallback recommendation if the candidate plan shows network detachment.
- **Stay on 2.19.x and backport only fixes.** This has no migration risk, but the maintenance debt the issue wants reduced keeps growing. It is recorded as the NO-GO default.
- **Accept v3 defaults and fix drift afterwards.** Rejected. These defaults would turn OS auto-upgrade on for a single control plane (an outage), move DNS resolvers, switch the k3s channel to `stable` and float add-on versions.

## Platform impact
- **No runtime impact in this phase.** It is a draft PR plus documentation; there is no apply and no merge. The only shared artefact is the run summary of any plan dispatch. Because it is public, it must show only the existing `# address` lines and the digest.
- **Risks of the eventual rollout**, which the report must classify:
  - `control_plane_config` replace, which restarts k3s on the single CP, so the API server is down for minutes;
  - `agent_config` replace, which restarts the agents;
  - `hcloud_server_network` delete or inline `network` changes, which can mean a NIC detach or a loss of node identity;
  - `public_net` updates, which can power-cycle nodes;
  - SSH key reconciliation commands;
  - base kustomization re-apply, which can reset kured/SUC resources, mitigated by the hash wiring;
  - CCM HelmChart re-render, which can touch the LB through svc/traefik.
- **Cost.** The candidate must show no `server_type`, LB type or count changes, and no new primary IPs or placement-group-driven resources. Any of these blocks the migration.
- **Mitigations for a later rollout.** All of these are prerequisites, recorded in the report:
  - `tofu state pull` backup per `docs/runbooks/opentofu-state-restore.md` (plus the `opentofu-state-backup.yml` artefact);
  - a fresh on-demand etcd snapshot uploaded to R2;
  - verified CNPG backups (14d);
  - SSH access via the deploy key;
  - a Hetzner console fallback;
  - a maintenance window that accepts a single-CP API outage;
  - an apply dispatch with the narrowest `allow_*` flags, after digest match.
- **Backward compatibility.** The lockfile and provider changes are isolated in their own commit, so they can be reverted without touching inputs.
