# Glovo C2 cutover plan (owner-only stage)

Status: PLANNING DOCUMENT, a draft for review. Closes the problem statement of
mctlhq/mctl-gitops#2777. It authorizes nothing: no merge, no release, no
deploy, no flag flip, no admission and no edge change happens because of this
file. Every production effect below needs its own separately recorded owner
GO (c2-operations runbook, section 2.2, mctlhq/mctl-glovo; unmerged draft at
the time of writing, [U]).

Parent epic: mctlhq/.github#365. Gate matrix: mctlhq/mctl-glovo#40. The
rollback rehearsal is performed by mctlhq/mctl-glovo#43, not here.

Facts are tagged. `[V]` = verified by reading the cited path or API object on
the cited date (2026-11-18), at the cited SHA; this is "present in the file",
never "observed in the cluster". `[U]` = unknown or not verified. No live
state (cluster, Vault, ArgoCD, Cloudflare, tailnet, the mini) was read.

## 1. Scope

In: the order of the gitops switches for the first live stage, "owner-only,
read-only" (one principal, no basket writes, no checkout or payment ever); how
the public route is opened and closed; how the old mini route stays as the
fallback; who may change capacity; which steps are the owner's own (Vault, UI).

Out: stages 2, 10 and 20 users, basket writes (they need mctl-api#1011 and
#1012 and a separate canary GO), any change of the allowlist or capacity
beyond what a step names, Cloudflare apply (manual dispatch plus owner
approval, never implied by a merge).

## 2. State on main (basis of the plan)

| # | Fact | Tag | Source |
|---|---|---|---|
| F1 | All five existing switches `deploy`, `c2`, `allowlist`, `consent`, `control` are `false`. | [V] | `platform-gitops/bootstrap/values.yaml`, block `mctlGlovo`, main d712360fc |
| F2 | Render rules: `deploy` refuses the placeholder image tag; `c2` needs `deploy`; `allowlist`, `consent`, `control` need `c2`; `c2` needs `allowlist` or `consent`. | [V] | `platform-gitops/bootstrap/templates/mctl-platform/mctl-glovo.yaml` |
| F3 | The pinned service image tag is `0.1.0`, the only release at the time; it predates the read-only-by-default change (mctl-glovo#54, merged aa9b3cc3, unreleased). Deploying `0.1.0` does not give the read-only guarantee. | [V] | template image block; `gh api repos/mctlhq/mctl-glovo/releases`; mctl-glovo#59 (0.2.0) open |
| F4 | The service has a ClusterIP Service and, before the wiring PR below, no Ingress object. | [V] | same template |
| F5 | `glovo.mctl.ai` is in `reservedPlatformHosts` with an EMPTY owner list; admission (`mctl-reserved-platform-hosts-ingress`) refuses an Ingress for a reserved host from any namespace that is not an owner. | [V] | `bootstrap/values.yaml` (`reservedPlatformHosts`), `bootstrap/templates/system/admission-policies.yaml` |
| F6 | The public host is served by a Cloudflare tunnel to the mini (`glovo-home`). Worker routes: `glovo.mctl.ai/` and `glovo.mctl.ai/*` go to the `glovo-landing` Worker; `glovo.mctl.ai/mcp*` and `glovo.mctl.ai/.well-known/*` have no script (tunnel origin). There is NO route for `/link*`: with the current routes `/link` is answered by the landing Worker, not by an origin. | [V] | `infrastructure/cloudflare/zones/mctl-ai/workers.tf`, `scripts/validate-cloudflare-glovo-routes.py` |
| F7 | Where the tunnel's public-hostname and origin mapping is defined (which origin answers `/mcp`) is not in this repository. | [U] | not found by grep over `infrastructure/` |
| F8 | The service reads capacity from `GLOVO_C2_CAPACITY` (1..20, more is a boot error); mctl-api reads the same variable as the consent slot cap (unset, 0 or malformed means closed: no new consent). The template hard-coded `10`. | [V] | mctl-glovo `cmd/mctl-glovo/c2.go`, mctl-api `cmd/api/glovo_consent.go`, `docs/glovo-link-consent.md` (main, aa9b3cc3 and the 2026-11-18 mctl-api main) |
| F9 | The service's optional link-login variables `GLOVO_LINK_RESOURCE` and `GLOVO_LINK_MAX_AUTH_AGE` were added by mctl-glovo#56 (merged 2026-11-18, in release 0.2.0). Unset means the link preview and upload routes answer 503. A set-but-wrong value stops the boot. | [V] | mctl-glovo PR 56 `cmd/mctl-glovo/c2.go` |
| F10 | `/link` page, `/link/code`, `/link/preview`, `/link/upload`, `/link/unlink` (since mctl-glovo#64) and `/mcp` plus the RFC 9728 metadata are what the service mounts when C2 is on; the kill switch endpoint is `PUT /internal/v1/control/kill-switch`, mounted only with the control configuration; the same configuration also mounts `POST /internal/v1/control/unlink` and `/erase` (mctl-glovo#64, no mctl-api caller yet). Health paths `/livez`, `/readyz`. | [V] | `internal/linkflow/linkflow.go`, `cmd/mctl-glovo/control.go`, `cmd/mctl-glovo/mcp.go` (main) |
| F11 | mctl-api reads, for the consent side: `GLOVO_CONSENT_ENABLED`, `GLOVO_CONSENT_SERVICE_PROVIDER`, `GLOVO_CONSENT_SERVICE_SUBJECT`, `GLOVO_CONSENT_DB_URL` (else `AUDIT_DB_URL`), `GLOVO_C2_CAPACITY`. The reader provider must be a federated provider entry of KIND SERVICE in `MCTL_OIDC_PROVIDERS` and the subject must be in that entry's `service_subjects`. | [V] | mctl-api `cmd/api/glovo_consent.go`, `cmd/api/check_config.go` |
| F12 | RESOLVED 2026-11-19 (was a blocker). The `zitadel` entry of `MCTL_OIDC_PROVIDERS` carries `customers_org_id` AND, since mctl-api 4.169.0 (9aa297e, 4.165.0 to 4.168.0 refuse to boot on the combination), may list `service_subjects` for exact subjects: the consent reader machine user is a `kind: service` identity pinned to the mctl_api project id, never a customer, no groups. `service_subjects` for it is on main (gitops#2817, 1bea2d2a1). Not yet shown: the pinned image's own `--check-config` on the rendered config for the current pin (it runs in CI on amd64 via `scripts/check-mctl-api-oidc-config.py`; it cannot run on an arm64 laptop). | [V] source on main, [U] live | `platform-gitops/helm-charts/zitadel-iac/iac/mctl-api.tf`, gitops#2817, mctl-api 9aa297e |
| F13 | The consent read route is confined to the one configured service identity; the service reads it with a ZITADEL machine-user token written by its `token-refresher` sidecar (the `consent` switch). | [V] | mctl-api `docs/glovo-link-consent.md`; `mctl-glovo.yaml` (consent block) |
| F14 | mctl-gitops#2742 (control-caller token wiring for the kill switch) is a draft, dark. It needs the mctl-api chart pin to carry the `extraContainers` / `extraVolumes` / `extraVolumeMounts` slots (`chartSlots`), a released refresher tag and command, and a Vault role that reads one key. | [V] | PR 2742 diff |
| F15 | The mctl-api config guard (`--check-config` in the image) cannot be run offline; consent settings are cross-checked by it at release time. | [U] | `scripts/check-mctl-api-oidc-config.py` needs the image |
| F16 | Prerequisites outside gitops that gate the flip order, state 2026-11-19: mctl-api A2 (fresh-login, link audience) MERGED (#1129) and released in 4.170.0; mctl-api#1116 (masked identity) and the consent text `c2-link-v2` (#1126) released in 4.170.0; the consent page for every client kind (#1133) released in 4.170.1, LIVE 2026-11-19; mctl-glovo B2 `glovo-link` (#63) and `-unlink` (#64) merged, 0.2.0 released (tag d95db5096, contains `glovo-link`), 0.3.0 release PR open. All `mctlGlovo` switches stay false, the template pin is still `0.1.0`. Still open outside gitops: no live run of link or unlink, the fixed client id for `glovo-link` is not named, `GLOVO_LINK_RESOURCE` is not set anywhere. | [V] on GitHub as of 2026-11-19 | mctl-api #1116, #1126, #1129, #1133, releases 4.170.0 and 4.170.1; mctl-glovo #56, #63, #64, release 0.2.0 |
| F17 | Live versions of mctl-api and the service, ArgoCD sync, Vault contents and roles, CNPG state, tailnet ACL, the mini's allowlist. | [U] | not read |

## 3. Wiring that this plan assumes (the dark wiring PR)

The companion PR "feat(c2): dark wiring for the owner-only cutover (#2777)"
adds, all default false or unchanged, no existing switch touched:

| Value in `mctlGlovo` | Default | Effect when on |
|---|---|---|
| `linkLogin` | false | Sets `GLOVO_LINK_RESOURCE` (`https://<host>/link`) and `GLOVO_LINK_MAX_AUTH_AGE` (`linkMaxAuthAge`, default 5m, at most 15m). Needs `c2`. |
| `ingress` | false | One Ingress for `host` with the paths `/mcp`, `/link`, `/.well-known/oauth-protected-resource`; a Traefik-only source in the server policy; `GLOVO_LINK_TRUSTED_PROXIES`. Needs `c2`, `trustedProxies`, and the host's `reservedPlatformHosts` owner list to include the namespace; each missing one fails the render. |
| `apiConsent` | false | mctl-api gets `GLOVO_CONSENT_ENABLED=true`, `GLOVO_C2_CAPACITY` and the optional Secret `mctl-api-glovo-consent` (reader provider and subject, from Vault). |
| `capacity` | 10 | The one cohort size for the service and mctl-api. Whole number 1..20, else the render fails. |
| `host`, `trustedProxies`, `linkMaxAuthAge` | `glovo.mctl.ai`, empty, `5m` | Inputs of the above. |

Until that PR merges, rows below that rely on it are plans, not facts [U].

## 4. Flip order

Rule for the whole table: one switch per PR; every PR goes through the normal
review gate; a flip merged is not a flip observed (read the evidence after,
never assume); rollback of a switch is setting it back to `false` (capacity:
back to the previous number) in its own PR. Schema is forward-only: no step
below rolls the database back (c2-operations runbook, 10.2 and 10.3 [U,
unmerged]).

Owner column: AGENT = lead or agent (PR and review gate, read-only
verification); OWNER = the owner only (Vault, UI, MFA, decision); the owner's
GO for the action and window is required for every row that has a production
effect.

| Step | Switch / action | Who | Precondition evidence (before) | Effect | Rollback and proof it is closed |
|---|---|---|---|---|---|
| 0 | No switch. Code and releases: mctl-glovo release containing #53, #54 (read-only by default) and #56; mctl-api release with A1, A2 and the matching consent text version; service-kind provider entry for the reader (F12); gitops tag bump of the service image. | AGENT | Release tags and image digests on the exact SHAs; CI green; the matrix #40 rows updated with 40-hex SHA evidence. | none | not needed |
| 1 | Vault and infrastructure (owner). Names in section 7. | OWNER | Field names and metadata only, never values (`vault kv metadata get`). `[U]` today. | none (nothing reads them yet) | delete the entries |
| 2 | `deploy: true` (and the image tag set to the step 0 release). | AGENT, GO | Tag is not the placeholder (render refuses otherwise); database `mctl-glovo` and roles `glovo_c2_runtime` / `glovo_c2_migrator` in the CNPG manifests (present on main, [V] `infra-components/data/cnpg/shared/`), actual state [U]; step 1 migrator credentials exist. | Namespace, migration Job, a bare Deployment (no C2 code path). | `deploy: false`. Closed: the Deployment is gone. The schema stays (forward only). Evidence after: Job exit 0 and "schema at version N"; `/readyz` proves nothing about C2. |
| 3 | `apiConsent: true` (mctl-api side), with a `ROLLOUT_MARKER` bump in the same PR. | AGENT, GO | F12 solved (a service-kind provider entry and the subject exist); Vault `platform/mctl-api/glovo-consent` fields present; mctl-api image at the release with the consent routes (confirmed by `--check-config` in the release gate, F15); capacity value agreed (section 6). | mctl-api mounts the consent routes (record, read, withdraw) with the cap. No service reads them yet. | `apiConsent: false` (+ marker). Closed: `GET /api/v1/glovo/link-consent` answers 404 (routes unmounted); recorded consents stay in the table (history). |
| 4 | `c2: true` and `allowlist: true`, `capacity` set in this PR or left at its default. | AGENT, GO | Steps 2 and 3 observed; allowlist Vault entry holds exactly one principal (field count only); audit key, Vault transit key and role, tailnet key and proxy target present (names only); proxy reachable by the egress tag ACL [U]; image tag has read-only by default. | `GLOVO_C2_ENABLED=true`, Vault login, database connection, egress sidecars, `/link` and `/mcp` mounted INSIDE the cluster only (no route yet). Store ships KILLED. | `c2: false`. Closed: the routes answer 404 as seen from inside the cluster by a one-shot probe from an allowed namespace and the backend is identified by a distinct marker; `/readyz` is vacuously 200. Evidence after: no `exit` and no `initial jwks fetch failed` in a clean start. |
| 5 | `consent: true` (the service's reader and its `token-refresher` sidecar). | AGENT, GO | Step 3 observed; Vault `platform/mctl-glovo/consent-reader` (`key`, `user_id`, `key_id`, `scope`) present; zitadel-iac machine user applied (#2737). | The service reads consent from mctl-api; an active `glovo:c2` consent admits a principal (narrowed by the allowlist). | `consent: false`. Closed: the token file disappears and consent reads refuse (fail closed). Evidence after: refresher log `token refreshed`. |
| 6 | `control: true` and the #2742 chain: prerequisites, then `chartSlots: true` with the chart pin move and the refresher tag and command, then `apiC2Control.enabled`, verify the Secret and the token file, then `killSwitch: true`. | AGENT, GO per sub-step | Everything in #2742's own order list; Vault role for the one-key store; `platform/mctl-glovo/control` and `control-caller` fields present. | The kill switch endpoint is mounted (service side) and mctl-api can call it. Every PUT, even "keep killed", is a production action with its own GO. | mctl-api side first: `killSwitch: false`, then `enabled: false`, then `control: false`. Safe: without the token file the client answers "unknown". Closed: the endpoint answers 404. |
| 7 | `linkLogin: true`. | AGENT, GO | Step 4 observed; mctl-api A2 and mctl-glovo B2 released and deployed (F16); `linkMaxAuthAge` decided (default 5m). | `/link/preview` and `/link/upload` accept the link-audience fresh token. | `linkLogin: false`. Closed: both routes answer 503 again (documented behavior of the unset variable, F9). |
| 8 | Public route: `ingress: true` plus the host owner entry plus the edge change (section 5). | AGENT for the gitops PRs, OWNER for the host choice and the edge apply, GO | Steps 4 to 7 observed; host decided; Traefik pod CIDRs known (the same set as mctl-api `TRUSTED_PROXY_CIDRS`); the glovo-home fallback condition of section 5 recorded. | The route to the cluster service exists; traffic moves only when the edge points at it. | See section 5. Closed: external `/link` and `/mcp` identify the old backend again. |
| 9 | Owner links the account and records the consent (UI). | OWNER | Step 8 observed. `glovo-link` shows only a masked identity. | One stored session, one consent slot. | There is no operator Unlink or erase route today ([V] by the unmerged runbook, 6.2, [U]); the rollback is kill, `c2: false` and withdrawing the consent in mctl-api. |
| 10 | Un-kill for a bounded window, read-only calls, re-kill, evidence bundle. | OWNER decides, mctl-api admin acts | Separate GO for the window; observer named; kill state before is recorded. | Read-only tool calls by the one principal. | Flip to killed; then `c2: false` if needed. A latch after a decrypt-cap trip clears only by a pod restart (its own GO). |

Not in this plan, by design: raising the allowlist or capacity, basket writes,
stages above owner-only. A step that wants any of them is a different plan.

## 5. Ingress and edge: open, close, fallback

Opening, in this order. Each item is its own PR or action.

1. Owner decision on the host: reuse `glovo.mctl.ai` or a separate host for the
   hosted service. This plan assumes the first only because every audience in
   the code is `https://glovo.mctl.ai/mcp` and the link audience is derived
   from the same host; a different host changes both audiences and the CORS
   and metadata surface, so it is a separate design [U].
2. gitops PR: set `reservedPlatformHosts` for the host to include the service
   namespace. Without it admission refuses the Ingress (F5); the new render
   guard refuses the flip PR until this is done.
3. gitops PR: `trustedProxies` set to the Traefik pod CIDRs and `ingress: true`.
   Result: an Ingress exists, Traefik can reach the pod on 8080 (the server
   policy adds a Traefik-only source), the kill switch path and health paths
   are never in the Ingress. No traffic moves: the edge still points at the
   mini (F6).
4. Edge PR in `infrastructure/cloudflare` (applied only by the manual,
   owner-approved Cloudflare workflow): a `glovo.mctl.ai/link*` route with no
   script so `/link` reaches an origin (F6 shows it would otherwise be served
   by the landing Worker), and the tunnel public-hostname change that points
   the host at the cluster. The tunnel definition is not in this repository
   (F7), so this step cannot be written from here [U]. The route validator
   `scripts/validate-cloudflare-glovo-routes.py` pins the Worker routes and
   must get the `/link` cases in the same PR.
5. Evidence after the edge apply: an unauthenticated request to `/link/preview`
   answers 401 or 503 (never 200); `/mcp` without a token answers 401; the
   answering backend is identified by a response marker, not inferred from
   status codes alone.

Closing, in this order:

1. Edge first: point the host back at the mini origin (revert the tunnel
   mapping and the `/link*` route PR). This is the step that moves traffic.
2. gitops: `ingress: false` (the Ingress and the Traefik source disappear; the
   `reservedPlatformHosts` entry may stay).
3. Proof it is closed: external `/link` and `/mcp` identify the mini backend
   (or the landing Worker for `/link`), and the cluster Ingress object is
   absent. A 404 or 401 alone is not proof: two backends answer the same host.

The old mini route stays as the fallback:

- Do not stop or reconfigure `glovo-home` before the cluster route has been
  observed serving, and keep its launchd service and tunnel entry intact
  through the owner-only stage. The rollback of step 8 is the edge revert, not
  a rebuild of the mini.
- `glovo-home` offers three basket write tools without an approval step on the
  same host and audience (mctl-glovo#49 comment, 2026-11-17 [V]). While both
  backends answer one host, the mini must either not answer `/mcp` at the same
  time or run with `GLOVO_HOME_BLOCKED_TOOLS` blocking the three write tools,
  and `GLOVO_HOME_ALLOWED_PRINCIPALS` must hold only the owner. The live values
  on the mini are [U]; the mini is the owner's device, so this is the owner's
  action.
- A request for the cluster route while the edge still points at the mini is
  served by the mini: the Ingress existing proves nothing.

## 6. Capacity

- The cohort size is one value, `mctlGlovo.capacity` (default 10, unchanged by
  this plan). The service and mctl-api read the same number, so the consent
  slots and the service caps cannot drift. A value outside 1..20, or not a
  whole number, fails the render.
- Who may change it: only the owner, by an explicit recorded decision naming
  the new number and the stage. The change is its own PR that touches nothing
  else; the review confirms the diff is exactly one line of `capacity` plus,
  for a mctl-api that already runs consent, a pod restart (the variable is read
  at start, bump `ROLLOUT_MARKER`). No step of section 4 may carry a capacity
  change as a rider.
- Owner-only stage: the code allows 1. A lower value than 10 is the lead's
  proposal and is not decided; the default stays 10 until the owner says
  otherwise [U].
- `GLOVO_C2_CAP_*` overrides in the service exist; this plan sets none.
- No step raises capacity or the allowlist by itself. The allowlist is a
  principal list in Vault (`platform/mctl-glovo/c2-access`, field
  `allowed_principals`); it is never written into this repository.

## 7. Owner's own steps (Vault and UI)

Names only; values are never shown to an agent and never put in a PR.

| Vault path (KV, without the `secret/` prefix in ExternalSecrets) | Fields | Read by |
|---|---|---|
| `platform/mctl-glovo/database-runtime`, `database-migrator` | host, port, database, username, password | service |
| `platform/mctl-glovo/audit-key` | key | service |
| `platform/mctl-glovo/tailscale` | auth_key, proxy_target | service egress sidecars |
| `platform/mctl-glovo/c2-access` | allowed_principals (exactly the owner) | service (`allowlist`) |
| `platform/mctl-glovo/consent-reader` | key, user_id, key_id, scope | service refresher (`consent`) |
| `platform/mctl-glovo/control` | subjects, audience | service (`control`) |
| `platform/mctl-glovo/control-caller` | user_id, key_id, key | mctl-api (#2742, own store and role) |
| `platform/mctl-api/glovo-consent` | service_provider, service_subject | mctl-api (`apiConsent`) |

Also the owner's: Vault policies and roles (`eso-mctl-glovo`, the DB-creds
reader, `eso-mctl-api-control`, the transit mount and key and the service's
Kubernetes role), the choice of host (section 5), the mini's allowlist and
tool blocking, linking the account and recording the consent in the UI
(step 9), every GO, and the `STOP` word. Login to Vault is the owner's command
(`vault login -method=oidc`); an agent never reads Secret data.

## 8. Gaps found while writing this plan

1. F12: resolved (see the F12 row): the consent reader is a `service_subjects`
   entry on the existing provider entry. The `apiConsent` step still needs the
   Vault fields and the config guard on the exact pinned image.
2. F6: no `/link*` edge route; the tunnel definition is outside this
   repository (F7).
3. F16: the code prerequisites for linking (A2, B2, version match, releases)
   are merged and released; what blocks `linkLogin` and step 9 now is the
   live proof of unlink, the unnamed `glovo-link` client id and the owner-only
   items (Vault, edge route).
4. The image pinned in the template, `0.1.0`, predates the read-only default;
   0.2.0 is released but not pinned (a bump needs its own GO).
5. Observability: the service emits only logs (no metrics, no sender); a
   named observer is needed for the window [V per the unmerged runbook, [U]].
6. TLS: the wiring renders an Ingress with no `tls` block and no cert-manager
   annotation (the tunnel terminates TLS at the edge, if it does) [U]. If the
   origin must serve a certificate, that is an addition to the ingress step.

## 9. What this document does not do

It does not open or close any switch, merge, release or deploy anything,
write to Vault, change the edge, or grant the owner's GO. The conditional GO
wording belongs in the owner request, not here.
