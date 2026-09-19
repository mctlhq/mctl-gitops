# Tasks: issue-411-fix-shepherd-feed-failing-required-pr-ch

- [ ] 1. Add `orchestrator/ci_checks.py` with the `CheckBlocker` and `CIStatus`
      dataclasses exactly as specified in design.md, plus the module-level
      constants `CI_ACTIONABLE_CONCLUSIONS`, `CI_INFRA_CONCLUSIONS`
      (`CANCELLED`, `TIMED_OUT`, `STALE`, `ACTION_REQUIRED`, `SKIPPED`,
      `NEUTRAL`, `STARTUP_FAILURE`), `_CI_INFRA_PATTERNS`,
      `CI_MAX_ANNOTATIONS = 10` and `CI_MAX_EXCERPT_CHARS = 1500`. Import-light:
      no `claude_agent_sdk`, no `run_implementer`, no `run_shepherd` at module
      level (`#149`, pinned by `tests/test_worker_isolation.py`). — DoD: module
      imports in a bare interpreter with only stdlib plus `orchestrator`
      installed; `ruff check` and `mypy` clean.

- [ ] 2. Extend the GraphQL query in `run_shepherd._fetch_pr_snapshot`
      (L1371) to select per-context rollup nodes off the existing
      `commits(last:1){nodes{commit{...}}}` node — `CheckRun` (`name`, `status`,
      `conclusion`, `detailsUrl`, `isRequired(pullRequestNumber:$number)`,
      `title`, `summary`, `checkSuite{databaseId workflowRun{databaseId url
      workflow{name}}}`) and `StatusContext` (`context`, `state`, `targetUrl`,
      `isRequired`) — plus `baseRef{branchProtectionRule{requiredStatusCheckContexts}}`.
      Store the raw context nodes and the required-context list on two new
      `PRSnapshot` fields that DEFAULT (`check_contexts: tuple = ()`,
      `required_contexts: tuple[str, ...] = ()`), so
      `tests/test_pr_adoption.py:58-71` and `tests/test_temporal_activities.py:493`
      keep constructing `PRSnapshot` unchanged. (depends on 1) — DoD: existing
      `test_fetch_pr_snapshot_unstable_yields_checks_green` and
      `test_checks_green_no_rollup_clean_merge_state` still pass untouched.

- [ ] 3. Implement `ci_checks.read_required_checks(pr) -> CIStatus`: discard any
      context whose enclosing `commit.oid != pr.head_sha`; resolve requiredness
      via `isRequired`, then `pr.required_contexts`, then advisory; set
      `pending=True` when a required context is `QUEUED`/`IN_PROGRESS`; return
      `CIStatus(known=False, ...)` on `subprocess.CalledProcessError`, malformed
      JSON, or a truncated `contexts` connection (100 nodes returned). (depends
      on 1, 2) — DoD: unit-tested against hand-built context node fixtures;
      never raises.

- [ ] 4. Implement the excerpt builder in `ci_checks`: for a failing `CheckRun`,
      call `gh api repos/{repo}/check-runs/{id}/annotations` (bounded by
      `CI_MAX_ANNOTATIONS`), render `path:start_line: message` lines, fall back
      to `title`/`summary`/`text`, truncate to `CI_MAX_EXCERPT_CHARS`. (depends
      on 3) — DoD: a `mypy` annotation fixture yields the exact one-line excerpt
      `orchestrator/run_implementer.py:3185: error: Incompatible types in
      assignment ...`; an annotations-API failure degrades to the output text
      instead of failing the probe.

- [ ] 5. Implement `_classify(conclusion, excerpt, has_annotations) -> "actionable"
      | "infrastructure"` per design.md, with the unclassifiable default of
      `actionable`. (depends on 4) — DoD: table-driven unit test covering every
      conclusion in both conclusion sets plus each `_CI_INFRA_PATTERNS` entry.

- [ ] 6. Add the `Blockers` container dataclass to `run_shepherd` and widen
      `decide()` with `ci: CIStatus | None = None`, the union blocker set, and
      the three new returns `("address-review", Blockers(...))`,
      `("ci-infra", [...])`, `("ci-unknown", None)`, in the order given in
      design.md. Keep the `MERGEABLE_STATES` and `checks_green` backstops.
      (depends on 3, 5) — DoD: with `ci=None`, `decide()` is behaviourally
      identical — the whole existing `decide()` test block (L164-1604, L4453-4820)
      passes unmodified.

