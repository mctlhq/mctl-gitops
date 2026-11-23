# Glovo C2 cutover plan (owner-only stage)

Status: PLAN FOR THE FIRST LIVE STAGE, updated after the 2026-11-22 cutover.
Closes the problem statement of mctlhq/mctl-gitops#2777. It authorizes
nothing: no merge, no release, no deploy, no flag flip, no admission and no
edge change happens because of this file.

State update 2026-11-22: the owner-only stage was cut over. The account was
linked at 17:25Z, a read through the connector inside the cluster was
verified at 17:29Z (`glovo_get_basket` ok) and the kill-switch window was
closed again at 17:31Z. Sections 2 to 8 keep the plan as written on
2026-11-18/19; every statement the cutover overtook is marked SUPERSEDED in
place and points at the sections that now hold the working procedure:
section 9 (operator sequence for linking), section 10 (troubleshooting),
section 11 (rollback) and section 12 (releases and helper versions). Every production effect below needs its own separately recorded owner
GO (c2-operations runbook, section 2.2, mctlhq/mctl-glovo; unmerged draft at
the time of writing, [U]).

Parent epic: mctlhq/.github#365. Gate matrix: mctlhq/mctl-glovo#40. The
rollback rehearsal is performed by mctlhq/mctl-glovo#43, not here.

