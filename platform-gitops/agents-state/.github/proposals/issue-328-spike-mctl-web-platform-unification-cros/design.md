# Design: issue-328-spike-mctl-web-platform-unification-cros

## Current state

### This repository (`mctlhq/.github`, HEAD `b70a753`, "Merge PR #327")
- Spikes are research packages. A report goes in `docs/spikes/<name>.md`, an optional
  reference model in `docs/spikes/<name>/`, and a manifest in `roadmap/spikes/<name>.yaml`.
  Recent examples are `docs/spikes/finance-assistant.md` (stdlib Python model at
  `docs/spikes/finance-assistant/model.py` with `tests/test_finance.py`, fixtures and a
  `baseline/`) and `docs/spikes/automation-control-plane/` (Go model plus benchmarks).
- `roadmap/schemas/spike-definition.schema.json` defines `SpikeDefinition v1alpha1`:
  required `title`, `question`, `lifecycle`, `github.issue`, `outcomes` (pattern `^[A-Z][A-Z0-9_]*$`,
  at least 2). An optional `evidence.report` and `execution.devloop` are allowed, and a
  `decision` block may appear only when `lifecycle: decided` (`allOf` rule).
  `roadmap/spikes/finance-assistant.yaml` is the decided-shape example. This spike stays
  `proposed`.
- `roadmap/scripts/validate.py` (run by `.github/workflows/roadmap-validate.yml`) enforces
  schema and cross-kind invariants: unique spike names and unique issue bindings, and a spike
  issue cannot be an epic root. Tests are in `roadmap/tests/test_validate_spike.py`.
- `.github/workflows/workflow-tests.yml` lists each spike model path under `paths:` (lines
  11-35) and runs its tests. For example `python3 -I -m unittest discover -s
  docs/spikes/finance-assistant/tests -v` (line 59).
- `AGENTS.md` keeps a `# Spikes` index, and its "Spike issue creation rules" govern
  `.github/ISSUE_TEMPLATE/spike.yml`. The template body needs `Source / Question / Outcomes /
  Lifecycle / Related / Why mctl` and the labels `spike:scout` and `agents:intake`. Issue #328's
  body has all of these fields.
- Report conventions reused from `docs/spikes/finance-assistant.md`: section D0 lists
  non-claims and evidence tags (`[CODE] [CONFIG] [LIVE] [DOC] [PRIMARY] [MODEL]`,
  `unknown (not observed)`), an evidence ladder L0-L4, and a 40-hex pin table.
- `roadmap/epics/surfaces.yaml` ("Cross-surface working context and agentic UX") covers
  WorkItem/surface identity, not web architecture. The issue says not to bind to it, and this
  design does not.

### The six surfaces (source claims come from the issue and are re-verified in task 1)
The rendering, CSS and CSP facts in the issue's baseline table refer to files in other
repositories (`mctl-web/nuxt.config.ts`, `mctl-telegram/internal/web/headers.go`,
`mctl-academy/server/middleware/security-headers.mjs`, `seerrsense/src/auth/routes.ts`, and
others). Those repositories are not in this clone. They are treated as `[DOC]` claims until
task 1 pins and reads them.

Deployed state checked:
- `mctl_list_services(team=admins)`: ArgoCD reachable, `complete: true`. `mctl-web` runs image
  `7.21.0` on hosts `mctl.ai` and `mctl.ru`, port 80. `mctl-docs` runs `0.1.65` on `docs.mctl.ai`
  and `admins-mctl-docs.mctl.ai`, port 80. `mctl-design` runs `7e1fbb0634d5` on `ui.mctl.ai`,
  port 80. All three are Synced.
