# Design: issue-411-fix-shepherd-feed-failing-required-pr-ch

## Current state

Everything below was read in this clone of `mctlhq/mctl-agents`.

### The shepherd's view of CI is one boolean, derived from two aggregates

`orchestrator/run_shepherd.py::_fetch_pr_snapshot` (L1360-1483) issues a single
GraphQL query whose only CI selection is `statusCheckRollup{state}` (L1371).
There are no per-check nodes in the query — no name, no conclusion, no
`isRequired`, no annotations, no run identity. From that aggregate it derives
one field (L1461-1465):

```python
checks_green = (
    rollup_state == "SUCCESS"
    or merge_state_status in {"UNSTABLE", "HAS_HOOKS"}
    or (not rollup_state and merge_state_status == "CLEAN")
)
```

`PRSnapshot` (L965-986) carries `merge_state_status` and `checks_green: bool  #
required checks all SUCCESS` and nothing else about checks.

### `decide()` builds its blocker set from review findings only

`decide()` (L1816-1890) is pure and ordered:

1. `pr.merged` / `pr.closed_unmerged` / `pr.is_draft` shortcuts.
2. `if not codex_review.has_responded: return ("wait", None)` (L1843).
3. `findings = codex_review.fresh_findings_p1_p2(at=pr.head_sha, since=pr.head_pushed_at)`;
   `if findings: return ("address-review", findings)` (L1863-1865).
4. `head_verdict` gates (L1871-1879).
5. `if pr.merge_state_status not in MERGEABLE_STATES: return ("wait", None)` (L1880).
6. `if not pr.checks_green: return ("wait", None)` (L1883).
7. settle window, then `merge` / `defer-merge`.

The blocker set at step 3 is exclusively `CodexFinding` objects
(`@dataclass CodexFinding`, L880-894) produced by `read_codex_review` (L1566+)
from the two `GATING_BOTS`. CI is consulted only at steps 5 and 6, and only to
return `wait`.

### Why mctlhq/mctl-agents#409 wedged

On that PR Claude APPROVED the head with zero P1/P2, so step 3 produced no
findings and step 4 passed with `head_verdict == "APPROVED"`. One required check
(`PR validation / lint`, defined in `.github/workflows/pr-validation.yml` L232-264,
whose `Run mypy` step is the step that failed) was red, so GitHub reported
`mergeStateStatus: BLOCKED` and step 5 returned `("wait", None)` — before
`checks_green` was even consulted.

`process_one` (L2345-2766) treats `wait` as a no-op: `if decision == "wait":
return ShepherdResult(ref=ref, decision="wait")` (L2417-2418). No counter moves,
no `.status.yaml` write occurs, and the `MAX_REVIEW_ATTEMPTS` → `review-stuck`
arm (L2467-2477) is only reachable from the `address-review` branch. The
proposal therefore stays `implemented` with `review_attempts: 5` forever, and the
`mypy` error at `orchestrator/run_implementer.py:3185` never reaches an agent.

### The remediation channel that already exists

`apply_followup` (L2096-2260) builds a bundle with `_format_bundle_via_sdk`
(L1937-1998) or `_fallback_bundle` (L2063-2089), whose schema is
`{"p1": bool, "p2": bool, "summaries": [str, ...]}`, writes it to a temp JSON
file, and forks:

```
python -m orchestrator.run_implementer --service <s> (--slug <slug> | --adopted-pr <url>)
    --review-feedback <bundle.json> --refusal-out <refusal.json> [--state-dir <p>]
```

Exit codes are classified into `FollowupKind` (`refused` / `fenced` / `harness` /
`deterministic` / `transient`, L2240-2259) and `process_one` maps each kind onto
a distinct counter (`review_attempts`, `harness_failures`, `refusals` +
`refusals_head`).

On the receiving side, `orchestrator/run_implementer.py::_load_review_feedback`
(L1512-1535) validates exactly two things — the path exists and the top level is
a JSON object — and its docstring states "fields beyond the documented set are
ignored". `_render_review_feedback` (L1538-1573) reads only `summaries`, `p1`,
`p2` and emits a `## Code review findings (address each)` Markdown section that
`_build_prompt` (L1365-1394, call site L1841) interpolates into the follow-up
prompt.