Facts are tagged. `[V]` = verified by reading the cited path or API object on
the cited date (2026-11-18 unless a row says otherwise), at the cited SHA;
this is "present in the file", never "observed in the cluster". `[U]` =
unknown or not verified. When the plan was written no live state (cluster,
Vault, ArgoCD, Cloudflare, tailnet, the mini) was read; the 2026-11-22 live
outcomes are recorded in the state update above and in sections 9 to 11, as
reported by the owner who ran them.

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
| F1 | SUPERSEDED (2026-11-22). Written 2026-11-18: all five existing switches `deploy`, `c2`, `allowlist`, `consent`, `control` were `false`. On main now `deploy`, `c2`, `allowlist`, `consent`, `control`, `apiConsent`, `linkLogin`, `ingress` and `apiC2Control.killSwitch` are `true`, `capacity` is 1 and `linkAttemptsPerHour` is 15. | [V] | `platform-gitops/bootstrap/values.yaml`, block `mctlGlovo` and `apiC2Control`, main 4915c6f5e (re-read 2026-11-22) |
| F2 | Render rules: `deploy` refuses the placeholder image tag; `c2` needs `deploy`; `allowlist`, `consent`, `control` need `c2`; `c2` needs `allowlist` or `consent`. | [V] | `platform-gitops/bootstrap/templates/mctl-platform/mctl-glovo.yaml` |
| F3 | SUPERSEDED: the pin is now `0.4.0` (section 12). Written 2026-11-18: the pinned service image tag was `0.1.0`, the only release at the time; it predates the read-only-by-default change (mctl-glovo#54, merged aa9b3cc3, unreleased). Deploying `0.1.0` does not give the read-only guarantee. | [V] | template image block; `gh api repos/mctlhq/mctl-glovo/releases`; mctl-glovo#59 (0.2.0) open |
| F4 | The service has a ClusterIP Service and, before the wiring PR below, no Ingress object. | [V] | same template |
| F5 | `glovo.mctl.ai` is in `reservedPlatformHosts` with the service namespace `mctl-glovo` as its only owner (was an empty list until the owner-entry PR); admission (`mctl-reserved-platform-hosts-ingress`) refuses an Ingress for a reserved host from any namespace that is not an owner. | [V] | `bootstrap/values.yaml` (`reservedPlatformHosts`), `bootstrap/templates/system/admission-policies.yaml` |
| F6 | SUPERSEDED in part (2026-11-22, see section 5): the tunnel record for the host was removed and the host now reaches Traefik through the proxied wildcard; the `/link*` route is applied. Written 2026-11-18: the public host was served by a Cloudflare tunnel to the mini (`glovo-home`). Worker routes: `glovo.mctl.ai/` and `glovo.mctl.ai/*` go to the `glovo-landing` Worker; `glovo.mctl.ai/mcp*` and `glovo.mctl.ai/.well-known/*` have no script (tunnel origin). A `glovo.mctl.ai/link*` route without a script is declared in git (stays on the origin); until the owner dispatches the Cloudflare Apply it is not live, and then `/link` is still answered by the landing Worker. Which origin the tunnel maps for `/link*` is defined outside this repository (F7). | [V] | `infrastructure/cloudflare/zones/mctl-ai/workers.tf`, `scripts/validate-cloudflare-glovo-routes.py` |
| F7 | RESOLVED 2026-11-22. The tunnel CNAME for `glovo.mctl.ai` was managed by the private infra repository (OpenTofu, `dns_services`, tunnel to the mini), not by this repository, which is why grep over `infrastructure/` found nothing. That record was removed (section 5). | [V] reported by the owner | private infra repo; not readable from here |
| F8 | The service reads capacity from `GLOVO_C2_CAPACITY` (1..20, more is a boot error); mctl-api reads the same variable as the consent slot cap (unset, 0 or malformed means closed: no new consent). The template hard-coded `10`; it is now a value (`capacity`, default 1, section 6). | [V] | mctl-glovo `cmd/mctl-glovo/c2.go`, mctl-api `cmd/api/glovo_consent.go`, `docs/glovo-link-consent.md` (main, aa9b3cc3 and the 2026-11-18 mctl-api main) |
| F9 | The service's optional link-login variables `GLOVO_LINK_RESOURCE` and `GLOVO_LINK_MAX_AUTH_AGE` were added by mctl-glovo#56 (merged 2026-11-18, in release 0.2.0). Unset means the link preview and upload routes answer 503. A set-but-wrong value stops the boot. | [V] | mctl-glovo PR 56 `cmd/mctl-glovo/c2.go` |
| F10 | (2026-11-18) `/link` page, `/link/code`, `/link/preview`, `/link/upload`, `/link/unlink` (since mctl-glovo#64) and `/mcp` plus the RFC 9728 metadata are what the service mounts when C2 is on; the kill switch endpoint is `PUT /internal/v1/control/kill-switch`, mounted only with the control configuration; the same configuration also mounts `POST /internal/v1/control/unlink` and `/erase` (mctl-glovo#64, no mctl-api caller yet). Health paths `/livez`, `/readyz`. | [V] | `internal/linkflow/linkflow.go`, `cmd/mctl-glovo/control.go`, `cmd/mctl-glovo/mcp.go` (main) |
| F11 | mctl-api reads, for the consent side: `GLOVO_CONSENT_ENABLED`, `GLOVO_CONSENT_SERVICE_PROVIDER`, `GLOVO_CONSENT_SERVICE_SUBJECT`, `GLOVO_CONSENT_DB_URL` (else `AUDIT_DB_URL`), `GLOVO_C2_CAPACITY`. The reader provider must be a federated provider entry of KIND SERVICE in `MCTL_OIDC_PROVIDERS` and the subject must be in that entry's `service_subjects`. | [V] | mctl-api `cmd/api/glovo_consent.go`, `cmd/api/check_config.go` |
| F12 | RESOLVED 2026-11-19 (was a blocker). The `zitadel` entry of `MCTL_OIDC_PROVIDERS` carries `customers_org_id` AND, since mctl-api 4.169.0 (9aa297e, 4.165.0 to 4.168.0 refuse to boot on the combination), may list `service_subjects` for exact subjects: the consent reader machine user is a `kind: service` identity pinned to the mctl_api project id, never a customer, no groups. `service_subjects` for it is on main (gitops#2817, 1bea2d2a1). Not yet shown: the pinned image's own `--check-config` on the rendered config for the current pin (it runs in CI on amd64 via `scripts/check-mctl-api-oidc-config.py`; it cannot run on an arm64 laptop). | [V] source on main, [U] live | `platform-gitops/helm-charts/zitadel-iac/iac/mctl-api.tf`, gitops#2817, mctl-api 9aa297e |
| F13 | The consent read route is confined to the one configured service identity; the service reads it with a ZITADEL machine-user token written by its `token-refresher` sidecar (the `consent` switch). | [V] | mctl-api `docs/glovo-link-consent.md`; `mctl-glovo.yaml` (consent block) |
| F14 | mctl-gitops#2742 (control-caller token wiring for the kill switch) is a draft, dark. It needs the mctl-api chart pin to carry the `extraContainers` / `extraVolumes` / `extraVolumeMounts` slots (`chartSlots`), a released refresher tag and command, and a Vault role that reads one key. | [V] | PR 2742 diff |
| F15 | The mctl-api config guard (`--check-config` in the image) cannot be run offline; consent settings are cross-checked by it at release time. Since gitops#2830 the same script also boots the image on a throwaway Postgres (`--readyz`) and requires `/readyz` `stores: ok`; it still does not cover Vault, gitops sync or Temporal. | [U] | `scripts/check-mctl-api-oidc-config.py` needs the image |
| F16 | SUPERSEDED by the cutover (2026-11-22): every prerequisite below was met, the service runs 0.4.0 and the link helper has a fixed client id (section 12). Prerequisites outside gitops that gated the flip order, state 2026-11-19: mctl-api A2 (fresh-login, link audience) MERGED (#1129) and released in 4.170.0; mctl-api#1116 (masked identity) and the consent text `c2-link-v2` (#1126) released in 4.170.0; the consent page for every client kind (#1133) released in 4.170.1, LIVE 2026-11-19; mctl-glovo B2 `glovo-link` (#63) and `-unlink` (#64) merged, 0.2.0 released (tag d95db5096, contains `glovo-link`), 0.3.0 release PR open. All `mctlGlovo` switches stay false, the template pin is still `0.1.0`. Still open outside gitops: no live run of link or unlink, the fixed client id for `glovo-link` is not named, `GLOVO_LINK_RESOURCE` is not set anywhere. | [V] on GitHub as of 2026-11-19 | mctl-api #1116, #1126, #1129, #1133, releases 4.170.0 and 4.170.1; mctl-glovo #56, #63, #64, release 0.2.0 |
| F17 | Live versions of mctl-api and the service, ArgoCD sync, Vault contents and roles, CNPG state, tailnet ACL, the mini's allowlist. | [U] | not read by this document; the cutover outcome is reported in the state update |

## 3. Wiring that this plan assumes (the dark wiring PR)

The companion PR "feat(c2): dark wiring for the owner-only cutover (#2777)"
adds, all default false or unchanged, no existing switch touched:

| Value in `mctlGlovo` | Default | Effect when on |
|---|---|---|
| `linkLogin` | false | Sets `GLOVO_LINK_RESOURCE` (`https://<host>/link`) and `GLOVO_LINK_MAX_AUTH_AGE` (`linkMaxAuthAge`, default 5m, at most 15m). Needs `c2`. |
| `ingress` | false | One Ingress for `host` with the paths `/mcp`, `/link`, `/.well-known/oauth-protected-resource`; a Traefik-only source in the server policy; `GLOVO_LINK_TRUSTED_PROXIES`. Needs `c2`, `trustedProxies`, and the host's `reservedPlatformHosts` owner list to include the namespace; each missing one fails the render. |
| `apiConsent` | false | mctl-api gets `GLOVO_CONSENT_ENABLED=true`, `GLOVO_C2_CAPACITY` and the optional Secret `mctl-api-glovo-consent` (reader provider and subject, from Vault). |
| `capacity` | 1 | The one cohort size for the service and mctl-api. Whole number 1..20, else the render fails. |
| `linkAttemptsPerHour` | 0 (service default) | Service-wide cap on link attempts per hour (`GLOVO_C2_CAP_LINK_ATTEMPTS_GLOBAL_HOUR`); committed value 15. See section 6. |
| `host`, `trustedProxies`, `linkMaxAuthAge` | `glovo.mctl.ai`, empty, `5m` | Inputs of the above. |

The wiring PR and the follow-ups below have merged; the values above exist on main. The effective values on 2026-11-22 are in F1; `capacity` is 1 for the owner-only stage and `linkAttemptsPerHour` (a whole number 1..300, 0 = the service default) is the value added by mctlhq/mctl-gitops#2903 (section 6).

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
| 3 | `apiConsent: true` (mctl-api side), with a `ROLLOUT_MARKER` bump in the same PR. | AGENT, GO | F12 solved (a service-kind provider entry and the subject exist); Vault `platform/mctl-api/glovo-consent` fields present; mctl-api image at the release with the consent routes (config accepted by `--check-config`, and stores booting on a throwaway Postgres with `/readyz` stores ok, both in the release gate, F15; `--check-config` alone opens no store, which is how the first flip stalled, gitops#2827 / mctl-api#1136), and the mctl-api release containing mctl-api#1136 (per-store init contexts); capacity value agreed (section 6). | mctl-api mounts the consent routes (record, read, withdraw) with the cap. No service reads them yet. | `apiConsent: false` (+ marker). Closed: `GET /api/v1/glovo/link-consent` answers 404 (routes unmounted); recorded consents stay in the table (history). |
| 4 | `c2: true` and `allowlist: true`, `capacity` set in this PR or left at its default (1, which is also the committed value). | AGENT, GO | Steps 2 and 3 observed; allowlist Vault entry holds exactly one principal (field count only); audit key, Vault transit key and role, tailnet key and proxy target present (names only); proxy reachable by the egress tag ACL [U]; image tag has read-only by default. | `GLOVO_C2_ENABLED=true`, Vault login, database connection, egress sidecars, `/link` and `/mcp` mounted INSIDE the cluster only (no route yet). Store ships KILLED. | `c2: false` and `allowlist: false` in the same PR (`allowlist` requires `c2`, so setting only `c2: false` fails the render). Closed: the routes answer 404 as seen from inside the cluster by a one-shot probe from an allowed namespace and the backend is identified by a distinct marker; `/readyz` is vacuously 200. Evidence after: no `exit` and no `initial jwks fetch failed` in a clean start. |
| 5 | `consent: true` (the service's reader and its `token-refresher` sidecar). | AGENT, GO | Step 3 observed; Vault `platform/mctl-glovo/consent-reader` (`key`, `user_id`, `key_id`, `scope`) present; zitadel-iac machine user applied (#2737). | The service reads consent from mctl-api; an active `glovo:c2` consent admits a principal (narrowed by the allowlist). | `consent: false`. Closed: the token file disappears and consent reads refuse (fail closed). Evidence after: refresher log `token refreshed`. |
| 6 | `control: true` and the #2742 chain: prerequisites, then `chartSlots: true` with the chart pin move and the refresher tag and command, then `apiC2Control.enabled`, verify the Secret and the token file, then `killSwitch: true`. | AGENT, GO per sub-step | Everything in #2742's own order list; Vault role for the one-key store; `platform/mctl-glovo/control` and `control-caller` fields present. | The kill switch endpoint is mounted (service side) and mctl-api can call it. Every PUT, even "keep killed", is a production action with its own GO. | mctl-api side first: `killSwitch: false`, then `enabled: false`, then `control: false`. Safe: without the token file the client answers "unknown". Closed: the endpoint answers 404. |
| 7 | `linkLogin: true`. | AGENT, GO | Step 4 observed; mctl-api A2 and mctl-glovo B2 released and deployed (F16); `linkMaxAuthAge` decided (default 5m). | `/link/code`, `/link/preview` and `/link/upload` accept the link-audience fresh token (from 0.4.0 the helper requests its own code at `/link/code`, section 12). All three still refuse with 503 `linking_disabled` while the store is killed (section 9). | `linkLogin: false`. Closed: preview and upload answer 503 again (documented behavior of the unset variable, F9). |
| 8 | Public route: `ingress: true` plus the host owner entry plus the edge change (section 5). | AGENT for the gitops PRs, OWNER for the host choice and the edge apply, GO | Steps 4 to 7 observed; host decided; Traefik pod CIDRs known (the same set as mctl-api `TRUSTED_PROXY_CIDRS`); the glovo-home fallback condition of section 5 recorded. | The route to the cluster service exists; traffic moves only when the edge points at it. | See section 5. Closed: external `/link` and `/mcp` identify the old backend again; moving traffic back means re-adding the `glovo` record in the private infra repository (section 5, Closing, item 1). |
| 9 | CORRECTED 2026-11-22: linking happens INSIDE the kill-switch window, so the old order (link at step 9, un-kill at step 10) was wrong. While the store is killed the code request, the preview and the upload all refuse with 503 `linking_disabled`. Step 9 is now: record the consent, open the window, link, read check, close the window; the exact sequence with its separate GOs is section 9. | OWNER (a direct human platform admin opens and closes the window; agents get 403) | Step 8 observed. Section 9 preconditions. `glovo-link` shows only a masked identity. | One stored session, one consent slot. | Close the window (kill), `c2: false` and withdraw the consent in mctl-api. Unlink works under kill and needs no Vault (section 11). |
| 10 | Merged into step 9 (the window, the read check and the re-kill are one bounded operation). Evidence bundle: the times of the three steps and the `kill_switch_flip` and `link` audit lines. | OWNER decides, mctl-api admin acts | Separate GO per POST; observer named; kill state before is recorded. | Read-only tool calls by the one principal. | Flip to killed; then `c2: false` if needed. A latch after a decrypt-cap trip (100 an hour service-wide) clears only by a pod restart (its own GO). |

Not in this plan, by design: raising the allowlist or capacity, basket writes,
stages above owner-only. A step that wants any of them is a different plan.

## 5. Ingress and edge: open, close, fallback

State after the 2026-11-22 cutover (reported by the owner, [V] by the code and
the workers.tf comment, not re-read from Cloudflare here):

- `glovo.mctl.ai` used to be a proxied Tunnel CNAME managed by the private
  infra repository (OpenTofu, tunnel to the mini). That record was removed
  (infra PR merged, `tofu apply` done, one destroy). The host now falls under
  the proxied wildcard `*.mctl.ai`, which goes to Traefik, and Traefik
  requires the Cloudflare origin-pull client certificate: a probe that does
  not come through Cloudflare cannot reach the origin. The switch took about
  3 minutes (404 from the old origin until it propagated), so wait before
  judging a probe.
- Worker routes (`infrastructure/cloudflare/zones/mctl-ai/workers.tf`):
  `glovo.mctl.ai/` and `glovo.mctl.ai/*` go to the landing Worker;
  `glovo.mctl.ai/mcp*`, `glovo.mctl.ai/.well-known/*` and
  `glovo.mctl.ai/link*` have no script and go to the origin, which is now the
  cluster Ingress.
- The Worker also serves the link helper's Client ID Metadata Document at
  `/glovo-link/client.json` (section 12).

The list below is the plan as written; where it names the tunnel, read it
with the state above.

Opening, in this order. Each item is its own PR or action.

1. Owner decision on the host: reuse `glovo.mctl.ai` or a separate host for the
   hosted service. This plan assumes the first only because every audience in
   the code is `https://glovo.mctl.ai/mcp` and the link audience is derived
   from the same host; a different host changes both audiences and the CORS
   and metadata surface, so it is a separate design [U].
2. DONE (owner-entry PR): `reservedPlatformHosts` for the host lists the service
   namespace, and no other. Without it admission refuses the Ingress (F5); the new render
   guard refuses the flip PR until this is done.
3. gitops PR (the ingress flip): `trustedProxies` set to the cluster pod CIDR
   (`10.42.0.0/16`; per-pod /32 entries go stale on every Traefik restart) and
   `ingress: true`.
   Result: an Ingress exists, Traefik can reach the pod on 8080 (the server
   policy adds a Traefik-only source), the kill switch path and health paths
   are never in the Ingress. At the time of this plan no traffic moved
   because the edge still pointed at the mini (F6); SUPERSEDED 2026-11-22:
   the record was removed (item 4) and the host now reaches Traefik.
4. Edge, two changes in two repositories (DONE 2026-11-22). In this
   repository, a `glovo.mctl.ai/link*` route with no script so `/link` reaches
   an origin (it would otherwise be served by the landing Worker), applied
   only by the manual, owner-approved Cloudflare workflow; the route validator
   `scripts/validate-cloudflare-glovo-routes.py` pins the Worker routes. In
   the private infra repository (outside this one, F7), the removal of the
   `glovo` tunnel record from `dns_services`, followed by `tofu apply`; the
   host then falls to the proxied wildcard and Traefik.
5. Evidence after the edge apply: an unauthenticated request to `/link/preview`
   answers 401 or 503 (never 200); `/mcp` without a token answers 401; the
   answering backend is identified by a response marker, not inferred from
   status codes alone. Probe through the public host; the origin itself
   refuses a client without the Cloudflare origin-pull certificate.

Closing, in this order:

1. Edge first: re-add the `glovo` record to the private infra repository's
   `dns_services` and apply it (the proxied Tunnel CNAME to the mini wins over
   the wildcard again); revert the `/link*` route PR here if the route itself
   must go. This is the step that moves traffic. Expect the same few minutes
   of propagation as on the way in.
2. gitops: `ingress: false` (the Ingress and the Traefik source disappear; the
   `reservedPlatformHosts` entry may stay).
3. Proof it is closed: external `/link` and `/mcp` identify the mini backend
   (or the landing Worker for `/link`), and the cluster Ingress object is
   absent. A 404 or 401 alone is not proof: two backends answer the same host.

The old mini route stays as the fallback:

- Do not stop or reconfigure `glovo-home` before the cluster route has been
  observed serving, and keep its launchd service intact through the owner-only
  stage. The rollback of step 8 is the edge revert (the record re-added in the
  infra repository), not a rebuild of the mini. The mini's session is NOT a
  hot standby: once the cluster holds the refresh-token chain the mini must not
  refresh the same session (section 9, the mini keepalive rule), so after the link it is a
  fallback that needs its own fresh Glovo login.
- `glovo-home` offers three basket write tools without an approval step on the
  same host and audience (mctl-glovo#49 comment, 2026-11-17 [V]). After a
  rollback of the edge, while the mini answers the host, it must either not answer `/mcp` at the same
  time or run with `GLOVO_HOME_BLOCKED_TOOLS` blocking the three write tools,
  and `GLOVO_HOME_ALLOWED_PRINCIPALS` must hold only the owner. The live values
  on the mini are [U]; the mini is the owner's device, so this is the owner's
  action.
- Before the record was removed, a request for the cluster route while the
  edge still pointed at the mini was served by the mini: the Ingress existing
  proves nothing. After a rollback the same holds again, so identify the
  backend by a marker, never by the Ingress object.

## 6. Capacity

- The cohort size is one value, `mctlGlovo.capacity` (committed value 1 for
  the owner-only stage since 2026-11-18; the template default is 1, the
  service's own default without the variable is 10). The service and mctl-api read the same number, so the consent
  slots and the service caps cannot drift. A value outside 1..20, or not a
  whole number, fails the render.
- Who may change it: only the owner, by an explicit recorded decision naming
  the new number and the stage. The change is its own PR that touches nothing
  else; the review confirms the diff is exactly one line of `capacity` plus,
  for a mctl-api that already runs consent, a pod restart (the variable is read
  at start, bump `ROLLOUT_MARKER`). No step of section 4 may carry a capacity
  change as a rider.
- Owner-only stage: 1, an owner decision. Raising it needs the explicit
  recorded decision above.
- `GLOVO_C2_CAP_*` overrides in the service exist. One is set, through its
  own value: `linkAttemptsPerHour` (mctlhq/mctl-gitops#2903) sets
  `GLOVO_C2_CAP_LINK_ATTEMPTS_GLOBAL_HOUR`, committed at 15, 0 meaning the
  service default, a whole number 1..300 (the service refuses anything else at
  boot). Why: the code request, the preview and the upload each count one
  link attempt, so one link takes 3, and the service-wide default is 5 x
  capacity an hour (5 at capacity 1). That was exhausted during the first
  link. Two caps apply to every attempt: the service-wide cap (15 an hour as
  committed) and the per-address cap (10 an hour, untouched, counted on the
  same 3 calls). Both must have room, so the tighter one rules: one address
  gets 3 complete links an hour (9 attempts), not 5; the service-wide 15 only
  matters for several addresses. The counters live in pod memory; a pod
  restart (or a rollout from changing the value) resets them as a side effect.
  That is NOT a remedy for a 429: a restart is a production action with its
  own owner GO, and it also drops the in-memory client and latches the kill
  state (token-store design, retention table). A cap change is its own PR.
- Decrypt caps can self-kill a pilot: more than 30 decrypts an hour for one
  principal suspends that principal, and more than 100 an hour service-wide
  trips the kill switch and latches it until a pod restart (its own GO). No
  Glovo-specific alert rule exists in gitops yet; observation is manual, from
  the service log.
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
tool blocking, recording the consent and linking the account (step 9,
section 9), every kill-switch POST, every GO, and the `STOP` word. Login to Vault is the owner's command
(`vault login -method=oidc`); an agent never reads Secret data.

## 8. Gaps found while writing this plan

1. F12: resolved (see the F12 row): the consent reader is a `service_subjects`
   entry on the existing provider entry. The `apiConsent` step still needs the
   Vault fields and the config guard on the exact pinned image.
2. F6/F7: RESOLVED 2026-11-22 (section 5): the `/link*` route is applied and
   the tunnel definition was in the private infra repository.
3. F16: RESOLVED 2026-11-22: the link ran live; the fixed `glovo-link` client
   id is the CIMD document URL (section 12). The live proof of unlink is still
   open [U].
4. RESOLVED: the pin is `0.4.0` (the read-only default shipped in 0.2.0).
5. Observability: the service emits only logs (no metrics, no sender); a
   named observer is needed for the window [V per the unmerged runbook, [U]].
6. TLS: the wiring renders an Ingress with no `tls` block and no cert-manager
   annotation. Since 2026-11-22 the host reaches Traefik through the proxied
   wildcard with the origin-pull client certificate (section 5), not through
   the tunnel; which certificate Traefik serves for this host is [U], and
   nothing in this repository states it. If the origin must serve a specific
   certificate, that is an addition to the ingress step.
7. Session lifecycle: the hosted service has NO keepalive and no refresh
   caller (the token-store design describes one in section 4.5, but it is not
   built; `cmd/mctl-glovo` has none). The linked session is refreshed only when
   a tool call uses it, so a dormant linked session can silently die. The kill
   switch does not protect it. Recovery is a relink, which needs the service
   un-killed (section 9) and a session whose access token is fresh.

## 9. Operator sequence for linking (verified live 2026-11-22)

Linking needs the kill-switch window: while the store is KILLED the code
request, the preview and the upload all refuse with HTTP 503 `linking_disabled`
(the store ships killed, step 4). The earlier plan (link first, un-kill later)
cannot work. Each numbered action is its own production action with its own
recorded owner GO. A kill-switch POST is made by a direct human platform admin
(the owner); a call from an agent identity answers 403.

Order matters because of the freshness rule below: the slow, interactive
parts come first, and the session refresh is the LAST preparation, right
before the helper runs.

1. Preconditions, read-only: the service runs the pinned release (section 12),
   the helper on the owner's machine is at least 0.4.0, and the kill state
   before is recorded (the control route has no read, so it is UNKNOWN unless a
   dated observation exists; section 4 step 6 and the c2-operations runbook).
   Attempts left: count the attempts used since the window opened (3 per
   helper run) against both caps of section 6 (per-address 10 an hour,
   service-wide 15 an hour). Never start a run that cannot finish all 3.
2. Record the consent: `PUT /api/v1/glovo/link-consent`, version `c2-link-v2`.
3. Install the helper (0.4.0 or later) and have the browser sessions ready
   (the Glovo login and the platform login).
4. Open the window: `mctl auth login` first (the CLI token lives about one
   hour, owner-reported), then `POST /api/v1/admin/glovo-c2/kill-switch` with
   `{"killed":false}`.
5. Last preparatory step: the fresh Glovo session (see the freshness rule
   below), taken immediately before the helper, so the upload happens within
   the ~20 minute deadline.
6. Link: run `glovo-link`, type the answer to the y/N question in Latin
   letters (section 10, last row), upload the session. One link is three
   attempts (section 6).
7. Read check through the connector (a read-only tool such as
   `glovo_get_basket`). 2026-11-22: linked 17:25Z, read verified 17:29Z.
8. Close the window: the same POST with `{"killed":true}`. 2026-11-22: closed
   17:31Z. Confirm the response is `200 {"killed": true}` and nothing else is
   assumed about other replicas.

Retry rule. Before re-running the helper, count the attempts used since the
window opened (3 per run; a failed upload still consumes one) against both
caps. Never retry in a loop. A pod restart resets the in-memory counters only
as a side effect; it is not a remedy (section 6).

Session freshness (this cost two attempts on 2026-11-22, when the session was
prepared before the slow steps). The upload validator makes one basket read
with the uploaded session and never refreshes it (a refresh would rotate the
refresh token). The Glovo access token lives about 20 minutes (`expiresIn`
1198 s, owner-observed), so a session file older than that is refused as
`glovo_validation_failed` inside the service, which the client sees as
`session_refused` (HTTP 422). The session must have been refreshed within the
last ~20 minutes when it is uploaded.

Mini keepalive procedure. PRECONDITION: use it ONLY for the very first link,
while the cluster holds no session and no earlier upload succeeded. Never use
it for a relink or after a successful upload (even one whose read check
failed): the keepalive calls a basket read that refreshes and rotates the
refresh token, which would break the cluster's copy. A relink needs a fresh
Glovo login captured by the normal capture tooling, not the mini. For the
first link only:

1. set `GLOVO_HOME_KEEPALIVE=1m` on the mini and wait for the first tick (it
   refreshes and rewrites the session file);
2. set it back to `0` at once;
3. copy the file and run the helper within minutes.

After the cluster holds the chain, the mini must NOT refresh the same session
again. Keep `GLOVO_HOME_KEEPALIVE=0` there and treat the mini as a fallback
that needs its own fresh login.

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| HTTP 503 `linking_disabled` (helper: "refused: linking is switched off") on code, preview or upload | The store is killed. Linking is refused under kill, by design (section 9). | Open the window (section 9, step 4, owner GO), link, close the window. Do not flip `linkLogin`; that variable answers a different 503 (F9). |
| HTTP 429 `rate_limited` (helper: "too many link attempts") | A link attempt cap was hit: service-wide (`GLOVO_C2_CAP_LINK_ATTEMPTS_GLOBAL_HOUR`, 5 x capacity by default, 15 as committed) or per address (10 an hour, so 3 complete links from one address). Code, preview and upload each count one against both caps, so one link takes 3. | Wait for the oldest attempt to leave the one-hour window, or raise `linkAttemptsPerHour` in its own PR (the per-address cap of 10 is not raised by it). Count attempts before any rerun (section 9, retry rule). Do not retry in a loop; the helper does not retry a refused code request. A pod restart resets the counters only as a side effect and is not a remedy (section 6). |
| HTTP 422 `session_refused` (server side `glovo_validation_failed`) | Glovo rejected the one basket read made with the uploaded session, in practice because the access token had expired (about 20 minutes) or the session was already rotated elsewhere. | Section 9, freshness rule: the refresh is the last step before the helper, upload within the deadline. Each failed upload still consumes an attempt, so check attempts left before a rerun (section 9, retry rule). Check the mini did not refresh the same session after an earlier successful link; if a link already succeeded, do not use the mini keepalive, take a fresh login with the normal capture tooling. |
| Helper prints "refused: no link code" on release 0.4.0 or later (owner-observed) | From 0.4.0 the helper logs in with the link audience and requests its own code; `/link/code` accepts only a link-audience token. A code minted separately, or a refused code request, leaves it without a code. | Run `glovo-link` again so it logs in itself, with a server that is also on the new behavior (section 12). A refused request shows its own reason first (503, 429 or the consent text). The message is the stdin-code path message of helpers before 0.4.0, verified by running the old helper (it is no longer in the source on main). |
| An older helper (before 0.4.0) is refused by the server | Older helpers needed a code minted with an MCP-audience token; the new server refuses that path. | Upgrade the helper (section 12): `go install github.com/mctlhq/mctl-glovo/cmd/glovo-link@<tag>`. Server first, then helper. |
| The helper declines at the y/N question without asking | The answer was typed with a Cyrillic keyboard layout; the helper reads EOF and declines. | Switch to a Latin layout and type `y`. |
| `403` on the kill-switch POST | The caller is an agent or service identity. | The owner runs it as a direct human platform admin. |
| `401` on the POST | The CLI token (about one hour) expired. | `mctl auth login` again. |
| 404 from the public host for a few minutes after an edge change | Propagation: the old origin answered until the switch took effect (about 3 minutes on 2026-11-22). | Wait, then probe through the public host; identify the backend by a marker (section 5). |

## 11. Rollback notes

- Window left open or doubt about state: POST `{"killed":true}` (its own
  owner GO). `200 {"killed": true}` on an un-kill identifies a latch in that
  process, with the stored row possibly open; a non-200 or 503 `state_unknown`
  is UNKNOWN (c2-operations runbook, 8.1). A latch clears only by a pod
  restart (its own GO).
- Unlink works under kill and needs no Vault (token-store design, section 4);
  there is still no operator unlink route that mctl-api calls (F10).
- Edge: re-add the `glovo` record to the private infra repository's
  `dns_services` and apply (section 5, Closing, item 1). The service keeps
  running; only the route moves.
- KILLED does not protect a linked session: the hosted service has no
  keepalive and no refresh caller, so a dormant session can die unnoticed;
  recovery is a relink (section 8, item 7).
- Cap: set `linkAttemptsPerHour` back to 0 (service default) in its own PR.
- Image: bump the tag back through the release path of section 12; the schema
  is forward-only (section 4).
- Switches: the per-step rollbacks of section 4 still apply, one switch per
  PR.

## 12. Releases, image path and helper versions

- Client identity. The helper's `client_id` is
  `https://glovo.mctl.ai/glovo-link/client.json`, a Client ID Metadata Document
  (CIMD) served by the landing Worker (landing-worker in mctlhq/mctl-glovo).
  mctl-api accepts it because `OAUTH_CIMD_ALLOWED_HOSTS` includes
  `glovo.mctl.ai` (mctlhq/mctl-gitops#2899; the host's Worker answers 404 for
  every other path). Loopback redirects match any port. DCR still exists as a
  fallback, but CIMD is the supported path: nothing is registered by hand.
- Helper versions. From release 0.4.0 `glovo-link` logs in once with the link
  audience and requests its own one-time code; `/link/code` accepts only the
  link-audience token, there is no stdin code path, and the y/N confirmation
  stays. Versions before 0.4.0 need a code minted with an MCP-audience token
  and are refused by the new server. Roll out the server first, then the
  helper: `go install github.com/mctlhq/mctl-glovo/cmd/glovo-link@<tag>`.
- Release path. The mctl-glovo release-please workflow dispatches the image
  build only when the repository variable `GLOVO_IMAGE_DISPATCH` is `"true"`;
  when it is not, the tag is created and nothing is built. The manual
  equivalent is the mctl-gitops `release-deploy` workflow dispatched with
  `repo=mctlhq/mctl-glovo`, `git_ref=<tag>`,
  `image_name=ghcr.io/mctlhq/mctl-glovo`, `image_tag=<tag>`,
  `team_name=admins`, `component_name=mctl-glovo` and
  `values_path=platform-gitops/bootstrap/templates/mctl-platform/mctl-glovo.yaml`.
  It builds the image, bumps the `tag:` line in gitops with a bot commit
  (the template header describes this as the one line the bot rewrites) and
  ArgoCD rolls the pod. The current pin on main is `0.4.0`.

## 13. What this document does not do

It does not open or close any switch, merge, release or deploy anything,
write to Vault, change the edge, or grant the owner's GO. The conditional GO
wording belongs in the owner request, not here.
