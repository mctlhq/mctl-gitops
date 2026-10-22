# Restore runbook and verification for the alice database

## Context

The hosted `mctl-alice` service (tenant `labs`, image `2.2.6`) keeps all of its
state in one database (`labs-mctl-alice`) on the platform's shared CloudNativePG
cluster. That covers users, encrypted Yandex credentials, hashed MCP tokens,
OAuth clients and telemetry. The cluster takes a daily base backup and archives
WAL to off-cluster object storage, with 14 days of retention. Neither this repo
nor mctl-gitops has a procedure for restoring this one database without
touching the nine other tenant databases on the same cluster. Restoring the
cluster in place would roll every tenant back. No one has ever rehearsed a
restore, so nobody knows whether a restored database can be decrypted with
the current key, keeps the hashed-secret invariant, and is usable by the app
role.

The issue asks for four things: a runbook in `docs/` that restores the cluster
backup to a scratch cluster at a point in time, runs `pg_dump` on only the alice
database, restores that dump into a fresh database, switches the app over and
verifies it; a list of post-restore checks; one recorded exercise against a
scratch target; and no non-public hostnames, bucket names or credentials. It is
part of the public-launch plan (`docs/plans/public-launch-readiness.md`,
section 5: "restore a backup").

## User stories

- AS the platform operator I WANT a step-by-step procedure for restoring only the
  alice database to a chosen point in time SO THAT I can recover from data loss or
  a bad migration without rolling back other tenants.
- AS the platform operator I WANT a read-only check that tells me whether a
  restored database is usable (users present, grants correct, credentials
  decryptable with the current key, no clear-text bearer secrets) SO THAT I only
  switch traffic to a database the app can actually serve from.
- AS the launch owner I WANT evidence that the procedure has been run once SO THAT
  the "restore a backup" gate in the launch plan is backed by a recorded result.

## Acceptance criteria (EARS)

- WHEN an operator opens `docs/runbooks/restore-database.md` THE SYSTEM SHALL
  describe, in order: choosing a recovery target time, bootstrapping a scratch
  CNPG cluster from the shared cluster's backups with that target, running
  `pg_dump` on only the `labs-mctl-alice` database, restoring it into a fresh
  database, running the verification check, switching the app over, verifying
  the live service, and tearing down the scratch cluster.
- WHILE the scratch recovery cluster exists THE SYSTEM SHALL have no `backup`
  or WAL-archive destination configured on it, so that the production backup
  archive is never written to. The runbook states this as a hard precondition.
- WHEN the runbook restores into the shared cluster THE SYSTEM SHALL restore
  into a new database (`labs-mctl-alice-restore`) owned by the
  `labs-mctl-alice` role, leaving the live database untouched until the
  switch-over step.
- WHEN the operator switches over THE SYSTEM SHALL keep the app's
  `DATABASE_URL`, pg_hba rule and CNPG `Database` resource unchanged. To do
  this it scales the app to zero, renames the live database to a dated
  `-pre-restore` name, renames the restored database to `labs-mctl-alice`, and
  scales the app back up.
- WHEN `node dist/restore-check.js` runs against a database URL THE SYSTEM
  SHALL report, without writing anything: the row count for each table; whether
  every expected table exists and is owned by, or fully usable by, the
  connecting role; how many encrypted credentials are not under the active key;
  how many no configured key can decrypt; and how many bearer-secret values are
  not `sha256:` digests.
- IF any expected table is missing, any table is not usable by the connecting
  role, any stored credential cannot be decrypted with the configured keys, or
  any bearer secret is stored in clear text THEN THE SYSTEM SHALL exit non-zero
  and name the failing check without printing any secret, token, cookie or
  ciphertext value.
- WHEN the check runs in a container that has no `ENCRYPTION_KEY` and no
  `ENCRYPTION_KEYS` THE SYSTEM SHALL fail the decryption check instead of
  falling back to the development key.
- WHEN the exercise has been performed THE SYSTEM SHALL have a dated entry in
  the runbook's "Exercise log" section. The entry records the recovery target
  time, the elapsed time of each phase, the check output (counts only), any
  deviation from the runbook, and whether the scratch target was torn down.
- WHILE writing the runbook and exercise log THE SYSTEM SHALL contain no
  internal hostnames, object-store bucket or path names, endpoint URLs, Vault
  paths or credentials. It refers to the cluster's own backup configuration by
  resource name only, which is already public in this repo's deployment
  metadata.
- WHEN the exercise is recorded THE SYSTEM SHALL update the "restore a backup"
  item in `docs/plans/public-launch-readiness.md` to point at the runbook and
  the exercise result.

## Out of scope

- Restoring the whole shared cluster in place, or any tenant database other than
  `labs-mctl-alice`.
- Changing the shared cluster's backup schedule, retention or object store. That
  lives in mctl-gitops.
- Automating restores (a CronWorkflow or a platform operation). This proposal
  delivers a manual runbook and one manual exercise.
- Restoring the SQLite backend (`src/storage/oauth-storage.ts`,
  `src/storage/telemetry-storage.ts`). The hosted deployment does not use it.
- Key escrow. The runbook only states that keys must be kept for as long as
  the backups that need them (README "Rotating the encryption key", step 4).

## Open questions

- The issue labels this "security finding S7", but S7 in
  `docs/plans/public-launch-readiness.md` is "Additional hardening" (escaping,
  Keychain helper, embedded client secret). The restore requirement there is in
  section 5 ("restore a backup"). This proposal updates section 5. A reviewer
  should confirm which plan entry it closes.
- The switch-over renames databases, which needs a role with `CREATEDB` or
  superuser access. Superuser access over the network is disabled
  (`enableSuperuserAccess: false`), so the runbook uses a local `postgres`
  session inside the primary pod. This needs a reviewer to confirm that
  operator access to that pod is the accepted break-glass path.
- Restoring the whole cluster into a scratch namespace brings back the data
  of the other eight tenant databases for as long as the scratch cluster
  exists. The runbook limits that time and deletes the cluster, its PVCs and
  the dump. Does that need sign-off from the other tenants' owners?
- Not observed during investigation: the actual database sizes on `shared-pg`,
  the oldest available base backup, and whether the latest daily backup
  succeeded. No read-only tool available here exposed them. The exercise
  will record them, and the earliest recoverable time must not be assumed.
- Scratch target for the recorded exercise: a scratch namespace in the same
  Kubernetes cluster is assumed. The scratch database is restored into the
  scratch cluster, not the shared one. Production traffic is not switched
  during the exercise; the switch-over steps are run against the scratch
  cluster with a scratch app pod, or with the check alone.
