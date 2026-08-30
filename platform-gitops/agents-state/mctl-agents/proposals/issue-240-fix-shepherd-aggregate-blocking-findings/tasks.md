# Tasks: issue-240-fix-shepherd-aggregate-blocking-findings

- [ ] 1. Pull the real Agy event payloads for `mctlhq/mctl-agents#234`
      (`gh api repos/mctlhq/mctl-agents/pulls/234/reviews`,
      `.../pulls/234/comments`, `.../issues/234/comments`) and record the
      confirmed Agy bot login, comment shape (review vs. line comment vs.
      top-level issue comment), and exact severity/marker syntax. — DoD: a
      short note (can live in the PR description of the implementing
      change) captures the confirmed `AGY_BOT` login and a sample raw
      comment body used to drive task 3's parser and task 7's fixtures.
- [ ] 2. Introduce `ReviewerSource` dataclass and `GATING_REVIEWERS` tuple
      in `orchestrator/run_shepherd.py`, replacing `GATING_BOTS` with data
      describing `name`, `bot_login`, `required`, `drives_response_signal`
      for `claude`, `agy`, `codex-connector`. Keep `REVIEW_BOT`,
      `CODEX_CONNECTOR_BOT`, and a new `AGY_BOT` as named constants reused
      by the registry entries. — DoD: `GATING_BOTS` has no remaining
      references (`grep -rn GATING_BOTS orchestrator/ tests/` is empty);
      existing call sites read `GATING_REVIEWERS` instead.
- [ ] 3. Widen `CodexFinding` with `source: str`, `proposed_fix: str |
      None`, `url: str | None`, `reviewed_head_sha: str | None` (populated
      from `commit_id` when present, else parsed from the comment body),
      keeping `author` for compatibility. — DoD: existing fields keep their
      names/positions so #67-era tests that build `CodexFinding` by keyword
      still pass unmodified; new fields default so no existing call site
      needs updating just to compile.
- [ ] 4. Add `_parse_agy_finding(body, item) -> CodexFinding | None`
      implementing Agy's confirmed marker format from task 1 (severity,
      path, message, proposed fix, url, reviewed head SHA), following the
      same defensive multi-pattern approach as `_extract_severity`. — DoD:
      unit tests feed the task-1 sample body and assert every normalized
      field extracts correctly, including a case where the top-level
      comment carries no `commit_id` and the parser recovers
      `reviewed_head_sha` from the body's own marker.
- [ ] 5. Rename `read_codex_review` to `read_gating_reviews` (or add it as
      an alias with a short deprecation note if a narrower diff is
      preferred) and collapse its three per-endpoint `GATING_BOTS`-filtered
      loops plus `read_copilot_review`'s duplicate fetch into one pass that
      dispatches each review/comment by `login` to its `ReviewerSource`
      and per-source parser, producing per-source `responses: dict[str,
      bool]` instead of one bare `has_responded` bool. — DoD: `process_one` performs the existing review/comment reads plus the required cached, paginated Actions-runs lookup; tests assert bounded call counts and pagination. All pre-existing #67 tests
      (`test_connector_*`) pass against the refactored function with no
      behavior change for Claude/connector-only fixtures.
- [ ] 6. Implement `_dedupe_findings()` (path/line key, fuzzy-text
      fallback, keeps highest severity, merges into a `sources: list[str]`
      field) and wire it into the aggregation path before `decide()` sees
      the pooled findings list. — DoD: unit test with two reviewers
      reporting the identical `(path, line)` collapses to one finding with
      both names in `sources`; unit test with two different-path findings
      from different reviewers stays two findings (no over-merge).
