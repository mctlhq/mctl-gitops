# Tasks: issue-64-document-and-test-restoring-the-alice-da

- [ ] 1. In `src/storage/postgres-storage.ts`, export `POSTGRES_TABLES` (the
  nine OAuth/user tables plus `telemetry_samples`) and `SECRET_COLUMNS` (the
  five hashed-secret columns now inlined in `initTables()`). Make
  `initTables()` use `SECRET_COLUMNS`. — DoD: the SQL emitted by `initTables()`
  is unchanged, and the existing `tests/postgres-storage.test.ts` and
  `tests/hosted-postgres.test.ts` pass.
- [ ] 2. Add `src/storage/restore-check.ts` with
  `checkRestoredDatabase(pool)` (depends on 1). It checks tables,
  owners and every required privilege separately (all of SELECT/INSERT/UPDATE/DELETE,
  schema USAGE and required sequence rights), row counts, decryption of every envelope in
  `ENCRYPTED_COLUMNS` (ok/stale/failed via `decryptToken`/`rotateRow` with
  `rewrite=false`) and clear-text secret counts, all inside a
  `BEGIN READ ONLY` transaction on one checked-out pool client that is rolled
  back before the client is released. — DoD: it returns a typed
  report with `ok: boolean` and per-check results, and no secret values,
  ciphertexts or row keys appear in the report.
- [ ] 3. Add the CLI `src/restore-check.ts` and the `package.json` script
  `restore-check` (depends on 2). It reads `DATABASE_URL`, refuses to start
  without `ENCRYPTION_KEY`/`ENCRYPTION_KEYS`, prints the JSON report and exits
  1 on failure. — DoD: `npm run build` emits `dist/restore-check.js`, and the
  image built from the unchanged `Dockerfile` contains it.
- [ ] 4. Write `docs/runbooks/restore-database.md` (depends on 3). It covers
  target selection; a mandatory recovery-point encryption-key preflight; the
  scratch recovery `Cluster` manifest template (with no `spec.backup` and a
  warning box); dumping only `labs-mctl-alice`; restoring into
  `labs-mctl-alice-restore` with `--no-owner --role=labs-mctl-alice` and
  `statement_timeout=0`; verification with `restore-check` from a one-off Node
  Pod using `envFrom.secretRef` and authenticated TCP/TLS as the app role, with
  narrow temporary pg_hba/NetworkPolicy access via the owning GitOps path and
  cleanup (no local-postgres/`--as-role` shortcut); a hard switch-over gate
  requiring `ok: true`, zero decryption failures, no missing tables, correct
  ownership/privileges and no clear-text bearer secrets; the rename switch-over
  only after ArgoCD and parent reconciliation are suspended and all app pods are
  stopped; live verification; cleanup; rollback of the switch-over; the "What to
  check after a restore" section; and an empty "Exercise log" table. Record and
  restore prior reconciliation settings after verification or rollback. The key
  preflight maps the selected target time to the historical/current key
  material required to decrypt that point and stops recovery if that material
  cannot be identified or obtained; it never assumes the current production key
  is sufficient for an older target. — DoD: a grep shows no internal hostnames,
  object-store names, endpoint URLs, Vault paths or credentials. The reviewer
  confirms that only public resource names appear.
- [ ] 5. Link the runbook from `README.md` (the security/operations section
  near "Rotating the encryption key"), and add a note to key-rotation step 4
  that old keys are needed for a restore for as long as any retained backup can
  contain ciphertext encrypted by them (currently a 14-day backup retention
  window). — DoD: the README renders and the link resolves.
