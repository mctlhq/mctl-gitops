# Design: AMEND #328 — bounded web-platform research

## Governance
**AMENDED PROPOSAL — PROPOSED / RESEARCH ONLY. NOT APPROVED.**
This design supersedes the investigator's broad, mandatory framework benchmarks, Python reference model, schema/fixtures suite and CI wiring. Change the proposal through a reviewed mctl-gitops PR, never by changing \`.status.yaml\`, signalling Temporal approval, or starting the implementer. Source of truth: [mctlhq/.github#328](https://github.com/mctlhq/.github/issues/328), with its canonical Source key and five outcomes. Do not bind to completed \`roadmap/epics/surfaces.yaml\` (WorkItem UX, unrelated).

## Evidence at AMEND time — must be rechecked
- [mctl-design#206](https://github.com/mctlhq/mctl-design/pull/206): merge 7e1fbb0, tag 0.20.2; Publish and Deploy to ui.mctl.ai workflows succeeded. Live mctl-design ArgoCD Healthy/Synced with image 7e1fbb0634d5, and current mctl-gitops design values now pin that image (old alleged 75e6e4a27179 drift has been resolved).
- All six 0.20.2 consumer PRs are merged: mctl-web#239, mctl-docs#202, mctl-telegram#1245, mctl-academy#437, mctl-alice#172, seerrsense#117. A merge is not evidence of the new production consumer image or of effective browser CDN response headers.
- Academy package range \`^0.20.2\` is not an exact version; track exact-pinning through academy#210.
- Current architecture: mctl.ai = Nuxt 4 generate; tg = Go net/http + html/template, public CDN vs strict lite OAuth; docs = VitePress; academy = Vue/Vite + Hono; alice = native Node HTTP with locally vendored CSS; seerrsense = Fastify with locally vendored CSS and strict consent routes. Verify route-specific CSP from actual source and observed responses. CSS permission never implies script permission.

## Small, reviewable research package
Deliver a **single research report** at \`mctlhq/.github/docs/spikes/web-platform-unification.md\`, containing a proposed ADR. Optionally add one \`roadmap/spikes/web-platform-unification.yaml\` (lifecycle proposed, issue binding #328, no decision), and index in AGENTS.md. No reference-model code, fixtures, extra schemas, benchmark harness, new CI workflow, design/package/application changes or GitOps service values.

### D0 — Evidence discipline
Pin 40-hex main SHAs for the six surface repos, mctl-design and mctl-gitops. Tag each statement [CODE], [CONFIG], [LIVE], [DOC], or \`unknown (not observed)\`; link precise files or read-only observations. Distinguish published design assets, consumer source, desired GitOps image and observed runtime. Effective headers that cannot be checked remain unknown.

### D1 — Surface inventory
Build a six-row matrix covering rendering/runtime, dependency pins/lockfiles, mctl-design CSS/JS mode, public vs auth/consent/connect/manage/redirect/error CSP, scripts and no-JS behavior, CI/security tests, packaging, GitOps desired image, ArgoCD observed image, release status and rollback. No live secrets, auth traffic or load tests.

### D2 — Shared header behavior (not common JS everywhere)
Evaluate responsive nav semantics:
- open/close by keyboard, Escape, outside click;
- focus restoration, tab order, aria-expanded/controls and announcements;
- resizing between mobile/desktop, reduced motion, no-JS fallback.
Compare existing Nuxt/VueUse, Academy Vue, VitePress, Alice and SeerrSense vanilla JS, Telegram Go/CSS-only lite. Specify one behavior/a11y contract and acceptance table for all. A tiny, locally vendored, checksummed \`site-header.js\` is **only a potential future pilot** for **script-permitted public** Alice/SeerrSense routes. Keep Vue-specific implementations where cheaper and preserve script-free strict Telegram OAuth and strict consent pages. Do not implement the module or relax CSP.

### D3 — CSS delivery, SRI/CORS and supply chain
Define a **proposed** immutable manifest with exact \`designVersion\`, source 40-hex SHA, release provenance, per-file SHA-256, optional SRI SHA-384 and byte sizes, CDN versioned path and immutable cache header expectations, and local-vendor sync/check. For cross-origin stylesheets document \`integrity\`, compatible \`crossorigin\`, and response \`Access-Control-Allow-Origin\`; missing CORS can break SRI loading. Define per-route allowed mode (CDN or locally vendored), cache failure/rollback, no silent stylesheet/script origins added to strict CSP. Map owners to design#34/#78, telegram#599, academy#210 and gitops#500. All examples are proposals, not executable code shipped.

### D4 — Deployment and optional light baseline
Document build and rollback per site, pin actual CI, compare config with read-only ArgoCD. For mctl.ai homepage, report total bytes, JS bytes and timing metrics if reproducibly observed with source SHA and device/network methodology; otherwise \`not-run\`. Record the real constraints of Academy Hono + Better Auth, SeerrSense Fastify (cookies, rate-limit, static/hooks, MCP/OAuth) and Alice native http, rather than porting or microbenchmarking toy servers. Capture a trigger for any later research, not a framework verdict now.

### D5 — Proposed ADR: Federated Web Platform
Status **PROPOSED / RESEARCH ONLY**.
- A: keep existing runtimes; standardize header semantics, a11y tests and immutable assets (preferred research hypothesis).
- B: later pilot a shared narrow adapter on script-permitted public routes after separately approved issue.
- C: defer changes if evidence/CSP/live-version baselines are incomplete.
- D: commission targeted Nuxt-v-Astro or Hono-v-Fastify experiment only on measured performance/security/maintenance pain, with keep+optimize current baseline and security equivalence.
List advantages, costs, risks, route CSP protections, stakeholders, ownership, reversibility and quantitative revisit *triggers*, not unexecuted benchmark results. Owner explicitly selects one of the five issue Outcomes after review.

R0: evidence/live release inventory → R1: header and integrity/security contracts → R2: separately authorized tiny pilot proposal → R3: conditional framework benchmark if triggered → R4: human decision/ADR → R5: independently approved implementation issues, PRs and rollout. Portfolio remains comparison reference, never edited.

## Validation and non-goals
- Report is cited, reproducible where possible, and labels all unknown/not-run findings.
- An optional SpikeDefinition passes \`python roadmap/scripts/validate.py roadmap/epics roadmap/spikes\`, remains proposed and has no decision or epic.
- No Python model, SRI code shipping, JS publishing, migration, browser CI, GitOps values edit or cross-repo changes.
- No approval, merge, releases, DevLoop implementation, production auth or load testing.
- This AMEND PR is reversible by closing or reverting; proposal \`.status.yaml\` must remain \`proposed\`.
