# 🚀 Release Service

Builds and deploys your service to the preview cluster.

## When to use

Use this template when you want to:
- Deploy a new service for the first time
- Release a new version of an existing service
- Deploy a background worker (no HTTP port / ingress needed)

## Inputs

| Field | Required | Description |
|---|---|---|
| Team | ✅ | Your team name |
| Service name | ✅ | Slug for the service (e.g. `payment-api`) |
| Source repo | ✅ | GitHub repo with your Dockerfile (e.g. `acme/payment-api`) |
| Dockerfile path | | Path to Dockerfile, default: `Dockerfile` |
| Git tag | | Tag to build, default: latest commit |
| Port | | HTTP port for web services (e.g. `8080`) |
| Ingress host | | Public hostname (e.g. `payment-api.preview.mctl.me`) — leave empty for workers |
| Env vars | | Plaintext `KEY=value` pairs (stored in Kubernetes manifest) |
| Secret env vars | | Plaintext `KEY=value` pairs (stored in Vault, injected securely) |

## What gets created

1. **GitOps files** in `mctl.me/platform-gitops/services/preview/{team}/{service}/`
   - `values.yaml` — Helm values for the service
   - `catalog-info.yaml` — Backstage catalog entry
2. **ArgoCD Application** — auto-syncs from GitOps files
3. **Docker image** — built and pushed to GHCR
4. **Vault secrets** — if secret env vars provided

## Service types

- **Web service** (with port + host) — gets an Ingress and is publicly accessible
- **Worker** (no port/host) — runs as a background process, no HTTP exposure

## Links

- [GitHub Actions workflow](https://github.com/dmitriimashkov/mctl.me/actions/workflows/release-service.yml)
- [View deployed services in Catalog](/catalog?filters[kind]=component)