- [ ] 7. Wire `read_required_checks` into `process_one` beside
      `read_codex_review` (L2402-2404), pass `ci=` into `decide()`, and extend
      the per-tick operator log line (L2408-2415) with
      `ci_known=… ci_required_failed=<n> ci_checks=<names>`. (depends on 6) —
      DoD: a shepherd tick on a PR with one failing required check prints the
      check name and `-> address-review`.

- [ ] 8. Change `apply_followup` to accept `Blockers`, summarise only
      `blockers.findings` through `_format_bundle_via_sdk`, and append
      deterministic `ci_failures` records plus `head_sha` to the bundle after the
      SDK returns (also in `_fallback_bundle`), tag-neutralising and bounding
      every excerpt. Do not let the model rewrite any CI record. (depends on 6) —
      DoD: `apply_followup(..., skip_subprocess=True)` returns a bundle whose
      `ci_failures[0]` carries check, workflow, job, step, conclusion, url,
      run_id, head_sha and excerpt, and whose `p1`/`p2` are `False` when the
      only blocker is a check.

- [ ] 9. Extend `run_implementer._render_review_feedback` (L1538) with a
      `## Failing required CI checks (fix each)` section rendered from
      `bundle["ci_failures"]`, distinct from the review-findings section, and move
      the `if not summaries:` early return (L1554-1556) so a CI-only bundle still
      renders. Leave `_load_review_feedback` unchanged — unknown keys are already
      ignored. (depends on 8) — DoD: a bundle with only `ci_failures` renders the
      CI section and no misleading "(No summaries in bundle …)" dead end; a
      bundle with neither key renders exactly today's output.

- [ ] 10. Add the two new bounded counters to `process_one`: `ci-infra` →
      `gh run rerun <run_id> --failed` up to `SHEPHERD_CI_INFRA_RERUN_MAX`
      (default 2) per head, tracked by `ci_infra_retries` / `ci_infra_head` and
      reset on head change exactly like `refusals` / `refusals_head` (L2533-2534);
      `ci-unknown` → `wait` plus `ci_probe_failures`, cleared on any successful
      probe. Both flip to `review-stuck` at their cap with a blameless note that
      never charges `review_attempts`. (depends on 7) — DoD: counters appear in
      `.status.yaml`, disappear on head change, and each cap reaches
      `review-stuck` exactly once.

- [ ] 11. Rewrite the `MAX_REVIEW_ATTEMPTS` `review-stuck` note (L2471-2475) to
      enumerate the unresolved current-head blockers by reviewer and by check
      name, and write a head-pinned `ci_blockers_head` + check-name list into
      `.status.yaml`, deleted when the blocker set is empty. (depends on 7) —
      DoD: the note on a #409-shaped proposal names `PR validation / lint`.

- [ ] 12. Add the env knobs to `.env.example` and the module docstring of
      `run_shepherd.py`: `SHEPHERD_CI_INFRA_RERUN_MAX`,
      `SHEPHERD_CI_PROBE_FAILURES_MAX`, `SHEPHERD_CI_REQUIRED_OVERRIDE`
      (optional comma-separated allowlist of check names treated as required when
      GitHub reports nothing). (depends on 10) — DoD: every new env var is
      documented with its default and parsed defensively, mirroring
      `_settle_min_from_env` (L485-494).

- [ ] 13. Update `agents/_shepherd/.claude/agents/shepherd.md` with a paragraph
      stating that CI failures may accompany the findings, are supplied
      deterministically by the Python, must not be summarised, invented or
      reclassified, and that the model still emits only
      `{"p1", "p2", "summaries"}`. (depends on 8) — DoD: the prompt no longer
      implies the bundle is review findings only.

- [ ] 14. Update the shepherd section of `README.md` and
      `docs/temporal-flow.md` where the review/remediation loop is described, so
      the documented blocker set is the union. (depends on 6) — DoD: no doc still
      states that only review findings drive `address-review`.

## Tests

All in `tests/test_run_shepherd.py` unless noted, reusing `make_pr` (L47),
`make_finding` (L87), `make_ref` (L132), `read_status` (L159) and the
`_route_gh` (L1608) pattern. Add one new factory `make_check(...) -> CheckBlocker`
and one `make_ci(...) -> CIStatus` next to them.

