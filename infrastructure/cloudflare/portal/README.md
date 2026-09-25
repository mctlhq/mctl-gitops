# Cloudflare MCP Portal: `mcp-portal.tf`

Portal `mcp` (`mcp.mctl.ai`, the private aggregate over the six upstreams) is
described by `cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp` in
`mcp-portal.tf`. It was imported on 2026-09-25 without changing anything
(mctlhq/mctl-gitops#1370: plan `1 to import, 0 to change`, apply run
36117508212). From then on, `cloudflare-plan.yml`, `cloudflare-apply.yml` and
the nightly `cloudflare-drift.yml` own it like every other resource in this
root. Before the import, the switches were applied by a script from a
committed JSON file, and the tool mappings by a script in each service repo.
Both have been retired.

## What is pinned, and why each field

- `secure_web_gateway`: whether the portal routes its traffic through
  Cloudflare Gateway. This is the Phase 2 subject (`mctlhq/.github#43`,
  `#1181`), and `false` is the baseline the POC returns to.
- `code_mode` / `allow_code_mode`: pinned `off`/`false`. Phase 2 must leave
  Code Mode untouched, and "untouched" can only be checked if something
  records what it was. A drift here means the portal grew an execution
  surface nobody decided on.
  - `code_mode` is one of `off`, `opt_in`, `default_on`, `enforced`. It
    defaults to `opt_in` when omitted on create, so leaving it unpinned is
    not the same as leaving it off.
  - The two fields must agree. The API answers `7001: code_mode and
    allow_code_mode disagree` otherwise (measured).
  - `allow_code_mode` is deprecated in provider 5.24, but it is restated:
    left out, it plans as `(known after apply)`.
- `name` / `description`: copied from the live object at import. The
  description still says "Phase 0: tg only". Correcting it is a separate,
  visible change.
- `servers`: which upstreams are members and what each one exposes. See "The
  portal mapping" below.

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

## The fourth upstream, and the question it is there to answer

`projects.mctl.ai` is registered by **dynamic client registration**, not by
hand: `auth_type = "oauth"` with no `auth_credentials` and no `client_secret`.
Supplying either is what opts a server into manual mode, and manual mode is
the thing being avoided. It can be registered this way because it sits behind
a Cloudflare Access application with Managed OAuth and DCR enabled, so the
portal can register itself as a client with nobody pasting a client id.

The section below is about what manual mode costs: a catalogue captured once
and never refreshed. Cloudflare's own explanation of that limitation names the
reason -- synchronisation runs with an admin credential that only DCR
registration has. So this server is the test of whether the limitation ends
where the documentation says it does. **It is not yet proven.** The check,
after the first login:

1. `last_synced` and `last_successful_sync` are set.
2. Change the upstream's tool set (`mctlhq/projects-mcp` ships a new tool, or
   an existing description changes), deploy it, then `POST servers/projects/sync`.
3. `last_synced` moves and the new tool appears in `tools`. On the three
   manual servers step 3 answers `success` and changes nothing, which is the
   behaviour being compared against.

If it holds, a tool can be added to a DCR upstream without the auth-type flip
recipe below, and the catalogue stops being a thing to design around.

### What Terraform cannot do here

The apply creates the server and leaves it in `waiting`. An admin then opens
it in the dashboard and completes the upstream OAuth login once; **that
account becomes the admin credential** for every later sync. Two things follow
from that, both worth knowing before clicking:

- **Whoever logs in decides what the snapshot contains.** `projects` registers
  two extra tools for a caller in its `ADMIN_EMAILS`, so an owner's login
  snapshots eight tools and a customer's would snapshot six. The eight are the
  recorded decision (`mctlhq/projects-mcp`, `docs/portal-allowlist.json`).
- **The admin credential expires on the upstream's schedule and nobody is
  told.** `authentication_status` goes `stale`, the server stops appearing for
  end users, and the only way to notice is to look. It is read-only here, so
  it belongs in whatever watches the portal rather than in this root.

