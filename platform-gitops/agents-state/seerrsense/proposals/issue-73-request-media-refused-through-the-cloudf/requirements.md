# Default the authorize scope to `seerr:read seerr:request`

## Context

`/oauth/authorize` treats an authorization request that names no `scope` as a
request for `seerr:read` alone (`src/auth/routes.ts:330`:
`const requested = (params.scope ?? SCOPE_READ).split(/\s+/)`). The Cloudflare
MCP portal authorizes its upstreams without naming a scope, so the token it
holds for the `seerrsense` upstream carries `seerr:read` only. Search works
through the portal, while `request_media` answers `this token is not granted
the seerr:request scope` — the check in `src/mcp/server.ts:346`. A refresh
reuses the grant's stored scope (`src/auth/routes.ts:533`), so the portal's
token can never widen on its own; only a fresh authorization can change it.
Clients that read `scopes_supported` from the RFC 8414 document and ask for
both scopes (the direct Claude connector, the test helper in
`tests/oauth.test.ts:126`) are unaffected, which is why this only shows up
through the portal.

RFC 6749 §3.3 says an authorization server that receives no `scope` must
either fail the request or process it using a documented default. This
proposal makes that documented default the full interactive scope set —
`seerr:read seerr:request` — so a conformant client that omits `scope` gets a
token that can use every tool the consent screen offered it, while a client
that names its scopes keeps getting exactly those. The consent screen remains
the only place a grant is approved, and it already lists each scope it is
about to hand over (`src/auth/routes.ts:441`, `SCOPE_LABELS` at
`src/auth/routes.ts:78`), so the wider default stays visible to the person
clicking Allow.

## User stories

- AS a household member using SeerrSense through the mctl Cloudflare portal I
  WANT `request_media` to work after I approve the consent screen SO THAT I can
  ask for a film without being told my token lacks a scope I was never offered
  the chance to request.
- AS an operator of the SeerrSense authorization server I WANT the no-scope
  default written down in the README security model SO THAT the grant a portal
  or any other silent client receives is predictable and reviewable.
- AS the author of an MCP client that deliberately asks for read-only access I
  WANT an explicit `scope=seerr:read` to stay read-only SO THAT least privilege
  is still expressible.
- AS a maintainer I WANT a regression test that fails on the current `main` SO
  THAT the default cannot silently narrow again.

## Acceptance criteria (EARS)

- WHEN `/oauth/authorize` receives a valid request whose `scope` parameter is
  absent THE SYSTEM SHALL treat the request as asking for
  `seerr:read seerr:request` and persist that string as the pending
  authorization's scope.
- WHEN `/oauth/authorize` receives a request whose `scope` parameter is present
  but contains no scope tokens (empty or whitespace only) THE SYSTEM SHALL
  treat it exactly as an absent `scope` and apply the same documented default.
- WHEN `/oauth/authorize` receives a request that names one or more supported
  scopes THE SYSTEM SHALL grant exactly the named scopes and nothing more, so
  that an explicit `scope=seerr:read` yields a read-only token.
- IF an authorization request names a scope outside `SUPPORTED_SCOPES` THEN THE
  SYSTEM SHALL keep refusing it with an `invalid_scope` redirect error, exactly
  as today (`src/auth/routes.ts:331`).
- WHEN the consent page is rendered for an authorization that named no scope
  THE SYSTEM SHALL list every scope being granted, including the line for
  `seerr:request` ("Request new films and series on your behalf").
- WHEN a token minted from a no-scope authorization is used to call
  `request_media` over `/mcp` THE SYSTEM SHALL pass the `SCOPE_REQUEST` check
  in `src/mcp/server.ts:346` and attempt the request.
- WHILE a refresh token is exchanged THE SYSTEM SHALL keep issuing the scope
  recorded on the existing grant, so no already-issued read-only grant is
  widened by this change.
- THE SYSTEM SHALL keep advertising `scopes_supported` as
  `["seerr:read", "seerr:request", "offline_access"]` in both `.well-known`
  documents, unchanged.
- THE SYSTEM SHALL NOT include `offline_access` in the documented default; a
  refresh token is issued regardless (`issueTokens`, `src/auth/routes.ts:577`),
  and granting a scope the client did not ask for makes clients warn the user.
- THE SYSTEM SHALL document the no-scope default in the README Security Model
  section next to the existing scopes bullet (`README.md:405`).
- THE SYSTEM SHALL ship an automated test that exercises an authorize request
  with no `scope` end to end and fails against the current `main`.

## Out of scope

- Changing what `request_media` itself checks, or the `seerr:read` gate on
  `/mcp` and `/api/v1/*` (`src/api/server.ts:396`).
- Widening or migrating grants that already exist. The portal's current token
  stays read-only until its upstream is re-authorized by hand; that is an
  operational step after deploy, not a code path.
- Changing the account page client, which already names `scope=seerr:read`
  (`public/account.html:207`) and must stay read-only.
- Changing the Cloudflare portal's own OAuth registration in `mctl-gitops`
  (`infrastructure/cloudflare/portal`). Making the portal name its scopes is a
  possible belt-and-braces follow-up, not part of this fix.
- Making the default configurable through an environment variable.
- Any change to `docs/portal-allowlist.json`, which already records that
  `request_media` visibility on the portal is gated by the tool's own
  `seerr:request` check.

## Open questions

- An explicitly empty `scope=` is not covered by the issue text. This proposal
  treats "present but naming nothing" as "named nothing" and applies the
  default; the alternative is refusing it with `invalid_scope`. The chosen
  reading is the forgiving one and is covered by its own test.
- Whether the Cloudflare portal should additionally be taught to request
  `seerr:read seerr:request` explicitly is left open; the server-side default
  fixes every silent client at once, and a portal-side change would only
  duplicate it.
- The final acceptance step — re-authorizing the portal's `seerrsense` upstream
  once after deploy and re-running the Ratatouille (TMDB 2062) repro — cannot
  be automated from the repository and is recorded as a manual verification
  task.
