# Tasks: issue-127-spike-media-competitive-landscape-and-mc

The tasks fall into three groups:
- RESEARCH (R1-R9): delivered in this revision and marked done, with a pointer to the design section that holds the result.
- EXPERIMENT (X1-X3): proposed next. Each is isolated, uses fixtures only, and needs owner authorisation before it runs.
- FUTURE (F1-F5): implementation, and only after an independent review and an explicit owner GO.

No task deploys anything, touches household media, volumes or production data, creates a repo, contacts users, starts the implementer, or approves this proposal. The proposal stays status=proposed.

## Research (delivered)
- [x] R1. Competitor matrix for all nine candidates at tag, with SHA, date, SPDX, contributors, releases, CI/security and MCP class. Ambiguous names (MediaStack MCP, Mediabox MCP, Reelix) are resolved, each with its alternative listed. — DoD: design.md section 1 and Evidence annex E1-E14. Met.
- [x] R2. HolyArrs MCP re-assessment against tag 1.2.0 code. Covers: `ai_apps` gate, PKCE S256, DCR, single `mcp` scope, no refresh grant, confirm token (5 min), tools vs permission groups reconciled, the Seerr-compat meaning, metadata egress and opt-out. — DoD: design.md section 1 (E2-E6). Met. Live interoperability remains unverified and goes to X1.
- [x] R3. Auditable weighted matrix for Baseline, A, B, C, D and the hybrid H. Per-cell rationale, low/high ranges, three weight scenarios, sampled first-place share and single-cell rank reversals. — DoD: design.md section 2. Met.
- [x] R4. Experiment and business verdicts given separately. Gates G1-G6 are demonstrable and replace the age and maintainer thresholds. — DoD: design.md section 2. Met.
- [x] R5. Native replacement scope and complexity, including Russian release labels and the macOS path-mapping risk. — DoD: design.md section 3. Met.
- [x] R6. Data-plane security model: preview vs trusted approval, binding, atomic consume, outbox, TOCTOU, revocation, local agent enrollment, paths, offline behaviour. — DoD: design.md section 5. Met. No write tools added.
- [x] R7. Identity compatibility tests I1-I6 for the #120 two-door model. — DoD: design.md section 6. Met. No identity change.
- [x] R8. Effort by subsystem with ranges, DevLoop cost assumptions, parallel vs sequential work, and risk-ranked findings. — DoD: design.md section 8. Met.
- [x] R9. Licensing triage per integration boundary (not legal advice). The seerrsense MIT/ISC mismatch is verified. — DoD: design.md section 9. Met.

## Experiments (proposed; each needs owner authorisation)
- [ ] X0. Owner host baseline, read-only, done by or with the owner. Record:
  - Mac mini RAM, macOS version, container runtime and VM size;
  - services and versions running today;
  - `docker stats --no-stream` and `ps -o rss,comm` per service, VM RSS from Activity Monitor or `top -l 1`, swap.

  DoD: a dated baseline record, or an explicit "not observed".
- [ ] X1. Isolated benchmark and security probe (depends on X0).
  - Setup:
    - Separate compose projects, each on a network with `internal: true` (no egress), with digests pinned: current stack (Seerr, Radarr, Sonarr, Prowlarr, qBittorrent mock), HolyArrs 1.2.0, Streamline v3.4.0, and optionally Mediarium v4.1.0.
    - Volumes are fresh temp dirs only; no household volume is ever mounted.
    - HolyArrs `HOLYARRS_METADATA_URL` points at a local stub that records every request.
    - Fixtures: a synthetic library (500 movies, 50 series of tiny files) and the synthetic Torznab server from section 7.
  - Commands, recorded verbatim:
    - `docker image inspect -f '{{.Size}}'` and `docker manifest inspect -v`, for uncompressed and compressed size;
    - `docker stats --no-stream` at idle (10 minutes after start) and during a scripted 30-minute search+import loop, sampled every 5 s;
    - VM RSS measured separately;
    - search latency p50/p95 with `hyperfine` against each REST or MCP endpoint;
    - G1 runs of the vertical slice;
    - G2 `kill -9` drills and a disk-full drill (a small loop-mounted volume);
    - G3 OAuth/PKCE conformance and confirm-token replay checks;
    - G4 upgrade across two tags;
    - capture of the stub's requests for G6.

  DoD: raw outputs in the evidence report, each number labelled "measured (host, date, version)". Results are compared to E4 upstream claims. If the environment does not permit a run, the harness is committed to the evidence report and its outcomes are marked unknown.
- [ ] X2. Parser corpus. Write a synthetic corpus of about 150 release names covering:
  - Cyrillic and Latin titles, Dub/MVO/DVO/AVO/Rus+Eng labels, editions;
  - size and quality tokens, season packs vs single episodes.

  Run it through the parser tests at tag of HolyArrs `internal/core/releasename`, Streamline `internal/library`, Mediarium `internal/parser` and Reelix `crates/reelix-parser`, in isolated containers. DoD: a per-parser accuracy table with an error taxonomy, and a recommendation on whether D can borrow a design (Go) or must start clean.
