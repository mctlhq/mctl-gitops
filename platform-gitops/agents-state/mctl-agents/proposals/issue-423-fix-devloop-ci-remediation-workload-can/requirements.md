# Execution-budget contract for CI-remediation work

## Context

`mctl-agents#411` made failing required CI checks first-class review-remediation
blockers: `orchestrator/ci_checks.read_required_checks()` turns the per-context
nodes on a PR head into `CheckBlocker` records, `run_shepherd.decide()` returns
them inside a `Blockers` container, `run_shepherd._augment_bundle_with_ci()`
writes them into the follow-up bundle, and `run_implementer._render_ci_failures_section()`
renders them into the Tier 2 follow-up prompt. That ingestion works. What was not
revalidated is the envelope the resulting work has to fit into:
`run_implementer._run_implementer_agent()` still wraps the whole SDK run in a
single `anyio.fail_after(IMPLEMENTER_TIMEOUT_SECONDS)` (default `900`, set in
`orchestrator/options.py`), sized for the pre-#411 workload of "read a handful of
review findings and edit a few lines".

The bundle hands the agent a check name, a conclusion, a run URL and an
annotation-derived excerpt bounded to `CI_MAX_EXCERPT_CHARS = 1500`, but no
actual CI log. On `mctlhq/mctl-telegram#652` the implementer therefore did what
the prompt implicitly invites: it fetched the log for
`test-cross-platform (macos-latest)` itself. One step alone contributed ~64.6 KB,
a `gh` read exceeded the CLI's own 120-second Bash-tool timeout and continued in
the background, and the outer 900 s bound expired with the delegated child still
live. `_run_implementer_agent` raised `ImplementerOrphanedSubagent` (exit 46),
the shepherd classified it `harness` and advanced `harness_failures` without
charging `review_attempts` — correct, blameless, and still useless, because with
`MAX_HARNESS_FAILURES = 3` the PR converges to `review-stuck` with no code
mutation ever attempted. This proposal makes the budget match the work: move
CI-log retrieval out of the implementer's envelope and bound it there, derive the
remediation envelope from the work class instead of a fixed literal, and
guarantee that nothing survives the end of an execution.

## User stories

- AS the Tier 3 shepherd I WANT failing required checks to arrive at the Tier 2
  implementer with the evidence already retrieved and bounded SO THAT the
  implementer spends its execution budget on deciding and mutating code rather
  than on fetching logs of unknown size.
- AS the Tier 2 implementer I WANT an execution envelope derived from the work
  class I was handed SO THAT a CI-remediation bundle is not judged against a
  budget sized for a review-findings bundle.
- AS a platform operator I WANT every operation in the remediation path to name
  the budget that bounds it SO THAT a timeout tells me which budget was exceeded
  instead of only that "900 s expired".
- AS a platform operator I WANT a timed-out log fetch or sub-agent to be
  terminated, not abandoned SO THAT no `gh` read or CLI child outlives the run
  that started it.
- AS a proposal owner I WANT harness failures to stay blameless SO THAT
  `review_attempts` is never charged for work the platform itself threw away.

## Acceptance criteria (EARS)

Retrieval (outside the implementer envelope)

- WHEN the shepherd builds a follow-up bundle containing at least one actionable
  `CheckBlocker` THE SYSTEM SHALL retrieve the failing check's CI log in the
  shepherd process, before the implementer subprocess is forked.
- WHILE retrieving a CI log THE SYSTEM SHALL bound each fetch by
  `SHEPHERD_CI_LOG_TIMEOUT_SECONDS` (default 45 s) passed as the `timeout`
  argument of `orchestrator.proc.run_capturing`, so the child process is killed
  by `subprocess.run` rather than abandoned.
- WHILE retrieving CI logs for one bundle THE SYSTEM SHALL stop retrieving once
  the cumulative wall-clock exceeds `SHEPHERD_CI_LOG_BUDGET_SECONDS` (default
  120 s) or once `CI_LOG_MAX_CHECKS` (default 3) checks have been fetched, and
  SHALL mark every remaining blocker with `log_status = "skipped-budget"`.
- WHEN a retrieved log exceeds `CI_LOG_MAX_CHARS` (default 8000) THE SYSTEM
  SHALL store a head-and-tail excerpt of at most that size, set
  `log_truncated = True`, and record the original byte count.
- WHILE assembling one bundle THE SYSTEM SHALL keep the sum of all log excerpts
  at or below `CI_LOG_TOTAL_MAX_CHARS` (default 24000).
- IF a CI-log fetch fails, times out, or returns malformed output THEN THE
  SYSTEM SHALL record `log_status` in `{"timeout", "unavailable"}`, keep the
  existing annotation-derived `excerpt`, and SHALL NOT raise — preserving
  `read_required_checks`' documented "never raises" contract.

Envelope (inside the implementer)

- WHEN `run_implementer.review_feedback_one` is invoked with a bundle whose
  `ci_failures` is non-empty THE SYSTEM SHALL classify the run's work class as
  `ci-remediation` (CI only) or `mixed` (CI plus review findings) and SHALL
  select the outer deadline from that class rather than from
  `IMPLEMENTER_TIMEOUT_SECONDS` unconditionally.
