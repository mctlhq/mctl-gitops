# Glovo Basket MCP: production canary activation runbook

Source: mctlhq/mctl-api#1006 (working issue), plan mctlhq/mctl-gitops#2457.
Code: mctl-api #1007 (approval page), #1008 (MCP and store), #1014
(integration of both), #1017 (chart: per-host ingress paths, `extraPaths`,
`glovoBasketUISecret` slot), #1018 (`cmd/glovo-migrate`, the operator-run
schema migrator). #1013 (provider planner) is not needed. Staged GitOps
patches live under `deploy/staged/glovo-m1/` as `.md` (leak guard, below):
`canary/env.patch.md` (B1, B2), `canary/ingress.patch.md` (C),
`zitadel-client.patch.md` (Z), `db/` (D1, W).

Scope (owner, 2026-11-11): v1 is a synthetic Basket Approval Canary served by
mctl-api itself. Excluded: Temporal, trusted control worker, Telegram, fake
dispatch, any provider effect, the real Glovo API, session custody (#1020),
live adapter (#1021). The result is an approved or rejected basket, never an
order.
Earlier fake-order package and runbook: `docs/runbooks/glovo-m1.md` (not used
by this canary; its Temporal, Telegram and three-image parts are deferred).

This file is a preparation artifact. Nothing here is applied by merging it.
Every step that changes production is its own PR or operator action with its
own explicit owner GO. Merging a PR in this repository IS a production change
(the `admins-mctl-api` Application auto-syncs with prune and selfHeal), so a
step's "merge" is the step.

## Holds and the production DDL sequence (owner, 2026-11-11)

- Releases 4.155.0 and 4.156.0 are on HOLD. Each needs its own separate
  authorization packet; nothing in this runbook authorizes either.
- Production DDL (step D2) is forbidden until ALL of these have happened, in
  this order, and then a separate operator authorization is given:
  1. D0: the read-only inventory is recorded and read;
  2. D1: the roles, ownership transfer and grants are applied AND verified;
  3. a fresh review of #1018 on its final head (no unaddressed P1/P2);
  4. a rehearsal of D2 on a disposable copy of the database;
  5. the operator's separate, recorded authorization for production D2.
- Merge order of the staging PRs in mctlhq/mctl-gitops: #2582, #2592 and #2593
  first (or together), then this runbook (#2594), because the runbook cites
  the staged patches those PRs add.

## Definition of done

1. An authenticated OAuth MCP client run against `https://glovo.mctl.ai/mcp`
   on production: discovery, login, six tools listed, a synthetic basket
   created and edited, an approval requested.
2. The owner's own, personal decision on the approval page for that exact
   basket revision. The agent never opens the page as the owner, never holds
   the owner's ZITADEL session, never calls the decision route, and cannot
   approve (there is no MCP approve tool).
3. After activation, only the canary principal can reach it (negative checks
   in step E).
4. No real Glovo network effect, no order, no payment: the catalog is
   synthetic (`FAKE-*`, store `pst_SYNTHETICSTORE0001`, EUR).

## Roles

- **owner**: the repository owner. Merges activation PRs, signs in to ZITADEL
  and to Vault, holds the platform-admin credential, decides on the approval
  page.
- **operator**: whoever holds production database and Vault credentials. Today
  the owner. Agents never read Secret data or key names (including counters).
- **agent**: Claude. Prepares PRs, runs read-only verification, runs the
  scripted client up to the point that needs a human login, records evidence in
  mctl-api#1006. MCTL MCP / Control Plane is the preferred audit surface for
  supported operations (`mctl_get_service_status`, `mctl_get_service_pods`,
  `mctl_get_service_logs`, `mctl_rollback_service`); GitOps stays the source of
  truth. `kubectl` is read-only and never touches Secrets.

## Production changes, in activation order

| # | Step | Change | Repo | Who merges or acts |
| --- | --- | --- | --- | --- |
| 1 | R0 | mctl-api 4.155.0 dark (separate decision, not part of this package) | mctl-api | owner |
| 2 | R1 | mctl-api 4.156.0 with the Basket code, plus the chart pin move (#1017), deployed dark (no Glovo env) | mctl-api, mctl-gitops release PR | owner (release), release-deploy PR route under the #2590 hold |
| 3 | V | Optional convenience only: an operator Vault session. gitops#2584 is an unrelated task and NOT a Glovo gate | none | owner |
| 4a | D0 | Read-only catalogue inventory of the production database (no DDL) | database | operator |
| 4 | D1 | Database roles, transitional grants, ownership transfer (A15 operator plan) | database | operator |
| 5 | W | Move the A15 ExternalSecrets and the inert `GLOVO_DB_*` env into reconciled paths | mctl-gitops | owner |
| 6 | D2 | `glovo-migrate` (#1018) as `glovo_migrator`: Glovo base, approval v2, basket v1 | database | operator |
| 7 | Z | ZITADEL client `mctl-api-glovo-basket` (gitops#2582 moved to `zitadel-iac`) with the leak-guard change | mctl-gitops | owner |
| 8 | B1 | `GLOVO_ENABLED`, `GLOVO_MCP_RESOURCE`, `GLOVO_BASKET_MCP_ENABLED` + marker | mctl-gitops | owner |
| 9 | B2 | `glovoBasketUISecret` slot, `extraPaths: [/glovo]`, `GLOVO_BASKET_UI_ENABLED` + marker | mctl-gitops | owner |
| 10 | C | Ingress host `glovo.mctl.ai`, reserved host | mctl-gitops | owner |
| 11 | A | Allowlist entry for the canary (team, principal) | API call | owner (admin credential) |
| 11a | P | Default-deny egress policy for the Glovo workload: separate gate, prepared by another agent, link TODO; before P2 activation | mctl-gitops | owner |
| 12 | E, N, K | Client run, owner decision, negative checks, kill-switch drill | none | agent + owner |

No DNS change, no Cloudflare apply, no new certificate token, no
NetworkPolicy or RBAC change (see "What is not needed").

## Common rules

- Evidence: after each step, one short comment on mctl-api#1006 with the step
  id, the merged SHA, the image digest and the read-only command output (ids
  and statuses only).
- A step starts only when its precondition holds on freshly read state, not on
  an earlier comment. A step that cannot be observed is blocked, not passed.
- Never print a token. Commands below take credentials from the environment.
- Rollback order is always: unroute (C), revoke access (A), flags (B2, B1).
  Schemas are forward-only and stay.

---

## Step R0: mctl-api 4.155.0 dark

Out of scope here. Precondition for everything below: 4.155.0 is deployed and
Argo is Synced and Healthy on `admins-mctl-api`, per the release-readiness
matrix. The Basket code is NOT in 4.155.0.

## Step R1: mctl-api 4.156.0 (Basket code) deployed dark

- **Who**: owner decides the release; the release path deploys. The agent does
  not tag, bump or redeploy. HOLD: this step needs its own authorization
  packet (see "Holds"); it is documented here, not authorized.
- **What changes in 4.156.0 (chart, env, defaults)**:
  - Code: the host-routed router `withGlovoBasketHost`, the six-tool MCP, the
    store and the approval page. All of it is behind the env chain below and
    is OFF by default: with none of the `GLOVO_*` names set, the binary
    behaves as 4.155.0 (no `glovo basket` log line, no route on any host).
  - Chart (mctl-api#1017): per-host `paths`, `ingress.extraPaths` (default
    `[]`) and the `glovoBasketUISecret` slot (default `""`). A values file
    that uses none of them renders byte-identically to 4.155.0 (the chart's
    render test covers both).
  - Env chain, fail-closed: `GLOVO_ENABLED` then `GLOVO_MCP_RESOURCE`
    (`https://<host>/mcp`) then `GLOVO_BASKET_MCP_ENABLED` (needs the Glovo
    database pool, the work-items ledger and both schemas verified) then
    `GLOVO_BASKET_UI_ENABLED` (needs the UI client id and secret; otherwise
    the page stays off). Also read: `OAUTH_DB_URL` (explicit),
    `GLOVO_DB_URL`, `GLOVO_DB_RUNTIME_ROLE`, `GLOVO_DB_MIGRATION_ROLE`,
    `TENANT_AUTHZ_MODE=principal`. A wrong value refuses the boot; it never
    starts half-on. Every name is in `canary/env.patch.md`.
  - Kill switch: remove the Ingress host first (C), revoke the allowlist entry
    (A, instant, no deploy), then the flags (B2, B1). Schemas stay.
- **The chart is pinned, so the pin moves with the tag.** The chart source of
  `admins-mctl-api` is pinned to a mctl-api commit in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`
  (`targetRevision`, mctlhq/mctl-gitops#2599; today `a5b9ef9c`). Merging #1017
  into mctl-api `main` therefore ships nothing to production. The 4.156.0
  release PR (opened through the PR route, branch
  `release-bump/mctl-api-4.156.0`, author `mctl-gitops-pr[bot]`) bumps the
  image tag; the `targetRevision` move to the 4.156.0 release commit is the
  same PR or a reviewed sibling, never a later drift. Both are subject to the
  `mctl-api-bootstrap` version hold of #2590: 4.155.0 and later are held until
  a reviewed PR adds an allow record (grant, approved_by, expires). Do not
  pin to the 4.154.0 tag commit: that would drop `/devloop` from production
  (verified 2026-11-11).
- **Precondition**: #1007, #1008, #1014 (retargeted to `main`), #1017 and #1018
  reviewed on their final heads (Claude and agy, no unaddressed P1/P2, CI
  green) and merged into mctl-api `main` only after 4.155.0 is released, so
  that release-please #934 does not absorb them. 4.155.0 is deployed and
  Argo is Synced and Healthy.
- **Exact change**: the release PR described above: image tag and chart pin.
  No Glovo env, no flag, no Ingress host.
- **Image digest and provenance (before and after)**: read the digest the
  Deployment runs, by tag and by digest, and compare it with the build:
  `kubectl -n mctl-api get deploy mctl-api -o jsonpath='{.spec.template.spec.containers[0].image}'`
  and the pod `imageID`; the OCI label `org.opencontainers.image.revision`
  (since mctl-gitops#2597) must equal the commit of the release tag
  (`docker buildx imagetools inspect ghcr.io/mctlhq/mctl-api:4.156.0`, then
  the config label). The 4.154.0 digest today is
  `sha256:42d5a572156f179f0f697bd3279fe7817831294d9ccb4a55a91d28b02f9d4488`;
  record the 4.155.0 digest too, it is the rollback target. A digest that
  does not carry the expected revision label is a stop, not a pass.
- **Verification (read-only)**: `mctl_get_service_status mctl-api`; pods Ready;
  `curl -sS -o /dev/null -w '%{http_code}\n' https://glovo.mctl.ai/mcp` is
  still a Traefik 404 (observed 2026-11-11); `/devloop` still answers;
  startup log has no `glovo basket` line.
- **Rollback**: roll the tag AND the pin back together to the recorded
  4.155.0 digest and commit through the release path
  (`mctl_rollback_service`, or a revert PR; for an emergency, remove the
  image from `platform-gitops/release-bump-routes.yaml` to return to the
  direct route). Chart skew is harmless (the changes are inert) but is not
  left in place on purpose.
- **Why before the database**: 4.155.0 verifies the approval schema at version
  1 (`glovoApprovalSchemaVersion = 1` at `081bd6b7`); 4.156.0 verifies version
  2. Applying v2 while 4.155.0 is the only image would make the order-pilot
  readiness report `approval_schema_not_ready` (dark, so harmless, but it is a
  skew to avoid).
- **No Glovo egress**: the basket code has no outbound HTTP client (catalog,
  basket and approval are in-process and in the database). This is a
  code-level fact, not a network control: the `mctl-api` namespace has NO
  egress NetworkPolicy (verified read-only 2026-11-11), so nothing in the
  cluster would block an outbound call either. A reviewer of #1008 and #1014
  confirms the first by `grep`; the second is a known gap, listed under
  "Could not determine".

## Step V: Vault session (optional convenience, not a gate)

- gitops#2584 (`opt-in 8h admin tokens on auth/mctl`) is an unrelated task. It
  is NOT a Glovo prerequisite, and nothing in this runbook waits for it. An
  operator who finds the default 1h token too short for the unattended D1 and
  D2 session may use it if the owner has merged it for its own reasons, or
  simply log in again.
- Where the Glovo database credentials live: the A15 staging (gitops#2563,
  `deploy/staged/glovo-m1/db/externalsecrets.yaml`) PROPOSES these Vault paths
  (`username` and `password` properties): `platform/mctl-api/glovo-runtime-database`,
  `platform/mctl-api/glovo-migrator-database` and
  `platform/mctl-api/workitems-database`, read by `ClusterSecretStore
  vault-backend`. None of them exists yet (the file says so); the operator
  creates them in D1. No other Vault path, policy or role is needed by the
  basket.
- The owner logs in with `! vault login -method=oidc -path=mctl` and the role
  they normally use; the agent never holds the token.

---

## Step D0: read-only inventory (before any DDL)

- **Who**: operator. Read only; nothing here changes the database.
- **Why**: the legacy objects of database `mctl-api` are not known from this
  repository (owners, ACLs, whether `public.work_items_schema_version`
  exists, the Postgres minor version, open transactions). Decisions in D1 and
  D2 are made from this output, not from the plan.
- **Exact change**: none. Run the catalogue inventory queries of
  `deploy/staged/glovo-m1/db/roles.patch.md` (owners and ACLs via
  `aclexplode`, sequence ownership, triggers, `pg_stat_activity` on
  `public.action_approval_requests`, `SHOW server_version`, table sizes) from a
  read-only session, and record the output (names and counts, no row data)
  on mctl-api#1006. The migrator's `-dry-run` (step D2) repeats this against
  the three target schemas, but it connects as `glovo_migrator`, which does
  not exist until D1, so it is the second inventory, not the first.
- **Verification**: the output is recorded and a reviewer has read it before D1
  starts.
- **Rollback**: none needed.

---

## Database migrations (reference for steps D1, D2)

### What runs when

| Item | Startup (automatic) or manual | Notes |
| --- | --- | --- |
| Existing 4.155.0 startup DDL (five groups: `oauth_team_grants` and its indexes, `oauth_refresh_tokens.team_grant_id`, `audit_events.refusal_code`, `agent_run_tokens.grant_id`, the `action_approval_requests_spent` index) | startup, unconditional | Not Glovo, not changed by this package. Rehearsal and lock evidence are gate G5 of the 4.155.0 matrix |
| `glovo.ApplySchema` (base schema `glovo`, allowlist, connections, handoff) | MANUAL, as `glovo_migrator` | `glovo.NewStore` refuses the boot if the recorded version is missing |
| `workitems.ApplyGlovoApprovalSchema` (approval schema v2) | MANUAL, as `glovo_migrator` | Runs the generic work-items block first, then its own transaction |
| `glovobasket.ApplySchema` (basket schema v1) | MANUAL, as `glovo_migrator` | Needs v2 first (it refuses otherwise) |
| 4.156.0 boot | read-only | `VerifyGlovoApprovalSchema` and `glovobasket.VerifySchema`, only when `GLOVO_BASKET_MCP_ENABLED=true`. The boot never applies a schema |

No binary in mctl-api `main` calls the three `Apply*` functions. The program
that does is `cmd/glovo-migrate` (mctl-api#1018, approved at `04e4dd95`,
Draft, not in any image and not in `main` yet): it runs base, approval v2 and
basket v1 in that order, each in its own transaction, as `glovo_migrator`.
Where and how the operator runs it is step D2. The older plan of #1004 (with
`-with-bridge/-orders/-join`) is not used.

Order: base, then approval v2, then basket v1. Each takes advisory locks
(`glovo-schema`, `glovo-approval-schema`, `glovo-basket-schema`) and runs in one
transaction, and is idempotent.

### The ownership precondition (the real risk)

`VerifyGlovoApprovalSchema` requires `public.action_approval_requests`,
`glovo.approval_bindings` and `glovo.basket_approval_bindings` to have ONE
owner, and the Glovo pool's user must not be a member of it. Today
`public.action_approval_requests` is owned by the legacy `mctl-api` role, so
the migrator must take ownership of the work-items tables first: that is the
operator plan staged in gitops#2563
(`deploy/staged/glovo-m1/db/roles.patch.md`: roles `glovo_runtime`,
`glovo_migrator`, `mctl_api_workitems`, recorded ACLs, one transaction, no
automatic `ALTER OWNER`). The canary inherits that plan unchanged. Open there:
how the legacy role keeps working after the transfer (transitional grants),
which role the work-items DSN uses, and whether `public.work_items_schema_version`
exists.

### Lock risk at 55 MB

The whole database is 55 MB, so every scan below is sub-second. The risk is
not duration but queueing behind a long transaction.

| DDL | Table | Lock | Held |
| --- | --- | --- | --- |
| three `ADD CONSTRAINT ... NOT VALID` (state, kind, state-by-kind checks), `DROP CONSTRAINT` of the old state check | `public.action_approval_requests` | ACCESS EXCLUSIVE, metadata only | to the end of the approval transaction |
| three `VALIDATE CONSTRAINT` | same | SHARE UPDATE EXCLUSIVE, one scan | same |
| `CREATE TRIGGER aar_guard`, `aar_binding_required`, `ENABLE TRIGGER` | same | SHARE ROW EXCLUSIVE (blocks writes) | same |
| generic block of the work-items schema (`IF NOT EXISTS` DDL on its tables, the non-concurrent `action_approval_requests_spent` index) | work-items tables | SHARE or ACCESS EXCLUSIVE briefly | per statement |
| basket schema: new tables, triggers, one FK on `glovo.basket_approval_bindings` | new objects in schema `glovo` only | none on existing tables | n/a |

The ACCESS EXCLUSIVE request on `action_approval_requests` is the hazard: if a
DevLoop or agent transaction holds the table, the queued request blocks every
later reader and writer of that table until it is granted. Mitigation, all
operator-side: run in a quiet window; first read `pg_stat_activity` for open
transactions on that table; connect with `options=-c lock_timeout=5000 -c
statement_timeout=60000` in the migration DSN so a blocked step fails fast
(SQLSTATE 55P03) and is retried; the schema steps are idempotent. The migrator
sets `SET LOCAL lock_timeout = 5s` and `statement_timeout = 60s` in every
transaction by default (`-lock-timeout`, `-statement-timeout`), so a blocked
step fails with exit code 3 instead of queueing; the DSN options are an
extra guard, not the only one.

Behavioural side effect: `aar_guard` and `aar_binding_required` are BEFORE
triggers on the shared approvals table, so they run for existing DevLoop
approvals too. Step D3 includes a DevLoop approval read and a create/decide
smoke on a non-production-affecting path, or an owner-accepted equivalent.

### Rollback

There is no down migration. Everything is additive (widened CHECKs, new
tables and triggers) and 4.155.0 and 4.154.0 tolerate it except for the order
pilot's readiness probe (dark). Rollback of a failed or unwanted activation
is: unroute, revoke the allowlist entry, switch the flags off. The schema
stays. Emergency only, with its own approval: `ALTER TABLE
public.action_approval_requests DISABLE TRIGGER aar_guard` as the table owner
if the guard is found to block a DevLoop path; that makes the basket decisions
fail closed (`VerifyGlovoApprovalSchema` sees four enabled triggers expected).

## Step D1: roles, transitional grants, ownership transfer

- **Who**: operator (owner). No Vault convenience is required (step V).
- **Design (owner, 2026-11-11)**: one physical database `mctl-api`; a separate
  least-privilege work-items role `mctl_api_workitems` (DML only, no DDL, no
  ownership) with an explicit `WORK_ITEMS_DB_URL` for it; the migrator role
  `glovo_migrator` owns the schemas; `glovo_runtime` is the Glovo runtime
  role. The legacy `mctl-api` role stops being the owner of the work-items
  objects and receives only the transitional grants it still needs.
- **Precondition**: R1 done; D0 recorded and read; gitops#2563 and gitops#2579
  resolved on their open items (the UNVERIFIED list in #2563: connection
  limits, grantees via `aclexplode`, sequence ownership after the transfer,
  whether `work_items_schema_version` exists, URL-safe migrator password);
  the three Vault secrets of step V created by the operator; a fresh logical
  backup or snapshot of database `mctl-api` recorded (the database is 55 MB).
- **`COMMERCE_DB_URL` is not needed for the basket-only v1.** Proven from the
  code at #1014: it is read only by the commerce routes
  (`cmd/api/main.go`) and by the command bridge (`cmd/api/glovo_bridge.go`);
  no basket code path reads it, and the bridge stays off (its flags are not
  set). The basket-only v1 does not inherit the full-M1 requirements in
  gitops#2563 (bridge, orders, join, commerce role); D0 only confirms that no
  commerce table is among the objects whose ownership moves.
- **Exact change** (per `deploy/staged/glovo-m1/db/roles.patch.md`):
  1. BEFORE any change, save the original owners and ACLs of every object that
     will move (tables, sequences, functions, the schema) to a file the
     operator keeps: this is the rollback source.
  2. ONE transaction that contains the whole ownership transfer, INCLUDING
     sequences and functions (a table moved without its sequences or trigger
     functions leaves a half-owned set), and the transitional grants to the
     legacy `mctl-api` role. If any statement fails, nothing is applied. The
     transitional grants are not a later, separate step.
  3. Switch the work-items store to the explicit `WORK_ITEMS_DB_URL` for
     `mctl_api_workitems` (step W) and confirm healthy BEFORE D2.
- **Verification (read-only)**: the catalogue queries of `roles.patch.md`
  compared with the saved originals; the running mctl-api and DevLoop keep
  working: `mctl_get_service_status`, a DevLoop read, no new error lines in
  `mctl_get_service_logs`. The migrator's `-dry-run` is usable from here on.
- **Rollback**: from the SAVED owners and ACLs, never a blind REVOKE.

## Step W: reconciled A15 pieces (inert)

- **Who**: owner merges; the agent prepares the move PR from #2563.
- **Precondition**: D1 done and verified; the leak-guard change of "Leak guard
  at activation" is the first commit of the PR.
- **Exact change**: move the ExternalSecrets (`mctl-api-glovo-runtime-db`,
  `mctl-api-workitems-db`, `mctl-api-glovo-migrator-db`) and the inert env text
  of `deploy/staged/glovo-m1/db/mctl-api-env.patch.md` (`GLOVO_DB_URL`,
  `GLOVO_DB_RUNTIME_ROLE`, `GLOVO_DB_MIGRATION_ROLE`, `envFromOptionalSecrets`)
  into reconciled paths, plus the explicit `WORK_ITEMS_DB_URL` for
  `mctl_api_workitems`. No `GLOVO_ENABLED`. Marker bump (a Secret is new to
  the pods).
- **Verification**: `kubectl -n mctl-api get externalsecret` shows
  `SecretSynced` (status only; Secret `.data` is never read); pods Ready; no
  `invalid configuration` line.
- **Rollback**: revert the PR; Argo prunes the ExternalSecrets and the Secrets
  they own.

## Step D2: apply the three schemas with `glovo-migrate` (#1018)

- **Who**: operator, as `glovo_migrator`. FORBIDDEN until, in this order: D0
  inventory recorded and read; D1 applied and verified; a fresh review of
  #1018 on its final head; the disposable rehearsal below; and then a
  separate, recorded operator authorization for production D2 (and an agreed
  maintenance window).
- **Where it runs**: `cmd/glovo-migrate` is not in the mctl-api image and is
  not built by the release. The operator builds it from a checkout of the
  4.156.0 release tag (the commit the image's revision label names):
  `git checkout 4.156.0 && go build -o glovo-migrate ./cmd/glovo-migrate`
  (Go version from `go.mod`), and runs it from a host that reaches
  `shared-pg-rw.platform-db.svc:5432` (a port-forward or a pod in the
  cluster; never a public path). Record the binary's SHA-256 and the commit
  on mctl-api#1006. Until #1018 is on `main` the build uses its approved head
  `04e4dd95`; the tag build replaces that as soon as the code is released.
- **Credentials**: the migration DSN is read from the environment variable
  named by `-dsn-env` (default `MCTL_GLOVO_MIGRATE_DSN`), never from the
  command line, and is never printed. It must use `sslmode=require` or
  stricter over TCP and name role `glovo_migrator` (the tool refuses any other
  `current_user`, `-expect-role`). The operator exports it from the proposed
  Vault path `platform/mctl-api/glovo-migrator-database` (created in D1; step
  V) into the variable without echoing it; agents never read it.
- **Preflight (the tool does it)**: CREATE on the database, schema `public`
  and schema `glovo` (when present), USAGE on `plpgsql`, ownership of every
  table, function and sequence a step touches, no schema newer than the
  binary. A refusal is exit 1 and names what is missing.
- **Exact change, in this order**:
  1. `glovo-migrate -dry-run -workitems-role <work-items role> -runtime-role glovo_runtime`
     reads the catalogue and prints what the apply would do; applies nothing.
     This is the read-only inventory of the three target schemas. Read it
     with a reviewer. Exit 0 is "would apply cleanly", not "applied".
  2. Same flags without `-dry-run`: base, then approval v2, then basket v1,
     each in its own transaction, idempotent, each taking its advisory lock
     (`glovo-schema`, `glovo-approval-schema`, `glovo-basket-schema`). Quiet
     window; no open transaction on `public.action_approval_requests` (D0).
  3. `glovo-migrate -verify` (same flags): reads, changes nothing, exits 2
     unless all three schemas are ready.
- **Exit codes**: 0 ok; 1 refused (wrong role, no TLS, newer schema, ownership
  not transferred); 2 verify found the schemas not ready; 3 could not observe
  the catalogue, a lock timeout, or a step failed. A 3 is retried only after
  reading what it printed; an unobservable catalogue is never treated as
  "nothing to do".
- **Not applied here**: `-with-bridge`, `-with-orders`, `-with-join` of the
  older plan do not exist in #1018. The basket does not need those schemas
  (its decision gate is its own check, not `Store.Ready`). Whether 4.156.0
  reaches Ready without them is proven only by the rehearsal below.
- **Rehearsal**: run steps 1 to 3 first against a disposable copy of the
  database (restore of the D1 backup into a scratch instance, roles recreated)
  and record the exit codes. Production is not the first run.
- **Verification (read-only)**: `-verify` exit 0, plus: `SELECT max(version)
  FROM glovo.glovo_schema_version`, `glovo.approval_schema_version` (expect 2),
  `glovo.basket_schema_version` (expect 1); count of enabled triggers
  (`aar_guard`, `aar_binding_required`, `approval_bindings_guard`,
  `basket_approval_bindings_guard`, `basket_revisions_frozen`,
  `basket_revisions_no_truncate`, `baskets_guard`) is 7; the owner of the
  three binding-related tables is one role; table owner of the basket tables
  is `glovo_migrator`.
- **Rollback**: none needed (additive). See "Rollback" above.

## Step D3: shared-ledger smoke

Read-only: `GET /api/v1/action-approvals` as admin returns as before; the next
real DevLoop approval (or a synthetic one the owner chooses) creates and
decides normally. If anything on the DevLoop approval path regresses, stop:
this is the signal for the emergency `aar_guard` option above, with its own
approval.

---

## Leak guard at activation

`scripts/validate-glovo-m1-staging.py` denies `glovo|mctl-assistants` in any
file or path under `platform-gitops/**` (except `agents-state/`).
`gate.yaml` is never an unlock. The activation PRs therefore need the guard
changed, as the FIRST commit of each PR, reviewed on its own:

- replace the blanket deny by deny plus a per-file exact-line allowlist
  (`ALLOWED_LINES: {path: {exact line, ...}}`); a matching line not in the set,
  or a match in a file not in the map, still refuses;
- each activation PR adds only its own lines (the Ingress block and the
  reserved-host line for C; the env lines and the slot for B1, B2, W; the
  `zitadel-iac` additions for Z); removal PRs delete them;
- selftests added with it: an allowed line passes; the same line in another
  file refuses; an extra Glovo line next to an allowed one refuses; a file
  with only allowed lines but changed whitespace refuses; a forged
  `gate.yaml` still unlocks nothing.

The guard is PR-controlled content, so the reviewer reads its diff first and
the owner's merge GO names it. This is proposed text; nothing here changes the
guard. Until that first commit, every diff staged under
`deploy/staged/glovo-m1/` is refused if applied to a reconciled path, on
purpose (`REFUSED: Glovo/assistants reference in reconciled path`).

## Step Z: ZITADEL client and the owner's identity link

- **Who**: owner merges. The agent prepares the move PR from #2582.
- **Precondition**: R1 done (chart slot exists); D2 done. The #2582 note: the
  expected plan has no new action, one create plus an in-place update of
  Secret `mctl-api/mctl-api-oidc-zitadel`.
- **Exact change**: apply the diff of
  `deploy/staged/glovo-m1/zitadel-client.patch.md` (from #2582) to
  `platform-gitops/helm-charts/zitadel-iac`: `zitadel_application_oidc.
  mctl_api_glovo_basket`, a confidential web client with client_secret_basic,
  PKCE, authorization code only, one redirect `<SELF_URL>/glovo/basket/
  approvals/callback` = `https://api.mctl.ai/glovo/basket/approvals/callback`,
  opaque (BEARER) access token. It also adds `GLOVO_BASKET_UI_CLIENT_ID` and
  `GLOVO_BASKET_UI_CLIENT_SECRET` to the Secret. The `zitadel` Application
  applies it on sync (PostSync Job, and the hourly CronJob), so the merge is
  the production change.
- **Verification (read-only)**: the Job succeeded (`mctl_get_workflow_status`
  or `kubectl -n zitadel get jobs`); ZITADEL console shows the client with one
  redirect (owner). The Secret keys are verified by effect in B2, never read.
- **Rollback**: revert the PR; the Job removes the client. Pods are not
  affected before B2.

#### Checked against the code (2026-11-11, read-only)

The staged client of #2582 matches what the page does (mctl-api #1007/#1014):
confidential web application, `client_secret_basic`, PKCE, authorization code
grant only, one redirect `https://api.mctl.ai/glovo/basket/approvals/callback`,
`prompt=login` on the page's authorization request, BEARER access token. The
client id and secret reach the pods only as `GLOVO_BASKET_UI_CLIENT_ID` and
`GLOVO_BASKET_UI_CLIENT_SECRET` through the `glovoBasketUISecret` slot (B2).
This client is for the approval page only. The MCP clients (Inspector, Claude
connector) do not use it: they authenticate against the MCTL authorization
server (next section), which logs the user in through the existing ZITADEL
upstream.

### OAuth discovery, audience and scopes (MCP side)

- Protected-resource metadata is served on the Glovo host only, at
  `https://glovo.mctl.ai/.well-known/oauth-protected-resource` (and the `/mcp`
  suffixed path): `resource` is exactly `GLOVO_MCP_RESOURCE`
  (`https://glovo.mctl.ai/mcp`), `authorization_servers` is
  `["https://api.mctl.ai"]`, `scopes_supported` is `[]`. The 401 from `/mcp`
  carries `WWW-Authenticate: Bearer resource_metadata="..."`.
- The authorization server is the existing MCTL one at `https://api.mctl.ai`
  (discovery at `/.well-known/oauth-authorization-server`, PKCE S256). The
  Glovo token's audience is the resource (`https://glovo.mctl.ai/mcp`); the
  platform `/mcp` refuses it and `/mcp` on the Glovo host refuses a platform
  token (N3, N4). Authorization is the allowlist and the team grant, not an
  OAuth scope: no new scope is defined or needed.
- Redirect URIs for the MCP client are the existing
  `OAUTH_ALLOWED_REDIRECT_URIS` entries (the Inspector callback
  `http://localhost:6274/oauth/callback`, the Claude connector callback
  `https://claude.ai/api/mcp/auth_callback`); no change. The approval page
  callback above is a different client and a different redirect.

### Tenant binding and allowlist

A basket belongs to an explicit team (tenant) chosen on the consent screen;
it is never inferred. Access needs two things at once: an allowlist entry
`(team, principal)` (step A; empty until an admin writes it) and a live team
grant for that principal. Another team's baskets, and another user's baskets
in the same team, are refused (N6, N8). The approval decision requires live
`developer` membership of the basket's team.

### The owner's identity link (once, owner)

The approval page resolves the person with `auth.UserForSignIn` from the ZITADEL
subject of a fresh sign-in, as the same principal a bearer of theirs would be.
The owner already signs in to MCTL through ZITADEL (`OAUTH_UPSTREAM: zitadel`),
so a link normally exists. Verify before B2: `mctl_whoami` returns the owner's
principal; the identity-link list (`GET /api/v1/identity/links`, as the owner)
shows a ZITADEL link. If it does not, the owner runs the browser link flow
(`/identity/link/zitadel`) once, signed in as the same ZITADEL user they use at
the page. An unlinked identity gets the uniform 404 page and no decision form.

## Step B1: basket MCP on, page off

- **Who**: owner merges; the agent prepares the PR from `canary/env.patch.md`
  (diff B1).
- **Precondition**: R1, D2 verified; W done (explicit `WORK_ITEMS_DB_URL` for
  `mctl_api_workitems` live and healthy); the `OAUTH_DB_URL` CHECK done and
  recorded by the operator (names only: whether `mctl-api-secrets` supplies
  it, that the DSN is the intended database, that its role has the needed
  grants; agents never read Secret data; no automatic fallback to
  `AUDIT_DB_URL`); the allowlist is empty (never written); if the pilot team
  is `admins`, the extra `GLOVO_NON_SELECTABLE_TENANTS` line of
  `canary/env.patch.md` is in the PR and its proof (below) is recorded.
- **Exact change**: diff B1 of `deploy/staged/glovo-m1/canary/env.patch.md`:
  `GLOVO_ENABLED: "true"`, `GLOVO_MCP_RESOURCE:
  https://glovo.mctl.ai/mcp`, `GLOVO_BASKET_MCP_ENABLED: "true"`, marker
  `2026-MM-DD-glovo-basket-b1`. All flags are read at start; Argo rolls the
  pods.
- **Verification (read-only)**: pods Ready on the new revision; startup log
  has no `invalid configuration`; `/readyz` unchanged. Not yet reachable
  publicly (no Ingress host): the host-routed router lives in the pods only.
  The synthetic connection routes on the main host answer 503 `not_ready`
  (`/api/v1/glovo/facade/context` with any token), confirming the shared
  `GLOVO_ENABLED` side effect is closed.
- **Rollback**: revert B1. A boot that refuses leaves the old pods serving
  (stalled rollout): read `mctl_get_service_logs` for the refusal line, which
  names the missing piece.

## Step B2: approval page on

- **Who**: owner merges; the agent prepares the PR (diff B2).
- **Precondition**: Z done (keys exist); the owner's identity link verified;
  the #1017 chart (slot and `extraPaths`) released and pinned (R1).
- **Exact change**: diff B2: `glovoBasketUISecret: mctl-api-oidc-zitadel`,
  `ingress.extraPaths: [/glovo]` (routes the page on `api.mctl.ai`),
  `GLOVO_BASKET_UI_ENABLED: "true"`, marker `2026-MM-DD-glovo-basket-b2`.
  Apply B2 on top of B1 only; the diffs were generated as a stack
  (B1, B2, C) and verified with `git apply --check` in that order.
- **Verification (read-only)**: startup log line `glovo basket approval page
  enabled` with provider `zitadel` (the alternative is one ERROR line listing
  what is missing). `GET https://api.mctl.ai/glovo/basket/approvals/aar_x`
  returns a uniform page (no state, no oracle).
- **Rollback**: revert B2 (flag off first); the MCP keeps working but
  `glovo_request_approval` no longer returns `approval_url`.

## Step C: Ingress host

- **Who**: owner merges; the agent prepares the PR from
  `canary/ingress.patch.md`.
- **Precondition**: B1 and B2 verified; the reserved-host proof
  (`scripts/test-reserved-hosts-policy.sh --services --platform --admit` on a
  live route dump) clean; the #1017 per-host `paths` chart released and pinned
  (R1).
- **Exact change**: the Ingress host with two paths and `glovo.mctl.ai:
  [mctl-api]` in `reservedPlatformHosts`. No DNS, no Cloudflare change: the
  `*.mctl.ai` wildcard A record is proxied and already resolves; edge TLS is
  `strict` against the Origin CA wildcard that Traefik serves.
- **Verification (read-only)**: the `curl` block of `ingress.patch.md`: `/mcp`
  401 with `resource_metadata`, the metadata names resource
  `https://glovo.mctl.ai/mcp` and `https://api.mctl.ai` as authorization
  server, every other path 404. A 403 or HTML challenge body means a
  Cloudflare bot rule (UNVERIFIED until now): stop and report.
- **Rollback**: revert C first (kill switch step 1).

## Step A: allowlist entry (data, owner)

- **Who**: owner, with the platform-admin credential (human admin only; the
  agent has none and uses none).
- **Precondition**: C verified; the team chosen: tentatively `admins`, ONLY
  after proof of the owner's OAuth session and live `developer` membership of
  it (`mctl_whoami` for the principal id; the tenant membership read; both as
  the owner, never an agent or service identity). Because `admins` is
  unselectable by default (`GLOVO_NON_SELECTABLE_TENANTS`), choosing it needs
  the extra B1 line; if the proof fails, another team is chosen instead and
  no override is added. The decision handler requires live `developer`
  membership of the basket's team.
- **Exact change**: `PUT /api/v1/glovo/pilot/<team>/principals/<owner
  principal>` on `https://api.mctl.ai`. Exactly one entry. Never
  widen the list during the canary.
- **Verification**: by effect, in step E (a read route for the allowlist is not
  assumed).
- **Rollback**: `DELETE` the same path. Instant, no deploy.

---

## Step E: the DoD run

All of E1 to E5 on production, in order.

**E1 (agent, no credentials).** Discovery:

```bash
curl -sSi https://glovo.mctl.ai/mcp | head -n 12
curl -sS https://glovo.mctl.ai/.well-known/oauth-protected-resource
curl -sS https://api.mctl.ai/.well-known/oauth-authorization-server | head -c 600
```

Expect 401 with `resource_metadata`, resource `https://glovo.mctl.ai/mcp`,
and the authorization-server metadata with PKCE S256.

**E2 (agent + owner login).** A real OAuth MCP client, not a test harness: the
MCP Inspector (`npx @modelcontextprotocol/inspector`, transport Streamable
HTTP, URL `https://glovo.mctl.ai/mcp`; its callback
`http://localhost:6274/oauth/callback` is already in `OAUTH_ALLOWED_REDIRECT_URIS`),
or a Claude custom connector (`https://claude.ai/api/mcp/auth_callback` is
also allowed). The agent may drive a scripted client bound to that callback;
the human step is the ZITADEL login and the team consent screen, done by the
owner in their own browser, choosing the team explicitly. The token stays in
the client's memory and is never printed or written. The in-repo E2E tests
(`glovo_basket_*_e2e_test.go`) use a fake ZITADEL and do not count for the DoD.

**E3 (client).** `tools/list` shows exactly six tools: `glovo_list_products`,
`glovo_create_basket`, `glovo_update_basket`, `glovo_get_basket`,
`glovo_request_approval`, `glovo_approval_status`. Then: list products;
create a basket with `client_key` `canary-<date>`; update it with two or three
`FAKE-*` lines (the server computes prices; a client price is refused); read
it back; `glovo_request_approval` returns an `approval_url` of the form
`https://api.mctl.ai/glovo/basket/approvals/aar_...`; `glovo_approval_status`
shows `pending`.

**E4 (owner, personally).** The owner opens `approval_url` in their own
browser, signs in again (the page forces `prompt=login`), checks that the page
shows exactly the basket from E3 (lines, fees, total, currency, team, basket
id, revision, the fingerprint) and presses Approve (or Reject; either outcome
is a valid decision, the DoD records the owner's choice). The agent does not
open the link as the owner and does not call the decision route.

**E5 (client).** `glovo_approval_status` returns `approved` and
`authorizes_current_revision: true`. Replay: the owner reloads or resubmits the
confirm form: 400, state unchanged. The agent updates the basket (revision 2):
the old approval then reports `authorizes_current_revision: false`, a new
request creates a new `aar_` in `pending`, and the page offers no decision on
the superseded one. Record: image digest, gitops SHA, approval id, timestamps
(ids only) in mctl-api#1006 and #2457.

## Step N: "only the canary principal can reach it"

| # | Check | Expect | Who |
| --- | --- | --- | --- |
| N1 | `POST https://glovo.mctl.ai/mcp` with no token | 401, `WWW-Authenticate` has `resource_metadata` | agent |
| N2 | same with a garbage bearer | 401 `invalid_token` | agent |
| N3 | same with the owner's normal MCTL API token (audience `api.mctl.ai`), read from the environment, never printed | 401 `invalid_token` ("audience is not the glovo resource") | agent |
| N4 | the Glovo-audience token from E2 sent to `https://api.mctl.ai/mcp` | 401 (the platform `/mcp` refuses a Glovo audience) | agent via the scripted client |
| N5 | other paths on the Glovo host: `/healthz /readyz /openapi.yaml /docs /oauth/token /identity/links /api/v1/glovo/pilot /devloop/decide/x` | 404 each | agent |
| N6 | a second human account (not allowlisted) runs the same OAuth flow | no Glovo token (refusal at consent or token); no tool call succeeds | a second REAL human account is not chosen yet. A bot or service identity is never substituted; without a real test this row is reported UNPROVEN, not passed |
| N7 | allowlist drill: owner `DELETE`s the entry, the client calls `glovo_get_basket` | refused; then `PUT` again and the call succeeds | owner + agent |
| N8 | the approval page with a signed-in user who is not the basket owner | uniform 404 page (needs a second real human account; same rule as N6: UNPROVEN until tested) | owner supplies the account |
| N9 | decision replay (E5) | 400 | owner |
| N10 | kill switch: Ingress revert (C) | `https://glovo.mctl.ai/mcp` 404 at Traefik within about a minute; restore | owner |

## Step P: egress policy (separate gate, TODO)

Before P2 activation a default-deny, least-privilege outbound NetworkPolicy
for the Glovo workload must be in place. Another agent prepares it under its
own gate; link: TODO. Until it lands, "no Glovo egress" is a code-level
property only (no outbound client in the basket path; no egress policy exists
in namespace `mctl-api`, verified read-only 2026-11-11). This runbook neither
writes nor applies that policy.

## Step K: after the DoD

Decide with the owner whether the canary stays on. To stop: C revert, then the
allowlist `DELETE`, then B2 and B1 reverts. Basket data is insert-only and
stays. Close mctl-api#1006 only on the observed E5 result.

---

## What is not needed

- **DNS and Cloudflare**: none (wildcard proxied; no `dns.tf` change; no
  Terraform apply). **cert-manager**: no new token; the existing DNS-01 token
  covers `mctl.ai`. The edge uses the Origin CA wildcard, so a
  `mctl-api-glovo-mctl-ai-tls` certificate is optional.
- **Egress policy**: a default-deny, least-privilege outbound policy for the
  Glovo workload is a SEPARATE GATE, prepared by another agent, and must land
  before P2 activation. Link: TODO (not yet opened; this runbook does not
  prepare or apply it). It is a step, not an open question; see "Step P".
- **NetworkPolicy**: `allow-mctl-api-ingress` in namespace `mctl-api` already
  admits Traefik to every pod of the namespace; the host-routed MCP is the
  same pods and the same port. There is no egress policy in that file, and none exists in the namespace
  (verified read-only 2026-11-11), so "no Glovo egress" is a property of the
  code (no outbound client in the basket path), not of the network. The
  Glovo database is the same `shared-pg-rw.platform-db.svc:5432` as the audit
  and lifecycle databases. ZITADEL is reached like the existing identity-link
  and OAuth flows. The basket MCP calls no other service. No change.
- **RBAC / Kubernetes API**: the basket MCP uses none (the `mctl-api-rbac`
  Role covers Argo Workflows only). No change, no ServiceAccount change.
- **Temporal, Telegram, bridge, join, control worker, three images**: not in
  the canary; their flags stay unset (see `env.patch.md`).
- **A second workload or Service**: none; `mctl-api` serves the host.
- **New Secret, Vault path or policy for the basket itself**: none beyond the
  A15 database credentials (the three proposed Vault paths of step V, none of
  which exists yet) and the two ZITADEL client keys.

## Could not determine (from this repository, read-only)

1. Which Postgres versions and real legacy objects production has beyond what
   the migrator preflight checks (only 16.15 was observed): answered by step
   D0, not by this repository. The migrator itself is #1018 (approved at
   `04e4dd95`, not in the image): the operator builds it from the release tag
   (D2).
2. The real `OAUTH_DB_URL`: the live Deployment spec has no literal
   (only `AUDIT_DB_URL` and `LIFECYCLE_DB_URL`); `mctl-api-secrets` may supply
   it via `envFrom`, which agents do not read. This is the operator's CHECK
   before B1 (names only), not a decision to default it to `AUDIT_DB_URL`.
3. Whether any Secret already supplies a `GLOVO_*` name (the #2529 G4(b)
   names-only check, by the operator).
4. After the ownership transfer: how the legacy `mctl-api` role keeps its
   startup DDL, which role the work-items DSN uses, and the role of
   `COMMERCE_DB_URL` (all open in gitops#2563).
5. Table sizes and open transactions on `action_approval_requests` at the
   moment of D2 (the 55 MB figure is the whole database). The migrator sets a
   5s `lock_timeout` by default.
6. Whether Cloudflare bot rules challenge a non-browser MCP client on the new
   host (checked at step C, first real request).
7. Proof of the owner's OAuth session and `developer` membership of `admins`
   (tentative pilot team); a second real human account for N6 and N8 (not
   chosen; UNPROVEN until tested).
8. Whether 4.156.0 reaches the same `Ready` state with the bridge, orders and
   join schemas absent: the code paths read here (`scope.Resolver`,
   `GlovoBasketDecisions.ReadyFn`) do not use `glovo.Store.Ready`, but this is
   proven only by the rehearsal on a disposable database, not run here.
9. Whether Super Bot Fight Mode treats the new host like `api.mctl.ai`.
10. Whether the PR release route is proven live: it is proven only by the first
    real routed bump (does Claude approve an App-authored PR, does the
    review-triggered auto-merge fire). 4.156.0 may be that first bump; if it
    is not proven by then, the owner decides between a hand-run PR and the
    direct route for that release.
11. Egress: no egress NetworkPolicy exists; the least-privilege policy is
    step P (separate gate, TODO).