- [ ] X3. Rescore (depends on X1, X2). Update the section 2 cells from measured data, rerun s0-s3 and the sampling, and report score deltas with causes. Turn the verdicts into a business recommendation for the owner. DoD: an updated matrix with a delta table, and the proposal still status=proposed.

## Future implementation (only after owner GO; each also gated on #120 settling)
- [ ] F1. Option A, read-only: add a `MediaBackend` port in `src/providers/` and read-only queue, disk and library adapters. `SeerrClient` stays behaviour-identical. DoD: existing tests pass unmodified, and the new tools are read-only and additive.
- [ ] F2. Preview/approval/execute model (depends on F1). Adds `plan_acquisition`, a first-party approval page, `execute_plan(approval_id)`, `get_acquisition_status`, the additive tables (`plans`, `approvals`, `executions`, `outbox`, `agents`) and additive scopes. DoD: T1-T14 and I1-I6 pass.
- [ ] F3. Local agent, T1 topology (depends on F2): enrollment, signed outbound channel, closed job schema, path validation, offline expiry. DoD: T15-T17 pass.
- [ ] F4. Engine adapter for the option chosen in X3 (`HolyArrsBackend`, `StreamlineBackend`, or the D/H engine). DoD: the vertical slice passes against it in CI with no egress, and gates G1-G6 pass.
- [ ] F5. Decide on `mctlhq/mctl-media` (depends on X3, and on F3 if needed). DoD: an owner decision is recorded. No repo is created without it.
- [ ] F6. Follow-up hygiene, independent of the strategy: align the seerrsense `package.json` license with `LICENSE` (MIT). DoD: a separate PR, reviewed by the owner.

## Tests
Research verification:
- [ ] T0. A reviewer spot-checks 5 random claims in design.md section 1 against the cited tag/SHA/path. All 5 match, or the mismatches are recorded as corrections.

Future vertical slice (fixtures only; the same fixtures for every option):
- [ ] T1. Happy path: the public-domain title is resolved, found absent, the correct release is chosen from 5 synthetic releases, previewed, approved by a human, mock-downloaded, hardlink-imported, and shown in the Jellyfin mock as `imported`.
- [ ] T2. Duplicate: a title already in the library or already requested produces a refusal and no plan (mirrors `requestMediaSafely`).
- [ ] T3. Missing episode: a season where the fixture lacks one episode produces a plan that lists the gap. No silent partial success.
- [ ] T4. Failed download: the mock reports an error, retries are bounded, and the final status `failed` is observable.
- [ ] T5. Insufficient space: the preflight refuses before any grab. A space change between approval and dispatch yields `needs_reapproval`.
- [ ] T6. Wrong language/quality: a release labelled with the wrong audio track, or below the cutoff, is never selected.
- [ ] T7. Expired approval: execute is refused after expiry.
- [ ] T8. Revoked session, subject or principal: execute and agent dispatch are both refused after revocation, including for an already-approved plan.
- [ ] T9. Cross-tenant and cross-door: subject B cannot read, approve or execute subject A's plan. A door-2 principal cannot touch a door-1 plan, and the reverse also holds.
- [ ] T10. Replay: a second execute with the same approval returns the original execution and performs no second grab. A mismatched digest, backend or agent is refused.
- [ ] T11. Preview is not consent: `execute_plan` called with a `preview_id`, or with an approval not created by a human first-party action, is refused.
- [ ] T12. Concurrency: two simultaneous executes on one approval result in exactly one execution (atomic consume).
- [ ] T13. Crash: `kill -9` between consume and outbox delivery, and again mid-import, reconciles to a consistent state with no duplicate grab.
- [ ] T14. Prompt injection: a release title containing instructions is returned as capped, inert data, and tool descriptions are unchanged.
- [ ] T15. Agent least privilege: an agent cannot fetch another agent's jobs, and a job containing a raw URL or a host from the control plane is rejected.
- [ ] T16. Path validation: `..`, a symlink escape, and a cross-filesystem hardlink target are each refused, or the cross-filesystem case falls back to a verified copy.
- [ ] T17. Offline agent: jobs that expire while the agent is offline never run on reconnect.
- [ ] T18. Compatibility: the existing `whoami`, `search_media`, `resolve_media`, `get_media` and `request_media` tests in `tests/integration.test.ts` and `tests/oauth.test.ts` pass unmodified. Identity tests I1-I6 (design.md section 6) pass.

## Rollback
- Research: changes nothing deployed. Rolling back means discarding this proposal revision. `labs/seerrsense` 1.14.4 and its gitops values are untouched.
- Experiments: each runs in its own compose project. Remove it with `docker compose -p <project> down -v`. No household volume is ever mounted, and the networks are `internal: true`, so there is nothing external to undo.
- Future tasks:
  - Each is additive (new tools, scopes and tables) behind the `MediaBackend` port. Rollback means reverting the release, which is a one-line gitops revert of the digest-pinned image in `services/labs/seerrsense/values.yaml`. The additive tables can stay in place harmlessly.
  - The local agent is revoked from `/account` and uninstalled.
  - Engine adoption (B/C/D/H) runs in parallel with the existing stack until the gates pass. Rollback means pointing the household back at Seerr/Radarr/Sonarr, which are kept running and unmodified throughout. Option H rolls back movies only.
