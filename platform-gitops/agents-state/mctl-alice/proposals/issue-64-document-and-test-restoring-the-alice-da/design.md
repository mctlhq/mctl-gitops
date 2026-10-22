# Design: issue-64-document-and-test-restoring-the-alice-da

## Current state

### Application storage (clone at `34f5e31`, release 2.2.6)

- `src/storage/index.ts` selects `PostgresStorage` and `PostgresTelemetryStorage`
  when `DATABASE_URL` or `PGHOST` is set; otherwise it uses SQLite.
- `src/storage/postgres-storage.ts` `initTables()` creates the schema
  idempotently with `CREATE TABLE IF NOT EXISTS`. The tables are
  `browser_transactions`, `users`, `user_credentials`, `web_sessions`,
  `quasar_proxy_scenarios`, `oauth_clients`, `oauth_pending`, `oauth_codes` and
  `oauth_tokens`, plus `telemetry_samples` (line ~848). There is no migration
  table, so a `pg_dump` of the schema and data restores cleanly, and app startup
  will not fight with it.
- Hashed-secret state. In the same transaction, `initTables()` counts values not
  prefixed with `SECRET_DIGEST_PREFIX` (`"sha256:"`, `src/storage/crypto.ts:174`)
  in `oauth_tokens.access_token`, `oauth_tokens.refresh_token`,
  `oauth_codes.code`, `web_sessions.session_hash` and `browser_transactions.key`.
  It rewrites them only when `REHASH_STORED_SECRETS=true`.
- Credential encryption. `src/storage/crypto.ts` uses AES-256-GCM with the owner
  id as AAD. There are two envelopes: `v1:` under `ENCRYPTION_KEY`, and
  `v2:<id>:` under `ENCRYPTION_KEYS`/`ENCRYPTION_KEY_ID`. `getEncryptionKey()`
  falls back to a development key unless `NODE_ENV=production` and
  `AUTH_REQUIRED=true`.
- `src/storage/credential-rotation.ts` declares `ENCRYPTED_COLUMNS` for
  `user_credentials`, `oauth_tokens` and `oauth_codes`. `staleRowsQuery()`,
  `staleRowsParams()` and `rotateRow(..., rewrite=false, counts)` already
  implement a read-only "stale / undecryptable" count. `PostgresStorage.rotateCredentials()`
  runs them after start, but only when an active key id exists. Without one it
  returns `null`, so today nothing reports `v1` decryption failures.
- The README sections "Upgrading to hashed secrets" and "Rotating the
  encryption key" (step 4: "Keep a copy of it until the backups taken before
  step 3 have aged out") are the only text about backups. There is no `docs/`
  runbook; `docs/` holds only `plans/` and `portal-allowlist.json`.
- Tests. `tests/hosted-postgres.test.ts` runs against a real disposable
  PostgreSQL when `TEST_POSTGRES_URL` is set. It creates a per-test schema via
  `search_path` and is otherwise skipped. `tests/postgres-storage.test.ts` mocks
  the pool.
- `Dockerfile` ships only `dist/` (compiled from `src/`, `tsconfig.json`
  `rootDir: ./src`) and `public/`, so any operator tool must live under `src/`
  to be present in the running image.

### Deployed state checked