The shepherd sub-agent prompt at
`agents/_shepherd/.claude/agents/shepherd.md` describes the bundle purely as
P1/P2 review findings and says nothing about checks.

### Test-side state

`tests/test_run_shepherd.py` (~5,480 lines) builds every `PRSnapshot` through
`make_pr(...)` (L47-85), which takes `checks_green` as a pre-computed bool and
has no rollup parameter. `_route_gh(...)` (L1608) routes `_gh_api_json` by
endpoint suffix for the review endpoints. `test_decide_wait_ci_pending` (L1338)
is the only `decide()` test for red CI and asserts exactly today's terminal
`wait`. `test_fetch_pr_snapshot_unstable_yields_checks_green` (L1409) and
`test_checks_green_no_rollup_clean_merge_state` (L1460) pin the derivation.
`tests/test_pr_adoption.py:58-71` and `tests/test_temporal_activities.py:493-494`
also construct `PRSnapshot` directly, so any new field must default.

## Proposed solution

Introduce a second, structurally distinct blocker source alongside the semantic
one, join the two into a single head-pinned blocker set inside `decide()`, and
widen the remediation bundle with an additive key. No new tier, no new cron, no
new attempt budget.

### 1. New module `orchestrator/ci_checks.py`

Kept out of `run_shepherd.py` (already 3,485 lines) and import-light so the
Temporal reconcile activities that reuse this module's read-only helpers are not
affected (`#149` isolation, guarded by `tests/test_worker_isolation.py`).

Dataclasses:

```python
@dataclass(frozen=True)
class CheckBlocker:
    name: str                 # "lint" / context name
    workflow: str | None      # "PR validation"
    job: str | None
    step: str | None
    conclusion: str           # FAILURE / TIMED_OUT / CANCELLED / ...
    url: str | None           # detailsUrl / targetUrl
    run_id: str | None        # checkSuite.workflowRun.databaseId, as text
    head_sha: str             # the SHA this was observed on
    excerpt: str              # bounded failure text (annotations first)
    kind: str                 # "actionable" | "infrastructure"
    required: bool

@dataclass(frozen=True)
class CIStatus:
    known: bool               # False => probe failed; caller fails closed
    head_sha: str
    pending: bool             # a required check is QUEUED/IN_PROGRESS
    blockers: tuple[CheckBlocker, ...]        # required + failing, head-pinned

    @property
    def actionable(self) -> tuple[CheckBlocker, ...]: ...
    @property
    def infrastructure(self) -> tuple[CheckBlocker, ...]: ...
```

`read_required_checks(pr: PRSnapshot) -> CIStatus` is the single entry point.

Fetching. The existing `_fetch_pr_snapshot` GraphQL query is extended to select
per-context rollup nodes off the same `commits(last:1)` node it already reads —
which is what makes the result head-pinned by construction:

```
commits(last:1){nodes{commit{oid committedDate pushedDate
  statusCheckRollup{state contexts(last:100){nodes{
    __typename
    ... on CheckRun{name status conclusion detailsUrl isRequired(pullRequestNumber:$number)
                    title summary checkSuite{databaseId workflowRun{databaseId url workflow{name}}}}
    ... on StatusContext{context state targetUrl isRequired(pullRequestNumber:$number)}
  }}}}}}
```

Every node is discarded unless the enclosing `commit.oid == pr.head_sha`. That
is the whole staleness story: a failure observed on a previous head is not
merely filtered out, it is never fetched.

Requiredness resolution, in order: per-context `isRequired` when present;
otherwise the base branch's `branchProtectionRule.requiredStatusCheckContexts`
(selected in the same query via `baseRef{branchProtectionRule{...}}`); otherwise
`required=False` (advisory). Fail-open on requiredness is safe because
`mergeStateStatus` remains a fail-closed merge backstop — GitHub still refuses
the merge — whereas fail-closed on requiredness would let any experimental
workflow start burning the attempt budget.

