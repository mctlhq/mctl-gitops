# Tasks: issue-328-spike-mctl-web-platform-unification-cros

- [ ] 1. R0 evidence: pin the `main` 40-hex SHA of mctl-web, mctl-telegram, mctl-docs, mctl-academy, mctl-alice, seerrsense, mctl-design and mctl-gitops. Read the files named in the issue's evidence list, and re-read GitOps values and the ArgoCD state (`mctl_list_services` admins and labs, `mctl_get_service_status` for the 7 services). DoD: a pin table in the report, each claim tagged, the mctl-design tag drift (`75e6e4a27179` in config vs `7e1fbb0634d5` live) and the dual telegram images explained or kept as `unknown`.
- [ ] 2. Build the D1 6-by-N architecture matrix (depends on 1). DoD: every column filled or `unknown (not observed)`, with `[CONFIG]` and `[LIVE]` columns kept separate.
- [ ] 3. Write the D2 per-route CSP map and supply-chain threat model, covering auth, OAuth consent, manage/connect, redirect and error routes (depends on 1). DoD: one route table per surface with the effective directives (source-derived, or live if a permissioned read-only fetch is allowed) and the allowed delivery mode.
- [ ] 4. Write `docs/spikes/web-platform-unification/schemas/design-manifest.schema.json` and `route-csp-map.schema.json`, plus the D3 manifest contract text (exact version, per-file SHA-256/SRI, provenance, CDN and vendored preconditions, CI drift check, release and rollback). DoD: schemas are valid JSON Schema 2020-12 and the D3 section references them.
- [ ] 5. Implement `docs/spikes/web-platform-unification/model.py` (`validate_manifest`, `check_consumer`, `check_route_policy`, `evaluate_decision`) and synthetic `fixtures/` (depends on 4). DoD: stdlib only, runs under `python3 -I`, no network.
- [ ] 6. Write D4 adapter contracts for the @mctlhq/ui Vue, plain-HTML and Go html/template chrome (depends on 2). DoD: shared scope (tokens, typography, layout, a11y, header, theme) and the exclusion of auth/session/business middleware both stated.
- [ ] 7. Write D5 framework economics: the benchmark protocol and harness under `bench/` for Nuxt keep, Nuxt optimized and Astro on real prerendered mctl.ai routes, and for Hono, Fastify and native http with the security-equivalence checklist (depends on 1). DoD: the protocol is reproducible from pins, and results are marked `not-run` unless they were executed from pinned builds.
- [ ] 8. Write D6 acceptance matrix mapped to existing owners (mctl-design#34, #78, mctl-gitops#500) (depends on 3, 6). DoD: no row duplicates an existing issue's scope without a reference.
- [ ] 9. Write D7 proposed ADR with options A-E, risks, the parameterized thresholds and revisit triggers, plus D8 dedup map and R0-R5 plan, plus D9 proposed verdict (depends on 2-8). DoD: marked PROPOSED, RESEARCH ONLY, and it states that the owner decides.
- [ ] 10. Add `roadmap/spikes/web-platform-unification.yaml` (`lifecycle: proposed`, issue `mctlhq/.github#328`, the five outcomes, `execution.devloop: true`, `evidence.report`, no `decision` or `epic`). DoD: `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes.
- [ ] 11. Wire CI and the index: add `docs/spikes/web-platform-unification/**` to both `paths:` lists in `.github/workflows/workflow-tests.yml`, add a step running `python3 -I -m unittest discover -s docs/spikes/web-platform-unification/tests -v`, and add the `AGENTS.md` `# Spikes` entry (depends on 5, 10). DoD: the workflow triggers on the new path, and every commit carries the `Agent:` trailer.

## Tests
- [ ] T1. `validate_manifest` rejects `^0.20.1`, `~0.20.1` and `0.20` and accepts `0.20.1`. It rejects a missing or non-hex sha256 and a missing provenance.
- [ ] T2. `validate_manifest` with CDN mode and SRI fails when the CORS precondition or the immutable-cache precondition is missing.
- [ ] T3. `check_consumer` reports drift when one vendored file hash differs or the pinned version is not the manifest version, and reports clean on an exact match.
- [ ] T4. `check_route_policy` rejects adding `https://ui.mctl.ai` to `style-src` on a route with `default-src 'none'` (the Telegram OAuth and SeerrSense consent fixtures), and rejects CDN mode for any strict route.
- [ ] T5. `check_route_policy` accepts CDN mode on a public route whose existing CSP already permits ui.mctl.ai (mctl-web, docs and academy fixtures) without widening anything else.
- [ ] T6. `evaluate_decision` returns a non-migration outcome when any metric is `not-run`, when security equivalence is not `proven`, or when gains are below thresholds. It returns `TARGETED_MIGRATION_AFTER_BENCHMARK` only when every threshold is met.
- [ ] T7. The schemas parse, and every fixture validates against its schema.
- [ ] T8. `roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes, and the existing `roadmap/tests` still pass (`test_validate_spike.py`).
- [ ] T9. A grep check finds no secret-shaped strings in the fixtures, and none of the six surface repos or mctl-gitops is modified by the PR (diff limited to `docs/`, `roadmap/spikes/`, `AGENTS.md` and `.github/workflows/workflow-tests.yml`).

## Rollback
The change is documentation, a stdlib model and a CI step in `mctlhq/.github` only. To roll it
back, revert the PR. This removes the report, model, manifest, CI step and AGENTS.md entry. No
runtime, GitOps, package or CSP state changes, so there is nothing else to undo. If only the
manifest causes validation trouble, revert `roadmap/spikes/web-platform-unification.yaml` alone.
The report stays valid without it.
