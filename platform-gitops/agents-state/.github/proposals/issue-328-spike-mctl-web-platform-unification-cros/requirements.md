# Spike: MCTL Web Platform Unification - cross-surface contracts, CSS/CSP, framework evaluation (mctlhq/.github#328)

## Context
Issue #328 asks a research question: which UI, dependency, CSP, CI and deployment contracts
should be standardized across six MCTL web surfaces (mctl.ai, tg.mctl.ai, docs.mctl.ai,
academy.mctl.ai, alice.mctl.ai, seerrsense.mctl.ai), and whether a measured Nuxt-to-Astro or
Fastify/native-HTTP-to-Hono migration would beat keeping the present runtimes. The allowed
outcomes are `STANDARDIZE_CONTRACTS_KEEP_RUNTIMES | PILOT_SHARED_ADAPTERS |
TARGETED_MIGRATION_AFTER_BENCHMARK | DEFER_UNTIL_BASELINES | NO_ADOPTION`. The suggested
verdict, which nobody has accepted, is `STANDARDIZE_CONTRACTS_KEEP_RUNTIMES`.

The surfaces share design assets from ui.mctl.ai (`mctlhq/mctl-design`), but their rendering
stacks and CSP boundaries differ on purpose. The issue reports drift: consumers pinned to
0.20.1 while mctl-design main is at 0.20.2, a caret range in Academy (#210), and uneven CI
(gitops#500). Like the earlier spikes in this repo (`docs/spikes/finance-assistant.md`,
`docs/spikes/automation-control-plane.md`), this one ships a research package in
`mctlhq/.github` only: a report, a `SpikeDefinition` manifest that stays `lifecycle: proposed`,
and a stdlib reference model with tests. No surface repository, GitOps value or deployment
changes.

## User stories
- AS the platform owner I WANT an evidence-pinned 6-by-N architecture matrix with explicit unknowns SO THAT I can decide on unification from facts, not from remembered configuration.
- AS the platform owner I WANT quantitative decision thresholds for Nuxt-vs-Astro and Hono-vs-Fastify-vs-native-http SO THAT a migration is only proposed when its measured gain exceeds its migration, operational and security cost.
- AS a surface maintainer (web, telegram, docs, academy, alice, seerrsense) I WANT a design-artifact manifest contract (exact version, per-file SHA-256, provenance, CDN mode and vendored mode) SO THAT I can detect token/CSS drift in CI without widening my CSP.
- AS a security reviewer I WANT a per-route CSP and asset supply-chain threat model that covers auth, OAuth consent and error routes SO THAT strict-CSP pages are never loosened for convenience.
- AS a later implementer I WANT a dedup map and a staged plan (R0-R5) that point at existing owned issues SO THAT follow-up work does not duplicate mctl-design#34/#78, mctl-telegram#599, mctl-academy#210 or mctl-gitops#500.

## Acceptance criteria (EARS)
- WHEN the research package is delivered THE SYSTEM SHALL add `docs/spikes/web-platform-unification.md`, `roadmap/spikes/web-platform-unification.yaml` and a reference model under `docs/spikes/web-platform-unification/`, and nothing outside `docs/`, `roadmap/spikes/`, `AGENTS.md` and `.github/workflows/workflow-tests.yml`.
- WHEN the SpikeDefinition is validated with `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` THE SYSTEM SHALL pass, with `lifecycle: proposed`, `github.issue` = `mctlhq/.github#328`, the five outcomes from the issue, `evidence.report` pointing at the report, and no `decision` block.
- THE SYSTEM SHALL list in the report, for each of the six surfaces, the repository and a 40-hex commit pin, and SHALL tag every matrix cell `[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]`, `[PRIMARY]`, `[MODEL]` or `unknown (not observed)`.
- IF a source or live read was unavailable THEN THE SYSTEM SHALL record the cell as `unknown (not observed)` and SHALL NOT treat it as absent, off or passed.
- THE SYSTEM SHALL keep GitOps intended state (`[CONFIG]`) and ArgoCD-observed state (`[LIVE]`) in separate columns, and SHALL report any difference between them (for example the mctl-design image tag) as a finding.
- WHEN the report describes CSP THE SYSTEM SHALL give a per-route CSP map for each surface that covers public pages, auth/OAuth/consent routes, redirects and error responses, plus the CSS delivery mode each route allows (`cdn` or `vendored`).
- WHILE a route is classified strict (`default-src 'none'` or `style-src 'self'` without ui.mctl.ai) THE SYSTEM SHALL require the vendored delivery mode, and the reference model SHALL reject any proposed manifest or adapter that would add a CDN origin to that route's `style-src` or `default-src`.
- WHEN the reference model validates a design-artifact manifest THE SYSTEM SHALL require an exact semver version (no `^`, `~` or range), a SHA-256 for every file, a source commit and a publication provenance reference, and SHALL report drift when a consumer's vendored or pinned files do not hash to the manifest.
- IF a manifest declares CDN mode with SRI THEN THE SYSTEM SHALL require the manifest to state the CORS precondition (`Access-Control-Allow-Origin` on the CDN response) and the immutable cache precondition.
- WHEN the framework comparison is reported THE SYSTEM SHALL include keep-current and optimize-current baselines for each comparison (Nuxt 4 keep and optimize vs Astro; Hono vs Fastify vs native http) and SHALL use the existing prerendered mctl.ai routes and the real Academy/SeerrSense/Alice API behavior as workloads.
- IF a benchmark was not executed reproducibly from pinned sources THEN THE SYSTEM SHALL mark its result `not-run` and SHALL NOT use it to support a migration outcome.
- WHEN the reference model evaluates the decision thresholds THE SYSTEM SHALL return `TARGETED_MIGRATION_AFTER_BENCHMARK` only if the measured gain exceeds every declared threshold and security equivalence is `proven`; otherwise it SHALL return a non-migration outcome.
- THE SYSTEM SHALL include a proposed ADR marked PROPOSED, RESEARCH ONLY, with options A-E, risks, quantitative thresholds and revisit triggers, and SHALL state that the verdict belongs to the owner.
- THE SYSTEM SHALL include an adapter contract proposal covering @mctlhq/ui Vue components, plain-HTML semantics and Go html/template chrome, and SHALL exclude shared auth, session or business middleware.
- THE SYSTEM SHALL include a cross-surface UI/security acceptance matrix (Playwright visual and a11y, token/contrast/theme, CDN outage, no-JS, per-route CSP, immutable cache and integrity, preview evidence) that references mctl-design CI and mctl-gitops#500 rather than redefining them.
- WHEN the workflow-tests CI runs on changes to `docs/spikes/web-platform-unification/**` THE SYSTEM SHALL run `python3 -I -m unittest discover -s docs/spikes/web-platform-unification/tests -v` and pass.
- THE SYSTEM SHALL NOT change any surface repository, mctl-design (including PR #206), GitOps values, CSP header, package version or deployment, and SHALL NOT record an owner decision.

## Out of scope
- Any code, dependency bump, package publish, CSP relaxation or framework migration in mctl-web, mctl-telegram, mctl-docs, mctl-academy, mctl-alice, seerrsense or mctl-design.
- Gating, reviewing or approving mctl-design PR #206.
- Edits to mctl-gitops, deployments, secret reads, production auth tests.
- Changes to portfolio; it is a comparison reference only.
- Creating an implementation epic or follow-up implementation issues. That happens only after the owner accepts a verdict (stage R4).
- Binding this spike to the completed `roadmap/epics/surfaces.yaml` epic. That epic covers WorkItem/agent UX, not web architecture.
- Live load or performance tests against production hosts.

## Open questions
- Benchmark execution environment: a reproducible Nuxt/Astro and Hono/Fastify/native-http benchmark needs the six repositories built from pinned SHAs (and Lighthouse/Playwright for LCP/INP/CLS). The investigator's sandbox is read-only and cannot build them. The plan delivers a benchmark harness and protocol, records results as `not-run` until they are executed in CI or an isolated preview, and does not use unexecuted results to support a migration.
- Live state: GitOps pins mctl-design to image tag `75e6e4a27179`, while ArgoCD reports `7e1fbb0634d5` running with Synced status. Either the gitops checkout is stale or the state drifted. The report must re-read both before relying on either.
- mctl-telegram shows two images live (`0.136.0` and `0.137.0`) under `strategy: Recreate`. This may be a rollout in progress or a second container or job. Not resolved here.
- Which effective CSP headers reach browsers: the CSP figures in the issue come from source config (nginx.conf, headers.go, security-headers.mjs, routes.ts). Ingress or Cloudflare may add or rewrite headers. Live header observation needs a permissioned read-only fetch, and the cell stays `unknown (not observed)` if that fetch is not allowed.
- Decision thresholds: the issue asks for quantitative thresholds but does not give values. The design proposes defaults (see design.md) for the owner to adjust.
- The issue states the 0.20.2 version from mctl-design main. Whether a 0.20.2 CDN release is published was not observed.
