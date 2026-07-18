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

## Security notes

- `terraform.tfvars` contains the Hetzner API token — git-ignored, never commit
- `kubeconfig.yaml` contains cluster admin credentials — git-ignored
- Keep file permissions tight: `chmod 600 terraform.tfvars kubeconfig.yaml`
