# LLMS.md — mctl-gitops Platform Source of Truth

> `mctl-gitops` is the GitOps source of truth for the mctl.ai platform. It defines Helm values for services, Argo Workflows cluster templates, Terraform preview cluster infrastructure, and canonical development rules in `AGENTS.md`.

## Workspace Rules (`AGENTS.md`)

- **Strict Branch & PR Policy**: **NEVER commit directly to `main`**. Every change must flow through a feature branch (`feat/`, `fix/`, `docs/`, `chore/`) and a PR.
- **Merge Strategy**: Always merge with `gh pr merge <N> --merge --delete-branch` (merge commit pattern, never `--squash`).
- **Semantic Versioning & Tags**: Version format `MAJOR.MINOR.PATCH` without `v` prefix (e.g. `1.2.0`, except `mctl-openclaw` upstream forks).

## Structure & Layout

- `platform-gitops/argo-workflows/cluster-templates/`: ClusterWorkflowTemplate and CronWorkflow manifests (`cwft-mctl-agents-*.yaml`, `cronworkflow-mctl-agents-*.yaml`).
- `platform-gitops/services/<tenant>/`: Per-tenant Helm values (`values.yaml`, `catalog-info.yaml`).
- `platform-gitops/platform-skills/catalog/`: Platform skills source of truth (read by MCP clients and AI assistants).
- `infrastructure/k3s-preview/`: Local/preview K3s cluster kubeconfig and bootstrap manifests.

## Key Workflow Patterns

- **CronWorkflows**: Thin wrappers running on fixed cron schedules (`concurrencyPolicy: Forbid`).
- **Synchronization**: Workflows mutating Git state use the `mctl-gitops-main-writes` Argo mutex.
