# Design: mcp-oauth-client-lifetime

## Source commits
- mctl-api:f9fa393 — fix(oauth): bound access-token TTL and expire stale DCR registrations
- mctl-api:217e225 — fix(oauth): bound the DCR client registry and raise the register limit
- mctl-api:2ef473e — fix(oauth): reject a revocation request that carries no token
- mctl-api:82d75fd — fix(oauth): do not answer 200 to a revocation that never happened
- mctl-api:ca41c90 — fix(oauth): bound client_name on the registration success log too
- mctl-api:7439573 — fix(oauth): harden registration body, truncation and cache headers
- mctl-api:f5e1437 — fix(oauth): name the rejected redirect_uri on failed registration

## Current state of documentation
- `docs/mcp/connecting.md` — has "Prerequisites", "Setup" (points at the
  `<McpSetup />` component), "Verifying Connection", a "Token Types" table
  (3 formats), and a pointer to "Troubleshooting". No TTL, no rate limit,
  no revocation behavior.
- `docs/reference/troubleshooting.md` — "Authentication" section covers
  "Unauthorized", "Forbidden on tenant operations", "Forbidden on
  workflows.mctl.ai", and duplicates the "Token type confusion" table.
  No entry for registration rate-limiting or token expiry.

Verified via grep for `DCR|dynamic client|revocation|expire|TTL` against
both files — zero matches in either.

## Proposed solution
1. `docs/mcp/connecting.md` — add a "Token Lifetime & Client Registration"
   subsection after "Token Types", stating: 24h max access-token TTL with
   silent renewal via `refresh_token`; the 30/min/IP registration limit
   and who it's sized for (multi-process clients); that revocation
   requires a token and reports failure honestly.
2. `docs/reference/troubleshooting.md` — add one new entry under
   "Authentication": **"429 Too Many Requests on `/oauth/register`"** and
   fold a short **"Access token expired after ~24h"** note into the
   existing "Unauthorized" entry (rather than a whole new heading, since
   it's the same symptom — re-auth required — just a different, now
   documented, cause).

## Alternatives
1. **One combined new page for the whole OAuth lifecycle.** Dropped — the
   site already splits "how it works" (`connecting.md`) from "what to do
   when it breaks" (`troubleshooting.md`), and the existing token-type
   table is already duplicated across both; keeping that pattern is more
   consistent than introducing a third page for one topic.
2. **Only update `connecting.md`, skip troubleshooting.md.** Dropped —
   the rate-limit and TTL behaviors are exactly the kind of "why did this
   just fail" symptom the troubleshooting page exists for; a reader who
   hits a 429 mid-setup is more likely to search troubleshooting.md first.

## Impact
- Sidebar/nav: no change — both pages already exist and are linked.
- Diagrams: not needed: the added content is two short prose/table blocks,
  no new multi-step flow beyond what's already described.
- Versioning: none (no versioned docs on this site).
