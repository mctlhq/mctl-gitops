# mctl-gitops

GitOps repository. ArgoCD source of truth for the entire mctl platform.

## Stack
- Kubernetes manifests, Helm charts, Argo Workflows, Terraform
- ArgoCD watches this repo and reconciles cluster state

## Conventions
- YAML: 2-space indentation
- Helm templates: use `{{- ... }}` for whitespace control
- No hardcoded secrets — use Vault + ExternalSecrets
- Every platform change = a git commit here
- Comments explain non-obvious configuration, not what the YAML does

## Structure
- `platform-gitops/bootstrap/` — App-of-Apps bootstrap (ArgoCD entry point)
- `platform-gitops/services/` — per-tenant service values: `admins/`, `labs/`, `ovk/`
- `platform-gitops/argo-workflows/cluster-templates/` — ClusterWorkflowTemplates and CronWorkflows
- `platform-gitops/helm-charts/` — internal charts: `base-service`, `tenant`, `openclaw-skills`
- `platform-gitops/backstage/templates/` — Backstage scaffolder templates
- `infrastructure/k3s-preview/` — Terraform: preprod cluster on Hetzner (kube-hetzner module)
- `cli/mctl/` — Go CLI tool

## Key Paths
- `platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml` — App-of-Apps ApplicationSet
- `platform-gitops/helm-charts/base-service/` — chart used by every deployed service
- `platform-gitops/argo-workflows/cluster-templates/wft-deploy-service.yaml` — deploy workflow
- `platform-gitops/argo-workflows/config/vault-auth.yaml` — Vault auth for Argo Workflows

## Branch Protection Exception — Automated Bot Commits

The org-wide hard rule ("NEVER commit directly to main") does not apply to
two GitHub Actions workflows in this repo, which are designed to push
directly to `main` with no PR:

- `gitops-bump.yaml` — bumps `image.tag` in a service's `values.yaml` after
  a source-repo build succeeds.
- `release-deploy.yaml` — bumps `image.tag` after `mctl_deploy_service` /
  a release tag.

This is intentional: both use their own scoped `GITHUB_TOKEN` with
`contents: write` and only ever touch a single `image.tag` field, which is
the same class of change the human "trivial changes — merge immediately"
rule already allows to skip review. Requiring a PR (and therefore a human
or Claude review) for every automated image bump would add review latency
to the deploy path without a corresponding safety benefit.

Everything else — any change to templates, RBAC, resource limits, secrets
wiring, or ApplicationSet/Application specs — still goes through a feature
branch and a PR, reviewed by `claude-review.yml` and validated by
`validate-manifests.yml`, same as any other repo.

## Common Operations

### Deploy a new image tag
Use `mctl_deploy_service` MCP tool or the `release-deploy.yaml` GitHub Actions workflow.
Manual: edit `platform-gitops/services/<team>/<service>/values.yaml`, bump `image.tag`.

### Add a new service
1. Copy an existing `platform-gitops/services/<team>/<service>/` directory
2. Update `values.yaml`: `image.repository`, `image.tag`, `ingress.host`, resource limits
3. Add `catalog-info.yaml` for Backstage
4. ArgoCD picks it up automatically via the ApplicationSet

### Add a new tenant
Use the Backstage scaffolder template at `platform-gitops/backstage/templates/create-tenant/`
or run the `wft-create-tenant` workflow directly.

### Update Argo Workflow templates
After merging, wait ~3 min for ArgoCD to sync before triggering a workflow —
Argo snapshots templates at submit time.

## Secrets Management

All secrets follow this pattern:
1. Secret lives in Vault at `secret/data/teams/<team>/<service>/<key>`
2. An `ExternalSecret` in `platform-gitops/services/<team>/<service>/` references the Vault path
3. The ESO operator syncs it to a Kubernetes Secret in the tenant namespace

Never put secret values in YAML. Use `${{ secrets.VAULT_TOKEN }}` in GHA only.

## Terraform (k3s-preview cluster)

See `infrastructure/k3s-preview/README.md` for full runbook.
Quick ops: `terraform plan -var-file=terraform.tfvars` then `terraform apply`.
State backend: Cloudflare R2 bucket `mctl-terraform-state`, key `k3s-preview/terraform.tfstate`.

## Testing & Validation

```bash
# Helm lint internal charts
helm lint platform-gitops/helm-charts/base-service
helm lint platform-gitops/helm-charts/tenant

# Dry-run a service template render
helm template test platform-gitops/helm-charts/base-service \
  -f platform-gitops/services/labs/mctl-telegram/values.yaml

# Terraform validate (no credentials needed)
cd infrastructure/k3s-preview && terraform validate
```
