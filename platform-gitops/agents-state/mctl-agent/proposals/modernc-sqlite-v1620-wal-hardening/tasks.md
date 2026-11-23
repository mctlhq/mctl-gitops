# Tasks: modernc-sqlite-v1620-wal-hardening

- [ ] 1. Check status of `modernc-sqlite-upgrade` and the other sqlite proposals; read the current driver version in `go.mod` — DoD: decision recorded to extend or supersede `modernc-sqlite-upgrade`, with no double bump.
- [ ] 2. Confirm v1.62.0 is latest, embeds SQLite 3.54.1, and its minimum Go version fits the toolchain (depends on 1) — DoD: facts and links in the PR; ordering versus `go-1274-nethttp-maxbytes-patch` noted.
- [ ] 3. Snapshot the tickets and skill-metrics DB files (main, `-wal`, `-shm`) from the PVC (depends on 1) — DoD: snapshot stored and a restore of it was verified.
- [ ] 4. Bump the driver to v1.62.0 and run `go mod tidy` (depends on 2) — DoD: build and unit tests pass.
- [ ] 5. Validate on a DB copy (depends on 3, 4) — DoD: `integrity_check` ok, journal mode unchanged, `wal_checkpoint(TRUNCATE)` ok, query replay matches. Also measure RSS and latency baseline versus new; set the RSS threshold.
- [ ] 6. Add the startup `quick_check` guard (depends on 4) — DoD: a corrupt test file makes the service exit with a clear log; a healthy file starts normally.
- [ ] 7. Check whether any `labs` workload or shared image embeds this driver (depends on 2) — DoD: yes/no recorded; if yes, `labs` memory measured and rollout there blocked until approved.
- [ ] 8. Roll out via ArgoCD to `admins` (depends on 5, 6, 7) — DoD: pod Ready, tickets readable and writable, RSS within threshold after 24h.

## Tests
- [ ] T1. Open a copy of the production DB with the new driver; `PRAGMA integrity_check` returns `ok`.
- [ ] T2. WAL mode: write under load, checkpoint, reopen, and data is intact.
- [ ] T3. A crafted file with a WAL page-size mismatch is rejected at startup, not served.
- [ ] T4. Existing ticket and skill-metrics tests pass unchanged.
- [ ] T5. RSS after upgrade is within the threshold set in task 5.

## Rollback
Redeploy the previous image through ArgoCD. If the DB was only opened with unchanged pragmas, the old driver reads it as is. If integrity problems appear, stop the pod, restore the task 3 snapshot to the PVC, then start the old image.
