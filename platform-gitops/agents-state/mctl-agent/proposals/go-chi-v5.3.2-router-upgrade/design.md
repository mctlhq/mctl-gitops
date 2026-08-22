# Design: go-chi-v5.3.2-router-upgrade

## Current state
Per `context/architecture.md`, mctl-agent uses `chi/v5 5.2.1` as its
HTTP router for the REST API, the AlertManager webhook, the Telegram
webhook, and the MCP JSON-RPC endpoint. All routes are presumably
registered through chi's `Mount()`/`Route()` grouping (typical chi
usage pattern for a service with multiple endpoint families as listed
in the API endpoints section of architecture.md). The current pin
predates the 5.3.2 bugfixes and predates confirmation either way on
CVE-2025-69725.

## Proposed solution
1. Bump `github.com/go-chi/chi/v5` from 5.2.1 to 5.3.2 in `go.mod` /
   `go.sum`.
2. Audit the codebase for any use of chi's `RedirectSlashes`
   middleware (`grep -r "RedirectSlashes"`). Two possible outcomes:
   - **Not used:** record this explicitly as the CVE-2025-69725
     closure — mctl-agent was never exposed regardless of chi version.
   - **Used:** manually verify the redirect behavior against the
     GHSA-mqqf-5wvp-8fh8 advisory description (open redirect via a
     crafted `Location` value derived from request path) using a local
     test against chi 5.3.2's `RedirectSlashes` source. If the flaw is
     still present, remove/replace the middleware (e.g. handle
     trailing-slash redirects manually with a fixed, validated target)
     as part of this same change rather than treating the version bump
     as sufficient.
3. Re-run route registration and the router's own request-routing
   tests, plus targeted tests for the two documented bugfixes: a
   Mount()+Route() collision case and a 405-response `Allow`-header
   dedup case, to confirm both are fixed under 5.3.2.
4. No handler or endpoint-contract changes; this is purely a router
   library version bump plus a verification/documentation step for one
   CVE.

## Alternatives
1. **Bump chi without verifying CVE-2025-69725.** Rejected: the chi
   5.3.2 release notes don't explicitly confirm the CVE fix, and the
   inbox rationale explicitly calls out not to assume it is silently
   resolved. Skipping verification would leave an unconfirmed
   assumption in a security-tagged proposal.
2. **Skip the version bump and only patch/verify CVE-2025-69725 in
   isolation.** Rejected: the Mount()/Route() collision fix and 405
   Allow-header dedup are real, low-risk bugfixes worth taking anyway;
   splitting them into a separate change adds process overhead for no
   benefit given it's a single small dependency bump.
3. **Replace chi with a different router entirely.** Rejected: far
   higher migration effort and risk than a patch-level bump; no driver
   in the inbox or architecture.md suggests chi itself is
   unsuitable — only that it needs a routine bump.

## Platform impact
- **Migrations:** none. No route paths, request/response schemas, or
  API contracts change.
- **Backward compatibility:** fully compatible for API consumers
  (AlertManager, Telegram, MCP clients, REST API callers) — this is an
  internal router library bump. If the `RedirectSlashes` audit
  concludes the middleware needs to be removed or altered, that change
  will be scoped to preserve existing redirect behavior for legitimate
  trailing-slash requests while closing the open-redirect vector.
- **Resource impact (tenant `labs`):** none — this proposal is scoped
  entirely to the `admins`-tenant mctl-agent binary and does not touch
  `labs` in any way, so it carries no risk to `labs`'s memory headroom.
- **Resource impact (tenant `admins`):** negligible; chi is a thin
  routing layer, and a patch-level bump is not expected to change
  CPU/memory characteristics measurably.
- **Risks and mitigations:**
  - *Risk:* CVE-2025-69725 audit finds mctl-agent is exposed and 5.3.2
    does not fix it. *Mitigation:* task 3 below scopes a concrete
    mitigation (remove/replace `RedirectSlashes` usage) inside this
    same proposal rather than deferring indefinitely.
  - *Risk:* the Mount()/Route() collision fix changes route-matching
    precedence for an existing (possibly accidental) overlapping route
    registration. *Mitigation:* task 2 below explicitly tests all
    existing endpoint groups for collisions before merge.
  - *Risk:* compress-middleware wildcard fix changes behavior for a
    route mctl-agent relies on. *Mitigation:* confirm during testing
    whether mctl-agent uses chi's compress middleware with wildcard
    patterns at all; if not, this fix is a no-op for us.
