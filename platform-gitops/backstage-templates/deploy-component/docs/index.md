# Onboard Service

Onboard a new service to the preview cluster — clone the repo, build the Docker image, and create the GitOps config.

## When to use

Use this template when you want to:
- Deploy a **new** service for the first time
- Deploy a background worker (no HTTP port / ingress needed)

> For deploying a new version of an **existing** service, use [Deploy Version](/create/templates/default/deploy-version) instead.

## Inputs

| Field | Required | Description |
|---|---|---|
| Team | ✅ | Your team name |
| GitHub Repository | ✅ | Source repo with your Dockerfile (e.g. `acme/payment-api`) |
| Dockerfile path | | Path to Dockerfile, default: `Dockerfile` |
| Git tag | | Tag to build, default: latest commit |
| Port | | HTTP port for web services (e.g. `8080`) |
| Ingress host | | Public hostname (e.g. `myteam-payment-api.mctl.ai`) — leave empty for workers |
| Provision DB | | Auto-provision PostgreSQL database and inject credentials |
| Skip health checks | | Skip liveness/readiness probes (recommended if `/healthz` not implemented yet) |
| Env vars | | Plaintext `KEY=value` pairs (stored in Kubernetes manifest) |
| Secret env vars | | Plaintext `KEY=value` pairs (stored in Vault, injected securely) |
| Repo PAT | | Fine-grained PAT with Contents:Read — only needed if GitHub App is not installed on the repo |

## What gets created

1. **GitOps files** in `mctl.ai/platform-gitops/services/{team}/{service}/`
   - `values.yaml` — Helm values for the service
   - `catalog-info.yaml` — Backstage catalog entry
2. **ArgoCD Application** — auto-syncs from GitOps files
3. **Docker image** — built in-cluster via Kaniko and pushed to GHCR
4. **Vault secrets** — if secret env vars provided
5. **PostgreSQL database** — if "Provision Database" is enabled

## Service types

- **Web service** (with port + host) — gets an Ingress and is publicly accessible
- **Background Service** (no port/host) — runs as a background process, no HTTP exposure

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [View deployed services in Catalog](/catalog?filters[kind]=component)
