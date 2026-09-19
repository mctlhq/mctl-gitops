# Design: mcp-oauth-flow-fixes

## Source commits
- mctl-api:3a88f82 — fix(oauth): move client-registration state out of client_name
- mctl-api:ea2194b — fix(oauth): bound the echoed client fields and split the unnamed case
- mctl-api:da6192d — fix(oauth): widen the refresh rotation grace window and name the client on a failed exchange

## Current state of documentation
- `docs/security/authentication.md` — existing page. The `## OAuth JWT`
  section describes the PKCE login flow (client initiates via
  `mctl.ai/api/github/login`, GitHub auth, JWT issuance, redemption via
  `POST /api/github/session`) but says nothing about **refresh** — no
  mention of rotation, replay, or grace windows anywhere on the page. This
  is a gap, not a stale statement: the page simply doesn't cover this
  behavior yet, at any level of detail (correct or incorrect).
- `docs/mcp/connecting.md` — existing page. Covers prerequisites, setup,
  verifying the connection, and a token-type table. No mention of refresh
  behavior either; same gap.
- `docs/reference/troubleshooting.md` — existing page, `## Authentication`
  section has entries for "Unauthorized" error, "Forbidden" on tenant
  operations, "Forbidden" on workflows.mctl.ai, and token type confusion.
  None of these mention refresh-token replay or family revocation as a
  cause of unexpected re-authentication — the closest existing entry
  ("Unauthorized" error, which says "For OAuth tokens (Claude.ai
  connector): disconnect and reconnect the MCP server") already gives the
  *fix* for this symptom, but not the *cause*, so a reader who wants to
  understand why this happened has nothing to read.
- `proposals/mcp-oauth-client-lifetime/` — an existing, separate proposal
  (from an earlier `mctl-api` release, 4.32.5) already covers OAuth
  access-token TTL, DCR registration rate limits, and `/oauth/revoke`
  semantics for `docs/mcp/connecting.md` and `docs/reference/troubleshooting.md`.
  This proposal is scoped narrowly to refresh-token **rotation and replay**
  specifically, which that proposal does not cover, and should link to it
  rather than re-describe adjacent territory.

## Proposed solution
1. **Update** `docs/security/authentication.md` — add a short new
   subsection under `## OAuth JWT` (after the existing numbered flow list)
   explaining refresh-token rotation: each use issues a new refresh token
   and invalidates the previous one; a short grace window tolerates a
   client retrying because it didn't receive the rotation response; a
   replay outside that window is treated as reuse and revokes the whole
   token family, requiring re-authentication. Framed as security behavior
   ("why"), not as an API contract with a numeric guarantee.
2. **Update** `docs/reference/troubleshooting.md` — add one new entry
   under `## Authentication`, e.g. "Unexpectedly logged out / refresh
   token errors," naming rotation + replay-detection as a cause and
   pointing at the (fix already documented on the "Unauthorized" entry
   above it: disconnect and reconnect).
3. Do **not** touch `docs/mcp/connecting.md` for this proposal — the
   token-type table there is about initial authentication, not refresh
   behavior, and the existing "Troubleshooting" pointer at the bottom of
   that page already routes a confused reader to
   `docs/reference/troubleshooting.md`, where the new entry (step 2) will
   now answer the question.

## Alternatives
1. **Treat this as originally flagged — a correction to existing text.**
   Rejected after reading the actual current page content: neither page
   says anything about refresh rotation today, correct or incorrect, so
   there is nothing to "correct." Framing this as a stale-docs fix would
   misrepresent what changed; it's presented here as a documented gap
   instead, closing the loop the researcher/analyst flagged as
   "needs a content read to confirm."
2. **A dedicated new page, `docs/security/oauth-refresh.md`.** Rejected as
   disproportionate: this is a two-paragraph addition to an existing
   section plus one troubleshooting entry, not enough standalone content
   to justify a new page and sidebar entry.

## Impact
- Does not touch `.vitepress/config.ts` — both edits land inside existing
  pages, no new page.
- No mermaid diagram required for this cycle; a future, larger OAuth flow
  diagram (covering DCR + PKCE + rotation together) could reasonably use
  one, but is out of scope for a two-paragraph addition.
- Applies to the current `main` branch of `mctl-docs`; no versioning
  split. Should be merged with awareness of `proposals/mcp-oauth-client-lifetime/`
  (both touch `docs/mcp/connecting.md`'s general OAuth-flow neighborhood,
  though this proposal edits `authentication.md` and `troubleshooting.md`
  instead) to avoid conflicting edits if both are implemented in the same
  cycle.