Failure text. For a `CheckRun` with a failing conclusion, fetch annotations via
`gh api repos/{repo}/check-runs/{id}/annotations` (bounded: first
`CI_MAX_ANNOTATIONS`, default 10) and render each as
`path:start_line: message`. This is exactly the shape a `mypy`/`ruff` failure
produces, and it is what makes the #409 case a one-line, directly actionable
excerpt. Fall back to `title`/`summary`/`text` from the check output. The
rendered excerpt is truncated to `CI_MAX_EXCERPT_CHARS` (default 1,500) per
check, mirroring the `MAX_NOTES_CHARS` philosophy already in this module.

Classification (`kind`):

- Conclusions `CANCELLED`, `TIMED_OUT`, `STALE`, `ACTION_REQUIRED`, `SKIPPED`,
  `NEUTRAL`, `STARTUP_FAILURE` → `infrastructure`, unconditionally.
- Conclusion `FAILURE` with at least one file-anchored annotation → `actionable`.
- Conclusion `FAILURE` with no annotations and an excerpt matching the
  infrastructure signature set (`_CI_INFRA_PATTERNS`: runner lost / the runner
  has received a shutdown signal / connection reset / TLS handshake / 429 rate
  limit / no space left on device / `The operation was canceled`) →
  `infrastructure`.
- Everything else → `actionable`. Unclassifiable failures default to actionable
  deliberately: a wrong "actionable" costs one attempt out of five, a wrong
  "infrastructure" reinstates exactly the silent wedge this change removes.

Probe failures (`subprocess.CalledProcessError`, malformed JSON) return
`CIStatus(known=False, ...)` rather than raising, matching how
`read_codex_review` degrades on a failed fetch (L1596-1599).

### 2. `decide()` joins the two blocker sources

