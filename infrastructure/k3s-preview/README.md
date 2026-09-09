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
- Terraform variables from the macOS Keychain: `source ./tfenv.sh`. It exports
  `TF_VAR_hcloud_token`, `TF_VAR_etcd_s3_access_key` and
  `TF_VAR_etcd_s3_secret_key` from the Keychain items it documents. There is no
  `terraform.tfvars` any more — it held the same values in plaintext on disk,
  and CI never used it (`terraform.yml` passes `TF_VAR_*` from Actions secrets),
  so local and CI runs now read the same variables from different stores.
  The etcd R2 token must also cover the `mctl-etcd-snapshots` bucket. All three
  are required: `kube.tf` treats the etcd pair as optional (`etcd_s3_backup =
  var.etcd_s3_access_key == "" ? {} : {...}`), which is true only for a cluster
  that never had snapshots. This one has them, so leaving the pair blank does not
  mean "snapshots stay off" — measured, it plans a **replacement of
  `terraform_data.control_plane_config`**, rewriting k3s configuration on the
  single control-plane node. `tfenv.sh` therefore refuses to continue when any of
  the three is missing, on purpose.
  Restore procedure: `docs/runbooks/restore.md` at the repo root.
- Cloudflare R2 credentials for the **state backend**, as env vars. These are a
  different credential from the etcd one (bucket `mctl-terraform-state`;
  Keychain service `mctl-terraform-state-local`) and `terraform init` needs them
  before any variable is read, which is why `tfenv.sh` does not set them:
  ```bash
  export AWS_ACCESS_KEY_ID=$(security find-generic-password -s mctl-terraform-state-local -a access-key-id -w)
  export AWS_SECRET_ACCESS_KEY=$(security find-generic-password -s mctl-terraform-state-local -a secret-access-key -w)
  ```
- SSH key at `~/.ssh/id_ed25519`

## First-time setup

```bash
cd infrastructure/k3s-preview
source ./tfenv.sh
terraform init
terraform plan
terraform apply
```

After apply, save the kubeconfig locally (git-ignored):
```bash
terraform output --raw kubeconfig > kubeconfig.yaml
chmod 600 kubeconfig.yaml
```

## Day-to-day operations

```bash
source ./tfenv.sh

# Plan only (safe, no changes)
terraform plan

# Apply changes
terraform apply
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
├── audit-policy.yaml          # k3s apiserver audit policy (SOC F20; not kubectl-applied)
└── extra-manifests/           # Additional K8s resources applied post-cluster:
    ├── letsencrypt-*.yaml.tpl # cert-manager ClusterIssuers (prod + staging + http01)
    ├── cert-manager-helmchartconfig.yaml.tpl
    ├── cloudflare-origin-allowlist.yaml.tpl  # Traefik Middleware: Cloudflare-only ingress (#1119)
    ├── traefik-helmchartconfig.yaml.tpl      # Traefik PDB + the websecure entrypoint reference
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

## Origin allowlist (Cloudflare-only ingress)

Traffic reaches the platform through Cloudflare, then the Hetzner Cloud Load
Balancer for `svc/traefik`, then Traefik. Until #1119 the origin also answered
anyone who held its address — measured, `app.mctl.ai` and `ops.mctl.ai` both
returned `200` to a request sent straight at it — so every Cloudflare-layer
control was out of the path for anyone who read the (public) repository.

The load balancer cannot be firewalled: Hetzner cloud firewalls attach to
servers, and the CCM ignores `spec.loadBalancerSourceRanges`. The nodes have
nothing to close either, since kube-hetzner only opens 80/443 on them when
`using_klipper_lb` is true. It closes the origin's *public* address and nothing
else — a pod talking to Traefik's ClusterIP directly can still supply its own
PROXY header, because the entrypoint trusts `10.0.0.0/8` and the pod and service
CIDRs are inside it (gitops#1138). So the control is the `Middleware`
`traefik/cloudflare-origin` (`extra-manifests/cloudflare-origin-allowlist.yaml.tpl`),
referenced from the `websecure` entrypoint in
`extra-manifests/traefik-helmchartconfig.yaml.tpl`. Traefik sees the real client
address because the LB speaks PROXY protocol and the entrypoint trusts it from
`10.0.0.0/8`.

`.github/workflows/cloudflare-origin-allowlist.yml` re-checks the committed
ranges against `https://api.cloudflare.com/client/v4/ips` daily.

### Break-glass

A wrong or missing allowlist takes out every host on `:443` at once. It is a
`Middleware` object rather than a static entrypoint argument precisely so the
first level of recovery is one command with no restart.

```bash
# kubectl still works when the ingress does not: the kubeconfig points at the
# control-plane NODE on :6443, which is not behind the load balancer.
export KUBECONFIG=infrastructure/k3s-preview/kubeconfig.yaml

# Level 0 — locked out of app.mctl.ai / ops.mctl.ai. Widen the allowlist to
# everything. The kubernetescrd provider watches the object; effective in
# seconds, no helm upgrade, no pod restart.
kubectl -n traefik patch middleware cloudflare-origin --type=merge \
  -p '{"spec":{"ipAllowList":{"sourceRange":["0.0.0.0/0","::/0"]}}}'

# Level 1 — the Middleware itself is broken or gone, so every router on
# websecure is down. Remove the reference; helm-controller re-runs the upgrade
# job (~1-2 min).
kubectl -n kube-system edit helmchartconfig traefik   # delete the ports: block
kubectl -n kube-system get jobs -w | grep helm-install-traefik

# Level 2 — the API server is unreachable. SSH is open on the nodes.
ssh root@<control-plane-node>
```

Two things to know before you use it:

- A level-0 or level-1 patch is **undone by the next `terraform apply`**, which
  re-renders both manifests from Git. It must be followed by a pull request —
  the same discipline as the break-glass section in
  `infrastructure/cloudflare/README.md`.
- `kubectl apply -k` never prunes, so removing the manifest from
  `kustomization.yaml` does **not** delete the live `Middleware`.

## Security notes

- Terraform credentials live in the macOS Keychain, not on disk. `tfenv.sh`
  reads them; there is no `terraform.tfvars`. If you recreate one, `.gitignore`
  still covers `*.tfvars`, but a plaintext token in the working tree is exactly
  what the Keychain move removed — and note that any tool which prints a diff of
  that file (`terraform fmt -diff` does) will echo the token.
- `kubeconfig.yaml` contains cluster admin credentials — git-ignored
- Keep file permissions tight: `chmod 600 kubeconfig.yaml`
