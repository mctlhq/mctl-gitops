# mctl-gitops

GitOps repository. ArgoCD source of truth for the entire mctl platform.

**Note:** This repo is being renamed from `mctl-gitops` to `mctl-gitops`.

## Stack
- Kubernetes manifests, Helm charts, Argo Workflows, Terraform
- ArgoCD watches this repo and reconciles cluster state

## Conventions
- YAML: 2-space indentation
- Helm templates: use `{{- ... }}` for whitespace control
- No hardcoded secrets — use Vault + ExternalSecrets
- Every platform change = git commit here
- Comments to explain non-obvious configuration

## Structure
- `platform-gitops/apps/` — ArgoCD Application definitions (App-of-Apps pattern)
- `platform-gitops/services/` — per-tenant service configurations
- `platform-gitops/argo-workflows/` — workflow templates and CronWorkflows
- `platform-gitops/backstage-templates/` — Backstage scaffolder templates
- `infrastructure/` — Terraform, cluster bootstrap
- `cli/mctl/` — Go CLI tool

## Key Paths
- `platform-gitops/apps/values.yaml` — App-of-Apps source URL
- `platform-gitops/apps/templates/backstage.yaml` — Backstage deployment config
- `platform-gitops/argo-workflows/workflow-templates/tpl-git-commit.yaml` — base git commit template
