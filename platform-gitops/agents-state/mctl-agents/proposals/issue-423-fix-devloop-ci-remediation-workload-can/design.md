# Design: issue-423-fix-devloop-ci-remediation-workload-can

## Current state

### How a required-check failure reaches the implementer today

1. `orchestrator/run_shepherd.py::_fetch_pr_snapshot` attaches per-context nodes
   to `PRSnapshot.check_contexts` (GraphQL `contexts(last:100)`).
2. `orchestrator/ci_checks.py::read_required_checks` normalises those nodes into
   `CheckBlocker` records. Evidence is annotation-derived only:
   `_fetch_annotations` runs `gh api repos/{repo}/check-runs/{id}/annotations`
   through `orchestrator.proc.run_capturing` with **no timeout argument**, keeps
   at most `CI_MAX_ANNOTATIONS = 10`, and `_bound_excerpt` truncates the rendered
   text at `CI_MAX_EXCERPT_CHARS = 1500`. No CI *log* is ever fetched.
3. `run_shepherd.decide()` returns `("address-review", Blockers(findings, checks))`
   where `checks = list(ci.actionable)`.
4. `run_shepherd.apply_followup()` builds the bundle: the summariser SDK call is
   skipped entirely for a CI-only bundle (`_fallback_bundle`), then
   `_augment_bundle_with_ci()` appends `bundle["ci_failures"]` — `check`,
   `workflow`, `job`, `step`, `conclusion`, `url`, `run_id`, `head_sha`,
   `excerpt` (tag-neutralised) — and writes it to a temp file.
5. The bundle path is passed to a forked
   `python -m orchestrator.run_implementer --review-feedback <path>`; exit codes
   are classified by `_followup_code_sets()` into
   refused / fenced / harness / deterministic / transient.
6. `run_implementer.review_feedback_one()` clones the repo, checks out the
   branch, builds the prompt via `_build_prompt(..., review_feedback=bundle)` —
   which renders `_render_ci_failures_section()` and, for a CI-only bundle,
   switches every framing line to the failing-check variant — then calls
   `_run_implementer_agent()`.

### Where the budget is applied

`run_implementer._run_implementer_agent()` (around L1761-1865) is the whole
enforcement surface:

```python
with anyio.fail_after(IMPLEMENTER_TIMEOUT_SECONDS):
    async with ClaudeSDKClient(options=options) as client:
        ...
        await drain_until_settled(stream, ledger,
                                  timeout_s=IMPLEMENTER_DRAIN_TIMEOUT_SECONDS)
```

- `IMPLEMENTER_TIMEOUT_SECONDS` (`orchestrator/options.py` L105, default `900`)
  is a module-level constant read directly at the call site. There is no
  per-run parameter and no notion of a work class.
- `IMPLEMENTER_DRAIN_TIMEOUT_SECONDS` (default `300`, clamped by
  `_positive_seconds`) is the sub-deadline for awaiting a delegated child, and
  exists for *classification*, not liveness (see the `orchestrator/subagent_wait.py`
  module docstring).
- `IMPLEMENTER_COMMAND_TIMEOUT_SECONDS` (default `300`) bounds each synchronous
  git/gh command run by `run_implementer._run`, i.e. the work **around** the SDK
  call, not inside it.
- On `TimeoutError` with `ledger.live` non-empty the driver raises
  `ImplementerOrphanedSubagent` -> exit `EXIT_ORPHANED_SUBAGENT = 46`; the
  shepherd counts `harness_failures` and never charges `review_attempts`
  (`run_shepherd.process_one`, L2909-2940). That classification is correct and
  is preserved verbatim by this proposal.

### Why #652 failed

Nothing in the path above retrieves a CI log, and nothing forbids the agent from
retrieving one. The prompt hands it `Run: <url>` plus a 1500-char annotation
excerpt; for a cross-platform test failure the annotations are empty or
uninformative, so the agent ran the log read itself. Three properties then
combine:

- the payload is unbounded (one step contributed ~64.6 KB);
- the Claude Code Bash tool backgrounds a command that exceeds its own
  ~120 s tool timeout, so the prompt's existing "Never defer work to the
  background" ground rule (L1545-1551) cannot prevent it — backgrounding is the
  CLI's choice, exactly as `subagent_wait.py` documents for async sub-agent
  launch;
- the retrieval happens **inside** the 900 s envelope that also has to cover
  analysis and code mutation.

The result is the observed orphan: outer bound expired, one `local_agent` task
still live, exit 46, no mutation, and after three such ticks a `review-stuck`
flip that reflects the harness, not the proposal.

### Second-order coupling

