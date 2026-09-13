# Cloudflare MCP Portal controls

`mcp-portal-controls.json` is the committed state of the account-level
switches on portal `mcp` (`mcp.mctl.ai`, the private aggregate over `tg`,
`seerrsense` and `api`). It is applied by `scripts/portal-controls-apply.sh`
and compared against the live portal by the same script's `--check` mode.

This is not OpenTofu. The portal was created through the API and the
dashboard, and declarative ownership is an import task blocked on a CI
Cloudflare write identity (`mctlhq/mctl-gitops#1092`, `mctlhq/.github#47`,
`#1111`). Until that lands the switches are applied the way the tool
allowlists are: a scripted API call from a repository-pinned file, run by an
operator, with the state recorded here. When the import lands, this file
becomes a resource and the script goes away.

## What is pinned, and why each field

- `secure_web_gateway` — whether the portal routes its traffic through
  Cloudflare Gateway. This is the Phase 2 subject (`mctlhq/.github#43`,
  `#1181`): committed `false` is the baseline the POC returns to.
- `code_mode` / `allow_code_mode` — pinned `off`/`false` because Phase 2 must
  leave Code Mode untouched, and "untouched" is only checkable if something
  records what it was. A drift here is as interesting as a drift in the
  Gateway switch: it means the portal grew an execution surface nobody
  decided on. `code_mode` is one of `off`, `opt_in`, `default_on`,
  `enforced`, and defaults to `opt_in` when omitted on create — leaving it
  unpinned is not the same as leaving it off. The two fields must agree: the
  API answers `7001: code_mode and allow_code_mode disagree. Send only
  code_mode, or a consistent pair.` — measured, not inferred — so the script
  refuses a file where they do not, and then sends the pair. Sending both is
  what makes an apply converge on a portal someone left at `opt_in`: naming
  only `code_mode` would leave the stored `allow_code_mode` true under the
  merge semantics below, and `--check` would stay red on a field the apply
  had no way to settle.
- `portal` and `hostname` — the address. The script refuses a file naming a
  different portal: this file writes to a shared surface, and a retargeted
  file would rewrite a mapping this repository does not own.

The tool allowlists are **not** here. They live with the servers that
register the tools — `mctl-telegram`, `mctl-api`, `seerrsense` — because the
decision "this tool is safe to expose" belongs in the same diff as the tool.

## What the write does not touch

The endpoint is a `PUT` that behaves as a merge: a field the body leaves out
keeps its stored value. Measured against the live portal — a write omitting
`description` left it intact, and a write omitting `servers` left all three
upstream mappings at 74/5/30 tools with `default_disabled` untouched.

So the script sends `secure_web_gateway` and the two Code Mode fields, and
nothing else.
That is not tidiness. `servers` carries the tool allowlists owned by
`mctl-telegram`, `mctl-api` and `seerrsense`, and sending it back as read
would make every apply a read-modify-write over their state: an allowlist
applied between this script's read and its write would be silently reverted,
and the API would answer `200`. A field that is never sent cannot lose that
race. The apply still checks that no mapping disappeared across the write —
by id, not by contents, because a concurrent allowlist edit is legitimate
and must not read as a failure.

## Running it

```
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-controls-apply.sh --check
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-controls-apply.sh --dry-run
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-controls-apply.sh
```

`--check` exits non-zero on drift and prints the fields that differ; it is
the operator's stand-in for `cloudflare-drift.yml`, which does not watch this
file. Nothing in CI applies or checks it today.

That is no longer for want of a credential: `CF_PORTAL_READ_TOKEN` and
`CF_APPLY_TOKEN_PORTAL` (see the root below) are `Account -> MCP Portals`
Read and Edit, and the portal object these switches live on is inside that
permission. What is missing is the wiring, and the durable answer is the same
one the servers took — describe the portal as
`cloudflare_zero_trust_access_ai_controls_mcp_portal` and let plan and apply
own it. That import is a separate decision, because the portal object also
carries the tool allowlists owned by `mctl-telegram`, `mctl-api` and
`seerrsense`.

# Cloudflare MCP Portal upstream OAuth registration — an OpenTofu root

