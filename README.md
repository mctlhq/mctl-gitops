# mctl-gitops

GitOps source of truth for the mctl.ai platform — Helm charts, Argo Workflows, Terraform infrastructure, and the mctl CLI.

## What It Does

ArgoCD watches this repository and continuously syncs all platform components to Kubernetes. Every change merged to `main` — whether a new service, an updated image tag, or a tenant configuration — is automatically reconciled to the cluster within 60 seconds. This repo is the single source of truth for what runs on mctl.ai.

## Architecture

```
Developer / mctl CLI / GitHub Actions
            │
            ▼
   ┌─── mctl-gitops (this repo) ───┐
   │                                │
   │  services/{team}/{app}/        │   ◄── per-service Helm values
   │  tenants/{team}/               │   ◄── per-tenant config
   │  platform-gitops/apps/         │   ◄── ArgoCD App-of-Apps
   │  argo-workflows/               │   ◄── ClusterWorkflowTemplates
   │  infrastructure/               │   ◄── Terraform (Hetzner k3s)
   │                                │
   └────────────┬───────────────────┘
                │  git push
                ▼
         ArgoCD (ops.mctl.ai)
                │  sync (prune + selfHeal)
                ▼
        Kubernetes Cluster
   ┌────────────────────────────┐
   │  Platform: API, Web,       │
   │    Backstage, Vault,       │
   │    Monitoring, Workflows   │
   │  Tenants: ns + RBAC + quotas│
   │  Services: per-team apps   │
   └────────────────────────────┘
```

**App-of-Apps pattern:**

```
ArgoCD root app "apps"
  ├── ApplicationSet: platform apps (mctl-api, mctl-web, monitoring, backstage, vault, argocd, …)
  ├── ApplicationSet: tenant apps  (dynamic — from tenants/{team}/values.yaml)
  └── ApplicationSet: production services
```

All applications are configured with `automated: { prune: true, selfHeal: true }` and a 60-second reconciliation interval.

## Tech Stack

| Category | Details |
|---|---|
| GitOps | ArgoCD, ApplicationSets, App-of-Apps pattern |
| Orchestration | Argo Workflows (ClusterWorkflowTemplates) |
| Charts | Helm 3 (base-service, worker-service, tenant) |
| CLI | Go 1.21+, Cobra |
| Infrastructure | Terraform, Hetzner Cloud, k3s |
| Secrets | HashiCorp Vault, ExternalSecrets Operator |
| Database | CloudNativePG (PostgreSQL) |
| Monitoring | Prometheus, Grafana, Loki |
| Ingress/TLS | Traefik, Cert-Manager, Reflector |
| Storage | MinIO (S3-compatible), Cloudflare R2 (Terraform state) |
| CI/CD | GitHub Actions (6 workflows) |
| Catalog | Backstage (software templates + service catalog) |

## Project Structure

```
mctl-gitops/
├── cli/mctl/                          # Go/Cobra CLI tool
│   ├── main.go                        #   entry point
│   └── cmd/                           #   commands: deploy, delete, config, status, logs, repo, auth
├── infrastructure/
│   ├── k3s-preview/                   # Terraform — preview cluster (Hetzner)
│   └── k3s-prod/                      # Terraform — production cluster
├── platform-gitops/
│   ├── apps/                          # ArgoCD App-of-Apps (28 templates)
│   │   └── templates/                 #   mctl-api, mctl-web, backstage, monitoring, vault, …
│   ├── argo-workflows/                # ClusterWorkflowTemplates + platform config
│   │   └── mctl-platform-config.yaml  #   source of truth for platform-wide variables
│   ├── argocd/                        # ArgoCD Helm values (RBAC, Dex SSO)
│   ├── backstage-templates/           # Backstage software templates
│   ├── cnpg-clusters/                 # CloudNativePG PostgreSQL cluster definitions
│   ├── grafana/                       # Grafana dashboards
│   ├── helm-charts/
│   │   ├── base-service/              #   HTTP services with Ingress + TLS
│   │   ├── worker-service/            #   background workers (no Ingress)
│   │   └── tenant/                    #   team workspace (namespace + RBAC + quotas)
│   ├── minio/                         # MinIO object storage config
│   ├── services/{team}/{service}/     # Per-service Helm values
│   └── tenants/{team}/                # Per-tenant configuration
├── .github/workflows/                 # 6 GitHub Actions workflows
├── Makefile                           # CLI build commands
└── FORK.md                            # Self-hosting instructions
```