- [ ] 7. Update `decide()` to accept per-source `responses` and a
      `reviewer_wait_ticks` figure (or equivalent), and return
      `review-stuck` (not `wait`) once a required source's silence exceeds
      `REVIEWER_RESPONSE_TIMEOUT_TICKS` (default 3). Update `process_one`
      to persist/increment `reviewer_wait_ticks` in `.status.yaml`, reset it
      to 0 whenever `pr.head_sha` changes since the last observation. —
      DoD: `decide()` stays a pure function taking only its arguments (no
      new I/O); test asserts a PR silent from a required reviewer for
      fewer than the timeout returns `wait`, and one at/over the timeout
      returns a decision that flips the proposal to `review-stuck` with a
      note naming the silent reviewer.
- [ ] 8. Update `agents/_shepherd/.claude/agents/shepherd.md` to describe
      Agy's marker format alongside Codex's badge format, and instruct the
      summarizer to fold each finding's `sources` list into its one-line
      summary. — DoD: prompt still emits the same `{"p1", "p2",
      "summaries"}` JSON shape `_format_bundle_via_sdk` expects; no
      contract change to `apply_followup`.
- [ ] 9. Record merge evidence: in `process_one`'s `flip-to-merged` branch,
      add a `review_evidence` dict (`{source_name: {"responded": bool,
      "cleared_findings": int}}`) to the `update_status(..., "merged",
      ...)` call, built from the final aggregated review just before merge.
      — DoD: unit test on the merge path asserts `.status.yaml` gets a
      `review_evidence` key listing every `GATING_REVIEWERS` source; a
      pre-existing merge-path test without this assertion still passes
      unmodified (additive field, no key removed).
- [ ] 10. Sweep `tests/test_run_shepherd.py` and any other module that
      imports `run_shepherd.GATING_BOTS`, `run_shepherd.CodexReview`, or
      `run_shepherd.read_codex_review` by name, and update references to
      the new names/shapes introduced in tasks 2, 3, 5. — DoD: `pytest
      tests/test_run_shepherd.py` passes with zero references to the old
      `GATING_BOTS` name remaining anywhere in the tree.

## Tests