- `mctl_list_services(team=labs)`: `mctl-telegram` lists images `0.136.0` and `0.137.0` on
  `tg.mctl.ai` (port 8080, DB). `mctl-academy` runs `0.1.75` on `academy.mctl.ai` (8080, DB).
  `mctl-alice` runs `2.13.0` on `alice.mctl.ai` (8080, DB). `seerrsense` runs `1.14.0` on
  `seerrsense.mctl.ai` (8787, DB). `portfolio` runs `0.1.56` and stays out of migration scope.
  All are Synced.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-web/values.yaml`: tag `7.21.0`, hosts `mctl.ru`
  and `mctl.ai`. `catalog-info.yaml` source-repo is `mctlhq/mctl-web`.
- `services/admins/mctl-docs/values.yaml`: tag `0.1.65`. Source-repo is `mctlhq/mctl-docs`.
- `services/admins/mctl-design/values.yaml`: tag `75e6e4a27179`, which **differs** from the
  ArgoCD-reported `7e1fbb0634d5`. Recorded as an open question, not resolved.
- `services/labs/mctl-telegram/values.yaml`: tag `0.137.0`, `strategy.type: Recreate`
  ("MTProto auth keys must never be opened by overlapping pods"), hosts `tg.mctl.ai` and
  `labs-mctl-telegram.mctl.ai`.
- `services/labs/mctl-academy/values.yaml`: tag `0.1.75`, hosts `academy.mctl.ai` and
  `labs-mctl-academy.mctl.ai`.
- `services/labs/mctl-alice/values.yaml`: tag `2.13.0`, `replicaCount: 1`,
  `strategy.type: RollingUpdate`, host `alice.mctl.ai`.
- `services/labs/seerrsense/values.yaml`: tag `1.14.0`, hosts `seerrsense.mctl.ai` and
  `labs-seerrsense.mctl.ai`.
- No values file sets a CSP. A grep for `csp` or `content-security` in the six values files
  returned nothing, so CSP is set in application or nginx config, not in chart values. Whether
  ingress or Cloudflare rewrites headers was **not observed**.
- Not observed: effective response headers, the CSS versions consumers actually load at
  runtime, and whether a 0.20.2 CDN release is published.

## Proposed solution

Deliver a research-only package in `mctlhq/.github`, following the structure of the
finance-assistant and automation-control-plane spikes. It implements nothing in any surface.

### 1. Report `docs/spikes/web-platform-unification.md`
Sections:
- **D0 Non-claims, evidence tags, evidence ladder.** L0 is pinned source/config. L1 is the
  synthetic `[MODEL]`. L2 is benchmark runs from pinned builds. L3 is isolated preview. L4 is
  production. Anything above L1 that was not executed is `not-run`.
- **Evidence pins.** A 40-hex `main` SHA for each of the seven repositories (six surfaces plus
  mctl-design) and for mctl-gitops, with the files read.
- **D1 6-by-N architecture matrix.** Rows are the six surfaces. Columns cover route rendering,
  lockfile, UI imports and version spec (exact or caret), CSS/fonts/themes source, auth/session,
  CSP per path, analytics (umami at stats.mctl.ai, if present), security headers, security
  tests, CI workflows, image build, GitOps intended tag `[CONFIG]`, ArgoCD-observed tag
  `[LIVE]`, and rollout/rollback strategy. The deployed-state findings above go in as `[LIVE]`
  and `[CONFIG]` cells, including the mctl-design tag drift and the dual mctl-telegram images.
- **D2 Per-route CSP and asset supply-chain threat model.** For each surface there is a route
  table: path class (public, auth/OAuth, consent, manage/connect, error, redirect), the
  effective CSP directive set, the allowed CSS delivery mode, and the threats (CDN compromise,
  version swap, cache poisoning, missing CORS breaking SRI, CSP widening, inline style
  injection). The mitigation for each is either the manifest or vendored mode.
- **D3 Design-artifact manifest contract.** A JSON Schema is shipped in the model directory.
  Fields: `designVersion` (exact semver), `sourceCommit` (40-hex), `published` (provenance:
  registry or CDN URL, release ref), `files[]` (`path`, `sha256`, `bytes`, `sri` as sha384),
  `delivery.cdn` (base URL, immutable cache-control precondition, CORS precondition) and
  `delivery.vendored` (sync script contract matching the existing `sync-tokens` and
  `check:tokens` pattern in alice and seerrsense). Release is append-only and versioned.
  Rollback means re-pinning a previous exact version. A CI drift check compares the consumer's
  vendored or pinned files against the manifest hashes.
- **D4 Adapter contracts.** There are three narrow adapters: `@mctlhq/ui` Vue components
  (mctl-web, academy); plain-HTML class/semantic contract (docs, alice, seerrsense); and Go
  `html/template` chrome (telegram). They share tokens, typography, layout, a11y landmarks,
  responsive header and theme. They explicitly do **not** share auth, session, CSRF or business
  middleware.
- **D5 Framework economics.** Two comparisons, each with keep and optimize baselines.
  (a) Nuxt 4 generate (keep), Nuxt 4 optimized (payload and hydration trimming), and an Astro
  port of N real prerendered mctl.ai routes. Metrics: HTML/JS bytes, LCP/INP/CLS (lab,
  Lighthouse/Playwright), axe a11y, canonical/SEO parity, form behavior, image size, and
  migration effort in engineer-days.
  (b) Hono (Academy), Fastify (SeerrSense auth/MCP) and native http (Alice OAuth/MCP).
  Criteria: middleware/plugins, route typing, error semantics, cookie/CSRF/CORS, security
  headers on 3xx/4xx/5xx, SSE/streaming, observability, RSS/CPU at fixed RPS, testability, and
  the security-equivalence checklist for a port. The harness and protocol are committed. Results
  stay `not-run` until executed from pinned builds.
- **D6 Acceptance matrix.** Playwright visual and axe, token/contrast/theme, CDN outage (block
  ui.mctl.ai) and no-JS render, per-route CSP assertions, immutable cache and SRI checks, and
  preview release evidence. Each row is mapped to an existing owner: mctl-design CI (#34),
  Telegram fallback (#78), gitops#500 CI minimum.
- **D7 Proposed ADR (PROPOSED, RESEARCH ONLY).** Options A-E from the issue, with proposed
  quantitative thresholds for the owner to adjust:
  - migrate a site from Nuxt only if p75 lab LCP improves by at least 20% **and** JS bytes on
    real routes fall by at least 40% compared with the *optimized-Nuxt* baseline, with zero a11y,
    SEO or canonical regressions, and an estimated migration of at most 10 engineer-days;
  - migrate an API runtime only if security equivalence is `proven` on every checklist item
    **and** p99 latency or RSS improves by at least 25% at equal RPS, or a concrete maintenance
    cost is removed.
  Below these thresholds the model returns a keep-runtime outcome. Revisit triggers are listed.
- **D8 Dedup map and staged plan R0-R5.** References design#75 (closed), design#34, design#78,
  telegram#599, academy#210, seerrsense#16 (closed) and gitops#500. Implementation issues and
  an EpicDefinition are created only after R4.
- **D9 Proposed verdict.** `STANDARDIZE_CONTRACTS_KEEP_RUNTIMES` is the suggestion, conditional
  on the evidence. The owner decides. The report fixes the verdict at
  `DEFER_UNTIL_BASELINES` if R0 cannot be completed (pins or headers unobservable).

### 2. Reference model `docs/spikes/web-platform-unification/` (stdlib Python, run with `-I`)
- `model.py`: four pure functions.
  - `validate_manifest(doc)`: requires an exact semver, 40-hex commit, sha256 per file, and
    provenance. CDN mode requires the CORS and immutable-cache preconditions.
  - `check_consumer(manifest, consumer)`: drift detection for pinned version and vendored
    file hashes; rejects caret and tilde ranges.
  - `check_route_policy(route, proposal)`: a strict route must use vendored mode, and any
    added `style-src` or `default-src` origin is rejected.
  - `evaluate_decision(measurements, thresholds)`: maps measurements to an outcome. Anything
    `not-run` or not `proven` yields a non-migration outcome.
- `schemas/design-manifest.schema.json`, `schemas/route-csp-map.schema.json`.
- `fixtures/`: synthetic manifests, consumers and route maps that mirror the six surfaces'
  documented modes. These are synthetic, not live data.
- `bench/README.md` plus harness scripts (protocol only; executes nothing in CI).
- `tests/test_web_platform.py`: unittest cases.

### 3. Manifest `roadmap/spikes/web-platform-unification.yaml`
`lifecycle: proposed`, `github.issue: mctlhq/.github#328`, the five outcomes,
`execution.devloop: true`, `evidence.report: docs/spikes/web-platform-unification.md`, no
`decision` and no `epic`.

