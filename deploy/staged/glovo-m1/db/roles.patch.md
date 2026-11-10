# shared-pg changes for the Glovo roles (text only, not applied)

Target files are reconciled and are NOT touched here. Applying them needs the
two Vault secrets of `externalsecrets.yaml` to exist first, and the leak guard
in `scripts/validate-glovo-m1-staging.py` to be relaxed for that PR (it
refuses the word glovo under `platform-gitops/`). Both are activation steps.

## `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml`

`spec.managed.roles`, appended. Attributes are R1 and R2 of mctl-api#957 design
6d.1: not superuser, no `CREATEROLE`, no `CREATEDB`, no `BYPASSRLS`, no
replication. The names are the defaults of `runtimeRole` / the migration role.

    - name: glovo_runtime
      login: true
      inherit: false
      superuser: false
      createdb: false
      createrole: false
      replication: false
      bypassrls: false
      connectionLimit: 16          # one shared pool of 8 x 2 replicas (DB_POOL_MAX_CONNS)
      ensure: present
      passwordSecret:
        name: glovo-runtime-db-creds
    - name: glovo_migrator
      login: true
      inherit: false
      superuser: false
      createdb: false
      createrole: false
      replication: false
      bypassrls: false
      connectionLimit: 2
      ensure: present
      passwordSecret:
        name: glovo-migrator-db-creds

`spec.postgresql.pg_hba`, inserted before the final reject-all. `<database>` is
OPEN (see the PR body); it must be the database that already holds the bridge,
work-items and commerce tables:

    - host <database> glovo_runtime all scram-sha-256
    - host <database> glovo_migrator all scram-sha-256

No new `Database` CR: owner decision A puts Glovo in one existing physical
database, so the roles are granted into it by `ApplySchema`, not by CNPG.
`ApplySchema` also owns every grant; CNPG managed roles carry attributes only.

## Read-only check for the activation PR (no Secret data read)

    kubectl -n platform-db get cluster shared-pg -o jsonpath='{.spec.managed.roles[*].name}'
    SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication
      FROM pg_roles WHERE rolname IN ('glovo_runtime','glovo_migrator');