Customers never reach this server through the portal: they add
`https://projects.mctl.ai/mcp` as a connector directly, where Access is the
OAuth provider. The portal is the owner's own aggregate view, which is also
why the two admin tools being in its catalogue is not a customer-facing
decision.

### What the two nightly checks had to be told

Both drift detectors were written when every registered server was manual and
public, and a DCR server in a private repository is neither. Neither change is
cosmetic — without them this registration breaks the checks rather than being
covered by them.

- `portal-auth-credentials-drift.py` compares the applied `auth_credentials`
  blob against the live projection. This server has no blob **by design**, and
  the script raised `Undetermined` for a missing one from inside its resource
  loop, with no per-resource catch — so one DCR server in state aborted the
  whole scan and the nightly write-only registration check would have reported
  "could not run" for `tg` too, forever. `DCR_SERVERS` now names the servers
  whose absence is the expected state; every other empty one still raises, and
  a DCR server that *grows* a blob raises as well.
- `portal-catalogue-drift.py` fetches each upstream's allowlist from
  `raw.githubusercontent.com` with no token, which only works for a public
  repository. `mctlhq/projects-mcp` is private on purpose, so `projects` is in
  `PRIVATE_OWNERS` and its allowlist goes through the contents API with a
  mctl-agents App token (`ALLOWLIST_TOKEN`, minted in `cloudflare-drift.yml`).
  Its "an upstream vanished from production" branch now also consults OpenTofu
  state: an `OWNERS` entry that has not been applied yet is a plan, not an
  outage, which is the gap between merging this and clicking apply.

## The sixth upstream, `coolify`, and what this change does not do