This directory is also an OpenTofu root (`mcp-servers.tf`), holding the
portal's upstream servers. Its state key is `cloudflare/portal/terraform.tfstate`
in `mctl-cloudflare-state`, and `cloudflare-plan.yml`, `cloudflare-apply.yml`
and `cloudflare-drift.yml` pick it up the way they pick up any root.

It does **not** live in `account/`, which its README lists as the eventual
home for the portal (`#1092`). The reason is the rule stated in
`cloudflare-apply.yml`: one write token per root, so an apply of one root
cannot touch another surface. The account root's credential will carry Access,
R2 and organization settings; this one carries `MCP Portals` and nothing else.
Folding the two together would mean widening whichever token applies them.

## Why the scope needs describing at all

It is the one portal setting that fails silently. On 2026-09-12 the portal's
grant for `tg` was:

```
oauth: token authorization_code grant
client_id:       cloudflare-portal-mcp
requested_scope: telegram:dialogs:read telegram:messages:read
granted_scope:   telegram:dialogs:read telegram:messages:read admin:users
```

Every other layer looked healthy: all 30 `tg` tools enabled in the portal, the
identity on the admin tier, `send_enabled` on, `ALLOW_SEND` on. A send still
came back as a dry-run preview, because `mctl-telegram`'s `narrowGrant`
(`internal/oauth/scopes.go`) drops any negotiable scope the client did not ask
for. `admin:users` survived only because it is *not* negotiable and is granted
by membership — its presence beside a missing send scope is the signature of
this failure, and the reason "raise the access tier" is the wrong fix.

The two-scope string had been set by hand when the server was created on
2026-09-10, and was recorded nowhere.

## The field OpenTofu cannot see

`auth_credentials` is write-only: the API accepts it and returns only the
read-only `auth_config_summary` projection. Measured on 2026-09-12 against a
throwaway server created and destroyed for the purpose:

- **No perpetual diff.** After an apply, the next plan is `no-op` — the
  provider keeps the applied value in state rather than nulling it on refresh.
- **No drift detection either, for that attribute.** An out-of-band `PUT`
  changed the live scope to `probe:TAMPERED` and `tofu plan` still reported
  `no-op`. State said what had been applied; the API could not contradict it.

So the plan owns everything else on the server, and
`scripts/portal-auth-credentials-drift.py` owns that one attribute: it reads
the live projection and compares it against what state says was applied. There
is no second source of truth — the desired value comes from the state, not from
a file beside it — and `cloudflare-drift.yml` runs it nightly for this root,
only when the plan came back clean.

## Other things measured here

- Importing the live server plans exactly one update, to `auth_credentials`.
  `client_secret` does not appear in the diff and is not touched.
- **Creating** a manual-mode `oauth` server requires a non-empty
  `client_secret` (`7001: client_secret must be a non-empty string`); updating
  one does not. Adopting `tg` therefore needs no secret in state; a future
  server added from scratch will.
- `updated_tools` / `updated_prompts` are in `ignore_changes`. They are the
  allowlists owned by `mctl-telegram`, `mctl-api` and `seerrsense`, applied
  from those repositories. Nothing here sets them, so nothing here can revert
  them.

## After an apply

Sign the upstream out and back in in the portal. `boundRefreshGrant`
(`mctl-telegram/internal/oauth/server.go`) intersects a refresh with the
family's original grant, so a wider scope never reaches a token that already
exists.

## Re-snapshot: refreshing a manual-OAuth server's tool catalogue

The portal keeps a snapshot of each upstream's tools (`servers/{id}.tools`,
including every `outputSchema`) and serves clients from it. For a server in
manual OAuth mode — all three of ours — that snapshot is taken **once**, when
the first user completes upstream OAuth, and is never refreshed. That is
documented, not a bug: the MCP Portals limitations list says *"Manual OAuth
capabilities are captured during the first user authorization … Background
and manual capability synchronization do not refresh them."* Synchronisation
runs with an admin credential that only automatic (DCR) registration has, so
`POST servers/{id}/sync` answers `success` and does nothing; the only honest
signal is `last_synced`.

