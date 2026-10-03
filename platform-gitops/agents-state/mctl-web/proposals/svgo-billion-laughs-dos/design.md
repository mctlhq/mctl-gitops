# Design: svgo-billion-laughs-dos

## Current state
Per `context/architecture.md`, the Nuxt frontend build pins `sass 1.98.0` and
`vite-svg-loader 5.1.1`. `vite-svg-loader` uses `svgo` internally to optimize SVG
imports at build/dev time. The current pinned `vite-svg-loader` version resolves a
transitive `svgo` version that is affected by GHSA-xpqw-6gx7-v673 / CVE-2026-29074, a
Billion-Laughs XML entity-expansion DoS in svgo's parser. There is no existing
open proposal covering this package (distinct from `proposals/cloudflare-vite-plugin-cve-fix/`,
which targets `@cloudflare/vite-plugin`, and from `proposals/vite-dev-server-file-read-cve/`,
which targets Vite core).

## Proposed solution
1. Confirm the exact `svgo` version currently resolved via the lockfile (`npm ls svgo`).
2. Identify the minimum `svgo` version with the entity-expansion fix, and the minimum
   `vite-svg-loader` version that resolves to that fixed `svgo` version.
3. Bump `vite-svg-loader` in `package.json` to that minimum fixed version (staying
   within the same major line if possible, to avoid unrelated breaking changes to the
   SVG-loader API/options).
4. If `vite-svg-loader`'s own release cadence lags the `svgo` fix, add a direct
   `overrides`/`resolutions` entry pinning `svgo` to the fixed version as a stop-gap,
   with a follow-up task to remove the override once `vite-svg-loader` catches up
   upstream.
5. Re-run the full build (`nuxt build`) against all existing repo SVG assets to confirm
   no regression in SVG optimization output.
6. Add (or confirm existing) SCA/dependency-audit CI coverage flags `svgo` if it
   regresses below the fixed version in the future.

This is the minimal-diff approach: a version bump plus, if needed, a targeted
override — no change to how SVGs are imported or which loader is used.

## Alternatives
- **Replace `vite-svg-loader` with a different SVG-handling library entirely.**
  Rejected: much higher effort and blast radius for a build-time-only DoS that has a
  simple version-bump fix available; not proportionate to the risk.
- **Disable svgo optimization entirely (pass-through raw SVGs).** Rejected: removes the
  vulnerable code path but also removes SVG minification/optimization benefits and
  still leaves consumers of `vite-svg-loader` on a known-vulnerable transitive
  dependency in their lockfile, which would still fail SCA scans.
- **Do nothing / accept the risk.** Rejected: the fix is low-effort (Effort: 1 per
  analyst rating) and the SCA/audit tooling will keep flagging it; even though the
  exploitable surface is limited to build/dev time, an untrusted SVG (e.g. via a
  malicious PR) is a plausible vector for CI worker DoS.

## Platform impact
- **Migrations:** none — this is a `package.json`/lockfile version bump, no data or
  schema migration involved.
- **Backward compatibility:** low risk; `vite-svg-loader` patch/minor bumps are
  expected to preserve the existing `?component` / `?url` import API used in Nuxt
  pages. Full `nuxt build` re-run is the acceptance gate for any regression.
- **Resource impact:** mctl-web runs in the `admins` tenant, not `labs` — there is no
  `labs` memory impact from this change. This is a dev/CI-time dependency bump with no
  runtime (production request-serving) footprint at all.
- **Risks and mitigations:**
  - Risk: `vite-svg-loader` major bump forces incompatible peer dependencies (e.g. a
    newer Vite requirement). Mitigation: prefer the smallest version bump that resolves
    the fixed `svgo`, and use an `overrides` stop-gap instead of a major bump if needed.
  - Risk: SVG optimization output changes slightly (different minified SVG bytes),
    causing visual diffs. Mitigation: manual visual check of the small, fixed set of
    SVG assets in the repo after the bump, before merging.
