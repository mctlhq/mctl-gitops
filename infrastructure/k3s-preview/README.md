# k3s-preview — Preprod Cluster on Hetzner Cloud

Terraform configuration for the `mctl-preprod` K3s cluster.
Uses the [`kube-hetzner`](https://github.com/kube-hetzner/terraform-hcloud-kube-hetzner) Terraform module.

## Cluster specs

| Property | Value |
|----------|-------|
| Name | `mctl-preprod` |
| K3s version | v1.33 (managed by kube-hetzner) |
| Region | `eu-central` (Frankfurt) |
| Control plane | 1 × cx33 — single node, non-HA |
| Workers | 3 × cx43 |
| Load balancer | `lb11` (fsn1) |
| Ingress | Traefik |
| OS | openSUSE MicroOS (immutable; OS auto-upgrade **disabled** — single CP, see kube.tf) |
| Module version | 2.19.1 (pinned in `kube.tf`) |
| etcd snapshots | every 6h → R2 bucket `mctl-etcd-snapshots` (56 kept = 14 days) |

## Prerequisites

- Terraform >= 1.14
- `terraform.tfvars` with `hcloud_token` (not committed — see `.gitignore`)
- Cloudflare R2 credentials set as env vars:
  ```bash
  export AWS_ACCESS_KEY_ID=...
  export AWS_SECRET_ACCESS_KEY=...
  ```
- SSH key at `~/.ssh/id_ed25519`
- For etcd S3 snapshots: `TF_VAR_etcd_s3_access_key` / `TF_VAR_etcd_s3_secret_key`
  (R2 token must also cover the `mctl-etcd-snapshots` bucket — create it once in
  the Cloudflare dashboard; left unset, snapshots simply stay disabled).
  Restore procedure: `docs/runbooks/restore.md` at the repo root.

## First-time setup

```bash
cd infrastructure/k3s-preview
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

After apply, save the kubeconfig locally (git-ignored):
```bash
terraform output --raw kubeconfig > kubeconfig.yaml
chmod 600 kubeconfig.yaml
```

## Day-to-day operations

```bash
# Plan only (safe, no changes)
terraform plan -var-file=terraform.tfvars

# Apply changes
terraform apply -var-file=terraform.tfvars
```

The `terraform.yml` GitHub Actions workflow runs `terraform plan` automatically
on every push to `infrastructure/k3s-preview/**`. Apply requires manual dispatch with `apply: true`.

**Applying from CI needs secrets that do not exist yet.** The apply path had never
been exercised until 2026-09-09, when it destroyed the cluster's `hcloud_ssh_key`
and could not recreate it — `SSH_PRIVATE_KEY` and `SSH_PUBLIC_KEY` are referenced
by the workflow but are not set, in this repository or the organisation, so the
job wrote a lone newline and Hetzner refused it. The workflow now refuses the
apply up front instead, and applies run locally until someone decides to put a
node SSH key into Actions secrets. Four secrets gate it:

| Secret | Purpose |
| --- | --- |
| `HCLOUD_TOKEN` | exists |
| `SSH_PRIVATE_KEY` / `SSH_PUBLIC_KEY` | **absent** — the module drives node configuration over SSH, so an apply cannot work without them. Putting a node's private key in a repository secret makes it readable by every workflow in the repo (see #1118); that is a decision, not an oversight. |
| `ETCD_S3_ACCESS_KEY_ID` / `ETCD_S3_SECRET_ACCESS_KEY` | **absent** — the snapshots-bucket token. Until 2026-09-09 the workflow passed the *state-backend* token here instead, which made every CI plan propose replacing `terraform_data.control_plane_config` and restarting k3s on the single control-plane node. |

See #1139. Local applies read all of these from the Keychain via `tfenv.sh` and
are unaffected.

## Updating the kube-hetzner module

The module version is pinned in `kube.tf`:
```hcl
source  = "kube-hetzner/kube-hetzner/hcloud"
version = "2.19.1"
```

To upgrade:
1. Check the [upstream changelog](https://github.com/kube-hetzner/terraform-hcloud-kube-hetzner/releases)
2. Update `version` in `kube.tf`
3. Run `terraform init -upgrade` to refresh the module and update `.terraform.lock.hcl`
4. Run `terraform plan` and review for breaking variable changes
5. Commit both `kube.tf` and `.terraform.lock.hcl`

Subscribe to upstream releases to get notified of new versions.

## Structure

```
k3s-preview/
├── kube.tf                    # Main cluster config (module call + providers + outputs)
├── backend.tf                 # Remote state: Cloudflare R2
├── cluster-bootstrap/         # ArgoCD Helm install (one-shot, see "Disaster recovery") + Vault ExternalSecret bootstrap
│   ├── argocd.tf
│   ├── helm-values/argocd.yaml
│   └── vault-config/          # Vault policies + ClusterSecretStore
├── audit-policy.yaml          # k3s apiserver audit policy (SOC F20; not kubectl-applied)
└── extra-manifests/           # Additional K8s resources applied post-cluster:
    ├── letsencrypt-*.yaml.tpl # cert-manager ClusterIssuers (prod + staging + http01)
    ├── kured.yaml.tpl         # Automated node reboots after OS upgrades
    └── metrics-server-*.tpl   # metrics-server resource patches
```

## State backend

Remote state in Cloudflare R2:
- Bucket: `mctl-terraform-state`
- Key: `k3s-preview/terraform.tfstate`

`cluster-bootstrap/` is a child module invoked from root `kube.tf` — it has
no `backend.tf`/`versions.tf` of its own and must never be `init`'d/applied
as an independent root; doing so once (before 2026-07-01) split the ArgoCD
Helm release across two disconnected state files and caused a chain of
ownership conflicts (see "Disaster recovery" below and PR history around
2026-07-01 in this repo).

Local `.tfstate` files are git-ignored. Never commit state files.

## Disaster recovery: re-bootstrapping ArgoCD from zero

`cluster-bootstrap/helm_release.argocd` is a **one-shot bootstrap resource**,
gated behind `var.bootstrap_argocd` (default `false`) and deliberately kept
OUT of Terraform state during routine operation — ArgoCD self-manages its
own config via GitOps (`platform-gitops/argocd/`) once bootstrapped, and
letting Terraform keep tracking the same Helm release causes it to fight
ArgoCD's reconciler for ownership (this happened 2026-04-06 to 2026-07-01:
Terraform's tracked state went stale for ~85 days while ArgoCD kept the live
cluster current; re-running `terraform apply` against it then required
manually re-labelling `argocd-self-managed`/`root-app` with Helm ownership
metadata that ArgoCD's own reconciliation had stripped).

For a genuine from-zero cluster rebuild:
1. `terraform apply -var="bootstrap_argocd=true"` — installs ArgoCD and seeds
   the `argocd-self-managed` + `root-app` Applications.
2. Wait for both Applications to report `Healthy`/`Synced`
   (`kubectl get application -n argocd`).
3. `terraform state rm module.cluster-bootstrap.helm_release.argocd[0]` —
   detaches it from Terraform again so routine `plan`/`apply` stays clean.

**There is no ArgoCD SSO during step 2.** The bootstrap release ships no dex
connector and `admin.enabled: false`; SSO arrives with `argocd-self-managed`,
and its issuer is Backstage, which is itself deployed later by `root-app`.
So the UI has no login until the platform is up — which is exactly the window
step 2 asks you to watch.

Drive it from the CLI instead, against the kubeconfig Terraform just wrote:

```bash
export KUBECONFIG=$PWD/kubeconfig.yaml
argocd --core app list
argocd --core app get argocd-self-managed
argocd --core app get root-app
```

`--core` talks to the Kubernetes API directly and never authenticates to the
ArgoCD server, so it works before any connector exists. Plain
`kubectl -n argocd get application` works too; `--core` is only nicer for
sync/health detail. Once `argocd-self-managed` is `Synced`, the Backstage
connector is live and the UI at `ops.mctl.ai` behaves normally.

## Security notes

- `terraform.tfvars` contains the Hetzner API token — git-ignored, never commit
- `kubeconfig.yaml` contains cluster admin credentials — git-ignored
- Keep file permissions tight: `chmod 600 terraform.tfvars kubeconfig.yaml`