- [ ] T1. Reproduce #234: Claude posts a P2 review at `head_sha`; Agy posts
      a top-level comment with the only P1 plus additional P2s at the same
      head. Assert `read_gating_reviews()` returns findings from both
      sources, `decide()` returns `address-review` with the P1 present, and
      the bundle passed to `apply_followup`/the shepherd sub-agent contains
      every current-head blocker from both reviewers (per
      requirements.md's "Tests reproduce #234" criterion).
- [ ] T2. Claude and Agy disagree on severity for the *same* underlying
      finding (Claude: P2, Agy: P1, same path/line) — assert
      `_dedupe_findings()` keeps the higher severity (P1) and both names
      survive in `sources`, and `decide()` treats it as a P1 blocker.
- [ ] T3. Agy reports a finding anchored to an older head; a follow-up push
      lands; assert `findings_p1_p2(at=new_head_sha)` drops it, mirroring
      `test_connector_stale_commit_finding_does_not_gate`.
- [ ] T4. Agy's workflow never posts anything on the current head while
      Claude has approved cleanly: assert `decide()` returns `wait` for the
      first `REVIEWER_RESPONSE_TIMEOUT_TICKS - 1` ticks and a decision that
      flips to `review-stuck` (never `merge`) once the timeout is exceeded
      — this is the direct regression test for "never silently treat it as
      approval."
- [ ] T5. Both `sources[]`-merged and single-source findings round-trip
      through `_format_bundle_via_sdk`'s fallback path
      (`_fallback_bundle`) without the SDK, asserting the summaries mention
      every contributing source.
- [ ] T6. Merge-path test asserting `review_evidence` lands in
      `.status.yaml` with entries for `claude`, `agy`, and
      `codex-connector`, each recording whether it responded and how many
      of its findings were cleared by the time of merge.
- [ ] T7. Regression: all pre-existing tests in `tests/test_run_shepherd.py`
      (including the full `#67` connector suite at lines 896-1028 and the
      Claude-only fixtures earlier in the file) continue to pass unmodified
      in behavior against the refactored `read_gating_reviews`/`decide()`.

## Rollback

The change is confined to `orchestrator/run_shepherd.py`,
`agents/_shepherd/.claude/agents/shepherd.md`, and their tests — no
database migration, no `.status.yaml` field removal, and no change to the
implementer (`run_implementer.py`) contract (`--review-feedback <path>`
JSON shape is unchanged). If Agy's real comment format turns out to differ
from what task 1 confirms, or the no-response timeout proves too aggressive
in production and starts flipping healthy PRs to `review-stuck`:

1. Revert the `mctl-agents` commit(s) implementing this proposal (single
   module + prompt + tests, straightforward `git revert`).
2. Any proposal already flipped to `review-stuck` by the new timeout logic
   is not stuck permanently — `review-stuck` is an existing, human-
   triageable terminal status (same recovery path operators already use
   for the pre-existing `MAX_REVIEW_ATTEMPTS` flip): an operator moves it
   back to `implemented`/`review-fixing` via a GitOps-reviewed
   `.status.yaml` edit once the underlying issue (bad Agy parsing, too-
   tight timeout) is fixed or reverted.
3. Because `review_evidence` and `reviewer_wait_ticks` are additive fields,
   reverting the code does not require cleaning up `.status.yaml` — the
   old code simply ignores fields it does not know about, exactly as today's
   code already tolerates unknown keys via `_load_status`.
4. No feature flag is introduced; if a staged rollout is wanted instead of
   a full revert, `AGY_BOT`'s `required` flag can be flipped to `False`
   (demoting Agy to connector-style "gates on findings but never on
   silence") as a one-line mitigation short of a full revert.

## Corrected implementation tasks (authoritative)

- [ ] C1. In `mctlhq/.github`, add head SHA and run ID to success/findings/failure Agy markers; pass normal review/checks.
- [ ] C2. Bump mctl-agents' Agy reusable-workflow pin to C1 and capture real pinned PASS/FAIL payload fixtures.
- [ ] C3. Match actor `github-actions[bot]` plus marker; reject missing/malformed/stale SHA and require equality with current head.
- [ ] C4. Use `reviewer_wait_head_sha` plus per-source counters, reset atomically on head change.
- [ ] C5. Agy failure marker means wait then `review-stuck`, never approval; Actions conclusion alone is not semantic approval.
- [ ] C6. Use exact conservative dedupe.
- [ ] C7. Test stale/missing SHA, unrelated shared actor, overlapping runs, current-head PASS/FAIL, per-source timeout reset and merge evidence pinned to merged head.

## P1 rollout and ordering tasks (authoritative)

- [ ] P8. Add `head_sha`, `run_id`, and `run_attempt` to shared Agy success/findings/failure markers and pin the reviewed reusable-workflow commit.
- [ ] P9. Join comments to Actions runs and select the newest non-superseded current-head run/attempt; a newer queued/in-progress run blocks and all older markers are ignored.
- [ ] P10. Before enabling `required=True`, enumerate open PRs and dispatch/rerun pinned Agy for each current head; require a verified new-format marker. Include PR #234 as a mandatory fixture.
- [ ] P11. Test old PASS/new FAIL, old FAIL/new PASS, rerun-attempt supersession, newer in-progress run, malformed/missing run identity, and the open-PR backfill path.

## Executable backfill and findings tasks (authoritative)

- [ ] P12. Add a permission-checked `workflow_dispatch` backfill entry point to the pinned mctl-agents Agy caller with required PR number and exact head SHA; fail closed if the head changed.
- [ ] P13. Have the rollout enumerate open PRs, dispatch P12, and persist/verify the returned run ID, run attempt, and exact-head marker before enabling `required=True`.
- [ ] P14. Add semantic marker outcomes `clean|findings|reviewer_error`. Route authoritative current-head findings to `address-review` even when the blocking job concludes failure; route reviewer/infrastructure errors through bounded wait-to-`review-stuck`.
- [ ] P15. Test dispatch against a stale head, current-head backfill for PR #234, failure-with-findings, reviewer error, malformed payload, and failure without findings.

## Explicit-target and Actions-query tasks

- [ ] P16. Make backfill accept explicit repository, PR number, and 40-hex head SHA; verify the live head, fetch/review that exact detached commit, pass explicit target inputs to the reusable workflow, and revalidate before posting.
- [ ] P17. Ensure dispatch never uses the default-branch `GITHUB_SHA` or assumes a `pull_request` payload. Test wrong PR, stale SHA, changed-during-review SHA, fork/head targeting, and marker destination.
- [ ] P18. Add a cached, paginated Actions-runs lookup for the Agy workflow/current head, including queued/in-progress runs and rerun attempts; replace prior no-new-call assertions with bounded call-count and pagination tests.

## Dispatch correlation tasks

- [ ] P19. Persist a unique dispatch intent and pass its correlation ID, PR number, and reviewed SHA to the trusted caller; expose the correlation ID in immutable run metadata such as `run-name`.
- [ ] P20. Query dispatch runs without Actions `head_sha` filtering and join queued/in-progress runs to the intent using workflow/event/ref/correlation/time; join completed markers using run ID, attempt, correlation, PR, and exact reviewed SHA.
- [ ] P21. Test queued dispatch before marker, default-branch head mismatch, unrelated concurrent dispatch, spoofed correlation, stale intent, completed marker mismatch, and coexistence with PR-triggered runs.

## Markerless-run authority tasks

- [ ] P22. Keep a correlated dispatch authoritative after completion even with no marker; map missing/malformed semantic output to `reviewer_error` and never reveal an older PASS.
- [ ] P23. Retain dispatch intents until the authoritative result is consumed or superseded; join completed markerless runs using trusted run metadata plus the durable intent.
- [ ] P24. Test newer markerless success/failure/cancelled runs over an older PASS, delayed marker arrival, malformed marker, intent retention across restart, and explicit supersession.

## Pending authority and wait-key tasks

- [ ] P25. Include uncorrelated current-head dispatch intents in authority selection from creation; block older PASS until correlation, explicit supersession, or durable failure resolution.
- [ ] P26. Bound dispatch/correlation retries and retain failed/lost-response intents as `reviewer_error` evidence rather than deleting them.
- [ ] P27. Key reviewer waits by source, head, and correlation/run identity; atomically reset that source on pending-to-run correlation, rerun, or newer attempt.
- [ ] P28. Test dispatch response loss, delayed Actions indexing, intent supersession, same-head rerun after near-timeout, per-source isolation, and restart during correlation.

## Exact-PR and clearance-evidence tasks

- [ ] P29. Scope `pull_request`-triggered Agy runs to the exact target PR association plus head repository, ref, workflow identity, and SHA. Test two PRs sharing one commit, different bases, and fork/ref isolation.
- [ ] P30. Treat a valid current-head `findings` marker containing only P3/P4 findings as a successful nonblocking response while retaining those findings as advisory merge evidence.
- [ ] P31. Persist exact per-source P1/P2 finding history across head changes and idempotently derive merged-head `cleared_findings` records and counts from prior-head observations.
- [ ] P32. Test blockers on an earlier head followed by a clean merged head, repeated observation deduplication, restart/reconciliation persistence, and stable source/head attribution without double-counting.

## Same-head lifecycle fence tasks

- [ ] P29. Read/project `ready_for_review` and `reopened` lifecycle generations and invalidate older same-head Agy authority immediately.
- [ ] P30. Correlate the post-event run by exact PR, head repository/ref/SHA, workflow, and creation time; keep the event generation pending until correlated or bounded reviewer-error resolution.
- [ ] P31. Test ready-for-review/reopen before Actions indexing, old same-head PASS, delayed run visibility, missing run, duplicate events, and unrelated PRs sharing a SHA.
