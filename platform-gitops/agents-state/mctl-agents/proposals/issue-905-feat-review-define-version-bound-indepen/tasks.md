# Tasks: issue-905-feat-review-define-version-bound-indepen

- [ ] 1. Write `docs/adr/025-independent-review-receipts.md` (contract: documents, outcomes, rubrics, `spike_report_digest_v1` byte layout, gate order, independence rules, Tier B adapter checklist, reviewer capability bounds, non-goals) — DoD: ADR states reuse of `proposal_state.content_digest_of` / `read_proposal_content_digest` and #701/#702/#703 scope limits; lists every typed refusal code.
- [ ] 2. Implement `spike_report_digest()` and `InventoryEntry` validation in new `orchestrator/review_receipts.py` (depends on 1) — DoD: pure function; rejects symlink/submodule modes, `..`/`.`/backslash/NUL/absolute/non-UTF-8 paths, case-fold collisions, size caps with `SpikeDigestError`; golden vectors in `tests/fixtures/review/spike_digest_vectors.json` asserted literally.
- [ ] 3. Implement `read_spike_inventory(repository, report_root, sha)` async reader (depends on 2) — DoD: git trees API at a full SHA, refuses `truncated`, verifies blob sha of returned bytes, any non-200 raises; never returns a partial inventory.
- [ ] 4. Implement `ReviewSubject`, `ReviewRequest`, `ReviewReceipt`, rubrics `spike_v1`/`proposal_v1`, `seal()`/`from_dict()` (depends on 1) — DoD: unknown keys rejected; full-SHA validation; `PASS` with any non-`met` criterion rejected; rubric/subject-kind mismatch rejected; manual mode forces `assurance=advisory`; proposal subject built only via `content_digest_of`.
- [ ] 5. Implement pure `evaluate_review_gate()` (depends on 4) — DoD: answers `unknown`, `missing`, `stale`, `not_independent`, `advisory_only`, `satisfied`, `changes_requested`, `needs_human`, `unobservable` per design order; signature has no GitHub-review input.
- [ ] 6. Cross-repo mctl-api adapter: `review_requests`/`review_receipts` tables, `POST /api/v1/review-requests`, `POST /api/v1/review-receipts` (worker and manual auth paths), `GET /api/v1/review-receipts`, MCP `mctl_submit_review_assertion` and `mctl_get_review_gate` (depends on 1; tracked as a linked mctl-api issue) — DoD: server-derived tenant/actor; single-use nonce; fence check; typed refusals store nothing; append-only immutability trigger; conformance vectors copied from task 2/4 fixtures.
- [ ] 7. Enrol `service:mctl-agents-reviewer` principal and define `independent-review` ExecutionProfile (read-only inputs + submit tool; no GitHub write, merge, label or approval capability) (depends on 6) — DoD: policy checkpoint refuses `github_write` for this profile; profile holds no GitHub write token; no `GATING_BOTS` login reachable.
- [ ] 8. Reviewer run seals `ExecutionEvidence` with `ArtifactRef(kind="review-receipt")` via `evidence_producer.py` (depends on 4, 6) — DoD: envelope links receipt hash; no findings text in the envelope.
- [ ] 9. Live-acceptance check (depends on 6, 7) — DoD: deployed mctl-api answers the new endpoints (observed via read tool), recorded in the PR; no live-acceptance claim before this.

## Tests

- [ ] T1. Golden vectors for `spike_report_digest_v1` (empty measurements, nested dirs, binary, byte-move between files) — literal hashes; mutation of the framing turns them red.
- [ ] T2. Digest refusal: symlink, submodule, `..` path, case-fold collision, truncated tree, 500 on one blob, oversize — each raises `SpikeDigestError`, none returns a hash.
- [ ] T3. Proposal subject digest equals `content_digest_of` for the `tests/test_proposal_digest.py` vectors (no parallel digest).
- [ ] T4. Invalidation: report byte change, measurement byte change, added measurement file, `source_sha` change with identical bytes, `base_sha` change, proposal amendment -> `stale`; unchanged -> `satisfied` (positive and negative per rule).
- [ ] T5. Unknown live revision or `observation_failed` -> `unknown`, never `missing` or `satisfied`.
- [ ] T6. `PASS` with an `unobserved` criterion rejected; `UNOBSERVABLE` accepted.
- [ ] T7a. Authors and reviewer have different actors (operator identity vs service principal) but share an attempt id or lineage root -> `not_independent`; a worker request with no `authoring_execution_id` -> `unknown`; removing the lineage check turns this red.
- [ ] T7. Independence: reviewer actor in `author_actors` -> `not_independent`; same execution/attempt id -> `not_independent`; manual-only receipts under `required_assurance=independent` -> `advisory_only`; model-name strings are never consulted (a receipt whose reviewer name differs but actor matches is still `not_independent`).
- [ ] T8. Regression: amended `.github` spike PR fixture with an old `claude[bot]` `APPROVED` review and green checks -> gate `stale` (receipt bound to pre-amendment head/inventory).
- [ ] T9. mctl-api adapter (in mctl-api repo): replayed nonce, closed request, subject mismatch, unenrolled producer, stale fence, forged actor field -> typed refusal, zero rows written; valid worker and manual submissions stored with server-derived actor.
- [ ] T10. Reviewer profile: static check that the `independent-review` profile has no GitHub write tool and that no code path in `review_receipts.py` imports a GitHub writer or references `GATING_BOTS` logins as an actor.

## Rollback

All changes are additive and unconsumed by existing gates. Rolling back the
mctl-agents side is reverting the PR adding `orchestrator/review_receipts.py`,
its tests/fixtures and ADR 025. On mctl-api, disable the new routes and MCP
tools (revert the release); the append-only tables can remain (no reader) or
be dropped by a follow-up migration. Revoke the
`service:mctl-agents-reviewer` principal. `run_shepherd`, `aar_` approvals,
`content_digest_of` and ADR 018 evidence are untouched, so no data or
in-flight DevLoop needs repair.