The cost is not just "a new tool never reaches clients" (mctlhq/.github#64).
Clients validate live responses against the snapshot's `outputSchema`, so an
output-schema change to a tool that is already enabled breaks that tool
through the portal (mctlhq/mctl-telegram#637).

### What moves the snapshot, measured 2026-09-13 on `seerrsense`

| Lever | Result |
| --- | --- |
| `PUT` `auth_credentials` with a different `scope` | `status: ready`, `last_synced` unchanged |
| `PUT` `hostname` alone (`…/mcp?v=2`) | `7000 D1_ERROR: near "WHERE": syntax error` — nothing written |
| `PUT` `hostname` with `name` and `auth_type` | `200`, hostname silently kept as before |
| `PUT` `auth_type: bearer` (dummy token), then back to `oauth`/`manual` | **works** — see below |

Only the auth-type flip puts the server back through `waiting`. It clears the
stored manual registration (`auth_config_summary: null`) while in bearer mode,
so the second `PUT` must resend the full `auth_credentials` blob **and** a
`client_secret` (a switch *to* manual requires one; any non-empty value works
with `token_endpoint_auth_method: none`, and it bumps `client_secret_version`).

### Recipe

The token never reaches a command line: `cf()` hands it to curl in a config on
a file descriptor, the same shape `scripts/portal-controls-apply.sh` uses, so
it is in neither the shell history nor the process table. `--fail-with-body`
and `jq -e` are load-bearing on step 0 — curl succeeds on an HTTP error by
default and plain `jq` writes `null` with status 0, which would leave the
operator holding an empty backup of the only copy of the registration.

```
read -rs CLOUDFLARE_API_TOKEN           # Account -> MCP Portals -> Edit
CLOUDFLARE_ACCOUNT_ID=<account id>      # the same name the rest of this README uses
SERVER=<tg|api|seerrsense>

cf() { curl -sS --fail-with-body \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$CLOUDFLARE_API_TOKEN") \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/access/ai-controls/mcp/servers/$SERVER" "$@"; }

# 0. save the registration FIRST and refuse to continue without it. Step 1
#    clears it, and for api and seerrsense nothing else records it (only tg is
#    described in mcp-servers.tf). The read-only projection carries every field
#    step 2 needs except the secret. One fetch, validated and saved, so the
#    bytes checked are the bytes kept.
summary=$(cf) || { echo "the GET failed -- do not flip"; exit 1; }
printf '%s' "$summary" | jq -e '.success and (.result.auth_config_summary != null)' >/dev/null \
  || { echo "no usable registration to back up -- do not flip"; exit 1; }
printf '%s' "$summary" | jq '.result.auth_config_summary' > "$SERVER.summary.json"

# 1. flip to bearer: status goes waiting -> error ("unable to connect"), last_synced moves
cf -X PUT --json '{"auth_type":"bearer","auth_credentials":"resnapshot-not-a-token"}'

# 2. flip back to manual OAuth. auth_credentials is the saved summary's
#    auth_mode + config + registration_info as ONE JSON-encoded string, and a
#    client_secret (a switch to manual requires one; any non-empty value with
#    token_endpoint_auth_method none). Build it with jq from the saved file
#    rather than hand-encoding it into a quoted shell string: jq does the
#    escaping, and an apostrophe anywhere in a redirect URI or scope would
#    otherwise close the quote and send a mangled registration.
jq -n --arg creds "$(jq -c '{auth_mode, config, registration_info}' "$SERVER.summary.json")" \
      --arg secret "$(openssl rand -hex 24)" \
      '{auth_type:"oauth", auth_credentials:$creds, client_secret:$secret}' \
  | cf -X PUT --json @-
#    -> status: waiting, authentication_status: manual

# 3. ONE user signs the server out and back in on the portal's server selection
#    page (portal_toggle_servers gives the URL), and it must be an identity on
#    the upstream's highest tier. The snapshot holds whatever tools/list THAT
#    identity is shown, and it is taken once: if a lower-tier user authorizes
#    first, the catalogue keeps their reduced set and the later high-tier login
#    does not refresh it. Announce the window, and read the tool count back
#    before telling anyone else to reconnect.

# 4. give the new tools a decision in the owning repository's allowlist and
#    apply it: scripts/portal-allowlist-apply.sh in mctl-telegram and mctl-api
#    (then --check). seerrsense has no apply script yet (mctlhq/seerrsense#70).
```

For `seerrsense`, step 4 is the read-modify-write PUT on `portals/mcp` that
Phase 0 used, and it carries the race this file describes under "What the
write does not touch": it sends every server's mapping back, so a `tg` or
`api` allowlist applied between the read and the write is silently reverted,
with a `200`. Until a targeted script exists, run it when no other apply is in
flight, and read the other two mappings back afterwards — their tool counts
and `default_disabled` must be what they were before.

Measured on the day: `seerrsense` `last_synced` 2026-09-10 19:32 → 2026-09-13
05:42, `api` 74 → 75 tools with the allowlist re-applied 75/75. The portal
mapping (`updated_tools`, `default_disabled`, `on_behalf`) survived both flips
untouched; `description` survived; the Access application was not involved.

What it costs: for the minutes between step 1 and step 3 the server is
unusable through the portal, and every portal user has to re-authorise it
afterwards. Live MCP sessions keep the old `tools/list` until they reconnect.

Two rules follow. Re-snapshot **after** the release that changed the tool
definitions is deployed, never before — the snapshot copies whatever the
upstream advertises at that moment (`tg` waited for the release carrying
mctl-telegram#638, or the closed schemas would have been captured again).

And any PR that changes what `tools/list` advertises owes this step: a tool
added or removed, an `outputSchema` changed, and equally an `inputSchema` —
the snapshot carries the whole tool definition, so a renamed or newly required
parameter leaves clients calling the tool the old way against a server that no
longer accepts it. Nothing automatic notices a missed re-snapshot on this
branch — the nightly catalogue check is mctlhq/mctl-gitops#1242, stacked on
this one — so until that lands the only thing that notices is a failing
client.

For `tg`, which OpenTofu describes in `mcp-servers.tf`: the flip is done with
the same API token outside tofu and the registration is resent from the file's
values, so the next `tofu plan` comes back `no-op`. The secret does not: step 2
bumps `client_secret_version`, and `scripts/portal-auth-credentials-drift.py`
compares the live version with the one state recorded at the last apply, so
the nightly check reports drift until state learns the new version. Its
backend credential is read-only, so a plan cannot record it -- run the
`cloudflare-apply.yml` workflow for this root once (it applies nothing and
refreshes state; the environment approval is the gate) before expecting the
detector to pass. Measured after the `tg` re-snapshot on 2026-09-13: live
version 2, state version 1.

### The check that notices

`scripts/portal-catalogue-drift.py` runs nightly from `cloudflare-drift.yml`
for this root, after the registration check and independently of its result.
It reads every server mapped on the portal, compares the stored tool names
with the `docs/portal-allowlist.json` each owning repository commits on `main`
— test-enforced there to equal what the server registers, so it is the honest
statement of which tools the upstream advertises — and reports any stored
`outputSchema` that is still closed. Exit 1 means "re-snapshot per the recipe
above". Its `--selftest` runs on every pull request from
`validate-manifests.yml`, because a detector never seen to fire is not known
to work.

Read its green carefully: it says *names match and the stored schemas are
open*, not *the catalogue is fresh*. A schema whose content changed under an
unchanged name and an open snapshot passes, and would still break clients.
Seeing that needs a committed copy of each upstream's schemas to compare
against, which no repository has today.

`KNOWN_STALE` in the script is the list of findings already written down
elsewhere. It exists because a job that is red every night is one people stop
reading — this file's own argument about green checks, pointed the other way.
A waiver covers one kind of finding on one server, **and enumerates the tools
it was written against**: the closed-schema finding arrives as one line for
all of them, so without that list a sixth tool going closed would ride in on
the excuse for the five known ones. It stops excusing on the day after its
date, and a waiver whose finding has gone fails on its own — under a separate
heading, because deleting three lines from a script is not the same job as
taking a server down to re-snapshot it. One waiver is committed today:
`seerrsense` publishes closed output schemas in code, and the fix waits on
that repository's review freeze.

The waived findings are printed even on a passing run, and the nightly summary
repeats them, so a green check never reads as more than it is.