- [ ] 6. Perform the exercise against a scratch namespace (depends on 3, 4).
  Recover to a target time at least one hour old using the actual CNPG PITR
  mechanism; confirm the key material required by that recovery point is
  available; run an actual `pg_dump -Fc` of `labs-mctl-alice` and an actual
  `pg_restore` into a fresh database on the scratch cluster; run
  `restore-check` with the recovery-point key material from a one-off pod that
  has the key through a Secret reference and connects as the app role over
  authenticated TCP/TLS using scratch-only access rules and working scratch
  credentials; require the hard switch-over gate to pass; run the rename
  switch-over there; remove the access rules afterwards; optionally start a
  non-ingress app pod and probe `/readyz`; then tear everything down.
  Production traffic is not switched. `CREATE TABLE ... AS` or another logical
  copy is NOT an acceptable substitute for PITR + pg_dump/pg_restore in this
  end-to-end exercise. — DoD: `restore-check` exits 0 with zero unexplained
  failures, the gate passes before rename, and the scratch namespace, PVCs and
  dump are deleted.
- [ ] 7. Record the exercise in the runbook's Exercise log. Include the date,
  target time, confirmation of the required encryption-key epoch/material
  without recording key values, phase durations, check counts, deviations from
  the runbook (and fix the runbook for each), and teardown confirmation. Update
  section 5 "restore a backup" in `docs/plans/public-launch-readiness.md`
  (depends on 6). — DoD: the entry contains counts/metadata only, and the plan
  links the runbook and the exercise date.

## Tests

- [ ] T1. Unit test (`tests/restore-check.test.ts`, mocked pool): the report
  flags a missing table, a table not owned by or usable by the role, a
  clear-text `oauth_tokens.access_token`, and an envelope encrypted under a
  different key. Seed SELECT-only access and assert failure for the missing
  INSERT/UPDATE/DELETE rights; missing schema or sequence rights must also fail. The serialized report contains none of the seeded token,
  cookie or ciphertext strings.
- [ ] T2. Real-Postgres test (in `tests/hosted-postgres.test.ts` style, skipped
  without `TEST_POSTGRES_URL`): seed two users with credentials through
  `PostgresStorage`, `pg_dump`/`pg_restore` the schema into a second schema when
  the client binaries are available, run `checkRestoredDatabase`, and expect
  `ok: true` with matching counts. Then switch `ENCRYPTION_KEY` and expect
  `failed > 0` and `ok: false`. `CREATE TABLE ... AS` copies MAY be used as a
  fallback only for this automated integration test when the binaries are
  absent; they do not satisfy T6 or the launch-readiness restore gate.
- [ ] T3. Read-only guarantee: after `checkRestoredDatabase` on the real
  database, row data and `xmin` of seeded rows are unchanged, and no
  `UPDATE`/`DELETE` was issued (asserted on the mocked pool in T1).
- [ ] T4. CLI: with neither `ENCRYPTION_KEY` nor `ENCRYPTION_KEYS` set,
  `restore-check` exits non-zero before connecting.
- [ ] T5. Refactor guard: a snapshot of the SQL text `initTables()` sends to
  the mocked client is identical before and after task 1.
- [ ] T6. Manual end-to-end: the recorded exercise (task 6) MUST exercise real
  CNPG PITR plus real `pg_dump -Fc`/`pg_restore`, MUST verify the key material
  required by the selected recovery point, and MUST demonstrate that the
  switch-over hard gate fails closed on any restore-check failure.

## Rollback

- Code: revert the PR. The check is not on the serving path (`src/index.ts`
  does not import it), so removing it has no runtime effect. The constants
  refactor is behaviour-neutral.
- Exercise: delete the scratch namespace (Cluster, PVCs, secrets, dump). It
  never touches `shared-pg` or the live database.
- A real switch-over that goes wrong: record and suspend ArgoCD and parent
  reconciliation, verify it remains suspended, then scale `labs-mctl-alice` to 0, rename
  `labs-mctl-alice` back to `labs-mctl-alice-restore` and
  `labs-mctl-alice-pre-restore-<yyyymmdd>` back to `labs-mctl-alice`, then
  scale up again. Restore the recorded reconciliation settings after verification
  and confirm sync/health. The runbook keeps the pre-restore database for 7 days so
  this stays possible.
