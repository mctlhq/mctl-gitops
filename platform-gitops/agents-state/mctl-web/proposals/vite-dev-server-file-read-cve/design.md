# Design: vite-dev-server-file-read-cve

## Current state
Per `context/architecture.md`, mctl-web's frontend is built with **Nuxt 4.3.1**, which
internally bundles Vite as its dev-server/build-tool dependency (Nuxt does not expose
Vite as a top-level pinned dependency in `context/architecture.md`'s tracked list — it
is transitive). The exact Vite version resolved by Nuxt 4.3.1 has not been confirmed in
this repo's context files or in the researcher's pass; the CVE relevance is explicitly
flagged as "not independently confirmed" in today's inbox.

Separately, `proposals/cloudflare-vite-plugin-cve-fix/` is an already-open proposal
targeting a *different* package, `@cloudflare/vite-plugin` (CVE-2025-59427), which
wraps Vite for Cloudflare Worker dev-server integration — it is not Vite itself and
does not resolve these two CVEs. `proposals/nuxt-security-patch/` is also open,
targeting a Nuxt upgrade to ≥4.5.1 for four unrelated Nuxt-level CVEs; that upgrade may
incidentally bump the bundled Vite version as a side effect, but this has not been
confirmed either.

## Proposed solution
Stage 1 — Verification spike (always executed first):
1. Run `npm ls vite` (or `npm ls --all vite` to see all resolved instances, since Nuxt,
   `@cloudflare/vite-plugin`, and other tooling may each pull their own Vite range)
   against the current `node_modules`/lockfile state, on Nuxt 4.3.1.
2. Compare the resolved version(s) against the fixed-version thresholds for
   CVE-2025-31125 (6.2.4/6.1.3/6.0.13/5.4.16/4.5.11) and CVE-2026-53571
   (8.0.16/7.3.5/6.4.3).
3. Check whether `proposals/nuxt-security-patch/` has already landed; if so, re-run
   `npm ls vite` against the post-upgrade state before proceeding, since that upgrade
   may have already resolved this independently.

Stage 2 — Conditional patch (only if Stage 1 finds an affected, unpatched Vite version):
- If Vite is a direct/overridable transitive dependency, add an `overrides`/
  `resolutions` entry pinning it to the minimum fixed version compatible with the
  installed Nuxt version.
- If Nuxt's own dependency range does not permit a compatible fixed Vite version without
  a Nuxt bump, defer to `proposals/nuxt-security-patch/` (or a follow-on Nuxt bump) as
  the actual remediation path, and document that dependency explicitly rather than
  attempting an incompatible override.
- Run a full `nuxt build` plus a manual dev-server smoke test (attempt to fetch a
  known-sensitive file path like `/@fs/../../.env` from the dev server) to confirm the
  file-read/`server.fs.deny` bypass is closed.

## Alternatives
- **Skip verification and pre-emptively bump/override Vite anyway.** Rejected: the
  researcher explicitly could not confirm the bundled version or exposure; bumping
  blind risks an incompatible Vite version being force-pinned under Nuxt 4.3.1 (Nuxt's
  internal Vite integration is version-sensitive), potentially breaking the dev server
  or build for no confirmed security benefit.
- **Fold this into `nuxt-security-patch`.** Rejected: `nuxt-security-patch`'s scope is
  four specific Nuxt-level CVEs unrelated to Vite's own file-read bugs; conflating them
  would blur two independently-tracked CVE remediation efforts and make it harder to
  verify each is actually closed. Keeping this as a separate spike that explicitly
  checks `nuxt-security-patch`'s outcome avoids duplicate work without merging scopes.
- **Wait indefinitely for `nuxt-security-patch` to land and only then check.** Rejected:
  `nuxt-security-patch` has no committed timeline in this proposal set, and the two Vite
  CVEs (especially CVE-2025-31125, arbitrary file read) are independently serious enough
  to warrant an immediate, cheap verification spike now rather than blocking on an
  unrelated proposal's timeline.

## Platform impact
- **Migrations:** none — dependency-version verification and (if needed) an
  `overrides`/`resolutions` bump only.
- **Backward compatibility:** Stage 1 has zero impact (read-only check). Stage 2, if
  triggered, carries a small risk of Vite/Nuxt internal-integration incompatibility;
  mitigated by testing the full `nuxt build` and dev server smoke test before merging.
- **Resource impact:** mctl-web runs in the `admins` tenant, not `labs` — there is no
  `labs` memory impact from this spike or any conditional patch. Vite is a build/dev-time
  tool; it has no production runtime footprint (the Nuxt app is built to static output
  and served separately, per `context/architecture.md`).
- **Risks and mitigations:**
  - Risk: forcing a Vite version via override that Nuxt 4.3.1 does not officially
    support could break the dev server or production build silently. Mitigation: test
    `nuxt build` and dev server startup explicitly before merging any override; prefer
    deferring to a coordinated Nuxt bump if compatibility is in doubt.
  - Risk: duplicated effort with `nuxt-security-patch` if both proposals independently
    attempt to bump Vite. Mitigation: explicit acceptance criterion requiring a
    re-check against `nuxt-security-patch`'s outcome before doing independent work.
  - Risk: CVE-2026-53571 is Windows-specific (`server.fs.deny` bypass); if all dev/CI
    machines are non-Windows, this specific CVE's practical risk may be lower.
    Mitigation: still confirm the fixed version is used for defense-in-depth, since
    contributor environments may vary.
