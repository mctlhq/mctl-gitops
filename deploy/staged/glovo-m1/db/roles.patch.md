# shared-pg changes for the Glovo roles (text only, not applied)

Target files are reconciled and are NOT touched here. Applying them needs the
three Vault secrets of `externalsecrets.yaml` to exist first, and the leak guard
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
      connectionLimit: 16          # UNVERIFIED, see "Connection limits"
      ensure: present
      passwordSecret:
        name: glovo-runtime-db-creds
    - name: mctl_api_workitems       # D1: DML only; no DDL, no ownership
      login: true
      inherit: false
      superuser: false
      createdb: false
      createrole: false
      replication: false
      bypassrls: false
      connectionLimit: 8           # UNVERIFIED sizing, see "Connection limits"
      ensure: present
      passwordSecret:
        name: workitems-db-creds
    - name: glovo_migrator
      login: true
      inherit: false
      superuser: false
      createdb: false
      createrole: false
      replication: false
      bypassrls: false
      connectionLimit: 2           # UNVERIFIED, see "Connection limits"
      ensure: present
      passwordSecret:
        name: glovo-migrator-db-creds

`spec.postgresql.pg_hba`, inserted before the final reject-all. Entries are
role-specific, so each of the three roles needs its own line. The database is
`mctl-api`, the existing database on `shared-pg` that already holds the
work-items tables (it is also the database of `AUDIT_DB_URL`):

    - host mctl-api glovo_runtime all scram-sha-256
    - host mctl-api glovo_migrator all scram-sha-256
    - host mctl-api mctl_api_workitems all scram-sha-256

No new `Database` CR: owner decision A puts Glovo in one existing physical
database, so the roles are granted into it by `ApplySchema`, not by CNPG.
`ApplySchema` also owns every grant; CNPG managed roles carry attributes only.

## Read-only check for the activation PR (no Secret data read)

    kubectl -n platform-db get cluster shared-pg -o jsonpath='{.spec.managed.roles[*].name}'
    SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication
      FROM pg_roles WHERE rolname IN ('glovo_runtime','glovo_migrator','mctl_api_workitems');

## Connection limits: UNVERIFIED, activation blocker

The limits 16 (`glovo_runtime`), 2 (`glovo_migrator`) and 8
(`mctl_api_workitems`) are placeholders of this staging, not confirmed by the
#1004 amendment. mctl-api sizes one pool per distinct `*_DB_URL` per replica
(`DB_POOL_MAX_CONNS`, default 8, plus 3 unpooled connections), so the correct
figure depends on replica count and rolling-update surge. Required read-only
evidence before activation: deployed `replicaCount` and surge, the
`pgshared: pools` startup log line, `mctl_api_db_pool_max_conns`, and the
current `rolconnlimit` of the legacy role (`SELECT rolname, rolconnlimit FROM
pg_roles`).

## Privileges the roles themselves need (operator step, un-applied)

CNPG managed roles carry attributes only; `ApplySchema` owns the table grants.
Two prerequisites sit outside the code:
- `glovo_migrator` needs `CREATE` on database `mctl-api` (for `CREATE SCHEMA
  glovo`) and `CREATE` on schema `public` (for the version table and new
  objects).
- An operator `ALTER TABLE ... OWNER TO glovo_migrator` requires the new owner
  to hold `CREATE` on the schema and the operator to be able to `SET ROLE` to
  it (role membership that permits `SET`), or to act as a break-glass
  identity. Decide the mechanism with the operator; nothing here grants it.

## Operator plan: transitional grants and ownership transfer (documented, NOT applied)

Separately authorized deployment gate (#1004 design section 10, step 2). This
text is a plan, not a manifest; no script or Job in this PR performs it, and no
`ALTER ... OWNER TO` is ever automatic (`cmd/glovo-migrate` only prints the text
for the operator and exits 2 on a foreign-owned object).

0. Assume nothing about existing production objects or owners. Make a complete,
   source-backed catalogue inventory, read-only: for every object that
   `ApplySchema` and the selected `-with-*` steps check (13 `genericRelations`,
   2 `genericFunctions`, `work_item_intents_id_seq`, schema `glovo` if present,
   bridge `ownedRelations` and `bridge_command_transitions_id_seq` if present),
   record the owner (`pg_class.relowner`, `pg_proc.proowner`,
   `pg_namespace.nspowner`) and the full ACL (`aclexplode`) with every grantee.
   An unexpected grantee or owner stops the step.
1. Record the pre-change ACL and owner of each object (rollback needs it).
2. Transitional grants to the legacy `mctl-api` role, BEFORE any transfer, so
   the unchanged production DSN keeps working across it without a deploy:
   DML equal to `genericGrants` on the tables (DELETE only on
   `agent_run_tokens`), USAGE on `work_item_intents_id_seq` (and any other
   sequence old pods or DevLoop use), EXECUTE on the 2 functions, USAGE on
   schema `public`, and SELECT on `public.work_items_schema_version`.
   OPEN OPERATOR DECISION (not decided here): `work_items_schema_version` may
   not exist in production (UNVERIFIED; it depends on the running image).
   Either pre-create it as the legacy owner before the transfer, or grant
   SELECT right after the migration inside a maintenance window. Without it the
   old pod fails `verifySchemaVersion` once it is a non-owner.
3. Ownership transfer limited to the inventory of step 0, by hand, by the
   operator. Afterwards check `pg_class.relowner` of `work_item_intents_id_seq`
   (UNVERIFIED whether it follows its table).
4. Run the read-only grants verifier (design section 8); `unknown` never counts
   as a pass.
5. Only then may a separately authorized activation PR unsuspend the Job.

Rollback restores the RECORDED pre-change ACL and owner of step 1, object by
object. It never issues a blanket `REVOKE` against an owner, and created roles
stay in place (dropping one needs `DROP OWNED` / `REASSIGN OWNED`, a separate
operator decision). The transitional grant is revoked only after the later
switch to `mctl_api_workitems` is confirmed healthy.

The bridge, glovo, orders and join `-with-*` steps are required before
activation, because `control.ProveOneDatabase` uses the work-items pool.

## UNVERIFIED, with the read-only evidence required

| Item | Evidence |
| --- | --- |
| Which bridge tables or schema `glovo` exist in production, and their owners | the inventory of step 0 |
| Other work-items consumers (DevLoop, agents, other pods) under a role other than `mctl-api` | grantees of the 13 relations (`aclexplode`) and `pg_stat_activity` by `usename` |
| Sequence ownership after `ALTER TABLE ... OWNER TO` | `pg_class.relowner` of `work_item_intents_id_seq` after the transfer |
| `COMMERCE_DB_URL` role | see mctl-api-env.patch.md |
| Connection limits | see above |
| Image version production runs | deployed tag vs mctl-api `081bd6b7` |