`run_implementer._review_claim_lease_default()` (L742-760) derives the review
lifecycle claim lease from `IMPLEMENTER_TIMEOUT_SECONDS + 2 *
IMPLEMENTER_COMMAND_TIMEOUT_SECONDS` with a 30-minute floor. Any widening of the
execution envelope must widen that lease in the same commit, or a longer run
expires its own claim mid-flight and the push-site check stands it down as
`CLAIM_UNCLAIMED`.

## Proposed solution

Four changes, in the order the work flows.

### 1. Bounded CI-log retrieval, in the shepherd, outside the envelope

Extend `orchestrator/ci_checks.py`:

- New tunables next to the existing ones:
  `CI_LOG_MAX_CHARS = 8000`, `CI_LOG_TOTAL_MAX_CHARS = 24000`,
  `CI_LOG_MAX_CHECKS = 3`, plus env-read
  `SHEPHERD_CI_LOG_TIMEOUT_SECONDS` (45) and `SHEPHERD_CI_LOG_BUDGET_SECONDS`
  (120), and a kill switch `SHEPHERD_CI_LOG_FETCH` (default on).
- `CheckBlocker` gains `log_excerpt: str = ""`, `log_truncated: bool = False`,
  `log_bytes: int = 0`, `log_status: str = "skipped"`. All defaulted, so every
  existing constructor in `tests/test_ci_checks.py` and `tests/test_run_shepherd.py`
  keeps compiling.
- New `fetch_failure_logs(repo, blockers, *, now) -> tuple[CheckBlocker, ...]`
  which, for each actionable blocker in order and while the cumulative budget
  and check count allow, runs
  `gh api repos/{repo}/actions/jobs/{job_id}/logs` (primary; `job_id` is the
  check-run id) or `gh run view <run_id> --log-failed` (fallback) through
  `run_capturing(..., timeout=SHEPHERD_CI_LOG_TIMEOUT_SECONDS)`.
  `subprocess.run`'s `timeout` kills the child, which is the cancellation
  guarantee for retrieval: a wedged `gh` cannot survive the call that made it.
  Each payload is reduced by a `_bound_log(text)` helper that keeps a head slice
  and a tail slice with an explicit `...(N bytes elided)...` marker — the tail
  matters because a build log puts the failure at the end.
- The existing `_fetch_annotations` call also gains the same explicit
  `timeout=SHEPHERD_CI_LOG_TIMEOUT_SECONDS`; today it has none at all, which is
  the same unbounded-retrieval defect one layer down.
- `read_required_checks` stays the "never raises" entry point: retrieval failures
  degrade to `log_status in {"timeout", "unavailable"}` and the annotation
  excerpt is kept.

Retrieval therefore executes in the shepherd tick, is bounded in time and bytes,
and is provably outside the implementer's `fail_after` because it happens before
`apply_followup` forks the subprocess.

### 2. The bundle carries the evidence and the work class

