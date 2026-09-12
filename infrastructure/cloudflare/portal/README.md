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
the operator's stand-in for `cloudflare-drift.yml`, which cannot watch this
until CI has a Cloudflare identity. Nothing in CI holds the token today, so
nothing in CI applies or checks this file — that is the gap `#1111` closes,
not something this script works around.


# Cloudflare MCP Portal upstream OAuth registration

`mcp-portal-server-auth.json` is the committed state of the OAuth
registration each upstream is connected with — the endpoints, the client, and
above all the **scope the portal asks that upstream for**. It is applied by
`scripts/portal-server-auth-apply.sh`, with the same `--check` and
`--dry-run` modes as the controls script above.

## Why a scope needs pinning at all

It is the one portal setting that fails silently in both directions. On
2026-09-12 the portal's grant for `tg` was:

```
oauth: token authorization_code grant
client_id:       cloudflare-portal-mcp
requested_scope: telegram:dialogs:read telegram:messages:read
granted_scope:   telegram:dialogs:read telegram:messages:read admin:users
```

Every other layer looked healthy: all 30 `tg` tools enabled in the portal,
the identity on the admin tier, `send_enabled` on, `ALLOW_SEND` on. A send
still came back as a dry-run preview, because `mctl-telegram`'s `narrowGrant`
(`internal/oauth/scopes.go`) drops any negotiable scope the client did not
ask for — `admin:users` survived only because it is *not* negotiable and is
granted by membership. The two-scope string had been set by hand when the
server was created on 2026-09-10 and was recorded nowhere.

The scope is also not a field of the MCP Server API. It lives inside
`auth_credentials`, a write-only blob, surfaced back only as the read-only
`auth_config_summary` projection — so it is invisible to anything that lists
the server's own fields.

A new scope does not reach a live session: `boundRefreshGrant`
(`mctl-telegram/internal/oauth/server.go`) intersects a refresh with the
family's original grant, so **the upstream must be signed out and back in in
the portal after an apply**. The script says so on every apply.

## Measured, not inferred

Against the live `tg` server on 2026-09-12:

- `PUT /servers/{id}` **merges**: a write naming only `description` left
  `auth_credentials`, `tools` (30) and `has_client_secret` (v1) intact. The
  first attempt re-sent the description it already had and proved nothing —
  the API answers 200 to a no-op — so it was repeated with a value that
  actually changed, then restored.
- `modified_at` did **not** move across that real write. It stays at creation
  time, so it is not a change signal; drift is decided by comparing fields.
- `client_secret` is a separate top-level write-only field, not part of the
  blob, so the scope can be rewritten without knowing the secret. The apply
  asserts `has_client_secret` survived anyway.
- Server-level `tools` is the synced capability catalogue — name, description,
  schemas, no enabled flags. The flags live on the portal object's `servers[]`
  entries, which this script never touches.

The blob's own shape is **not** published in the OpenAPI schema; it is
mirrored from the projection. That is why the apply reads the projection back
after every write and fails — printing the pre-write snapshot as the restore
point — rather than trusting a 200.

## What the write does not touch

Only `auth_credentials` is sent. Not `client_secret`, not
`updated_tools`/`updated_prompts` (the capability overrides owned by
`mctl-telegram`, `mctl-api` and `seerrsense` — naming them would make every
apply a read-modify-write over their state), not `hostname`/`name`/
`description`.

## Running it

```
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-server-auth-apply.sh --check
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-server-auth-apply.sh --dry-run
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-server-auth-apply.sh
```

Same gap as the controls script: nothing in CI holds a Cloudflare token, so
`--check` is the operator's stand-in for `cloudflare-drift.yml` until `#1111`
lands. After an apply, sign the upstream out and back in in the portal — a
refresh cannot widen an existing grant.
