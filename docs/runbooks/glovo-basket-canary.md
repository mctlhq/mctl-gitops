# Glovo Basket MCP: production canary activation runbook

Source: mctlhq/mctl-api#1006 (working issue), plan mctlhq/mctl-gitops#2457.
Code: mctl-api #1007 (approval page), #1008 (MCP and store), #1014
(integration of both). #1013 (provider planner) is not needed.
Earlier fake-order package and runbook: `docs/runbooks/glovo-m1.md` (not used
by this canary; its Temporal, Telegram and three-image parts are deferred).

This file is a preparation artifact. Nothing here is applied by merging it.
Every step that changes production is its own PR or operator action with its
own explicit owner GO. Merging a PR in this repository IS a production change
(the `admins-mctl-api` Application auto-syncs with prune and selfHeal), so a
step's "merge" is the step.

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
| 2 | R1 | mctl-api 4.156.0 with the Basket code and three chart changes, deployed dark (image tag only, no Glovo env) | mctl-api, mctl-gitops bump | owner (release), release-deploy path |
| 3 | V | Vault `zitadel-admin` 8h role (gitops#2584), for the operator session | mctl-gitops | owner |
| 4 | D1 | Database roles, transitional grants, ownership transfer (A15 operator plan) | database | operator |
| 5 | W | Move the A15 ExternalSecrets and the inert `GLOVO_DB_*` env into reconciled paths | mctl-gitops | owner |
| 6 | D2 | Apply three schemas as `glovo_migrator`: Glovo base, approval v2, basket v1 | database | operator |
| 7 | Z | ZITADEL client `mctl-api-glovo-basket` (gitops#2582 moved to `zitadel-iac`) with the leak-guard change | mctl-gitops | owner |
| 8 | B1 | `GLOVO_ENABLED`, `GLOVO_MCP_RESOURCE`, `GLOVO_BASKET_MCP_ENABLED` + marker | mctl-gitops | owner |
| 9 | B2 | `glovoBasketUISecret` slot, `GLOVO_BASKET_UI_ENABLED` + marker | mctl-gitops | owner |
| 10 | C | Ingress host `glovo.mctl.ai`, reserved host | mctl-gitops | owner |
| 11 | A | Allowlist entry for the canary (team, principal) | API call | owner (admin credential) |
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

- **Who**: owner decides the release; the platform release path (MCTL MCP /
  Control Plane, then `release-deploy` bump) deploys. The agent does not tag,
  bump or redeploy.
- **Precondition**: #1007, #1008, #1014 reviewed on their final heads
  (Claude and agy, no unaddressed P1/P2, CI green) and merged into mctl-api
  `main` only after the 4.155.0 decision, with #1014 retargeted to `main`
  before #1008's branch is deleted. The three chart changes below are in the
  same release: (a) per-host `paths` in `helm/templates/ingress.yaml`,
  (b) `/glovo` in the default `paths`, (c) the `glovoBasketUISecret` slot. The
  chart tracks mctl-api `main`, so they go live at the merge, all inert: no
  host sets `paths`, no code answers `/glovo/*`, no env fills the slot.
- **Exact change**: image tag bump only. No Glovo env, no flag.
- **Verification (read-only)**: `mctl_get_service_status mctl-api`; pods Ready;
  `curl -sS -o /dev/null -w '%{http_code}\n' https://glovo.mctl.ai/mcp` is
  still a Traefik 404; startup log has no `glovo basket` line.
- **Rollback**: revert the tag to 4.155.0 through the release path. Chart skew
  is harmless (the chart changes are inert).
- **Why before the database**: 4.155.0 verifies the approval schema at version
  1 (`glovoApprovalSchemaVersion = 1` at `081bd6b7`); 4.156.0 verifies version
  2. Applying v2 while 4.155.0 is the only image would make the order-pilot
  readiness report `approval_schema_not_ready` (dark, so harmless, but it is a
  skew to avoid).

## Step V: Vault admin session (optional but advised)

- **Who**: owner. **Change**: merge gitops#2584 (Draft today) after its own
  review. **Verification** (from the PR): `vault read sys/auth/mctl/tune`
  (max 8h, default 1h), `vault read auth/mctl/role/zitadel-admin`.
- **Why**: steps D1 and D2 are one unattended operator session of more than the
  1h default token life.
- **Rollback**: the PR's runbook section (revert needs the role in
  `allowedDeletes`). A leaked 8h token is revoked with `vault token revoke
  -accessor`.
- The owner logs in with `! vault login -method=oidc -path=mctl
  role=zitadel-admin`; the agent never holds the token.

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

No binary in mctl-api `main` calls the three `Apply*` functions. The planned
`cmd/glovo-migrate` (mctl-api#1004) is not merged and has no `-with-basket`
step. This is the main open item (see "Could not determine").

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
(SQLSTATE 55P03) and is retried; the schema steps are idempotent. The unknown
is whether `cmd/glovo-migrate` sets a `lock_timeout` itself (not in main).

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

- **Who**: operator (owner), with the 8h Vault session of step V.
- **Precondition**: R1 done; gitops#2563 and gitops#2579 resolved on their
  open items (UNVERIFIED list in #2563: `COMMERCE_DB_URL` role, connection
  limits, grantees via `aclexplode`, sequence ownership after the transfer,
  whether `work_items_schema_version` exists, URL-safe migrator password);
  Vault values for the three roles created by the operator; a fresh logical
  backup or snapshot of database `mctl-api` recorded (the 55 MB database makes
  this cheap).
- **Exact change**: per `deploy/staged/glovo-m1/db/roles.patch.md`: read-only
  catalogue inventory first and the recorded ACL and owner; then ONE
  transaction with the ownership transfer, followed by the transitional grants
  to the legacy `mctl-api` role.
- **Verification (read-only)**: the `-verify` mode of the migrator once it
  exists, else the catalogue queries of `roles.patch.md`; the running
  mctl-api and DevLoop keep working: `mctl_get_service_status`, a DevLoop
  read, no new error lines in `mctl_get_service_logs`.
- **Rollback**: from the RECORDED owner and ACL, never a blind REVOKE.

## Step W: reconciled A15 pieces (inert)

- **Who**: owner merges; the agent prepares the move PR from #2563.
- **Precondition**: D1 done and verified; the leak-guard change of "Leak guard
  at activation" is the first commit of the PR.
- **Exact change**: move the ExternalSecrets (`mctl-api-glovo-runtime-db`,
  `mctl-api-workitems-db`, `mctl-api-glovo-migrator-db`) and the inert env text
  of `deploy/staged/glovo-m1/db/mctl-api-env.patch.md` (`GLOVO_DB_URL`,
  `GLOVO_DB_RUNTIME_ROLE`, `GLOVO_DB_MIGRATION_ROLE`, `envFromOptionalSecrets`)
  into reconciled paths. No `GLOVO_ENABLED`. Marker bump (a Secret is new to
  the pods).
- **Verification**: `kubectl -n mctl-api get externalsecret` shows
  `SecretSynced` (status only; Secret `.data` is never read); pods Ready; no
  `invalid configuration` line.
- **Rollback**: revert the PR; Argo prunes the ExternalSecrets and the Secrets
  they own.

## Step D2: apply the three schemas

- **Who**: operator, as `glovo_migrator` (the #2563 Job once its image and
  command exist, or an operator-run binary).
- **Precondition**: D1 verified; W done (credentials present); no open
  transaction on `public.action_approval_requests` (`pg_stat_activity`, read
  only); quiet window; the migration DSN carries `lock_timeout` as above.
- **Exact change**: in order, `glovo.ApplySchema`, then
  `workitems.ApplyGlovoApprovalSchema` (with the work-items role and
  `glovo_runtime`), then `glovobasket.ApplySchema(…, "glovo_runtime")`.
  The #2563 job args also name `-with-bridge`, `-with-orders`, `-with-join`
  (needed by the order pilot's colocation proof); the basket needs none of
  them (its decision gate is its own schema check, not `Store.Ready`). Whether
  to apply them anyway is an owner decision, not assumed here.
- **Verification (read-only)**: `SELECT max(version) FROM
  glovo.glovo_schema_version`, `glovo.approval_schema_version` (expect 2),
  `glovo.basket_schema_version` (expect 1); count of enabled triggers
  (`aar_guard`, `aar_binding_required`, `approval_bindings_guard`,
  `basket_approval_bindings_guard`, `basket_revisions_frozen`,
  `basket_revisions_no_truncate`, `baskets_guard`) is 7; the owner of the
  three binding-related tables is one role; table owner of the basket tables is
  `glovo_migrator`.
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
guard.

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
- **Precondition**: R1, D2 verified; W done; `OAUTH_DB_URL` question answered
  (see env patch, Unknowns); the allowlist is empty (never written).
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
  chart slot released (R1).
- **Exact change**: diff B2: `glovoBasketUISecret: mctl-api-oidc-zitadel`,
  `GLOVO_BASKET_UI_ENABLED: "true"`, marker `2026-MM-DD-glovo-basket-b2`.
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
  live route dump) clean; R1's per-host `paths` chart change released.
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
- **Precondition**: C verified; the team chosen; the owner holds `developer`
  membership of it (the decision handler requires live `developer` membership
  of the basket's team); the owner's principal id from `mctl_whoami`.
- **Exact change**: `PUT /api/v1/glovo/pilot/<team>/principals/<owner
  principal>` on `https://api.mctl.ai`. Exactly one entry. `admins` is
  non-selectable by default and is not the team. Never widen the list during
  the canary.
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
| N6 | a second human account (not allowlisted) runs the same OAuth flow | no Glovo token (refusal at consent or token); no tool call succeeds | owner supplies the account; if none exists this row is reported UNPROVEN, not passed |
| N7 | allowlist drill: owner `DELETE`s the entry, the client calls `glovo_get_basket` | refused; then `PUT` again and the call succeeds | owner + agent |
| N8 | the approval page with a signed-in user who is not the basket owner | uniform 404 page (needs a second account; same rule as N6) | owner supplies the account |
| N9 | decision replay (E5) | 400 | owner |
| N10 | kill switch: Ingress revert (C) | `https://glovo.mctl.ai/mcp` 404 at Traefik within about a minute; restore | owner |

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
- **NetworkPolicy**: `allow-mctl-api-ingress` in namespace `mctl-api` already
  admits Traefik to every pod of the namespace; the host-routed MCP is the
  same pods and the same port. There is no egress policy in that file. The
  Glovo database is the same `shared-pg-rw.platform-db.svc:5432` as the audit
  and lifecycle databases. ZITADEL is reached like the existing identity-link
  and OAuth flows. The basket MCP calls no other service. No change.
- **RBAC / Kubernetes API**: the basket MCP uses none (the `mctl-api-rbac`
  Role covers Argo Workflows only). No change, no ServiceAccount change.
- **Temporal, Telegram, bridge, join, control worker, three images**: not in
  the canary; their flags stay unset (see `env.patch.md`).
- **A second workload or Service**: none; `mctl-api` serves the host.
- **New Secret, Vault path or policy for the basket itself**: none beyond the
  A15 database credentials and the two ZITADEL client keys.

## Could not determine (from this repository, read-only)

1. Which program applies the three schemas in production: `cmd/glovo-migrate`
   (#1004) is not merged and has no basket step; the basket and approval-v2
   `Apply*` functions have no caller in `cmd/`.
2. Whether `OAUTH_DB_URL` is set explicitly in production (Secret names and
   data are not read). B1 refuses the boot if it is not.
3. Whether any Secret already supplies a `GLOVO_*` name (the #2529 G4(b)
   names-only check, by the operator).
4. After the ownership transfer: how the legacy `mctl-api` role keeps its
   startup DDL, which role the work-items DSN uses, and the role of
   `COMMERCE_DB_URL` (all open in gitops#2563).
5. Table sizes and open transactions on `action_approval_requests` at the
   moment of D2 (the 55 MB figure is the whole database); whether the migrator
   sets a `lock_timeout`.
6. Whether Cloudflare bot rules challenge a non-browser MCP client on the new
   host (checked at step C, first real request).
7. The team the owner uses and their membership role; a second human account
   for N6 and N8.
8. Whether 4.156.0 reaches the same `Ready` state with the bridge, orders and
   join schemas absent: the code paths read here (`scope.Resolver`,
   `GlovoBasketDecisions.ReadyFn`) do not use `glovo.Store.Ready`, but this is
   proven only by the rehearsal on a disposable database, not run here.
9. Whether Super Bot Fight Mode treats the new host like `api.mctl.ai`.
