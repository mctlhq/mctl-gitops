# Spike: MCTL Web Platform Unification — AMEND (mctlhq/.github#328)

## Amendment authority and status
Owner-directed AMEND, 2026-11-08. This replaces the initial proposal's mandatory cross-framework benchmark, executable reference model and extensive CI scope with **bounded research**. This is **not** an approval or implementation authorization. The existing Temporal DevLoop remains at its human approval gate; do not signal it as part of this AMEND.

## Context
Six sites intentionally have different runtimes: Nuxt 4 generated static site (mctl.ai), Go html/template (tg.mctl.ai), VitePress (docs.mctl.ai), Vue/Vite + Hono (academy.mctl.ai), native Node http (alice.mctl.ai), Fastify (seerrsense.mctl.ai). Concrete cross-surface duplication concerns header behavior, CSS integration and release discipline, not necessarily frameworks.

mctl-design 0.20.2 has a successful Publish and deploy to ui.mctl.ai. Six consumer PRs have been merged: mctl-web#239, mctl-docs#202, mctl-telegram#1245, mctl-academy#437, mctl-alice#172, seerrsense#117. **Merged source does not establish that every production image is serving 0.20.2**. Re-read source, GitOps desired images and ArgoCD observed images; distinguish each. Academy's @mctlhq/ui dependency still uses a caret (^0.20.2) unless #210 has independently resolved that; a bump alone is not exact pinning.

## Research questions — required
1. **Header behavior and accessibility.** Inventory Escape, outside click, focus restoration, keyboard activation/tab order, resize, reduced motion and no-JS behavior on the six surfaces. Define a framework-independent behavior contract. Investigate, but DO NOT implement, a tiny vendorable vanilla-JS module for **script-permitted public** Alice/SeerrSense pages. Keep Vue/VueUse in mctl.ai/Academy and VitePress/Go-specific adaptations where appropriate. Telegram strict OAuth and any no-script consent routes remain JS-free. Do not weaken CSP for a shared header.
2. **Design integrity and route CSP.** Propose an immutable release manifest: exact design semver, pinned source commit, SHA-256 per file, SRI SHA-384, publication provenance, CORS/immutable-cache preconditions for CDN CSS and reproducible local sync/check for vendored CSS (and any later JS). Validate against CSP per public, OAuth/consent/manage/connect/redirect/error route rather than assuming one policy per site. SRI across origins requires crossorigin and valid Access-Control-Allow-Origin. Preserve strict CSP and define rollback/CDN-failure behavior.
3. **Inventory and initial measurements.** Pin full commit SHAs; map runtimes, packages/lockfiles, CSS/JS imports, security boundaries, CI, image building, GitOps desired versions, live ArgoCD versions and rollback. Record a light mctl.ai homepage baseline (transferred/JS bytes and loading metrics) ONLY if reproducibly observable without production load. Otherwise say not-run. Document actual Hono, Fastify and native-http functionality without rewriting it.

## Deferred / conditional questions
- A Nuxt 4 vs Astro experiment requires a real, measured loading/SEO/maintenance problem; first compare keep-Nuxt and optimize-Nuxt, then request separate authorization for an isolated benchmark.
- A Hono vs Fastify/native-http experiment requires a concrete security, resource-use or maintenance issue and proof of OAuth/MCP/SSE/cookie/error-header equivalence; separate authorization required.
- No mandatory framework ports, benchmark harness, stdlib Python reference model, fixtures, synthetic manifest schema, new CI workflow or functional shared site-header.js in this spike.

## User stories
- AS platform owner I WANT a pinned six-surface evidence matrix and small ADR SO THAT I can approve contracts based on facts.
- AS surface maintainer I WANT shared navigation semantics and asset-integrity rules SO THAT regressions and drift can be detected without framework rewrites.
- AS security reviewer I WANT per-route CSP boundaries and explicit CDN/SRI/CORS preconditions SO THAT authentication routes are not weakened for styling.

## Acceptance criteria (EARS)
- WHEN delivered THE SYSTEM SHALL prepare a cited research report in mctlhq/.github at docs/spikes/web-platform-unification.md and a proposed ADR; it MAY add a schema-valid roadmap/spikes/web-platform-unification.yaml with lifecycle proposed, no decision or implementation epic, and an AGENTS.md index entry.
- THE SYSTEM SHALL pin full source SHAs and tag conclusions [CODE], [CONFIG], [LIVE], [DOC] or unknown (not observed), separating GitOps desired and ArgoCD observed deployment state.
- THE SYSTEM SHALL inventory browser-relevant CSP by route, including auth/consent/redirect/error responses; it SHALL NOT infer script permission from style permission.
- THE SYSTEM SHALL describe current header behavior and a testable accessibility/no-JS contract, plus a proposed JS-adapter boundary limited to script-permitted public routes; no code shall be shipped.
- THE SYSTEM SHALL specify version provenance, per-file hashes, CDN SRI/CORS/cache preconditions, local vendoring checks and rollback; existing owners/issues are cited rather than duplicated.
- WHEN performance data is unavailable or irreproducible THE SYSTEM SHALL mark it not-run; no framework migration recommendation shall rely on unmeasured benefits.
- THE SYSTEM SHALL deliver ADR status PROPOSED / RESEARCH ONLY with tradeoffs, gaps, explicit follow-up triggers and a human owner decision gate.
- IF SpikeDefinition is added THEN \`python roadmap/scripts/validate.py roadmap/epics roadmap/spikes\` SHALL pass and outcomes SHALL remain the five canonical #328 outcomes.
- THE SYSTEM SHALL NOT change surface apps, mctl-design, GitOps service values, production, auth/CSP, release tags or portfolio; SHALL NOT approve, merge, start an implementer or automatically authorize a later pilot.

## Out of scope / decision gate
No production modifications, framework migration, shared JS implementation, new implementation epic, benchmark harness or reference model/CI suite, secrets or production auth/load testing. Existing design and consumer release work is an independent gate. Portfolio is comparison-only.

Owner chooses from:
STANDARDIZE_CONTRACTS_KEEP_RUNTIMES | PILOT_SHARED_ADAPTERS | TARGETED_MIGRATION_AFTER_BENCHMARK | DEFER_UNTIL_BASELINES | NO_ADOPTION.
The favored retain-runtime option is a **hypothesis**, not an accepted decision. Separate explicit owner approval is required for any implementation.