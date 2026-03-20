# Deploy Version

Build and deploy a new version of an existing service.

## When to use

- Releasing a new version of an already onboarded service
- Deploying from a specific git tag
- Updating env vars or secrets alongside a version bump

> To onboard a **new** service for the first time, use [Onboard Service](/create/templates/default/onboard-service) instead.
> To update only env vars/secrets without a rebuild, use [Update Environment](/create/templates/default/update-environment).

## Inputs

### Service & Version

| Field | Required | Description |
|---|---|---|
| Service | Yes | Select the deployed service from the catalog |
| Tag | | Select a git tag from the source repo. Leave empty to auto-increment from the latest deployed version. |

### Environment

| Field | Description |
|---|---|
| Environment Variables | `KEY=VALUE` pairs, one per line. Leave empty to keep current values unchanged. |
| Secure Variables | `KEY=VALUE` pairs, one per line. Leave empty to keep current secrets unchanged. |

## How it works

1. Reads the **source repo** from the service's catalog annotation (`github.com/source-repo`)
2. Fetches available **git tags** from that repo for version selection
3. Shows **current env vars and secrets** so you can see what's already configured
4. Submits the `deploy-service` WorkflowTemplate with `action: deploy`
5. The workflow updates the image tag in GitOps

ArgoCD picks up the GitOps change and rolls out the new version automatically (~2-3 min).

## Notes

- The source repo is read from the `github.com/source-repo` catalog annotation on the service — if missing, the deployment will fail. Contact the platform team to add it to the service's `catalog-info.yaml`.
- Tag auto-increment reads the latest image tag from GHCR and bumps the patch version (e.g. `1.2.3` → `1.2.4`)
- Env var and secret fields replace the full set of current values — include all vars you want to keep

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [View deployed services in Catalog](/catalog?filters[kind]=component)
