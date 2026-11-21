# Tasks: issue-127-spike-media-competitive-landscape-and-mc

Tasks 1-8 are RESEARCH: read-only, with isolated local fixtures at most. Tasks F1-F4 are FUTURE implementation. They are listed so that the scope is explicit, and they may start only after independent review and an explicit owner GO. No task deploys, touches household media or production data, creates a repo, or starts the implementer.

## Research
- [ ] 1. Verify the competitor matrix (design.md section 1) at the primary source. For each project, record the canonical repo, the latest tag and its date, the commit SHA inspected, the SPDX in its LICENSE file, CLA presence, release cadence (last 5 releases), open security advisories, and whether MCP is released, gated or planned, with the file or setting that proves it. Resolve the HolyArrs version inconsistency (1.1.0/1.1.3/1.1.4/1.2.0) and the Reelix canonical repo. Ask the owner for URLs for Streamline, MediaStack MCP and Mediabox MCP. Do a search pass for stronger alternatives. — DoD: every matrix cell is backed by a link with a tag/commit/date or marked U, and no "secondary" label remains on a material claim.
- [ ] 2. Analyse license obligations (depends on 1). Cover AGPL-3.0 section 13 for B (network use, unmodified) vs C (fork), the MovieClaw commercial restriction, the GPL-3.0 Reelix, the HolyArrs CLA, and the seerrsense MIT (`LICENSE`) vs ISC (`package.json`) inconsistency. — DoD: a short table of permitted options per license, flagged "not legal advice", with a recommendation for fixing the seerrsense metadata.
- [ ] 3. Collect the owner hardware baseline. With the owner's help, record the Mac mini RAM, macOS version, container runtime (Colima/Docker Desktop/native), the services running today with their versions, and idle RSS. If this cannot be observed, record it as unknown. — DoD: a baseline record with method and date, or an explicit "not observed" entry.
- [ ] 4. Write the benchmark harness and run it in isolation, if the environment permits (depends on 3). Build compose projects for the current stack vs HolyArrs on a synthetic library, following the methodology in design.md section 7. — DoD: raw outputs committed to the evidence report, each number labelled measured or upstream claim. If it cannot run, the harness and its commands are documented as a follow-up.
- [ ] 5. Probe the HolyArrs API and MCP in isolation (depends on 1, 4). Using fixture data only, enumerate the MCP tools and API endpoints, the auth model (API key vs OAuth), the scope granularity, and the Seerr-compatibility claims. Check whether the metadata server is required and what it receives. — DoD: a capability and security note that feeds back into B's scores.
- [ ] 6. Rescore the decision matrix (depends on 1-5). Update the scores in design.md section 2, rerun sensitivity scenarios s1-s3, and finalise GO/NO-GO/CONDITIONAL per strategy. — DoD: a matrix with final scores, the deltas against the provisional scores, and their causes.
- [ ] 7. Review MCP security and UX for the future write model (design.md section 5) against the existing code. Check `src/auth/store-pg.ts` grants storage, `src/auth/config.ts` additive scopes, `guard.ts` reuse for indexer/downloader URLs, prompt-injection handling of release titles, rate limits, and audit fields. Confirm compatibility with #120. — DoD: a reviewed threat list with a mitigation for each threat, and confirmation that no existing tool, schema or scope changes.
- [ ] 8. Assemble the evidence report and the owner decision brief (depends on 6, 7). — DoD: one report linked from this proposal containing the matrix, benchmark, license note, risks, P1-P3 gaps, PDLC metrics, early-user questions and the mctl-media repo recommendation. The proposal stays status=proposed.

## Future implementation (only after owner GO)
- [ ] F1. Option A: add read-only status adapters (queue, disk, library) behind a `MediaBackend` port in `src/providers/`. `SeerrClient` stays behaviour-identical. — DoD: existing tests pass unchanged, and the new tools are read-only and additive.
- [ ] F2. Add the plan/grant model (depends on F1): the `plan_acquisition`, `execute_plan` and `get_acquisition_status` tools; additive scopes; a hashed single-use grant table. — DoD: tests T1-T12 pass.
- [ ] F3. Build the fixture vertical slice (depends on F2): a synthetic Torznab server, mock qBittorrent and mock Jellyfin, and a hardlink import into a temp dir. — DoD: the end-to-end fixture test passes in CI with no network egress.
- [ ] F4. Decide whether a standalone execution agent or engine and the `mctlhq/mctl-media` repo are warranted (depends on 6 and F3 results). — DoD: an owner decision recorded. No repo is created without it.

## Tests
Research verification:
- [ ] T0. Every material claim in the evidence report has a primary link with a tag/commit/date, and a spot check of 5 random claims by a reviewer matches its source.

Future vertical slice (fixtures only):
- [ ] T1. Happy path: a lawful test title is resolved, found absent from the library, a release is selected from the synthetic indexer, the plan is previewed and confirmed, the mock download runs, the import happens, and the library shows the item.
- [ ] T2. Duplicate: a title already in the library or already requested yields no plan, with a refusal (mirrors `requestMediaSafely`).
- [ ] T3. Missing episode: a season request where the fixture indexer lacks one episode yields a plan listing the gap, with no silent partial success.
- [ ] T4. Failed download: the mock client reports an error, the retry is bounded, and the final status is `failed` and observable.
- [ ] T5. Insufficient space: the preflight refuses before any grab.
- [ ] T6. Wrong language/quality: the fixture release labelled with the wrong audio language (for example a Russian "DUB" vs a required original track) or below the cutoff is never selected.
- [ ] T7. Expired grant: execute is refused after expiry.
- [ ] T8. Revoked grant or session: execute is refused after `/oauth/revoke` or subject revocation.
- [ ] T9. Cross-tenant: subject B cannot plan against, execute or read status for subject A's plan or backend.
- [ ] T10. Replay: a second execute with the same grant returns the original result and performs no second grab. A grant with a mismatched plan digest is refused.
- [ ] T11. Prompt injection: a release title containing instructions is returned as inert, capped data and never alters tool behaviour or descriptions.
- [ ] T12. Compatibility: the existing `whoami`, `search_media`, `resolve_media`, `get_media` and `request_media` tests in `tests/integration.test.ts` and `tests/oauth.test.ts` pass unmodified.

## Rollback
The research tasks change nothing deployed. Rolling back means discarding the proposal and its evidence report. The deployed `labs/seerrsense` 1.14.4 and its gitops values are untouched. For the future tasks: each is additive (new tools, scopes and tables) behind the `MediaBackend` port. Rollback means reverting the release, which the image digest pin in `services/labs/seerrsense/values.yaml` makes a one-line gitops revert. The additive tables can stay in place harmlessly. Any isolated benchmark environment is removed with `docker compose down -v` on its own project, with no household volumes ever mounted.
