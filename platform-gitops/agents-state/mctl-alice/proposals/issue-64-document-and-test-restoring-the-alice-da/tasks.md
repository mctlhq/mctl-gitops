# Tasks: issue-64-document-and-test-restoring-the-alice-da

- [ ] 1. In `src/storage/postgres-storage.ts`, export `POSTGRES_TABLES` (the
  nine OAuth/user tables plus `telemetry_samples`) and `SECRET_COLUMNS` (the
  five hashed-secret columns now inlined in `initTables()`). Make
  `initTables()` use `SECRET_COLUMNS`. — DoD: the SQL emitted by `initTables()`
  is unchanged, and the existing `tests/postgres-storage.test.ts` and
  `tests/hosted-postgres.test.ts` pass.
- [ ] 2. Add `src/storage/restore-check.ts` with
  `checkRestoredDatabase(pool, { asRole? })` (depends on 1). It checks tables,
  owners and privileges, row counts, decryption of every envelope in
  `ENCRYPTED_COLUMNS` (ok/stale/failed via `decryptToken`/`rotateRow` with
  `rewrite=false`) and clear-text secret counts, all inside a
  `BEGIN READ ONLY` transaction that is rolled back. — DoD: it returns a typed
  report with `ok: boolean` and per-check results, and no secret values,
  ciphertexts or row keys appear in the report.
- [ ] 3. Add the CLI `src/restore-check.ts` and the `package.json` script
  `restore-check` (depends on 2). It reads `DATABASE_URL`, refuses to start
  without `ENCRYPTION_KEY`/`ENCRYPTION_KEYS`, prints the JSON report and exits
  1 on failure. — DoD: `npm run build` emits `dist/restore-check.js`, and the
  image built from the unchanged `Dockerfile` contains it.
- [ ] 4. Write `docs/runbooks/restore-database.md` (depends on 3). It covers
  target selection, the scratch recovery `Cluster` manifest template (with no
  `spec.backup` and a warning box), dumping only `labs-mctl-alice`, restoring
  into `labs-mctl-alice-restore` with `--no-owner --role=labs-mctl-alice` and
  `statement_timeout=0`, the verification with `restore-check`, the rename
  switch-over, live verification, cleanup, rollback of the switch-over, the
  "What to check after a restore" section, and an empty "Exercise log" table.
  — DoD: a grep shows no internal hostnames, object-store names, endpoint
  URLs, Vault paths or credentials. The reviewer confirms that only public
  resource names appear.
- [ ] 5. Link the runbook from `README.md` (the security/operations section
  near "Rotating the encryption key"), and add a note to key-rotation step 4
  that old keys are needed for a restore within the 14-day retention
  (depends on 4). — DoD: the README renders and the link resolves.
- [ ] 6. Perform the exercise against a scratch namespace (depends on 3, 4).
  Recover to a target time at least one hour old, dump `labs-mctl-alice`,
  restore it into a fresh database on the scratch cluster, run the
  rename switch-over there, run `restore-check` from a one-off pod that has
  the production key, optionally start a non-ingress app pod and probe
  `/readyz`, then tear everything down. Production traffic is not switched.
  — DoD: the check exits 0 (or each failure is explained), and the scratch
  namespace, PVCs and dump are deleted.
- [ ] 7. Record the exercise in the runbook's Exercise log. Include the date,
  target time, phase durations, the check counts, deviations from the
  runbook (and fix the runbook for each), and teardown confirmation. Update
  section 5 "restore a backup" in `docs/plans/public-launch-readiness.md`
  (depends on 6). — DoD: the entry contains counts only, and the plan links
  the runbook and the exercise date.

## Tests

- [ ] T1. Unit test (`tests/restore-check.test.ts`, mocked pool): the report
  flags a missing table, a table not owned by or usable by the role, a
  clear-text `oauth_tokens.access_token`, and an envelope encrypted under a
  different key. The serialized report contains none of the seeded token,
  cookie or ciphertext strings.
- [ ] T2. Real-Postgres test (in `tests/hosted-postgres.test.ts` style, skipped
  without `TEST_POSTGRES_URL`): seed two users with credentials through
  `PostgresStorage`, `pg_dump`/`pg_restore` the schema into a second schema
  (or use `CREATE TABLE ... AS` copies when the binaries are absent), run
  `checkRestoredDatabase`, and expect `ok: true` with matching counts. Then
  switch `ENCRYPTION_KEY` and expect `failed > 0` and `ok: false`.
- [ ] T3. Read-only guarantee: after `checkRestoredDatabase` on the real
  database, row data and `xmin` of seeded rows are unchanged, and no
  `UPDATE`/`DELETE` was issued (asserted on the mocked pool in T1).
- [ ] T4. CLI: with neither `ENCRYPTION_KEY` nor `ENCRYPTION_KEYS` set,
  `restore-check` exits non-zero before connecting.
- [ ] T5. Refactor guard: a snapshot of the SQL text `initTables()` sends to
  the mocked client is identical before and after task 1.
- [ ] T6. Manual: the recorded exercise (task 6) is the end-to-end test of the
  runbook.

## Rollback

- Code: revert the PR. The check is not on the serving path (`src/index.ts`
  does not import it), so removing it has no runtime effect. The constants
  refactor is behaviour-neutral.
- Exercise: delete the scratch namespace (Cluster, PVCs, secrets, dump). It
  never touches `shared-pg` or the live database.
- A real switch-over that goes wrong: scale `labs-mctl-alice` to 0, rename
  `labs-mctl-alice` back to `labs-mctl-alice-restore` and
  `labs-mctl-alice-pre-restore-<yyyymmdd>` back to `labs-mctl-alice`, then
  scale up again. The runbook keeps the pre-restore database for 7 days so
  this stays possible.
