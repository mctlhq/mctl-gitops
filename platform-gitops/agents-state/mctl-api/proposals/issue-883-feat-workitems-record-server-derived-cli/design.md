# Design: issue-883-feat-workitems-record-server-derived-cli

## Current state

**Work-item provenance.** `internal/workitems/types.go` defines `WorkItem`
(`OwnerPrincipal`, `OwnerPrincipalID`, `OriginSurface`, `CreatedBy`),
`Event` (`ActorPrincipal`, `ActingPrincipal`, `Surface`) and `Intent`
(`ActorPrincipal`, `Surface`, `Text`, `TextRedacted`, `Params`). Every write
carries a `workitems.Mutation` (`internal/workitems/inputs.go`). It has
`Actor`, `ActingPrincipal`, `ActorPrincipalID`, `ViaPrincipalID`,
`ViaExecutionID`, `Surface`, `RequestID`, `IdempotencyKey` and `RequestHash`.
The schema in `internal/workitems/store.go` grows additively through
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... NOT NULL DEFAULT ''`, as
`actor_principal_id` and `via_execution_id` did. `Store.AppendIntent` inserts
into `work_item_intents (work_item_id, actor_principal, surface, text, params,
created_at, actor_principal_id)`. `getIntent`, `Store.Intents` and
`Store.Intent` select `id, work_item_id, actor_principal, surface, text,
params, created_at`. `appendEvent` writes every event row from the `Mutation`.
`itemColumns` / `scanItem` read work items.

**Where the Mutation comes from.** `mutationFor` in
`internal/api/handlers_work_items.go` builds it only from the authenticated
`*auth.User` (`principalOf(user)`, `user.ActingPrincipal()`,
`user.PrincipalID()`, `user.ViaPrincipalID()`, `user.ExecutionID()`) and
`ClientMetaFromContext` (request id). The surface label comes from the body,
except that a relay forces it. Before decoding, `refuseIdentityFields` rejects
any body key in `forbiddenIdentityFields` with 400 `actor_not_accepted`. The
decoder then uses `DisallowUnknownFields`.

**MCP path.** `internal/mcp/workitems.go` (`toolCreateWorkItem`,
`toolAppendWorkItemIntent`) builds an explicit REST body (`origin_surface` /
`surface: "mcp"`, `text`, `idempotency_key`, ...). `workItemCall` sends it
over HTTP to `s.apiURL` with `Authorization: Bearer <effectiveToken(ctx)>`,
which is the caller's own token. The REST auth middleware therefore
re-verifies the connector's token on every work-item call. The MCP transport
is stateless (`internal/mcp/server.go` around line 180: "no Mcp-Session-Id is
minted or required"), so no `initialize` `clientInfo` is retained for a later
tool call.

**OAuth token minting.** `internal/auth/oauth_server.go`:
- The authorization-code exchange checks `entry.ClientID != clientID` (around
  line 1557), then calls `issueJWTFor(entry.Login, entry.PrincipalID,
  entry.Groups, aud)`.
- Both refresh paths (refresh store, around lines 1785-1810, and the in-memory
  map, around line 1853) check that the presented `clientID` matches the
  session row, then call `issueJWTFor(...)`.
- `issueJWTFor` builds `jwtPayload{Issuer, Subject, Audience, PID, Groups,
  IssuedAt, ExpiresAt}`. **No client id is minted into the token**, although
  every caller of `issueJWTFor` holds the authenticated client id.
- `ValidateJWT` → `verifyAccessToken` (`json.Unmarshal` into `jwtPayload`,
  unknown claims ignored) → `userFromPayload` sets the `auth.User` fields.
  Then `tokenAudience` and `supportAudience` are set from verified claims.
  These unexported fields are the established pattern for "how the caller
  authenticated, not a claim" (`internal/auth/oidc.go`, `type User`).
- `ClientKind(clientID)` in `internal/auth/oauth_cimd.go` classifies a client
  as static, cimd, dcr or allowlisted. A CIMD client id is its https metadata
  URL. A persisted DCR id is `dcr_<hash>`.

**Contract.** `docs/work-context-contract.md` documents `WorkItemIntent`
(`actor_principal`, `surface`, `text`, `params`), the identity rule ("A
caller-supplied actor field is never accepted") and the MCP surface section.
That section says "For a direct caller, `surface` is a label, not an
authenticated claim."

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`:
  image tag `4.143.0`. This is the version the issue observed.
  `OAUTH_UPSTREAM: "zitadel"`, so MCP connectors sign in upstream and
  mctl-api still mints its own access token. `OAUTH_CIMD_ACCEPT/ADVERTISE:
  "true"` with `OAUTH_CIMD_ALLOWED_HOSTS: "chatgpt.com,claude.ai,vscode.dev"`,
  so the Claude and ChatGPT connectors use distinct URL client ids on those
  hosts. Access tokens are audience-bound (`aud`, mctl-api#805).
- `mctl_get_service_config(team=admins, service=mctl-api)`: error "service not
  found". mctl-api is deployed as a platform app from the bootstrap template,
  not as a tenant catalogue service. The access-token TTL in production was
  not observed. The code default in `issueJWTFor` is 1h, and the only
  `OAUTH_ACCESS_TOKEN_TTL` hits in gitops are for mctl-telegram ("1h").

## Proposed solution

Carry the authenticated OAuth client id from the token endpoint to the work-item
row as signed token state. Never read it from request input.

1. **Mint (`internal/auth/oauth_server.go`).** Add
   `ClientID string \`json:"client_id,omitempty"\`` to `jwtPayload`. This is
   the RFC 9068 claim name. Change `issueJWTFor` to take a `clientID`
   argument, used by the code exchange (`entry.ClientID`) and both refresh
   paths (the client id already matched against the stored session). The
   public `IssueJWT` passes `""`, and so does the support mint
   (`oauth_support_token.go`). Bound the value at mint (for example
   `len <= 512`, no control characters). If it is out of bounds, log and omit
   the claim rather than fail the grant.
2. **Verify (`internal/auth/oauth_server.go`, `internal/auth/oidc.go`).** Add
   an unexported field `oauthClientID string` to `auth.User`, with an accessor
   `func (u *User) OAuthClientID() string`. Set it only in `ValidateJWT` from
   `payload.ClientID`, next to `tokenAudience`. Apply the same bound check; a
   malformed value reads as `""`. No other constructor sets it, and relayed
   or delegated users do not inherit it. The value is provenance only:
   nothing in `principal_authz.go`, tenant access or visibility reads it.
3. **Mutation (`internal/workitems/inputs.go`).** Add
   `ActorClientID string` to `Mutation`, documented as "the OAuth client the
   authenticating access token was issued to; provenance only; '' when the
   credential is not an mctl-api OAuth access token". `mutationFor` sets
   `ActorClientID: user.OAuthClientID()`. It stays out of `RequestHash`: the
   hash covers the decoded body, which cannot contain it.
4. **Schema and store (`internal/workitems/store.go`).** Additive columns:
   - `ALTER TABLE work_item_intents ADD COLUMN IF NOT EXISTS actor_client_id TEXT NOT NULL DEFAULT '';`
   - `ALTER TABLE work_items ADD COLUMN IF NOT EXISTS origin_client_id TEXT NOT NULL DEFAULT '';`
   - `ALTER TABLE work_item_events ADD COLUMN IF NOT EXISTS actor_client_id TEXT NOT NULL DEFAULT '';`

   `AppendIntent` inserts `in.ActorClientID` and returns it. `getIntent`,
   `Intents` and `Intent` select it. `Create` inserts `origin_client_id` from
   `in.ActorClientID`. `itemColumns` and `scanItem` read it. `appendEvent`
   writes `m.ActorClientID`, and the event read path selects it. The retention
   sweeper is unchanged: the field is identity metadata like
   `actor_principal`, not intent text.
5. **Types (`internal/workitems/types.go`).** Add `Intent.ActorClientID`
   `json:"actor_client_id"`, `WorkItem.OriginClientID`
   `json:"origin_client_id"` and `Event.ActorClientID`
   `json:"actor_client_id"`. None of them uses `omitempty`: like
   `text_redacted`, an absent key must not be mistaken for a value, and `""`
   is defined as "not recorded".
6. **Refuse input (`internal/api/handlers_work_items.go`).** Append
   `"actor_client_id", "origin_client_id", "client_id"` to
   `forbiddenIdentityFields`. A body naming them gets 400
   `actor_not_accepted`, not a generic unknown-field error, so the refusal is
   explicit and covered by tests.
7. **MCP (`internal/mcp/workitems.go`).** No behavioural change: the tools
   already build a fixed body and forward the caller's token, so the REST layer
   derives the value. Add one sentence to the create and append tool
   descriptions ("the OAuth client your token was issued to is recorded by the
   server, never from an argument"). The tool count does not change.
8. **Docs.** Update `docs/work-context-contract.md`:
   - `WorkItem`: add `origin_client_id`.
   - `WorkItemIntent`: add `actor_client_id`.
   - Event: add `actor_client_id`.
   - "Identity and authorization": add a bullet saying what the field means,
     where it comes from (the signed `client_id` claim of an mctl-api access
     token), that it is never accepted from input, that it authorizes nothing,
     and that `""` means not recorded.
   - MCP surface: name it as the server-derived way to distinguish clients,
     with its limit (the shared portal's tokens name the portal's client).

   Add the `client_id` access-token claim to the token section of
   `docs/principals.md` or `docs/access-token-signing.md`, and add a
   CHANGELOG entry through release-please.

Why this way: the client id is decided by the OAuth server after client
authentication (PKCE, private_key_jwt for CIMD) and is then covered by the
token signature. Putting it in the token avoids any new store lookup on the
hot auth path, and it works unchanged for the MCP-to-REST loopback because
the same bearer is re-verified. Every handler that already uses
`mutationFor` picks it up.

## Alternatives

- **MCP `initialize` `clientInfo`, stored as an untrusted hint.** Dropped.
  The transport is stateless, so the value is not available when
  `tools/call` runs, and it is self-asserted anyway. If wanted later, add it
  as a separately named `*_hint` field.
- **Look the client up from the refresh session at request time.** A
  reverse index (access token or jti to refresh session) does not exist:
  access tokens are stateless JWTs without `jti`. It would add a DB read per
  request and a new failure mode. Dropped in favour of the signed claim.
- **Let the MCP layer send the client id in the REST body or a header.**
  Dropped. It turns a server-derived fact into a request field that any
  direct REST caller could also send, which is exactly what the issue forbids.
  It also would not cover non-MCP clients of the REST API.
- **Record the `User-Agent` from `ClientMeta`.** Dropped. It is
  caller-supplied and spoofable, and it is already in audit entries.

## Platform impact

- **Migration:** three additive `ADD COLUMN IF NOT EXISTS ... DEFAULT ''`
  statements in the existing `schema` constant. They are applied at startup
  like the earlier principal-id columns, with no backfill, and are safe across
  a rolling deploy: an old pod ignores the new columns.
- **Backward compatibility:** the `workitem/v1` response gains fields
  (additive, so `schema_version` is unchanged). Access tokens gain one claim.
  Old pods `json.Unmarshal` it into a struct without the field and ignore it,
  so rollback and mixed-version rollout are both safe. Tokens minted before
  the change carry no claim, so their writes record `""` until the next
  refresh, at most one access-token TTL (1h by code default). Nothing rejects
  a claim-less token.
- **Resource impact:** negligible. A few bytes per token and per row, and no
  extra queries.
- **Risks and mitigations:**
  - *Forgery via input.* This is mitigated by `forbiddenIdentityFields`, by
    `DisallowUnknownFields`, by the fixed MCP body, and by mutation-verified
    tests (see tasks T3 to T5).
  - *Someone reads the field as authorization.* The doc and code comments
    say provenance only, and no authz code references the accessor.
  - *Mistaking "" for "no client".* The contract defines `""` as "not
    recorded" (non-OAuth credential or legacy token), never as "the same
    client".
  - *The value reveals which product a user used.* It is visible only to
    callers who can already see the item. Exposure is an owner decision,
    recorded as an open question.
  - *Shared portal.* Tokens obtained through the Cloudflare portal name the
    portal's client, which is documented. The work-item write tools are
    disabled there.

## Open questions

- Field names and reader exposure need owner confirmation (see
  requirements.md).
- The production `OAUTH_ACCESS_TOKEN_TTL` for mctl-api was not observed. It
  only affects how long legacy claim-less tokens keep writing `""`.
- Whether a replay from a different client should be refused. This design
  replays.