`run_shepherd._augment_bundle_with_ci()` additionally emits, per record,
`log_excerpt` (tag-neutralised exactly like `excerpt` is today), `log_status`,
`log_truncated`; and at the top level `bundle["work_class"]`
(`"ci-remediation"` | `"mixed"`; absent means the pre-#411 `"review"` shape) plus
`bundle["budget_report"]` with retrieval seconds and bytes.

`run_implementer._render_ci_failures_section()` renders the log excerpt under a
`Log excerpt (bounded, {status})` sub-heading, and states when it was truncated
so the agent knows it is reading a slice, not the whole log. The rendering stays
deterministic and never passes through the summariser SDK, preserving #411's
"cannot be model-rewritten" property.

### 3. Work-class-derived execution envelope

New in `orchestrator/options.py`:

```python
IMPLEMENTER_CI_ANALYSIS_SECONDS = _positive_seconds(
    "IMPLEMENTER_CI_ANALYSIS_SECONDS", default=120.0)
IMPLEMENTER_TIMEOUT_CEILING_SECONDS = _positive_seconds(
    "IMPLEMENTER_TIMEOUT_CEILING_SECONDS", default=1800.0)
IMPLEMENTER_MUTATION_RESERVE_SECONDS = _positive_seconds(
    "IMPLEMENTER_MUTATION_RESERVE_SECONDS", default=180.0)

def implementer_envelope(work_class: str, n_checks: int = 0) -> float:
    if work_class not in ("ci-remediation", "mixed"):
        return IMPLEMENTER_TIMEOUT_SECONDS
    n = max(0, min(n_checks, CI_LOG_MAX_CHECKS))
    return min(IMPLEMENTER_TIMEOUT_CEILING_SECONDS,
               IMPLEMENTER_TIMEOUT_SECONDS + n * IMPLEMENTER_CI_ANALYSIS_SECONDS)
```

This is deliberately *not* a global timeout increase: the review-only class keeps
900 s exactly, the widening is proportional to a bounded count of bounded
evidence items, and it is capped at a declared ceiling. The widening is also
*paid for*: the retrieval it used to have to fund has been removed from inside
the envelope by change 1.

`_run_implementer_agent(repo_dir, prompt, proposal_dir, *, envelope_s, work_class)`
takes the envelope as a parameter, uses it in `anyio.fail_after`, and names it in
all three failure messages (the orphan raise, the post-drain warning, and the
plain operation timeout) so a log line says *which* budget expired.
`review_feedback_one` derives the class with a new `_bundle_work_class(bundle)`
(`ci_failures` and no `summaries` -> `ci-remediation`; both -> `mixed`;
otherwise `review`), reusing the already-present `_bundle_is_ci_only`.

A module-level `validate_budget_contract()` in `options.py` asserts
`envelope >= 2 * IMPLEMENTER_DRAIN_TIMEOUT_SECONDS + IMPLEMENTER_MUTATION_RESERVE_SECONDS`
for every work class; on violation it logs loudly and clamps the effective drain
sub-budget rather than raising — the same "loud and harmless, never silent and
unbounded" policy `_positive_seconds` already documents.

`_review_claim_lease_default()` changes its `bound` to
`IMPLEMENTER_TIMEOUT_CEILING_SECONDS + 2 * IMPLEMENTER_COMMAND_TIMEOUT_SECONDS`,
so the lease covers the widest envelope any work class can select.

### 4. Containment: deny unbounded retrieval, and never leave anything running

- `options.build_implementer_agent_options(repo_dir, model, proposal_dir, *, work_class="review")`
  composes `_command_audit_hooks()` with a new `_ci_log_guard_hook()` for the
  `ci-remediation` and `mixed` classes. The hook is a `PreToolUse` matcher on
  `Bash` that inspects `tool_input["command"]` and returns a deny decision for
  `gh run view` with `--log`/`--log-failed`, `gh api` on a `/logs` path, and
  `curl`/`wget` of a `.../logs` URL, with a reason that points at the bundle's
  already-retrieved excerpt and at the refusal marker as the correct escape.
  This is the enforcement the prompt cannot provide: backgrounding a slow Bash
  command is the CLI's decision, so the only reliable control is not letting the
  command start. The existing audit hook behaviour is unchanged for every other
  driver, which matters because `subagent_wait.py` depends on `hooks` being
  truthy for the drain to work at all.
- The prompt's CI variant gains one ground rule: the log evidence in the bundle
  is what exists; do not fetch more; if it is genuinely insufficient, stop and
  say so rather than start an open-ended retrieval.
- `_run_implementer_agent`'s `TimeoutError` handler performs a bounded, shielded
  teardown before re-raising:
  `with anyio.CancelScope(shield=True): with anyio.move_on_after(IMPLEMENTER_TEARDOWN_GRACE_SECONDS): await client.disconnect()`
  and, if the SDK transport exposes its child process, `terminate()` then
  `kill()`. Without the shield the teardown awaits inside an already-cancelled
  scope and is skipped, which is how a CLI child can outlive the exit. The
  handler keeps raising `ImplementerOrphanedSubagent` (exit 46) afterwards.
- A new sentinel `EXIT_CI_EVIDENCE_INSUFFICIENT = 50` lets a run end
  deliberately and boundedly when the bounded excerpt cannot support a decision.
  It joins the **harness** set in `run_shepherd._followup_code_sets()`: blameless
  (never charges `review_attempts`), still bounded by `MAX_HARNESS_FAILURES` so
  it cannot loop forever.

### 5. Documentation

`docs/adr/011-execution-budget-contract.md` records the coverage table — which
operation is bounded by which budget — and states the three invariants side by
side so #411, #418 and this issue stay distinct:

| Operation | Bounded by | Inside the implementer envelope? |
|---|---|---|
| Required-check discovery, annotations | `SHEPHERD_CI_LOG_TIMEOUT_SECONDS` per call | no |
| CI-log retrieval | per-fetch timeout + per-bundle budget + byte caps | no |
| Admission / claim acquisition | #418's boundary | no |
| Clone, fetch, push | `IMPLEMENTER_COMMAND_TIMEOUT_SECONDS` per command | no |
| Model turns, delegated sub-agents, drain | `implementer_envelope(work_class, n)` | yes |
| Awaiting one delegated child | `IMPLEMENTER_DRAIN_TIMEOUT_SECONDS` | yes (nested) |
| Teardown after expiry | `IMPLEMENTER_TEARDOWN_GRACE_SECONDS` (shielded) | no (after) |

README's budget section and `.env.example` get the new knobs with the same
"lengthen-only / clamped" framing the file already uses.

## Alternatives

1. **Raise `IMPLEMENTER_TIMEOUT_SECONDS` to 1800 globally.** One line, and the
   issue explicitly rules it out. It leaves retrieval unbounded inside the
   envelope, so the next 200 KB log reproduces the orphan at the larger number,
   and it silently widens every review-only run and (via
   `_review_claim_lease_default`) every review claim lease. Dropped.

2. **Let the implementer fetch logs, but through a sanctioned bounded wrapper
   tool** (an MCP tool or a `scripts/fetch_ci_log.sh` with `timeout` and `head`).
   Keeps the evidence fresh at decision time and is a smaller diff in
   `ci_checks.py`. Dropped because the retrieval still runs inside the execution
   envelope — the budget it consumes is variable and the agent decides how many
   times to call it — and because it requires the guard hook anyway to stop the
   unwrapped command. Retrieval in the shepherd is the only version where the
   cost is paid outside the bound it threatens.

3. **Split the follow-up into two executions: a retrieval/analysis run that
   writes an evidence file, then a mutation run.** The cleanest separation of
   sub-budgets, and it makes the mutation reserve structural rather than
   advisory. Dropped as too large for this issue: it doubles clone cost per tick,
   needs a new intermediate artefact and its own lifecycle claim semantics, and
   the shepherd's attempt accounting (`review_attempts`, `harness_failures`,
   `refusals`) would have to learn about half-attempts. Recorded here as the
   natural follow-up if bounded retrieval plus a derived envelope still proves
   insufficient.