- `mctl_get_service_status(labs, mctl-alice)` showed ArgoCD app
  `labs-mctl-alice` Healthy/Synced, image tag `2.2.6`, host `alice.mctl.ai`,
  `hasDatabase: true`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-alice/values.yaml` showed
  `replicaCount: 1`, RollingUpdate (`maxUnavailable: 0`, `maxSurge: 1`),
  `NODE_ENV=production`, `AUTH_REQUIRED=true`, `envFrom` secrets
  `mctl-alice-secrets` (`ENCRYPTION_KEY`, Yandex client values) and
  `labs-mctl-alice-db-creds` (`DATABASE_URL`, `DB_*`). It sets no
  `ENCRYPTION_KEYS` or `ENCRYPTION_KEY_ID`, so production stores `v1`
  envelopes under `ENCRYPTION_KEY`. A comment says the SQLite data was backed up
  out of band before the move to Postgres.
- `infra-components/data/cnpg/shared/cluster.yaml` (read-only; path is outside the
  provided `platform-gitops/` subset but present in the checkout): Cluster
  `shared-pg`, PostgreSQL 17.11, 2 instances, `enableSuperuserAccess: false`,
  cluster-wide `statement_timeout: 60s`, `backup.barmanObjectStore` with gzip WAL
  and data, `retentionPolicy: "14d"`, `target: prefer-standby`. The managed role is
  `labs-mctl-alice` (connection limit 10, password from
  `labs-mctl-alice-db-creds`), and the pg_hba line
  `host labs-mctl-alice labs-mctl-alice all scram-sha-256` lets that role reach
  only the database of the same name. Object-store endpoint and path were
  deliberately not copied into this proposal.
- `infra-components/data/cnpg/shared/scheduled-backup.yaml`: ScheduledBackup
  `shared-pg-daily`, 02:00 UTC daily.
- `infra-components/data/cnpg/shared/databases.yaml`: CNPG `Database`
  `labs-mctl-alice-db` → database `labs-mctl-alice`, owner `labs-mctl-alice`,
  `databaseReclaimPolicy: retain`.
- `argo-workflows/cluster-templates/wft-provision-database.yaml`: the database
  name is `${TEAM}-${APP}`, and `DATABASE_URL` is assembled from the Vault
  properties host, port, database, username and password.
- Not checked: the cluster's actual database sizes, the age of the oldest
  available base backup, and whether the latest ScheduledBackup succeeded. The
  read-only tools available did not expose them, and they are recorded under
  Open questions. They are inputs the exercise log will capture.

## Proposed solution

There are three deliverables. Only the first two are code or documentation in
this repo.

### 1. Runbook `docs/runbooks/restore-database.md`

A procedure with one `kubectl`/`psql` command block per step. Placeholders
like `<scratch-ns>` and `<target-time>` stand in for values, and resources are
named only by their public resource names (`shared-pg`, `labs-mctl-alice`,
`labs-mctl-alice-db-creds`). There are no hostnames, bucket or path names,
endpoint URLs, or Vault paths. The runbook tells the operator to copy the
`barmanObjectStore` block from the live Cluster spec instead of reproducing it.

1. **Decide the target.** Pick a UTC recovery time. It must fall within the
   retention window (14 days) and after the earliest available base backup.
   List backups with `kubectl get backups -n <db-ns>`. Note the time the
   incident started.
2. **Scratch recovery cluster.** Create `<scratch-ns>` and copy the read
   credential secret for the object store into it. Apply a `Cluster` named, for
   example, `alice-restore` with:
   - `bootstrap.recovery.source: shared-pg-origin` and
     `recoveryTarget.targetTime: <target-time>`;
   - `externalClusters[0]` named `shared-pg-origin`, whose `barmanObjectStore`
     is copied from the live cluster with `serverName: shared-pg`;
   - **no `spec.backup` section** (a hard rule, called out in a warning box).
     A recovered cluster that archives to the same `serverName` path would
     overwrite the production WAL timeline;
   - `instances: 1`, the same image digest as `shared-pg`, and a storage size
     matching the live cluster's.
   Wait for `Cluster` to report healthy. Confirm the recovered point with
   `SELECT pg_last_xact_replay_timestamp()`, or from the recovery log.
3. **Dump only alice.** Inside the scratch primary pod, as the local
   `postgres` user, run:
   `PGOPTIONS='-c statement_timeout=0' pg_dump -Fc --no-owner --no-acl -d labs-mctl-alice -f /var/lib/postgresql/data/alice.dump`.
   Record the per-table counts (`SELECT relname, n_live_tup ...`, or exact
   `count(*)` for the alice tables). The dump never leaves the cluster
   network. It is copied with `kubectl cp` between pods only, or streamed
   directly with `pg_dump | pg_restore` over `kubectl exec` pipes.
4. **Fresh database.** On `shared-pg` (production restore) or on the scratch
   cluster (exercise), as local `postgres` in the primary pod, run
   `CREATE DATABASE "labs-mctl-alice-restore" OWNER "labs-mctl-alice"`, then
   `pg_restore --no-owner --no-acl --role=labs-mctl-alice -d labs-mctl-alice-restore`
   with `PGOPTIONS='-c statement_timeout=0'` (the cluster default of 60s would
   cancel large `COPY`s). With `--role`, every object ends up owned by the app
   role, which is what `CREATE TABLE IF NOT EXISTS` in `initTables()` expects.
   This database is not declared in gitops. The CNPG `Database` resource and
   pg_hba keep pointing at the name `labs-mctl-alice`.
5. **Verify before the switch.** Run the new check (deliverable 2) against the
   restored database. Pass it the app's real key through the existing secret,
   from a one-off pod in the `labs` namespace:
   `kubectl run ... --env-from=secret/mctl-alice-secrets -- node dist/restore-check.js`
   with `DATABASE_URL` pointing at `labs-mctl-alice-restore`. During this step
   only, a temporary pg_hba line is needed, or the check runs as local
   `postgres` with `--as-role labs-mctl-alice`, which uses `SET ROLE` to test
   grants. The runbook uses the second option, so no gitops change is needed.
   Compare the counts with step 3.
6. **Switch over.** Scale `labs-mctl-alice` to 0 (`kubectl scale`, then let
   ArgoCD self-heal back after step 6c, or pause auto-sync for the window).
   Terminate leftover sessions with `pg_terminate_backend` for `datname =
   'labs-mctl-alice'`. Then:
   `ALTER DATABASE "labs-mctl-alice" RENAME TO "labs-mctl-alice-pre-restore-<yyyymmdd>"`;
   `ALTER DATABASE "labs-mctl-alice-restore" RENAME TO "labs-mctl-alice"`.
   Scale back to 1. `DATABASE_URL`, pg_hba and the CNPG `Database` (matched by
   name) are unchanged, so no secret or gitops edit is needed. That is why
   this approach was chosen.
7. **Verify live.** `/readyz` returns 200. The startup log carries no
   "cannot be decrypted with any configured key" line and no "still in clear
   text" line (messages in `credential-rotation.ts` / `postgres-storage.ts`).
   A test account can open `/account` and list devices. Re-run the check
   against `labs-mctl-alice`.
8. **Clean up.** Delete the scratch `Cluster`, its PVCs, the namespace and
   every dump file. Keep `-pre-restore-<date>` for a stated period (default 7
   days), then drop it with `DROP DATABASE`. Record the drop in the log.
9. **Rollback of a switch-over.** Reverse the two renames while scaled to zero.

The runbook also has a "What to check after a restore" section. It maps each
check to the user-visible risk:
- users / user_credentials counts match the source at the target time;
- tables owned by `labs-mctl-alice`;
- credentials decrypt with the *current* key;
- the key must be the one that was active at the target time; old keys are kept
  while backups need them (README key-rotation step 4);
- no clear-text bearer secrets. A restore to a time before 2.2.3 would bring
  them back, and the runbook says to set `REHASH_STORED_SECRETS=true` once;
- restored MCP tokens and sessions issued after the target time are lost, so
  users who connected after it must reconnect;
- Yandex refresh tokens rotated after the target time may be invalid upstream.
  Affected users re-login, and this is reported as expected.

The runbook ends with an **Exercise log** table (date, operator role, target
time, phase durations, check output counts, deviations, teardown confirmed).

### 2. Read-only verification tool `src/storage/restore-check.ts` + `src/restore-check.ts`

- `src/storage/restore-check.ts` exports
  `checkRestoredDatabase(pool: pg.Pool, opts?: { asRole?: string }): Promise<RestoreCheckReport>`.
  - **Tables:** it reads `information_schema.tables`/`pg_tables` for the ten
    expected names, taken from a new exported `POSTGRES_TABLES` constant next
    to `initTables()` in `postgres-storage.ts`, so the list cannot drift. It
    reports any that are missing.
  - **Grants:** `tableowner` per table, plus
    `has_table_privilege(<role>, tbl, 'SELECT,INSERT,UPDATE,DELETE')`.
  - **Counts:** `count(*)` per table; for `oauth_tokens`, also the count of
    unexpired rows.
  - **Decryption:** for each `ENCRYPTED_COLUMNS` spec, it pages through *all*
    rows, not only stale ones, and tries `decryptToken(value, owner)` on each
    envelope. It counts `ok` / `failed`, and `stale` (not under the active
    key) using the existing `rotateRow`/`isEncryptedEnvelope` helpers. Write
    mode is never used.
  - **Hashed secrets:** the same five columns as `initTables()`, counting
    values without the `sha256:` prefix. The column list is shared through a
    new exported `SECRET_COLUMNS` constant, so the two cannot diverge.
  - Every query runs inside `BEGIN READ ONLY ... ROLLBACK`.
- `src/restore-check.ts` is the CLI. It reads `DATABASE_URL`, refuses to run
  when neither `ENCRYPTION_KEY` nor `ENCRYPTION_KEYS` is set (so the dev
  fallback in `getEncryptionKey()` can never mask a missing key), prints a
  JSON report with counts only, and exits 1 on any failed check. It is built
  into `dist/restore-check.js` by the existing `tsc` build and ships in the
  image automatically. `package.json` gets `"restore-check": "node dist/restore-check.js"`.
- Never printed: row keys, user ids, logins, ciphertexts, or plaintexts.

### 3. Recorded exercise

Run steps 1–5 and 6–8 once, entirely on the scratch cluster:

- restore into `labs-mctl-alice-restore` on the scratch cluster;
- rename;
- run the check from a one-off pod;
- optionally start a throwaway `mctl-alice` pod with its own `DATABASE_URL`,
  `AUTH_REQUIRED=true` and the production key in the scratch namespace, and
  hit `/readyz`. It is not exposed through ingress.

Production traffic is not switched. Record the result in the Exercise log, and
update section 5 of `docs/plans/public-launch-readiness.md` ("restore a
backup") with a link to the runbook and the date.

## Alternatives

- **Restore the whole shared cluster in place (CNPG PITR on `shared-pg`).**
  Dropped: it rolls back all nine tenant databases and the platform databases
  (Forgejo, ZITADEL, Grafana). The issue explicitly asks not to touch the
  others.
- **Switch over by pointing the app at a new database name.** That means
  changing the Vault `database` property, adding a pg_hba line and a CNPG
  `Database` in mctl-gitops, and waiting for ExternalSecret refresh. Dropped
  as the default: it needs a gitops PR and a Vault write during an incident,
  and it leaves the canonical name pointing at stale data. The rename keeps
  every external reference stable. It is listed in the runbook as the
  fallback if renaming is impossible, for example when sessions cannot be
  terminated.
- **Restore from a `pg_dump` taken nightly per tenant instead of PITR.**
  Dropped: there is no such per-database dump today, and adding one is a
  platform change outside this repo. PITR from the existing base backups and
  WAL already gives a finer recovery point.
- **Verification as an ad-hoc SQL script in the runbook.** Dropped: SQL cannot
  check that an AES-GCM envelope decrypts with the current key. Reusing
  `decryptToken`/`ENCRYPTED_COLUMNS` keeps the check in sync with the code.

## Platform impact

- **Migrations / compatibility:** none. There are no schema changes; the new
  module and CLI are additive and not imported by `src/index.ts`. A tiny
  refactor exports `POSTGRES_TABLES` and `SECRET_COLUMNS` from
  `postgres-storage.ts`, and `initTables()` keeps identical SQL.
- **Resources:** the scratch recovery cluster restores the whole `shared-pg`
  data directory (nine small tenant databases according to the cluster.yaml
  comment) and replays WAL. It needs a PVC of the live cluster's size and
  about one CPU for the duration. It lives in a scratch namespace for about an
  hour. The R2 egress for one base backup plus WAL is small.
- **Risks and mitigations:**
  - *Writing to the production archive from the scratch cluster.* The runbook
    forbids `spec.backup` and uses a different cluster name. Review the
    manifest before applying it.
  - *Other tenants' data in the scratch cluster.* Restrict the namespace to
    admins, delete it within the session, and log the teardown.
  - *Secrets in logs or the exercise record.* The tool prints counts only, and
    the runbook says never to `cat` the dump or the secrets.
  - *`statement_timeout` 60s.* Use `PGOPTIONS='-c statement_timeout=0'` on the
    dump and restore sessions.
  - *Restored key mismatch.* Restoring before a key rotation needs the old
    key. The check reports `failed` decryptions, and the runbook says to add
    the old key to `ENCRYPTION_KEYS` instead of deleting the rows.
  - *ArgoCD self-heal re-scaling during the switch.* Pause auto-sync or use a
    gitops `replicaCount: 0` commit. The runbook documents both.
- **Disclosure:** the runbook and log name only resources already public in
  this repo or service metadata (`shared-pg`, `labs-mctl-alice`,
  `alice.mctl.ai`), and no security findings.