### 4. Index wiring
- Add the model path to both `paths:` lists and a test step to `.github/workflows/workflow-tests.yml`.
- Add an entry for the spike under `# Spikes` in `AGENTS.md`.

## Alternatives
- **Write only the report, without a reference model.** Cheaper, but the CSP non-widening rule
  and the manifest contract could not be tested. Past spikes (finance-assistant, mcp-gateway-g0)
  set the precedent of executable models. Dropped.
- **Run the full benchmarks inside this spike PR.** This needs builds of six external repos and
  browser tooling. The result would not be reproducible from the `.github` CI and would risk
  touching live hosts. Dropped in favor of a committed harness, `not-run` results, and a
  threshold evaluator that refuses to recommend migration on missing data.
- **Put the manifest schema in mctl-design now.** This would act as an implementation decision
  and could interfere with mctl-design PR #206, which the issue says must not be gated. Dropped;
  the schema lives in the spike as a proposal.
- **Bind to the `surfaces` epic.** The issue says that would be a misbinding. Dropped.

## Platform impact
- Migrations: none. Documentation, schemas, a stdlib model and CI test wiring only.
- Backward compatibility: no runtime, GitOps or package change. `validate.py` must still accept
  all existing manifests. The new spike name and issue binding (#328) are unique.
- Resource impact: one extra unittest step in `workflow-tests.yml`, a few seconds of runtime.
- Risks and mitigations:
  - Stale or contradictory evidence (for example the mctl-design tag drift). Mitigation: keep
    separate `[CONFIG]` and `[LIVE]` columns, pin SHAs, and use `unknown (not observed)`.
  - The report could be read as approval of the suggested verdict or of PR #206. Mitigation:
    the D0 non-claims, `lifecycle: proposed`, and no `decision` block.
  - Threshold defaults could steer the decision. Mitigation: they are labelled proposals that
    the owner can adjust, and the evaluator is parameterized.
  - Fixtures could be mistaken for live data. Mitigation: fixtures are labelled synthetic and
    contain no secrets or real tokens.
