# Verify and patch Vite dev-server file-exposure CVEs bundled via Nuxt

## Context
Two Vite CVEs were surfaced in research: CVE-2025-31125 (arbitrary file read via the
Vite dev server, fixed in 6.2.4/6.1.3/6.0.13/5.4.16/4.5.11) and CVE-2026-53571
(`server.fs.deny` bypass on Windows, fixed in 8.0.16/7.3.5/6.4.3). Both affect the Vite
build tool that Nuxt bundles internally for its dev/build pipeline. `context/architecture.md`
pins Nuxt at 4.3.1 but does not record which Vite version that Nuxt version bundles, so
relevance to mctl-web is **not yet confirmed** — this proposal starts as a verification
spike, not a committed patch.

This is a different package and different CVE from the already-open
`proposals/cloudflare-vite-plugin-cve-fix/`, which targets `@cloudflare/vite-plugin`
(CVE-2025-59427) — a separate npm package that wraps Vite for Cloudflare Worker
integration, not Vite itself. The two proposals should not be conflated or merged.

There is also a related in-flight proposal, `proposals/nuxt-security-patch/`, which
upgrades Nuxt to ≥4.5.1 for unrelated CVEs. If that upgrade lands first, it may already
bump the bundled Vite version past the affected range for CVE-2025-31125 and/or
CVE-2026-53571 as a side effect, in which case this proposal's spike should re-check
before doing any independent Vite-specific work.

## User stories
- AS a developer running the local Nuxt dev server I WANT confirmation of whether the
  bundled Vite version is exposed to CVE-2025-31125 or CVE-2026-53571 SO THAT I know
  whether my dev environment can leak arbitrary files (including `.env`/`.dev.vars`
  secrets) to any client with network access to the dev port.
- AS a security engineer I WANT the bundled Vite version confirmed and, if affected,
  patched SO THAT dependency audits report zero known vulnerabilities for the Vite
  build tool used by our Nuxt pipeline.
- AS a service owner I WANT to avoid duplicate work SO THAT this spike does not
  reinvent what `nuxt-security-patch` or `cloudflare-vite-plugin-cve-fix` already cover.

## Acceptance criteria (EARS)
- WHEN the verification spike is run (`npm ls vite` against the current Nuxt 4.3.1
  install) THE SYSTEM SHALL report the exact resolved Vite version bundled by Nuxt.
- IF the resolved Vite version falls within the affected range for CVE-2025-31125
  and/or CVE-2026-53571 THEN THE SYSTEM SHALL produce a patch plan (dependency bump
  and/or override) to move Vite to a fixed version.
- IF the resolved Vite version is already at or above the fixed version for both CVEs
  THEN THE SYSTEM SHALL close this proposal as "not applicable" with the confirmed
  version recorded, and make no dependency change.
- WHEN `proposals/nuxt-security-patch/` lands before this spike is executed THEN THE
  SYSTEM SHALL re-run `npm ls vite` against the post-upgrade Nuxt version before
  deciding whether independent Vite work is still needed.
- WHEN a patch (if needed) is applied THE SYSTEM SHALL run a full `nuxt build` and dev
  server smoke test to confirm no regression.
- WHILE the spike/patch is in progress THE SYSTEM SHALL NOT modify `@cloudflare/vite-plugin`
  version or configuration — that is the separate, already-open
  `cloudflare-vite-plugin-cve-fix` proposal's scope.

## Out of scope
- Any change to `@cloudflare/vite-plugin` — owned by `proposals/cloudflare-vite-plugin-cve-fix/`.
- Broader Nuxt version upgrade decisions unrelated to the Vite CVEs — owned by
  `proposals/nuxt-security-patch/` and the various `nuxt-upgrade-*`/`nuxt-minor-upgrade-*`
  proposals.
- The `vite-svg-loader`/`svgo` Billion-Laughs DoS fix — a separate package and CVE,
  tracked in `proposals/svgo-billion-laughs-dos/`.
- Production runtime changes — Vite is a build/dev-time tool for this project (Nuxt
  builds to static output served separately); this proposal only concerns the
  build/dev pipeline's dependency version.
