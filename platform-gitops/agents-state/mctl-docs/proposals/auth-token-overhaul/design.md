# Design: auth-token-overhaul

> version-status: unverified, see commit SHAs below

## Source commits

- `mctl-api:60b8034` — fix(auth): extend OAuth access token TTL from 1h to 7d
- `mctl-api:2930d1b` — fix(auth): persist OAuth refresh tokens in Postgres
- `mctl-api:5b166aa` — fix(auth): add retry grace window and client-scoped revocation to refresh store
- `mctl-api:b4d0c29` — fix(auth): sanitize invalid_grant error_description to avoid leaking internals

## Current state of documentation

Existing page: `docs/security/authentication.md`

The page exists and covers OAuth basics, token types, and the general flow. Based
on the inbox analysis it is stale on at least four counts:

1. **Token TTL** — documents (or implies) a 1-hour access token lifetime. The
   actual value is now 7 days (`7*24*time.Hour` in `internal/auth/oauth_server.go`).
2. **Refresh token persistence** — makes no mention of the Postgres-backed
   `refreshstore` package. A reader would assume in-memory storage, meaning they
   would expect tokens to be lost on pod restart.
3. **`/revoke` endpoint** — does not document the `client_id` form parameter or
   the RFC 7009 §2.1 client-scoped revocation semantics. Possibly documents an
   earlier, simpler version of the endpoint.
4. **`invalid_grant` error shape** — does not specify a stable `error_description`
   value. In the old code `err.Error()` was forwarded directly, which could expose
   internal strings.

Additionally, `docs/mcp/connecting.md` may reference the old 1-hour TTL or
include troubleshooting hints about hourly reconnects; that page needs a targeted
check and a one-line update if such language is present.

## Proposed solution

### Primary change: replace the token lifecycle section in `docs/security/authentication.md`

The page should be updated (not wholly rewritten) with the following additions
and corrections:

1. **Access token TTL** — change the documented lifetime to 7 days. Add a note
   that the value is controlled by the server; clients should not hardcode it and
   should rely on the `expires_in` field in the token response.
2. **Refresh token persistence** — add a paragraph under the refresh token
   section explaining that refresh tokens are stored in Postgres via the
   `refreshstore` backend and survive API server restarts and pod recycling.
   Framing: reliability guarantee for operators, not an implementation detail.
3. **`/revoke` endpoint** — add or rewrite the revocation section to document:
   - Endpoint: `POST /oauth/revoke` (form-encoded body)
   - Parameters: `token` (required), `client_id` (optional, RFC 7009 §2.1 — when
     supplied, revocation is scoped to tokens issued to that client only)
   - Retry grace window: a token that has already been rotated can be re-presented
     within the server's grace window without being rejected — this prevents
     race-condition failures during legitimate rotation.
   - Include a curl example.
4. **`invalid_grant` error shape** — add a small reference table or code block
   showing the stable error response format, with `error_description` set to
   `"invalid or expired token"`.

### Secondary change: targeted check of `docs/mcp/connecting.md`

Remove or correct any language that tells users their token expires in 1 hour or
that they need to re-connect hourly. A cross-link to `authentication.md` for
token lifetime details is appropriate.

### No structural changes

This is an update to an existing page. No new pages are needed. The sidebar and
nav configuration do not change.

## Alternatives

**Option A (adopted): in-place update of `docs/security/authentication.md`.**
Sections are updated or added where stale. The page structure is preserved.
Minimal diff, easy to review.

**Option B: full page rewrite.**
Rewrite the whole file from scratch as a comprehensive OAuth reference. Dropped
because: (a) the existing structure is sound, only specific facts are wrong;
(b) a full rewrite carries higher review burden and risks introducing new errors
in sections that are currently correct.

**Option C: new standalone page `docs/security/token-lifecycle.md`.**
Create a dedicated token lifecycle reference and link from authentication.md.
Dropped because the topic is not large enough to warrant a standalone page and
splitting it would fragment the security reference that readers naturally treat
as a single document.

## Impact

- VitePress sidebar / nav config: no change required (the page already exists in
  the sidebar).
- Mermaid diagrams: a simple sequence diagram for the OAuth token rotation +
  revocation flow would help; included in `proposed-content.md` as optional.
- Documentation versioning: this applies to `mctl-api` 4.18.4 and later. There
  is no multi-version docs setup, so no branching needed.
- Also touch `docs/mcp/connecting.md` with a one-sentence correction if the 1h
  language is confirmed present (implementer must verify by reading the current
  file).
