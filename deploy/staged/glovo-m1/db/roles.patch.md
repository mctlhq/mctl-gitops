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

## Migrator exit codes and flags (mctl-api#1004 design section 1)

`cmd/glovo-migrate` exits 1 when any read failed or returned a malformed result
(outranks everything: an unobserved state is never reported as clean or as a
foreign owner), 3 when observed but wrong (connecting role is not the expected
migrator, a named role is missing, a CREATE privilege is absent), 2 when
foreign-owned objects were observed (it prints the operator transfer text and
issues no DDL). Precedence: 1, then 3, then 2. `-migrator-role` (default
`glovo_migrator`) names the expected migrator; there is no env override.

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
for the operator and exits 2 on a foreign-owned object; exit codes 1 and 3
are described in "Migrator exit codes and flags" above).

0. Assume nothing about existing production objects or owners. Make a complete,
   source-backed catalogue inventory, read-only: for every object that
   `ApplySchema` and the selected `-with-*` steps check (13 `genericRelations`,
   2 `genericFunctions`, `work_item_intents_id_seq`, schema `glovo` if present,
   bridge `ownedRelations` and `bridge_command_transitions_id_seq` if present),
   record the owner (`pg_class.relowner`, `pg_proc.proowner`,
   `pg_namespace.nspowner`) and the full ACL (`aclexplode`) with every grantee.
   An unexpected grantee or owner stops the step.
1. Record the pre-change ACL and owner of each object (rollback needs it).
2. Pre-create the version table (approach proposed by #1004, "chosen", still
   REQUIRES owner/operator confirmation; the operator has not confirmed it).
   Only `ApplySchema` creates `public.work_items_schema_version`, so production
   may have at most 12 of the 13 generic relations (UNVERIFIED; it depends on
   the running image, images before `d2cca35` never create it). The legacy pod,
   once a non-owner, needs the table to exist with exactly one row equal to the
   compiled version (1), readable by it, or a restart fails. As `mctl-api`,
   before the transfer: `CREATE TABLE IF NOT EXISTS
   public.work_items_schema_version (version INT NOT NULL)` plus one row `1`.
   It then moves with the other relations and `ApplySchema`'s ownership check
   passes. Residual risk: the row asserts version 1 before `ApplySchema` ran
   (the migration re-records the same value). Rejected alternative: grant
   SELECT only after the migration, inside a stated maintenance window with a
   freeze of legacy pod restarts and rollouts; if the operator prefers it, the
   runbook must state the window and the freeze.
3. Ownership transfer and transitional grants, in ONE transaction, by hand, by
   the operator, limited to the inventory of step 0. The order matters: a grant
   to the current owner is a no-op, and `ALTER ... OWNER TO` re-keys the old
   owner's ACL entry to the new owner, which would leave the legacy `mctl-api`
   role with nothing. So the grants follow the owner change:
   a. `ALTER ... OWNER TO glovo_migrator` for each object in scope, run by a
      role that is a member of both owners (see the prerequisites above).
   b. Then, still in the same transaction and as the new owner or a member of
      it, `GRANT ... TO "mctl-api"` without any REVOKE: the `genericGrants`
      privileges on each existing generic table (SELECT, INSERT, UPDATE; DELETE
      only on `agent_run_tokens`), SELECT on `work_items_schema_version`,
      USAGE on `work_item_intents_id_seq` (and any other sequence old pods or
      DevLoop use), EXECUTE on the functions they need, USAGE on schema
      `public`. Whether the legacy role needs more than `genericGrants` for
      DevLoop is UNVERIFIED; the inventory must confirm it.
   c. A sequence owned by a table does not move automatically with it
      (UNVERIFIED on this server): transfer and verify `work_item_intents_id_seq`
      explicitly (`pg_class.relowner`).
   If anything fails the transaction rolls back and the legacy role is
   unchanged.
4. Run the read-only verifier, which also probes the legacy role's EFFECTIVE
   privileges after the transfer: `cmd/glovo-migrate -verify` with
   `GLOVO_MIGRATION_DB_URL` (the operator-held `glovo_migrator` login; no
   `-confirm`, READ ONLY transaction, never mounted into the API pod). Output is
   `ok`, `diverged` or `unknown`; `unknown` outranks `diverged` and never
   counts as a pass. It runs after this gate, after the migration, and before
   wiring.
5. Only then may a separately authorized activation PR unsuspend the Job.

Rollback restores the RECORDED pre-change owner and full ACL (`relacl`, column
ACLs, sequence ACL) of step 1, object by object, owner first
(`ALTER ... OWNER TO mctl-api` by an operator with the needed memberships), then
the ACLs. It is not "revoke what was granted": it never issues `REVOKE` against
a role that is the restored owner (that would strip its owner privileges), and
no order is claimed safe without the record. Step 1 must also record whether
`public.work_items_schema_version` and schema `glovo` existed. If the migration
already ran, the operator drops or disables the `aar_guard` and
`aar_binding_required` triggers and the `glovo` objects BEFORE ownership returns
to `mctl-api` (a migrator-owned trigger would otherwise stay on a table it
owns); the version table, widened CHECK constraints and bridge tables are kept
(dispositions and UNVERIFIED points are in #1004 design section 9). Created roles
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
| Which of the 13 generic relations exist (version table at most 12 of 13 on older images) | `pg_class` owner listing |
| Whether the legacy role needs more than `genericGrants` for DevLoop | the inventory of step 0 |
| Sequence ownership after `ALTER TABLE ... OWNER TO` | `pg_class.relowner` of `work_item_intents_id_seq` after the transfer |
| `COMMERCE_DB_URL` role | see mctl-api-env.patch.md |
| Connection limits | see above |
| Image version production runs | deployed tag vs mctl-api `081bd6b7` |
