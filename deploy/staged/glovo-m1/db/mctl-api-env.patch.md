# mctl-api env for Glovo (text only, not applied)

Target: `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`
(`env:` next to `AUDIT_DB_URL`, and `envFromOptionalSecrets`). Not touched here:
today the file sets only `AUDIT_DB_URL`, and `bridgeStoreDSN` reads only
`COMMERCE_DB_URL`, which is unset, so the bridge is off.

    envFromOptionalSecrets:
      - mctl-api-glovo-runtime-db        # optional: the pod boots without it

    env:
      GLOVO_DB_URL: "postgresql://$(GLOVO_DB_USER):$(GLOVO_DB_PASSWORD)@shared-pg-rw.platform-db.svc:5432/<database>?sslmode=require"
      WORK_ITEMS_DB_URL: "<same database, role that owns the work-items tables today>"
      COMMERCE_DB_URL: "<same database, role that owns the commerce tables today>"

The last two are not guessed here: each must keep the role the existing
consumers use (design 6d.1 R3), and setting `COMMERCE_DB_URL` is what would
switch the command bridge from 503 to enabled if `MCTL_BRIDGE_ENABLED` is
ever on. Owner decision first (see the PR body).

## Flags that stay off (all absent today, none is added)

`GLOVO_ENABLED`, `GLOVO_JOIN_ENABLED`, `MCTL_GLOVO_CONTROL_ENABLED`,
`MCTL_BRIDGE_ENABLED`. `GLOVO_TEAM_FALLBACK` does not exist any more and is
not added. Until the roles, secrets and migration have run, the deployment
keeps today's `NewStore` path (`bridge_schema_version` row absent).
