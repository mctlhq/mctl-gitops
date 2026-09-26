# Design: chi-v532-mount-route-fix

## Current state
Per `context/architecture.md`, mctl-agent uses `go-chi/chi v5.2.1` as the router for
its entire HTTP surface: `POST /api/v1/alerts` (AlertManager webhook),
`POST /api/v1/telegram` (Telegram bot webhook), `GET /api/v1/tickets` /
`GET /api/v1/skills` / `POST /api/v1/skills/register` (REST API), `POST /mcp` (MCP
JSON-RPC, 6 tools), and `GET /healthz` / `/readyz`. These are mounted as distinct
router groups on a single chi instance. `go-chi/chi v5.3.2` fixes a bug in that exact
mounting mechanism: `Mount()`/`Route()` handler collisions could silently drop a
registered handler rather than erroring or logging, which is a latent availability risk
for any of the mounted groups, most importantly the AlertManager webhook (the entry
point for the whole self-healing pipeline).

Two other proposals already exist for this same version bump:
`go-chi-v5.3.2-router-upgrade` and `chi-redirect-cve-boundary-check`. Both bundle the
v5.3.2 bump with an explicit CVE-2025-69725 boundary check (confirming whether
`RedirectSlashes` usage puts mctl-agent in the vulnerable `>=5.2.2` range). This
cycle's CVE research independently confirms the fix for CVE-2025-69725 landed in
v5.2.4+ and that mctl-agent's current v5.2.1 pin sits below the affected range, so that
part of the older proposals' scope is effectively already answered.

## Proposed solution
1. Bump `github.com/go-chi/chi/v5` in `go.mod` from `v5.2.1` to `v5.3.2`
   (`go get github.com/go-chi/chi/v5@v5.3.2 && go mod tidy`).
2. Audit every `Mount()`/`Route()` call across the AlertManager, Telegram, REST, and
   MCP router registration code for any pattern that could trigger the pre-5.3.2
   collision bug (e.g. overlapping path prefixes across mounted sub-routers), and add
   regression coverage for those registrations specifically.
3. Confirm the 405 `Allow:` header deduplication behavior with a targeted test on any
   route registered with multiple HTTP methods.
4. Do not re-do the CVE-2025-69725 audit work — reference this cycle's finding (fix at
   v5.2.4+, current pin v5.2.1 predates the affected range) as already closing that
   concern, and note in the PR description that this bump does not change v5.2.1's
   CVE-2025-69725 status (not affected before, not affected after — v5.3.2 is a
   superset fix version).
5. Before opening a PR, check whether `go-chi-v5.3.2-router-upgrade` or
   `chi-redirect-cve-boundary-check` has already been merged or is actively in
   progress; if so, close this proposal as fulfilled/superseded rather than shipping a
   duplicate `go.mod` change. If neither has progressed, this proposal's PR should
   explicitly close out both of those as fulfilled once merged.

## Alternatives
- **Proceed with three independent PRs (this proposal plus the two pre-existing ones)
  all bumping chi to v5.3.2.** Rejected: identical `go.mod`/`go.sum` diff three times
  is pure waste and creates confusing, conflicting proposal state; the reconciliation
  step (task 5 above) is required regardless of which proposal "wins."
- **Defer the Mount()/Route() fix until the CVE-boundary proposals are explicitly
  resolved.** Rejected: the availability risk from a silently dropped handler on the
  AlertManager webhook is independent of and more time-sensitive than the (now
  effectively closed) CVE question; there is no reason to gate one on the other.
- **Only fix the Mount()/Route() collision risk in mctl-agent's own routing code
  (defensive checks) without bumping chi.** Rejected: the bug is inside chi's own
  `Mount()`/`Route()` implementation; an application-level workaround would be fragile
  and duplicate a fix that already exists upstream.

## Platform impact
- **Migrations:** none — dependency version bump only, no data schema changes.
- **Backward compatibility:** v5.3.2 is a minor-version bump within chi v5.x; release
  notes describe only bugfixes and default-content-type additions, no removed APIs.
  mctl-agent's route paths, methods, and response contracts are unchanged.
- **Resource impact:** negligible — router library bump only. Not deployed to `labs`
  (mctl-agent runs only in `admins`), so the `labs` memory-pressure constraint from
  `context/architecture.md` does not apply.
- **Risks and mitigations:**
  - *Risk:* shipping this as a fourth/duplicate proposal alongside
    `go-chi-v5.3.2-router-upgrade` and `chi-redirect-cve-boundary-check` causes
    confusion about which PR is authoritative. *Mitigation:* task 5's explicit
    reconciliation step — whichever proposal's PR merges first closes the other two as
    fulfilled; this is called out in all three proposals' scope, not silently assumed.
  - *Risk:* the new default compressible content types (`text/markdown`, `text/csv`,
    `text/vtt`) or the rejected catch-all compress wildcards change response behavior
    for an existing endpoint that emits one of those content types. *Mitigation:* full
    existing test suite plus a manual content-type audit of REST API responses before
    merge.