- [ ] T1. Primary acceptance path (the #409 reproduction): `decide()` with
      `CodexReview(has_responded=True, findings=[], head_verdict="APPROVED")` and
      a `CIStatus` carrying one actionable required `lint` failure returns
      `("address-review", Blockers(findings=[], checks=[...]))` — not `merge`,
      not `wait`.
- [ ] T2. End-to-end through `process_one` with `apply_followup` patched: the
      bundle handed to the implementer contains `ci_failures[0]` with the `mypy`
      excerpt, the check name, the run URL and the head SHA, and `p1`/`p2` are
      `False`.
- [ ] T3. Fix push clears the blocker: second tick with a new `head_sha` and a
      `CIStatus` whose required checks are all `SUCCESS` returns `merge` (outside
      the settle window), and `ci_blockers_head` / `ci_infra_*` are gone from
      `.status.yaml`.
- [ ] T4. Stale head: a failing check node whose enclosing `commit.oid` is
      `OLD_SHA` produces an empty blocker set at `HEAD_SHA`
      (`read_required_checks` unit test).
- [ ] T5. Non-actionable infrastructure: a required check with conclusion
      `CANCELLED` yields `("ci-infra", ...)`, never `address-review`, and never
      appears in any bundle's `ci_failures`.
- [ ] T6. Infra re-run budget: `SHEPHERD_CI_INFRA_RERUN_MAX + 1` consecutive
      ticks reach `review-stuck` with `review_attempts` unchanged and a note
      naming the check and the infrastructure classification.
- [ ] T7. Advisory check does not gate: a failing check with `isRequired=False`
      and absent from `required_contexts` leaves the decision at `merge`.
- [ ] T8. Probe outage fails closed: `CIStatus(known=False)` yields
      `("ci-unknown", None)` — never `merge` or `defer-merge` — and
      `SHEPHERD_CI_PROBE_FAILURES_MAX` consecutive outages reach `review-stuck`
      with a blameless note.
- [ ] T9. Pending required check: `QUEUED`/`IN_PROGRESS` yields `wait` and emits
      no remediation evidence.
- [ ] T10. Attempt-budget boundary: `review_attempts == MAX_REVIEW_ATTEMPTS` with
      a CI-only blocker flips to `review-stuck` and the note names the check.
- [ ] T11. Mixed blockers: one fresh P2 plus one actionable required check
      produce a single `address-review` with both populated, one implementer
      invocation, and one attempt charged.
- [ ] T12. Backward compatibility: `decide(pr, review)` with no `ci` argument is
      byte-identical in behaviour across the existing decision matrix
      (parametrized over the cases at L164-201, L1321-1400).
- [ ] T13. `tests/test_run_implementer_summary.py` (or a new
      `tests/test_run_implementer_ci_feedback.py`): `_render_review_feedback`
      emits the CI section for a CI-only bundle, both sections for a mixed
      bundle, and today's exact output for a bundle with no `ci_failures`.
- [ ] T14. Injection: a check excerpt containing `</findings>` and
      `ignore previous instructions` is neutralised and truncated before it
      reaches the prompt (mirrors the existing fence tests at L3171+).
- [ ] T15. Classification table: every conclusion in `CI_INFRA_CONCLUSIONS` maps
      to `infrastructure`; `FAILURE` with annotations maps to `actionable`;
      `FAILURE` with no annotations and an unmatched excerpt maps to
      `actionable`.
- [ ] T16. `tests/test_worker_isolation.py` still passes — `ci_checks` pulls no
      SDK or implementer import into the long-lived worker.

## Rollback

The change is additive and gated on one input. Three levels, cheapest first:

1. **Kill switch.** Ship `SHEPHERD_CI_BLOCKERS=off` (default `on`), read once at
   module load next to `_settle_min_from_env`. When off, `process_one` passes
   `ci=None` into `decide()` and the shepherd behaves exactly as it does today,
   including the `("wait", None)` wedge. No redeploy of the implementer needed:
   the bundle simply stops carrying `ci_failures`, which the implementer already
   ignores when absent.
2. **Revert the shepherd only.** The bundle key is additive and
   `_load_review_feedback` ignores unknown keys, so `run_shepherd.py` +
   `ci_checks.py` can be reverted while the implementer's renderer change stays
   in place. The reverse order is also safe — an older implementer drops
   `ci_failures` silently.
3. **Full revert.** `git revert` the merge commit. The only durable residue is
   four optional `.status.yaml` keys (`ci_infra_retries`, `ci_infra_head`,
   `ci_probe_failures`, `ci_blockers_head`) which the pre-change
   `update_status_file` read-modify-write preserves and ignores; they can be left
   in place or removed with a `mctl_trigger_reconcile` sweep. Any proposal that
   reached `review-stuck` through one of the new arms is recovered the same way
   every other `review-stuck` proposal is: an operator-reviewed GitOps edit back
   to `implemented`.