`coolify.mctl.ai` is registered the same way as `projects`/`alice`: DCR, no
`auth_credentials`, no `client_secret` (mctlhq/mctl-gitops#1363). The apply
leaves it in `waiting`, exactly like `projects` and `alice` before their first
login — an admin completes the upstream OAuth login once from the dashboard,
from the owner address, and only then can it be mapped on the portal (see
"To add a seventh server" below). Until that login happens, `cloudflare-portal-health.yml`
reports `coolify` red every hour; that is expected, not a regression, and
clears once the login is done. Which coolify tools go live afterwards is a
separate decision for a `docs/portal-allowlist.json` in
`mctlhq/mctl-coolify-mcp`, vendored here as `allowlists/coolify.json`.

`alice` (already a DCR resource in this file before this change) is added to
`DCR_SERVERS` and `OWNERS` in the same commit: it had neither, so it was
silently aborting `portal-auth-credentials-drift.py`'s whole nightly scan
before this server was even the subject.

This change deliberately stops short of the rest of mctlhq/mctl-gitops#1363:
`seerrsense` and `api` are still live in manual OAuth mode with no Terraform
resource here at all. Moving them to automatic (DCR) mode needs, in order: a
live measurement of whether a manual registration can be cleared in place
(mirroring "What moves the snapshot" above, but for `auth_config_summary`
rather than the tool catalogue), a live DCR probe confirming each upstream
restricts registration to `https://mcp.mctl.ai/servers-callback`, and —
because that measurement and probe both write to production OAuth state —
credentials and judgment this automated change does not have. Whoever
performs them is expected to add the `import` blocks and resources here field
for field on `tg`'s model (manual, interim) or `projects`'s (automatic,
final), following mctlhq/mctl-gitops#1363's tasks 1, 2, 5 and 6, and extend
`DCR_SERVERS`/`OWNERS` accordingly once the mode of each is settled.

Creating the Terraform resource above registers a server with Cloudflare, but
it does not make the server reachable through `mcp.mctl.ai`. The portal keeps
its own membership list (`servers` on the portal object), and in this root
that list is `mcp-portal.tf`. To add a seventh server, in this order:

1. Add its `cloudflare_zero_trust_access_ai_controls_mcp_server` resource to
   `mcp-servers.tf`, merge, and apply the root.
2. An admin completes the first upstream OAuth login from the dashboard. A
   DCR server stays in `waiting` until then, and the portal has no
   catalogue to map.
3. The owning repository commits a `docs/portal-allowlist.json` that
   decides every tool. Vendor it here as `allowlists/<id>.json`, and add
   the server to `mapping.json`, `sources.json`, `baseline.json` and
   `catalogue.json` (catalogue in portal order). Then merge and apply.
   `scripts/validate-portal-allowlists.py` refuses a catalogue tool with no
   decision, and a server whose `baseline.json` entry is missing.

Adding the mapping and deciding what the server exposes are no longer two
scripts run in two repositories. They are one reviewed plan: the plan names
every tool with its `enabled` value before the apply writes anything.

## The portal mapping: `mcp-portal.tf` and `allowlists/`

`cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp` (in `mcp-portal.tf`)
builds each server's `updated_tools` from three committed files
(mctlhq/mctl-gitops#1370):

- `allowlists/<id>.json`, the decision for each tool. It is the owning repo's
  `docs/portal-allowlist.json`, vendored byte-identical, for all six servers.
  `mapping.json` can still carry a literal `updated_tools` for a server
  marked `vendored: false`, for an owning repo whose file fails the shape
  rules. `api` used that until mctlhq/mctl-api#396.
- `allowlists/mapping.json`, the per-server settings that are not the owning
  repo's call: `default_disabled`, `on_behalf` and `updated_prompts`.
- `allowlists/catalogue.json`, each server's synced tool names in the order
  the portal stores them.

`updated_tools` is built by walking `catalogue.json` and taking `enabled` from
the allowlist. `catalogue.json` exists because provider 5.24 types the
catalogue attribute `tools` as `list(map(string))`, and the API's tool objects
are nested. That attribute is therefore empty in state, and Terraform cannot
read the catalogue itself (measured on #1382).

**When a server re-syncs** (a tool added or removed upstream, or after the
re-snapshot below):

- the nightly `portal` plan in `cloudflare-drift.yml` goes red;
- `scripts/portal-catalogue-drift.py` exits 5 and names the difference;
- the fix is a PR that updates the server's list in `catalogue.json` to the
  portal's order. A newly synced tool also needs a decision in the owning
  repo's allowlist first, and `scripts/validate-portal-allowlists.py` refuses
  a catalogue tool that has none.

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

Four things in here are load-bearing, each for a measured reason.

`set -euo pipefail`, because the middle of this procedure is a server that
does not work: any command substitution that fails silently — a missing backup
file, an `openssl` that is not there — would otherwise reach the API as an
empty string and be discovered only after the flip.

`ok()`, because `--fail-with-body` catches HTTP errors and this API answers
`200` with `success: false`, and has been measured answering `200` while
silently keeping a field it was told to change. The envelope is the truth, and
after each write the server is read back to confirm the transition rather than
trusted to have made it.

The whole restoration payload is built **before** the destructive flip, while
the server still works, so nothing that can fail is left to run when the only
copy of the registration is already gone.

And the token reaches curl in a config on a file descriptor, while the
generated secret reaches `jq` through the environment and the body it ends up
in is written under `umask 077` and deleted once spent. A command line is
world-readable in `/proc`; both of these would otherwise sit in the process
table.

It is **four blocks, not one**, and they are not interchangeable. A single
block cannot be pasted: `read` would consume the next pasted line as the
token, and step 3 is a person in a browser, so everything after it would run
against a server that has not been re-authorized yet. Run each block on its
own, and the fourth only once step 3 is actually done.

Work inside a **nested shell**. `set -e` and the `exit 1` in step 4 are
honoured at an interactive prompt just as they are in a script, so without one
a failed `ok()` closes the terminal these blocks share — in step 1 or 2 that
means losing them in the middle of the destructive window. Exporting the token
first is what lets the nested shell die without taking it with it.

Type this one, do not paste it with anything else:

```
read -rs CLOUDFLARE_API_TOKEN           # Account -> MCP Portals -> Edit
export CLOUDFLARE_API_TOKEN
bash                                    # everything below runs in here
```

Then the target and the two helpers:

```
set -euo pipefail
export CLOUDFLARE_ACCOUNT_ID=6a09f637d20e1f66a8e9d45ebe778058
SERVER=tg                               # or api, or seerrsense

cf() { curl -sS --fail-with-body \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$CLOUDFLARE_API_TOKEN") \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/access/ai-controls/mcp/servers/$SERVER" "$@"; }
ok() { jq -e '.success' >/dev/null; }   # a 2xx envelope can still say success:false
```

Steps 0 to 2, the destructive half:

```
# 0. back up the registration, and refuse to go on without a file that has
#    something in it. Step 1 clears it, and for api and seerrsense nothing
#    else records it (only tg is described in mcp-servers.tf).
summary=$(cf)
printf '%s' "$summary" | ok
printf '%s' "$summary" | jq -e '.result.auth_config_summary != null' >/dev/null
#    umask, because this file carries the whole registration -- endpoints,
#    client id, scope -- for the rest of the procedure.
rm -f "$SERVER.summary.json"
(umask 077; printf '%s' "$summary" | jq '.result.auth_config_summary' \
  > "$SERVER.summary.json")
test -s "$SERVER.summary.json"

# 0a. and the catalogue as it stands, to diff against afterwards. WHOLE tool
#     objects: descriptions and annotations travel in the snapshot too, and
#     readOnlyHint in particular is a structural claim this platform acts on,
#     so a projection down to names and schemas would call a changed
#     annotation "no change".
printf '%s' "$summary" | jq -e '(.result.tools | type) == "array"
                                and (.result.tools | length) > 0' >/dev/null \
  || { echo "this server has no catalogue to diff against; stop"; exit 1; }
printf '%s' "$summary" | jq -S '[.result.tools[]] | sort_by(.name)' \
  > "$SERVER.catalogue.before.json"

# 0b. build the ENTIRE restoration body now, while the server still works.
#     auth_credentials is auth_mode + config + registration_info as one
#     JSON-encoded string; client_secret is required by a switch back to
#     manual and any non-empty value does with token_endpoint_auth_method none.
#     Written to a FILE, not just a variable: from step 1 on, the live server
#     no longer holds the registration, so a shell that dies in the window
#     takes the only in-memory copy of it with it.
CREDS=$(jq -ce '{auth_mode, config, registration_info}' "$SERVER.summary.json")
SECRET=$(openssl rand -hex 24); test -n "$SECRET"
rm -f "$SERVER.restore.json"             # umask does not re-mode an existing file
(umask 077; CREDS="$CREDS" SECRET="$SECRET" \
  jq -n '{auth_type:"oauth", auth_credentials:env.CREDS, client_secret:env.SECRET}' \
  > "$SERVER.restore.json")
test -s "$SERVER.restore.json"

# 1. flip to bearer, then READ BACK that the registration is really gone.
#    status goes waiting -> error ("unable to connect"), last_synced moves.
cf -X PUT --json '{"auth_type":"bearer","auth_credentials":"resnapshot-not-a-token"}' | ok
#    envelope FIRST: on success:false `.result` is null, and
#    `.result.auth_config_summary == null` is then true -- a failed read
#    reporting the flip as done.
gone=$(cf); printf '%s' "$gone" | ok
printf '%s' "$gone" | jq -e '.result.auth_config_summary == null' >/dev/null

# 2. restore, and read back that manual OAuth is in place and the server is
#    waiting for its first authorization. The trap is armed on the line
#    before the PUT, not after it: from that moment the secret in the file
#    is live, and every way out of this shell -- a failed read-back under
#    set -e, a dropped response, the operator closing it -- has to take the
#    file with it. Before the PUT the secret has never been sent, so the
#    file is worth more as the resume artifact than it costs.
trap 'rm -f "$SERVER.restore.json"' EXIT
#    and on a signal: a shell killed by SIGINT or SIGHUP dies of that signal
#    and never runs its EXIT trap -- ^C on a hanging PUT, or a dropped
#    terminal, both plausible here.
trap 'rm -f "$SERVER.restore.json"; exit 130' INT TERM HUP
cf -X PUT --json "@$SERVER.restore.json" | ok
cf | jq -e '.result.status == "waiting"
            and .result.auth_config_summary.auth_mode == "manual"' >/dev/null

# 2a. and that it is the SAME registration, field for field. status+auth_mode
#     only say a manual-OAuth registration exists; this API is on record
#     answering 200 while keeping a field it was told to change, and for api
#     and seerrsense nothing declarative would catch a narrowed scope or a
#     moved endpoint later. Compare against the copy taken in step 0.
#     rc, not a bare diff: under set -e a mismatch would abort the shell with
#     the live client_secret still in the file below.
rc=0
diff -u <(jq -S '{auth_mode, config, registration_info}' "$SERVER.summary.json") \
        <(cf | jq -S '.result.auth_config_summary
                      | {auth_mode, config, registration_info}') || rc=$?
#     every trap, not just EXIT: an INT trap left armed in a shell the
#     operator keeps using would turn a ^C in step 4 or 5 into an exit 130
#     that takes the shell and its variables with it.
rm -f "$SERVER.restore.json"; trap - EXIT INT TERM HUP   # the secret is spent
test "$rc" -eq 0 || { echo "registration changed: redo 0b and 2"; exit 1; }
```

**Step 3 is a person, not a command.** One user signs the server out and back
in on the portal's server selection page (`portal_toggle_servers` gives the
URL), and it must be an identity on the upstream's highest tier. The snapshot
holds whatever `tools/list` THAT identity is shown, and it is taken once: if a
lower-tier user authorizes first, the catalogue keeps their reduced set and
the later high-tier login does not refresh it. Announce the window, and do not
run the next block until this is done.

Steps 4 and 5, the verification:

```
# 4. diff the whole tool definition set against the copy from 0a. The
#    difference must be exactly what the release changed. An identical
#    catalogue is a FAILURE, not a pass: it means the snapshot never moved,
#    whatever last_synced says.
after=$(cf); printf '%s' "$after" | ok
#    and that there IS a catalogue. `tools` is null for a server nobody has
#    authorized -- which is the state this step is verifying its way out of,
#    and the state the server is in if step 3 was announced but never done.
#    Unguarded, jq dies with "Cannot iterate over null" and set -e takes the
#    shell at the one point where access is still closed; worse, an empty
#    ARRAY would diff as every tool removed and read as a release delta.
printf '%s' "$after" | jq -e '(.result.tools | type) == "array"
                              and (.result.tools | length) > 0' >/dev/null \
  || { echo "the portal holds no tools: step 3 did not complete, do NOT reopen access"; exit 1; }
printf '%s' "$after" | jq -S '[.result.tools[]] | sort_by(.name)' \
  > "$SERVER.catalogue.after.json"
printf '%s' "$after" | jq -r '.result.last_synced'

rc=0; diff -u "$SERVER.catalogue.before.json" "$SERVER.catalogue.after.json" || rc=$?
case $rc in
  0) echo "catalogue identical: the snapshot did not move, do NOT reopen access"; exit 1 ;;
  1) echo "read the diff above: it must be exactly what the release changed" ;;
  *) echo "diff could not run ($rc)"; exit 1 ;;
esac

# 5. the catalogue moved, so the portal mapping follows it through a PR,
#    not an API call: give any new tool a decision in the owning repository's
#    docs/portal-allowlist.json, vendor that file into allowlists/, copy the
#    refreshed catalogue (names, in portal order) into allowlists/catalogue.json,
#    and merge. The nightly plan is red until this lands, and
#    portal-catalogue-drift.py exits 5 and names the difference. Then
#    dispatch cloudflare-apply.yml for this root.
```

If the nested shell dies between step 1 and step 2, the server is in bearer
mode with `auth_config_summary` null and nothing on Cloudflare's side to
rebuild the registration from — but `$SERVER.summary.json` and
`$SERVER.restore.json` are on disk, which is why step 0b writes the payload
rather than holding it in a variable. Start a new shell, redo the two helper
definitions, and rerun step 2 as written; it does not depend on anything else
step 0 put in the environment. If `$SERVER.restore.json` is gone — it survives a
shell that dies before step 2's `PUT`, and is deleted by the trap or by step
2a itself on every path after it, because from that point it holds a live
`client_secret` — step 0b's three lines rebuild it from the summary file with
a fresh secret.

Steps 0 to 2 are a window in which this server's registration must have no
other writer. The backup is a point-in-time copy and step 2 puts it back, so a
scope or endpoint change made by anyone else in between is silently reverted —
including one made by `cloudflare-apply.yml`, which owns `tg`'s registration
and serializes against other applies but knows nothing about this procedure.
Do not run it while an apply of this root is in flight, and say in the channel
that the window is open.

Step 5 is the same for every server, `seerrsense` included. Until #1370 it
was a hand-written read-modify-write `PUT` on `portals/mcp`, which sent
every server's mapping back and so silently reverted any allowlist applied
between the read and the write. That race is gone: `mcp-portal.tf` is the
only writer of the mapping, and an apply is serialized per root.

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
longer accepts it. What notices a missed re-snapshot is the nightly
check described below; before it existed, the only thing that did was a
failing client.

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
`inputSchema` or `outputSchema` that is still closed. The two sides are
separate findings, because their remedies differ: a closed output schema is
fixed by a release and a re-snapshot, while a closed input schema may be
deliberate upstream and leave a waiver as the only way out. Its `--selftest`
runs on every pull request from `validate-manifests.yml`, because a detector
never seen to fire is not known to work.

Read its green carefully: it says *names match and the stored input and
output schemas are open*, not *the catalogue is fresh*. A schema whose content
changed under an unchanged name and an open snapshot passes — a retyped or
newly required parameter as much as an added field — and would still break
clients.
Seeing that needs a committed copy of each upstream's schemas to compare
against, which no repository has today.

`KNOWN_STALE` in the script is the list of findings already written down
elsewhere. It exists because a job that is red every night is one people stop
reading — this file's own argument about green checks, pointed the other way.
A waiver covers one kind of finding on one server, **and enumerates the tools
it was written against**: a closed-schema finding arrives as one line for all
of them, so without that list a sixth tool going closed would ride in on the
excuse for the five known ones. The side is part of the kind for the same
reason — an excuse written for five closed output schemas does not cover those
same five tools going closed on the input side. It stops excusing on the day
after its date, and it answers for its own upkeep under a separate heading —
because editing a list in a script is not the same job as taking a server down to
re-snapshot it. Two things land there: a waiver whose finding has gone
entirely, which is a deletion, and one that is merely wider than what fires,
which is a narrowing. Deleting in the second case is the wrong half: for the
committed `seerrsense` waiver it would fail the still-closed schemas unwaived
on the next run and point at the recipe, which captures them closed again.

One waiver is committed today: `seerrsense` publishes closed output schemas
in code, and the fix waits on that repository's review freeze.

The waived findings are printed even on a passing run, and the nightly summary
repeats them, so a green check never reads as more than it is.

Its exit statuses are five, not two, because the remedies cost different
things — and `3` in particular is good news with a chore attached, not a
reason to take a server down:

| exit | meaning | remedy |
| --- | --- | --- |
| 0 | names match, stored schemas open | nothing (read the waived lines) |
| 1 | the catalogue is stale | the recipe above |
| 2 | a side could not be read, or a server holds no tools at all | fix the check; an unauthorized server needs a user to sign in |
| 3 | a waiver matches nothing, or is wider than what fires | delete or narrow it in the script — **not** the recipe |
| 4 | an upstream is missing from the portal | restore the mapping, or retire it from `OWNERS` |

`4` outranks `1`, so a night with both names only the missing upstream; the
run says in that case that catalogue findings also fired. The alert and the
run summary carry the same table's wording.
