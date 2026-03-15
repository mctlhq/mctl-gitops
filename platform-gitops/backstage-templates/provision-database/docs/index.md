# Provision Database

Provisions a dedicated PostgreSQL database for your service on the shared CNPG cluster.

## When to use

Use this template when your service needs a PostgreSQL database and you didn't enable it during [Onboard Service](/create/templates/default/onboard-service), or you want to provision a database for a service that's already running.

## Inputs

| Field | Required | Description |
|---|---|---|
| Service | Yes | Select the service from the catalog — team and service name are read from catalog metadata automatically |

## What gets created

| Resource | Name |
|---|---|
| PostgreSQL role | `{team}-{app}` |
| PostgreSQL database | `{team}-{app}` |
| Vault secret | `teams/{team}/{app}/database` |
| Kubernetes ExternalSecret | `{team}-{app}-db-creds` |

### Injected environment variables

Once the ExternalSecret syncs to the pod, the following env vars are available:

```
DATABASE_URL   — postgresql://{user}:{password}@{host}:5432/{database}
DB_HOST        — cluster-internal hostname
DB_PORT        — 5432
DB_NAME        — {team}-{app}
DB_USER        — {team}-{app}
DB_PASSWORD    — auto-generated
```

## Viewing credentials

Open the service in the Backstage catalog and go to the **Database** tab. Credentials are shown masked with **Reveal** and **Copy** buttons — no direct Vault access required.

## Notes

- Databases use `reclaimPolicy: retain` — the database is preserved if the CNPG resource is accidentally deleted
- Connection limit per role: 10
- To rotate credentials, update the Vault secret and re-run this workflow
- This is safe to run on a service that already has a database — the workflow skips creation if the database already exists

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [CNPG cluster config](https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/cnpg-clusters/shared)
