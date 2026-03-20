# Onboard Service

First-time setup for a new service — commits GitOps config and deploys to your team's namespace.

## When to use

- Deploying a **new** service for the first time
- Onboarding a background worker (no HTTP port or ingress needed)

> To deploy a new version of an **already onboarded** service, use [Deploy Version](/create/templates/default/deploy-version) instead.

## Inputs

### Service & Source

| Field | Required | Description |
|---|---|---|
| Team | Yes | Your team name |
| GitHub Repository | Yes | Source repo containing the Dockerfile (e.g. `acme/payment-api`) |
| Dockerfile Path | | Path to the Dockerfile, default: `Dockerfile` |
| Tag | | Git tag to checkout and build. Leave empty to build from HEAD. |

### Networking

| Field | Description |
|---|---|
| Port | HTTP port exposed by the container (e.g. `8080`). Required for web services. |
| Ingress Host | Public hostname (e.g. `myteam-myapp.mctl.ai`). Leave empty for background workers — no ingress will be created. |
| Skip Health Checks | Skip liveness/readiness probes. Recommended during onboarding if `/healthz` is not yet implemented. |

### Database

| Field | Default | Description |
|---|---|---|
| Provision PostgreSQL Database | off | Create a dedicated database with Vault-backed credentials auto-injected as env vars (`DATABASE_URL`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`). Safe to enable — skips if database already exists. |

### Environment

| Field | Description |
|---|---|
| Environment Variables | `KEY=VALUE` pairs, one per line. Stored as plaintext in GitOps manifests — do not put secrets here. |
| Secure Variables | `KEY=VALUE` pairs, one per line. Stored in Vault, never written to Git. |



## What gets created

1. **GitOps files** committed to `mctl-gitops` under `platform-gitops/services/{team}/{service}/`:
   - `values.yaml` — Helm values (image, port, ingress, env vars, secrets reference)
   - `catalog-info.yaml` — Backstage catalog entry
3. **ArgoCD Application** — auto-syncs GitOps files to the cluster
4. **Vault secrets** — created at `teams/{team}/{service}/env` if secret vars provided
5. **PostgreSQL database** — if "Provision Database" is enabled (see [Provision Database](/create/templates/default/provision-database))

## Service types

| Type | When | What gets created |
|---|---|---|
| Web service | Port + Host provided | Deployment + Service + Ingress with TLS |
| Background worker | No port/host | Deployment only, no network exposure |

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [View deployed services in Catalog](/catalog?filters[kind]=component)