## Getting Started

### Prerequisites

- Go 1.21+ (for building the CLI)
- Helm 3
- kubectl with cluster access
- Terraform 1.5+ (for infrastructure changes only)
- ArgoCD CLI (optional, for manual sync)

### Local Development (CLI)

```bash
cd cli/mctl
go build -o mctl -ldflags "-X .../cmd.version=dev" .
./mctl --help
```

Or use the Makefile from the repository root:

```bash
make build      # builds cli/mctl/mctl
make install    # installs to $GOPATH/bin
```

### Adding a Service

1. Create the values file at `platform-gitops/services/{team}/{service}/values.yaml`:

```yaml
image:
  repository: ghcr.io/mctlhq/my-service
  tag: "1.0.0"
host: my-service.mctl.ai
port: 8080
```

2. Commit and push. The production ApplicationSet detects the new directory and ArgoCD creates the Application automatically.

Alternatively, use the CLI or API:

```bash
mctl deploy --team billing --service payment-api --repo mctlhq/payment-api --tag v1.0.0
```

### Adding a Tenant

1. Create the values file at `platform-gitops/tenants/{team}/values.yaml`:

```yaml
name: payments
displayName: "Payments Team"
contactEmail: payments@example.com
quota:
  cpu: "2"
  memory: "4Gi"
  pods: "20"
```

2. Commit and push. The tenant ApplicationSet picks it up and ArgoCD provisions the namespace, RBAC, ResourceQuota, LimitRange, and NetworkPolicy.

## Configuration

### Platform Config

The file `platform-gitops/argo-workflows/mctl-platform-config.yaml` is the source of truth for platform-wide variables. It is mounted as a ConfigMap in the `argo-workflows` namespace.

```yaml
GITOPS_ORG: "mctlhq"
GITOPS_REPO: "mctl-gitops"
PLATFORM_DOMAIN: "mctl.ai"
PLATFORM_DOMAIN_ALT: "mctl.ai"
CONTAINER_REGISTRY: "ghcr.io/mctlhq"
```

To self-host the platform under your own domain and org, edit this file and see [FORK.md](FORK.md).

### Service Values

Located at `platform-gitops/services/{team}/{service}/values.yaml`. Consumed by the `base-service` or `worker-service` Helm chart.

| Field | Description |
|---|---|
| `image.repository` | Container image (e.g. `ghcr.io/mctlhq/my-app`) |
| `image.tag` | Pinned image version |
| `host` | Ingress hostname (base-service only) |
| `port` | Container port (default: `8080`) |
| `env` | Plaintext environment variables |
| `secrets` | References to ExternalSecrets (Vault-backed) |

### Tenant Values

Located at `platform-gitops/tenants/{team}/values.yaml`. Consumed by the `tenant` Helm chart.

| Field | Description |
|---|---|
| `name` | Workspace name (DNS-safe) |
| `displayName` | Human-readable team name |
| `contactEmail` | Team contact |
| `quota.cpu` | CPU request quota |
| `quota.memory` | Memory request quota |
| `quota.pods` | Maximum pod count |

## CLI (mctl)

The `mctl` CLI is a Go/Cobra tool for platform operations. It lives in `cli/mctl/` and communicates with Argo Workflows and the GitOps repo.

| Command | Purpose |
|---|---|
| `mctl deploy` | Deploy or onboard a new service |
| `mctl delete` | Remove a service and clean up resources |
| `mctl config` | Update service configuration (env vars, secrets) |
| `mctl status` | Check Argo Workflow execution status |
| `mctl logs` | Stream or tail workflow logs |
| `mctl repo` | Manage repository access and secrets |
| `mctl auth` | Authenticate with the platform |

