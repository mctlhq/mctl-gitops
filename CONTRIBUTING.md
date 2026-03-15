# Contributing to mctl-gitops

Thank you for your interest in contributing to mctl-gitops! This repository is the **GitOps source of truth** for the entire mctl platform, managed by [ArgoCD](https://argo-cd.readthedocs.io/).

## Prerequisites

Before contributing, make sure you have the following tools installed:

- [kubectl](https://kubernetes.io/docs/tasks/tools/) -- Kubernetes CLI
- [helm](https://helm.sh/docs/intro/install/) -- Helm package manager
- [argocd](https://argo-cd.readthedocs.io/en/stable/cli_installation/) -- ArgoCD CLI

## Repository Structure

```
mctl-gitops/
├── platform-gitops/
│   ├── apps/              # ArgoCD Application manifests
│   ├── services/          # Per-tenant service configurations
│   └── argo-workflows/    # Argo Workflow templates
├── infrastructure/        # Terraform modules and configurations
└── cli/                   # CLI tooling
```

- **`platform-gitops/apps/`** -- ArgoCD Application definitions that describe what should be deployed and where.
- **`platform-gitops/services/`** -- Per-tenant Helm values and Kubernetes manifests organized by tenant name.
- **`platform-gitops/argo-workflows/`** -- Reusable Argo Workflow templates for CI/CD pipelines.
- **`infrastructure/`** -- Terraform code for provisioning cloud infrastructure.

## YAML Conventions

- Use **2-space indentation** (no tabs).
- Add comments for any non-obvious configuration values.
- Keep manifests well-organized and consistent with existing files in the same directory.

## Secrets Policy

**Never hardcode secrets in this repository.** All sensitive values must be managed through:

- [HashiCorp Vault](https://www.vaultproject.io/) for secret storage.
- [ExternalSecrets Operator](https://external-secrets.io/) for syncing secrets into Kubernetes.

If your change requires a new secret, document the expected Vault path and create the corresponding `ExternalSecret` manifest.

## Commit Conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Please format your commit messages as:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Common types:

- `feat` -- A new feature or service configuration
- `fix` -- A bug fix
- `docs` -- Documentation changes
- `chore` -- Maintenance tasks (dependency updates, CI changes)
- `refactor` -- Code/config restructuring without behavior change

Examples:

```
feat(services): add redis cache for tenant acme
fix(apps): correct health check path for mctl-api
chore(infrastructure): upgrade Terraform AWS provider to 5.x
```

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`.
2. Make your changes following the conventions described above.
3. Ensure all YAML files are valid (`kubectl apply --dry-run=client` where applicable).
4. Open a pull request against `main`.
5. Fill out the PR template with a description of your changes.
6. Wait for review -- at least one maintainer approval is required.
7. PRs are merged via **squash merge** to keep the history clean.

## Getting Help

If you have questions or need guidance, feel free to open an issue or start a discussion in the repository.
