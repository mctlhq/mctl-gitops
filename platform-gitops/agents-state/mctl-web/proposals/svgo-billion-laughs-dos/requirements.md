# Patch vite-svg-loader/svgo Billion-Laughs XML entity-expansion DoS (CVE-2026-29074)

## Context
`context/architecture.md` pins `vite-svg-loader 5.1.1` as a build-time dependency of the
Nuxt frontend. This package pulls in `svgo` transitively to optimize SVG assets during
build/dev. GHSA-xpqw-6gx7-v673 / CVE-2026-29074 describes a high-severity "Billion
Laughs" XML entity-expansion denial-of-service in svgo's SVG/XML parser: a crafted SVG
file containing deeply nested entity references can cause unbounded memory/CPU
consumption when parsed.

Because svgo only runs at build/dev time (processing SVG assets checked into the repo or
imported by developers), the exploitable surface is narrower than a runtime,
user-facing vulnerability — but it is still a real risk for CI build workers and local
dev machines if an SVG from an untrusted source (e.g. a third-party icon pack, a
community PR, or a copy-pasted asset) is ever added to the repo and processed by the
build pipeline. The fix is a low-effort version bump of `vite-svg-loader` (and/or a
direct override of its transitive `svgo` dependency) to a version that has patched the
entity-expansion issue.

## User stories
- AS a developer building or running dev mode for mctl-web I WANT the SVG build pipeline
  to reject or safely bound maliciously crafted SVG entity expansion SO THAT a bad SVG
  asset cannot hang or crash my build/dev process.
- AS a security engineer I WANT `vite-svg-loader`/`svgo` pinned to a version with
  CVE-2026-29074 fixed SO THAT dependency audits report zero known vulnerabilities for
  this package pair.
- AS a CI operator I WANT the build pipeline to remain stable and fast SO THAT a
  crafted SVG committed by mistake (or via a malicious PR) cannot exhaust CI worker
  resources.

## Acceptance criteria (EARS)
- WHEN `vite-svg-loader` is upgraded to a version whose resolved `svgo` transitive
  dependency has CVE-2026-29074 fixed THE SYSTEM SHALL build successfully with all
  existing SVG assets in the repo.
- WHEN `npm audit` (or the project's equivalent SCA tool) is run after the upgrade THE
  SYSTEM SHALL report zero known vulnerabilities for `svgo` and `vite-svg-loader`.
- IF the resolved `svgo` version in `node_modules`/lockfile is below the fixed version
  THEN THE SYSTEM SHALL fail the dependency-audit CI step with a descriptive error.
- WHEN an SVG file containing a deeply nested XML entity-expansion payload is processed
  by the build pipeline after the upgrade THE SYSTEM SHALL reject or safely bound
  parsing without unbounded memory/CPU growth.
- WHILE the upgrade is in progress THE SYSTEM SHALL keep all other pinned frontend
  dependencies (Nuxt, Vue, vue-router, vee-validate, yup, @vueuse/core, sass) unchanged
  unless the `vite-svg-loader` bump forces a peer dependency update.

## Out of scope
- Any change to runtime (production request-serving) code paths — this is a build/dev-time
  dependency fix only.
- Broader SVG-handling architecture changes (e.g. switching away from `vite-svg-loader`).
- The unrelated `@cloudflare/vite-plugin` CVE-2025-59427 fix, already tracked separately
  in `proposals/cloudflare-vite-plugin-cve-fix/`.
- The unrelated Vite dev-server file-read CVEs, tracked separately in
  `proposals/vite-dev-server-file-read-cve/`.