- WHEN the work class is `ci-remediation` or `mixed` THE SYSTEM SHALL compute the
  envelope as `min(IMPLEMENTER_TIMEOUT_CEILING_SECONDS,
  IMPLEMENTER_TIMEOUT_SECONDS + n_checks * IMPLEMENTER_CI_ANALYSIS_SECONDS)`
  where `n_checks` is capped at `CI_LOG_MAX_CHECKS`, and SHALL log the chosen
  envelope, the work class and the inputs it was derived from.
- WHILE any implementer run is in progress THE SYSTEM SHALL keep the existing
  `anyio.fail_after` as the single outer wall-clock bound, now parameterised by
  the computed envelope.
- IF the configured envelope cannot satisfy
  `envelope >= 2 * IMPLEMENTER_DRAIN_TIMEOUT_SECONDS + IMPLEMENTER_MUTATION_RESERVE_SECONDS`
  THEN THE SYSTEM SHALL log the violation at import time and SHALL clamp the
  drain sub-budget so the reserve for code mutation survives.
- WHEN the review-remediation lifecycle claim lease is computed
  (`run_implementer._review_claim_lease_default`) THE SYSTEM SHALL derive it from
  `IMPLEMENTER_TIMEOUT_CEILING_SECONDS + 2 * IMPLEMENTER_COMMAND_TIMEOUT_SECONDS`
  so no widened envelope can outlive its own claim.

Containment and cleanup

- WHILE the work class is `ci-remediation` or `mixed` THE SYSTEM SHALL install a
  `PreToolUse` guard hook that denies Bash commands matching unbounded CI-log
  retrieval (`gh run view ... --log`/`--log-failed`, `gh api .../logs`,
  `curl` of a `.../logs` URL) and SHALL return a deny reason that points the
  agent at the bundle's already-retrieved excerpt.
- WHEN the outer deadline expires with delegated tasks still live THE SYSTEM
  SHALL perform a shielded teardown bounded by
  `IMPLEMENTER_TEARDOWN_GRACE_SECONDS` (default 15 s) that disconnects the SDK
  client and terminates the CLI child before the process exits.
- WHEN teardown completes THE SYSTEM SHALL still exit
  `EXIT_ORPHANED_SUBAGENT` (46) and SHALL name both the envelope that expired and
  the live task ids in the message.
- IF the evidence in the bundle is insufficient for a code decision and the agent
  declines for that reason THEN THE SYSTEM SHALL exit with a dedicated bounded
  sentinel that the shepherd classifies as blameless (`harness` kind), SHALL NOT
  charge `review_attempts`, and SHALL remain bounded by `MAX_HARNESS_FAILURES`.

Blamelessness and evidence

- WHILE classifying any follow-up subprocess exit THE SYSTEM SHALL keep exit 46
  and the new bounded sentinel in the harness set of
  `run_shepherd._followup_code_sets()` so `review_attempts` is never charged for
  them.
- WHEN a CI-remediation follow-up completes THE SYSTEM SHALL log a one-line
  budget report (work class, envelope, retrieval time, bytes ingested, per-check
  `log_status`) so an operator can attribute a future timeout to a named budget.
- WHEN the repository's documentation is read THE SYSTEM SHALL state the three
  distinct invariants of #411 (ingestion correctness), #418 (admission and lock
  waiting must not consume the execution budget) and this issue (work newly added
  inside the execution must fit, or explicitly negotiate, the envelope).

## Out of scope

- Raising `IMPLEMENTER_TIMEOUT_SECONDS` globally as the fix. The base envelope
  for review-only work is unchanged; only the CI-remediation class gets a
  derived, capped widening that is paid for by removing retrieval from inside it.
- Changing what #411 classifies as actionable versus infrastructure
  (`ci_checks._classify`), or the required-check discovery path itself.
- Changing `MAX_REVIEW_ATTEMPTS`, `MAX_HARNESS_FAILURES`, or the
  `review-stuck` terminal semantics.
- The #418 admission/lock-waiting boundary. This proposal only guarantees that
  its own accounting does not contradict it.
- Retries or reruns of failing CI workflows (`ci-infra` arm in
  `run_shepherd.process_one`) — untouched.
- Any budget work for the issue-investigator or service-agent drivers, whose
  drain knobs (`ISSUE_INVESTIGATOR_DRAIN_TIMEOUT_SECONDS`,
  `SERVICE_AGENT_DRAIN_TIMEOUT_SECONDS`) sit outside an outer `fail_after` by
  design.

## Open questions

- Job id versus check-run id: for GitHub Actions a check-run id and the Actions
  job id coincide in practice, which makes `gh api repos/{repo}/actions/jobs/{id}/logs`
  the cheapest per-job log route. Task 1 must verify this against a real failing
  run before relying on it; the documented fallback is
  `gh run view <run_id> --log-failed` with the same time and size bounds applied
  to a larger payload. Proceeding with the job-scoped route as primary.
- Default numbers (45 s per fetch, 120 s per bundle, 8000 chars per check, 24000
  per bundle, 120 s analysis per check, 1800 s ceiling) are sized from the single
  observed incident (~64.6 KB for one step, 900 s exhausted). They are all env
  overridable and should be re-tuned once the budget report line has produced a
  few weeks of data.
- Whether an insufficient-evidence stop deserves its own counter rather than
  riding `harness_failures`. Charging it to `harness_failures` keeps it bounded
  and blameless today; a distinct counter is deferred until it is observed more
  than anecdotally.
- Whether the guard hook should also apply to the plain implement path (no
  bundle). Scoped to CI-remediation and mixed runs here to keep the blast radius
  minimal.