**Examples:**

```bash
# Onboard a new service
mctl deploy --team billing --service invoice-api \
  --repo mctlhq/invoice-api --tag v1.0.0

# Check deployment status
mctl status --workflow deploy-invoice-api-abc123

# Update environment variables
mctl config --team billing --service invoice-api \
  --env "LOG_LEVEL=debug" --env "CACHE_TTL=300"

# View recent workflow logs
mctl logs --workflow deploy-invoice-api-abc123 --tail 100
```

## GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `release-service.yml` | Manual / API dispatch | Deploy, update, or onboard services (validate → build → onboard → deploy) |
| `retire-service.yml` | Manual dispatch | Delete services and clean up Vault, Backstage, and ArgoCD resources |
| `provision-db.yml` | Manual dispatch (self-hosted) | Provision PostgreSQL via CloudNativePG + store credentials in Vault |
| `terraform.yml` | Push to `infrastructure/**` | Terraform plan/apply for k3s clusters |
| `auto-merge.yml` | PR creation | Auto-merge Dependabot and Renovate PRs |
| `fix-db-host.yml` | Manual dispatch | Database connection troubleshooting utility |

## Testing

Helm charts can be validated locally with `helm lint` and `helm template`:

```bash
helm lint platform-gitops/helm-charts/base-service
helm template my-svc platform-gitops/helm-charts/base-service -f values.yaml
```

Terraform plans are validated automatically on push via the `terraform.yml` workflow.

## CI/CD

All CI/CD runs through GitHub Actions. The primary deployment flow:

1. **`release-service.yml`** is triggered (manually or via API dispatch from mctl-api).
2. The workflow validates inputs, builds the Docker image, and pushes to `ghcr.io/mctlhq`.
3. It commits the updated image tag to this repo under `services/{team}/{service}/values.yaml`.
4. ArgoCD detects the change and syncs the new version to the cluster.

Infrastructure changes follow a similar pattern: push to `infrastructure/**` triggers `terraform.yml`, which runs `terraform plan` on PRs and `terraform apply` on merge to `main`.

## Deployment

All deployment is declarative and Git-driven:

- **Platform components** — defined in `platform-gitops/apps/templates/`. Change a template, push, ArgoCD syncs.
- **Tenant workspaces** — defined in `platform-gitops/tenants/`. Add a directory, push, namespace is provisioned.
- **User services** — defined in `platform-gitops/services/`. Update `image.tag`, push, new version rolls out.
- **Infrastructure** — defined in `infrastructure/`. Push changes, Terraform applies via GitHub Actions.

There is no imperative deployment step. The cluster state always converges to match this repository.

### Key URLs

| URL | Description |
|---|---|
| `ops.mctl.ai` | ArgoCD dashboard |
| `workflows.mctl.ai` | Argo Workflows UI |
| `api.mctl.ai` | mctl REST API and MCP server |
| `app.mctl.ai` | Backstage service catalog |

## Release Process

1. Make changes in a feature branch and open a PR.
2. GitHub Actions run validation (lint, Terraform plan where applicable).
3. Merge to `main`. ArgoCD auto-syncs within 60 seconds.
4. For service image updates, `release-service.yml` handles the full build → commit → sync cycle.
5. Rollback: revert the commit or update `image.tag` to a previous version and push.

## Related Projects

| Repository | Description |
|---|---|
| [mctl-api](https://github.com/mctlhq/mctl-api) | REST API and MCP server powering the platform |
| [mctl-web](https://github.com/mctlhq/mctl-web) | Landing page and MCP connect interface |
| [mctl-agent](https://github.com/mctlhq/mctl-agent) | AI agent for platform operations |
| [mctl-portal](https://github.com/mctlhq/mctl-portal) | Developer portal and dashboard |

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
