# Record a server-derived OAuth client identity on work items and intents

## Context

The live proof for mctlhq/mctl-agents#909 (epic mctlhq/.github#281), run on
mctl-api 4.143.0, appended four intents to one WorkItem from two MCP clients
(Claude and ChatGPT), both signed in as the same principal through their own
OAuth flow to `api.mctl.ai/mcp`. Every intent carries the same server-owned
provenance: the same `actor_principal` and `surface: "mcp"`. Only a
self-label inside the caller-supplied intent text tells the two clients apart,
and that text must not be trusted. #909 requires evidence that can "distinguish
the two client operations without trusting caller-supplied identity". This is
the follow-up for that schema gap.

The server already knows which OAuth client each session belongs to. The code
exchange and the refresh grant in `internal/auth/oauth_server.go` both hold the
authenticated `client_id`. Deployed, these are distinct CIMD URLs on
`claude.ai` and `chatgpt.com` (`OAUTH_CIMD_ALLOWED_HOSTS`). But the minted
access token (`jwtPayload`) does not carry it, so `auth.User`, and therefore
`workitems.Mutation`, never sees it. This proposal stamps the OAuth `client_id`
into mctl-api-issued access tokens as a signed claim (RFC 9068 `client_id`).
The work-item handlers then record it next to `actor_principal`, as
`actor_client_id` on intents and events and `origin_client_id` on work items.
The value is never accepted from a request body or tool argument.

## User stories

- AS an auditor of a WorkItem I WANT each intent to name the OAuth client
  that the authenticating token was issued to SO THAT I can tell a Claude
  operation from a ChatGPT operation by the same principal without trusting
  intent text.
- AS the mctl-agents#909 proof author I WANT a server-owned field to assert
  on SO THAT the cross-client acceptance criterion passes without inventing
  identity fields in the test.
- AS a platform operator I WANT the field to be impossible for a caller to set
  or override SO THAT provenance cannot be forged by a tool argument or body
  key.

## Acceptance criteria (EARS)

- WHEN the OAuth server mints an access token in the authorization-code
  exchange or a refresh grant THE SYSTEM SHALL include a signed `client_id`
  claim equal to the client the code or refresh session is bound to.
- WHEN a request authenticates with an mctl-api-issued access token carrying a
  `client_id` claim THE SYSTEM SHALL expose that value on the authenticated
  `auth.User` (`OAuthClientID()`), and only through verification of the signed
  token.
- WHEN `POST /api/v1/work-items/{id}/intents` stores a new intent THE SYSTEM
  SHALL record `actor_client_id` from the authenticated user, next to
  `actor_principal`, and return it on the intent.
- WHEN `POST /api/v1/work-items` creates a new work item THE SYSTEM SHALL
  record `origin_client_id` from the authenticated user, next to
  `origin_surface`.
- WHEN any work-item event is written THE SYSTEM SHALL record
  `actor_client_id` on the event row from the same `Mutation`.
- WHEN an intent, an intent page, a work item or an event is read by a caller
  who can see the item THE SYSTEM SHALL return `actor_client_id` /
  `origin_client_id`, always present, with `""` meaning "not recorded".
- IF a request body to any work-item route contains `actor_client_id`,
  `origin_client_id` or `client_id` THEN THE SYSTEM SHALL answer 400
  `actor_not_accepted` and store nothing.
- IF the MCP tools `mctl_create_work_item` or `mctl_append_work_item_intent`
  are called with a `client_id`-like argument THEN THE SYSTEM SHALL NOT
  forward it. The REST body the tool builds contains no client identity field.
- IF the authenticating credential is not an mctl-api-issued OAuth access token
  (GitHub PAT, Dex/ZITADEL bearer, service, surface, agent run or CI token), or
  is an access token minted before this change, THEN THE SYSTEM SHALL record
  `""` and never substitute a guess, a user agent or a default.
- WHILE an idempotent replay returns an existing intent or work item THE SYSTEM
  SHALL return the originally recorded client id unchanged.
- WHILE the claim is present THE SYSTEM SHALL use it for provenance only and
  never for authorization, tenant access or visibility.

## Out of scope

- MCP `initialize` `clientInfo` as an untrusted hint. The MCP transport is
  stateless (`internal/mcp/server.go`), so no session `clientInfo` exists at
  tool-call time. This can be revisited as a separate, explicitly untrusted
  field.
- Distinguishing clients that reach mctl-api through the shared Cloudflare MCP
  portal. Those tokens are issued to the portal's own client registration. The
  work-item write tools are disabled on the portal (`docs/portal-allowlist.json`).
- A human-readable client name, or `client_kind` (static/cimd/dcr/allowlisted)
  on the record. Readers can derive the kind from the id format.
- Backfilling existing rows, or adding the field to execution requests,
  approvals, snapshots or audit entries.
- Using the client id for authorization or rate limiting.

## Open questions

- Owner decision on the field names. This proposal uses `actor_client_id`
  (intents, events) and `origin_client_id` (work items).
- Owner decision on reader exposure. This proposal exposes the field to every
  caller who can already see the item: an OAuth `client_id` is a public client
  identifier, not a secret. The alternative is admin-only or audit-only, which
  would not serve #909's proof run by a tenant member.
- Whether an idempotent replay from a different client than the original
  should be refused rather than replayed. This proposal replays, matching how
  `surface` behaves today. The client id stays out of the request hash.
- Whether the support-token mint (`oauth_support_token.go`) should carry a
  client id. This proposal leaves it empty.
