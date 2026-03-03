# 🗄️ Provision Database

Provisions a dedicated PostgreSQL database for your service.

## When to use

Use this template when your service needs a PostgreSQL database. It provisions a database on the shared CNPG cluster and makes credentials available as a Kubernetes secret.

> Run this **after** deploying your service with the Release Service template.

## Inputs

| Field | Required | Description |
|---|---|---|
| Service | ✅ | Select the service from your catalog (uses the service name and team from catalog metadata) |

## What gets created

| Resource | Name |
|---|---|
| PostgreSQL role | `{team}-{app}` |
| PostgreSQL database | `{team}-{app}` |
| Kubernetes secret | `{team}-{app}-db-creds` |
| Vault secret | `teams/{team}/{app}/database` |

### Kubernetes secret fields

The secret `{team}-{app}-db-creds` contains:

```
host      — cluster internal hostname
port      — 5432
database  — {team}-{app}
username  — {team}-{app}
password  — auto-generated
url       — full postgresql:// connection string
```

Mount it in your deployment as environment variables or a volume.

## Viewing credentials

After provisioning, open the service in the Backstage catalog and go to the **Database** tab. Credentials are displayed masked (`••••••••`) with **Reveal** and **Copy** buttons — no direct Vault access required.

## Notes

- The database uses `databaseReclaimPolicy: retain` — the database survives accidental CRD deletion
- Connection limit per role: 10 (increase via support request)
- Credentials are rotated by updating the Vault secret and re-running the workflow

## Links

- [Argo Workflows UI](https://workflows.mctl.me)
- [CNPG cluster config](https://github.com/mctlhq/mctl-core/tree/main/platform-gitops/cnpg-clusters/shared)