`decide()` gains a third positional-or-keyword parameter `ci: CIStatus | None =
None` so every existing call site and test keeps working (`None` reproduces
today's behaviour bit for bit). The payload of `address-review` widens from
`list[CodexFinding]` to a small container:

```python
@dataclass(frozen=True)
class Blockers:
    findings: list[CodexFinding]
    checks: list[CheckBlocker]
```

A `CheckBlocker` is never coerced into a `CodexFinding` and never given a P1/P2
severity — the acceptance criterion "without pretending that a check failure is
a review comment" is a type-level property here, not a convention.

New ordering inside `decide()`:

```
... merged / closed / draft (unchanged) ...
if not codex_review.has_responded: return ("wait", None)      # unchanged (see Open questions)
findings = codex_review.fresh_findings_p1_p2(...)             # unchanged
checks   = ci.actionable if (ci and ci.known) else ()
if findings or checks: return ("address-review", Blockers(list(findings), list(checks)))
... head_verdict gates (unchanged) ...
if ci and ci.known and ci.infrastructure: return ("ci-infra", list(ci.infrastructure))   # NEW
if ci and not ci.known:                  return ("ci-unknown", None)                     # NEW
if ci and ci.known and ci.pending:        return ("wait", None)                          # NEW
if pr.merge_state_status not in MERGEABLE_STATES: return ("wait", None)   # unchanged backstop
if not pr.checks_green: return ("wait", None)                            # unchanged backstop
... settle window, merge / defer-merge (unchanged) ...
```

`merge` and `defer-merge` are now unreachable while any required check on the
current head is failing, or while the probe is unknown — the fail-closed
requirement — because those arms are all returned before the merge arm. The two
legacy backstops stay: they are cheap, they are what protects the
`ci=None` path, and they catch required failures GitHub knows about that our
probe somehow missed.

### 3. `process_one` handles the two new decisions and widens the existing one

`address-review` (L2460-2722) is unchanged in structure. It passes the
`Blockers` container to `apply_followup`, and the `MAX_REVIEW_ATTEMPTS` note
(L2471-2475) becomes an enumeration of what is actually unresolved, e.g.

```
Current-head blockers persisted across 5 follow-up attempts:
2 review finding(s) (claude[bot]); 1 failing required check (PR validation / lint).
Human triage required.
```

`ci-infra`: re-run the failing required runs at most
`SHEPHERD_CI_INFRA_RERUN_MAX` (default 2) times per head SHA via
`gh run rerun <run_id> --failed`, tracked by two new `.status.yaml` fields
`ci_infra_retries` / `ci_infra_head`, reset on head change exactly like
`refusals` / `refusals_head` (L2533-2534). `review_attempts` is never charged —
the proposal is blameless. When the budget is exhausted, flip to `review-stuck`
with a note naming the check and stating the infrastructure classification,
which follows the precedent set by `MAX_HARNESS_FAILURES` (L2585-2602).

`ci-unknown`: `wait`, plus a new `ci_probe_failures` counter; at
`SHEPHERD_CI_PROBE_FAILURES_MAX` (default 6) flip to `review-stuck` with a note
naming the probe outage and stating that `review_attempts` was never charged.
Any successful probe clears the counter.

Self-clearing falls out of head pinning: a follow-up push moves `head_sha`, the
next probe reads the new head only, and `ci_infra_head` / `ci_blockers_head`
are rewritten (or deleted when the blocker set is empty), so a green check
removes its blocker with no operator action.

The per-tick operator log (L2408-2415) gains
`ci_known=… ci_required_failed=<n> ci_checks=<comma-separated names>`.

### 4. Bundle and prompt changes

`apply_followup(service, slug, blockers, ...)` keeps its signature shape but
takes `Blockers`. `_format_bundle_via_sdk` continues to summarise only
`blockers.findings` through the SDK (the sub-agent's job is severity triage,
which CI failures do not have); the CI records are appended deterministically,
never model-rewritten, so a run/URL/SHA cannot be hallucinated:

```json
{
  "p1": false, "p2": false, "summaries": [],
  "head_sha": "143312e4858cc1a3a6a5e99f66af5894a0ab85ec",
  "ci_failures": [
    {"check": "lint", "workflow": "PR validation", "job": "lint",
     "step": "Run mypy", "conclusion": "FAILURE",
     "url": "https://github.com/mctlhq/mctl-agents/actions/runs/…",
     "run_id": "…", "head_sha": "143312e4…",
     "excerpt": "orchestrator/run_implementer.py:3185: error: Incompatible types in assignment (expression has type \"dict[str, Any] | None\", variable has type \"bool\")"}
  ]
}
```

`ci_failures` is additive, and `_load_review_feedback` already ignores unknown
keys, so an older implementer paired with a newer shepherd degrades to today's
behaviour rather than crashing. `_render_review_feedback` gains a second,
separately headed section — `## Failing required CI checks (fix each)` — emitted
after the review-findings section, and the "(No summaries in bundle …)"
early-return is moved so a CI-only bundle still renders its CI section. The
excerpt text is routed through `_neutralize_findings_tags`-equivalent escaping
before it reaches any prompt, because check output is attacker-influenceable on
a fork PR the same way a review comment body is.

`agents/_shepherd/.claude/agents/shepherd.md` gains a short paragraph stating
that CI failures may accompany the findings, are supplied deterministically by
the Python, must not be summarised, invented, or reclassified, and that the
model still emits only `{"p1", "p2", "summaries"}`.

## Alternatives

**A. Flip straight to `review-stuck` when `mergeStateStatus == BLOCKED` and the
review is clean.** Two lines in `decide()`, removes the infinite wait, and
requires no new API surface. Dropped: it converts a silent wedge into a loud
one without repairing anything. The #409 failure is a single-line type error the
implementer fixes in one attempt; escalating it to a human is a worse outcome
than the loop the issue asks for, and the issue's acceptance criteria require
remediation evidence, not just a terminal state.

**B. Reuse `gh pr checks <url> --required --json name,state,link` instead of
extending the GraphQL query.** Much less code, and `--required` answers the
requiredness question directly. Dropped: it returns no annotations, no check-run
id, no job/step, and no commit OID, so both the "concise failure text" and the
"failure from an older head is ignored" criteria would need a second call
anyway — and the PR-level `gh pr checks` output is not commit-pinned, which is
exactly the property the union blocker set depends on.

**C. Synthesise a `CodexFinding` per failing check (severity `P1`, `author`
`"ci"`) and change nothing downstream.** Zero changes to `decide()`'s signature,
`apply_followup`, the bundle schema, or the implementer. Dropped: the issue
explicitly forbids pretending a check failure is a review comment, and the
practical consequences are real — such a finding would flow through
`fresh_findings_p1_p2`'s `created_at` freshness filter (which has no meaning for
a check run), would be rewritten by the SDK summariser (losing the run URL and
SHA), and would corrupt the `p1`/`p2` severity signal the implementer prompt
branches on.