4. **Cap only the payload, keep the fixed 900 s envelope.** Attractive because it
   avoids touching timing at all. Dropped because the analysis of three bounded
   logs plus a cross-platform test fix is genuinely more work than the pre-#411
   review-finding case, and refusing to acknowledge that is what produced the
   mismatch this issue is about. The derived envelope is capped and logged, which
   is the difference between a contract and a blind increase.

## Platform impact

**Migrations.** None. No schema in `.status.yaml` changes; `ci_blockers` /
`ci_blockers_head` keep their meaning. New `CheckBlocker` fields are defaulted,
so pickled/constructed instances in existing tests are unaffected. New bundle
keys (`log_excerpt`, `log_status`, `work_class`, `budget_report`) are additive
and the implementer's `_load_review_feedback` already documents that unknown
fields are ignored, so an old implementer image reading a new bundle degrades to
today's behaviour.

**Backward compatibility.** A new shepherd with an old implementer: the extra
bundle keys are ignored, the CI section renders as today. An old shepherd with a
new implementer: no `work_class`, so `_bundle_work_class` falls back to
`ci-remediation`/`review` from `ci_failures`/`summaries` exactly as
`_bundle_is_ci_only` does now. `SHEPHERD_CI_LOG_FETCH=0` restores pre-change
retrieval behaviour without a redeploy.

**Resource impact.** Up to 3 extra `gh` calls per CI-remediation bundle, each
capped at 45 s, at most 120 s per tick — charged to the shepherd tick, which has
no wall-clock `fail_after` of its own and is bounded by the CronWorkflow limit.
Prompt growth is capped at `CI_LOG_TOTAL_MAX_CHARS` (24000 chars, ~6-8k tokens),
which sits inside `IMPLEMENTER_BUDGET_USD = 3.00`; the budget report line makes
the real cost observable.

**Risks and mitigations.**

- *Widened envelope slows a tick that is already slow.* Mitigated by the
  ceiling, by `CI_LOG_MAX_CHECKS` capping the multiplier, and by the fact that
  only `ci-remediation`/`mixed` runs widen at all.
- *Claim lease drift.* Mitigated by deriving `_review_claim_lease_default` from
  the ceiling in the same commit, with a test pinning
  `lease >= implementer_envelope(worst case) + 2 * command timeout`.
- *Guard hook denies a command the agent legitimately needed.* Mitigated by the
  deny reason naming the bundle excerpt and the refusal path, by the pattern list
  being narrow (log retrieval only), and by the work-class scoping — a plain
  implement run is unaffected.
- *Guard hook regression breaks the drain precondition.* `subagent_wait.py`
  requires `hooks` to be truthy for the SDK to hold the CLI open past a result
  frame. The new hook is *composed with*, never replaces, `_command_audit_hooks()`;
  `tests/test_options.py` gets an assertion that every builder still passes a
  non-empty `hooks` mapping.
- *Attacker-influenceable CI logs reach a prompt.* Already the situation for
  `excerpt`; log text is passed through the same `_neutralize_findings_tags`
  before rendering, and it is never routed through the summariser SDK.
- *Job-id assumption wrong for some checks.* `StatusContext` blockers have no
  `check_run_id` or `run_id` at all and simply get `log_status = "unavailable"`;
  the `gh run view --log-failed` fallback covers Actions runs where the
  job-scoped route 404s.
