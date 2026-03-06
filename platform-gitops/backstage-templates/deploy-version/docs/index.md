# Deploy Version

Build and deploy a new version of an existing service.

## When to use

Use this template when you want to:
- Release a new version of an already onboarded service
- Rebuild and deploy from a specific git tag
- Update env vars or secrets alongside a version bump

> For onboarding a **new** service, use [Onboard Service](/create/templates/default/onboard-service) instead.
> To update only env vars/secrets without rebuilding, use [Update Environment](/create/templates/default/update-environment).

## Inputs

| Field | Required | Description |
|---|---|---|
| Service | ✅ | Select the deployed service from the catalog |
| Version Tag | | Select a git tag from the source repo, or leave empty for auto-increment |
| Env vars | | Plaintext `KEY=value` pairs — leave empty to keep current values |
| Secret env vars | | Secure `KEY=value` pairs — leave empty to keep current values |

## How it works

1. Reads the **source repo** from the service's catalog annotations (`github.com/source-repo`)
2. Fetches available **git tags** from that repo so you can pick a version
3. Shows **current env vars and secrets** so you know what's already configured
4. Dispatches the `release-service.yml` workflow with `action: deploy`
5. The workflow clones the source repo, builds a new Docker image, and updates the image tag in GitOps

## Notes

- The source repo is read from the `github.com/source-repo` catalog annotation. If this annotation is missing on your service, the deployment will fail — contact your platform team to add it to the `catalog-info.yaml`
- Version auto-increment reads the latest image tag from GHCR and bumps the patch version

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [View deployed services in Catalog](/catalog?filters[kind]=component)