**D. Let the implementer poll CI itself after pushing a follow-up.** Dropped:
it moves head-pinning and the attempt budget inside a paid agent loop, creates a
second remediation owner in violation of the issue's ownership section, and
makes the shepherd's `.status.yaml` projection stop describing why a PR is
blocked.

## Platform impact

**Migrations.** None. `.status.yaml` gains four optional keys
(`ci_infra_retries`, `ci_infra_head`, `ci_probe_failures`, `ci_blockers_head`),
all absent-means-zero and all written through the existing
`update_status` / `update_status_file` read-modify-write path, which already
preserves unknown fields (`orchestrator/proposal_state.py` module docstring).
No proposal needs rewriting.

**Backward compatibility.**
- `decide(pr, codex_review, now=None, *, fix_only=False)` gains `ci=None`; with
  `ci=None` the function is behaviourally identical, so the ~40 existing
  `decide()` tests are untouched.
- `PRSnapshot` gains no required field. New optional fields default, protecting
  `tests/test_pr_adoption.py:58-71` and `tests/test_temporal_activities.py:493`.
- The bundle key is additive and `_load_review_feedback` ignores unknown keys, so
  shepherd and implementer can be deployed in either order.
- `orchestrator/pr_adoption.py` rides the `Blockers` payload for free via
  `process_one`'s existing `adopted_pr=` plumbing (L2498).

**Resource impact.** Per shepherd tick per open PR: the existing GraphQL call
grows by one nested connection (`contexts(last:100)` plus a branch-protection
selection) — same request, larger response — plus at most one REST annotations
call per *failing required* check run, which is zero on the healthy path. The
infra re-run path adds at most `SHEPHERD_CI_INFRA_RERUN_MAX` `gh run rerun`
calls per head SHA. No new paid model calls: the CI records bypass the SDK.

**Risks and mitigations.**
- *Misclassifying a flaky test as a code defect* burns one attempt out of five
  and the agent will likely refuse (exit 47), which the existing `MAX_REFUSALS`
  logic already handles without charging the review budget. Mitigated further by
  the infrastructure signature set being configurable.
- *Misclassifying a real defect as infrastructure* re-runs it up to twice and
  then lands in `review-stuck` with a named check — visible, not silent. This is
  the reason the unclassifiable default is `actionable`.
- *`isRequired` unavailable on some schema/ruleset shapes* degrades to the
  branch-protection context list and then to advisory; the `MERGEABLE_STATES`
  and `checks_green` backstops are retained so the merge gate never loosens.
- *Prompt injection via check output* on a fork PR: the excerpt is tag-neutralised
  and bounded before it reaches any prompt, matching the `<findings>` fence
  treatment at `run_shepherd.py` L1901-1935 and L1957-1960.
- *`contexts(last:100)` truncation* on a repo with more than 100 contexts: log a
  warning and treat the probe as `known=False` for that tick (fail closed) rather
  than silently merging on a partial view.
- *A newly-blocking merge gate could stall PRs that merge today* where a required
  check is red but nobody noticed. That is the intended behaviour change, and it
  now terminates at `review-stuck` instead of waiting forever.
