# Design: issue-430-fix-implementer-bound-long-running-local

## Current state

### The envelope and who knows about it

`orchestrator/run_implementer.py:_run_implementer_agent()` (line 1897) is the
single place the Tier 2 implementer's SDK run is bounded:

```python
with anyio.fail_after(envelope_s):
    async with ClaudeSDKClient(options=options) as client:
        ...
        async for message in stream:
            ...
```

`envelope_s` is derived by the caller — `review_feedback_one()` at line 2209
does `work_class = _bundle_work_class(bundle)`, `n_checks = len(bundle.get
("ci_failures") or [])`, `envelope_s = implementer_envelope(work_class,
n_checks=n_checks)` — and passed through `functools.partial` into
`anyio.run(...)` at line 2213. `options.implementer_envelope()` (line 220) is
`IMPLEMENTER_TIMEOUT_SECONDS + n * IMPLEMENTER_CI_ANALYSIS_SECONDS`, capped at
`IMPLEMENTER_TIMEOUT_CEILING_SECONDS`; on #652 that produced the 1020s figure
in the issue (900 + 1 x 120).

The crucial property: **`envelope_s` never crosses into the agent's own
execution.** `build_implementer_agent_options()` (`orchestrator/options.py:553`)
receives `repo_dir`, `model`, `proposal_dir` and `work_class` — no deadline. So
no hook, no tool call and no prompt line inside the run knows how much budget
is left. The agent's commands are bounded only by the Claude Code CLI's own
Bash-tool timeout, which ADR-011 (`docs/adr/011-execution-budget-contract.md`,
"Containment") records as *backgrounding* an over-running command rather than
failing it.

### Why the background shell escapes entirely

`orchestrator/subagent_wait.py:69` defines

```python
AWAITED_TASK_TYPES = frozenset({"local_agent", "local_workflow"})
```

with the comment "Background *shells* are excluded on purpose, by the SDK and
therefore by us: they need not ever reach a terminal status, so awaiting one
would hang." That is correct — but it means `go test -race ./... &` is invisible
to `LiveTaskLedger`. What stayed visible on #652 was the delegated
`implementer` sub-agent (`local_agent`, task `a0d30394062640fb8`) that kept
*polling* the background shell. When `fail_after` fired at 1020s the
`TimeoutError` handler at line 1992 found `ledger.live` non-empty, ran the
shielded teardown (lines 2008-2045), and raised `ImplementerOrphanedSubagent`
→ `EXIT_ORPHANED_SUBAGENT = 46` (line 215). `run_shepherd._followup_code_sets()`
(line 656) puts 46 in the harness set, so `process_one`'s `e.kind == "harness"`
arm (line 2961) incremented `harness_failures` and left `review_attempts`
untouched. Every layer behaved as designed; the loss is structural.

### What already exists and must be reused

- **Containment via `PreToolUse`.** `options._ci_log_guard_hook()` (line 444)
  is the working precedent: it inspects `input_data["tool_input"]["command"]`,
  normalizes line continuations (`_normalize_shell_command`, line 420), matches
  deny patterns, and returns `hookSpecificOutput.permissionDecision = "deny"`
  with a reason. `_compose_hooks()` (line 503) merges it with
  `_command_audit_hooks()` rather than replacing it — mandatory, because
  `subagent_wait.drain_until_settled`'s whole precondition is that `hooks`
  stays truthy.
- **Structured refusal plumbing.** `REFUSAL_MARKER_FILENAME`
  (`.implementer-refusal.json`), `_read_refusal_marker()` (line 310) with its
  bounded read / untracked check, `_write_refusal_out()` (line 444),
  `_review_feedback_exit_code()` (line 469), and the shepherd side:
  `_read_refusal_reason()` (`run_shepherd.py:779`) gated at line 2414 on
  `_refusal_codes() | {EXIT_CI_EVIDENCE_INSUFFICIENT}`, then the `kind`
  ladder at line 2460.
- **Budget validation.** `options.validate_budget_contract()` (line 254) runs
  at import, asserts `envelope >= 2 * IMPLEMENTER_DRAIN_TIMEOUT_SECONDS +
  IMPLEMENTER_MUTATION_RESERVE_SECONDS` per class, and on violation logs and
  clamps the drain rather than raising.
- **Prompt ground rule.** `_build_prompt()` already says "Never defer work to
  'the background.' ... Run every command synchronously" (line ~1636). #652
  proves prose alone does not hold — the same conclusion ADR-011 reached for
  the log fetch.
- **Runtime image.** `Dockerfile` builds on `python:3.12-slim` (Debian), so GNU
  coreutils `timeout` is present; the design still probes rather than assumes.

## Proposed solution

Four changes, all inside the existing envelope/command-timeout/drain/teardown
vocabulary. Nothing widens an envelope.

### 1. `orchestrator/exec_budget.py` — a new, SDK-free module

Holds the pure logic so it is unit-testable and importable by the Temporal
worker without pulling in the agent SDK (the constraint
`tests/test_worker_isolation.py` enforces, and the reason
`subagent_wait.py` defers its SDK imports):

- `CommandBudgetLedger` — a per-run mutable record:
  `clamped: int`, `denied_background: int`, `denied_exhausted: int`,
  `last_bound_s: float | None`, `last_command: str` (truncated),
  `exhausted: bool`, plus `describe() -> str` and `as_dict() -> dict` for the
  JSON written to `--refusal-out`. Bounded fields only — the same discipline
  `MAX_REFUSAL_REASON_CHARS` imposes on model text.
- `command_budget(deadline_monotonic, now, *, ceiling_s, reserve_s, floor_s)
  -> float | None` — returns the derived bound, or `None` meaning "deny, the
  budget is exhausted":

  ```python
  remaining = deadline_monotonic - now
  budget = min(ceiling_s, remaining - reserve_s)
  return budget if budget >= floor_s else None
  ```

- `DETACH_PATTERNS` and `is_detached(command) -> str | None` — returns the
  matched detachment form or `None`. Covers the trailing async-list `&`
  (an `&` that is a control operator: not `&&`, not the `>&`/`<&` redirect
  forms, and terminating a command), plus `nohup`, `setsid`, `disown`. Reuses
  `_normalize_shell_command`'s continuation collapsing (moved here, re-exported
  from `options.py` so #427's patterns keep their exact current behaviour).
- `wrap_bounded(command, budget_s, *, kill_after_s) -> str` — renders
  `timeout --kill-after=<k>s <budget>s bash -c <shlex.quote(command)>`. GNU
  `timeout` puts the child in its own process group and signals the GROUP, so a
  test harness that forks workers dies with it; `--kill-after` guarantees SIGKILL
  if SIGTERM is ignored. This is the "no live child remains" guarantee.

### 2. `orchestrator/options.py` — a deadline-aware guard hook

- New knobs, all through `_positive_seconds`:
  `IMPLEMENTER_TEARDOWN_RESERVE_SECONDS` (default 120.0),
  `IMPLEMENTER_MIN_COMMAND_BUDGET_SECONDS` (default 20.0),
  `IMPLEMENTER_COMMAND_KILL_GRACE_SECONDS` (default 5.0). The per-command
  ceiling is the EXISTING `IMPLEMENTER_COMMAND_TIMEOUT_SECONDS` (300s) — the
  issue asks to reuse command-timeout semantics, and the orchestrator's own
  git/gh calls already use exactly that number.
- `_deadline_guard_hook(deadline_monotonic, ledger, *, timeout_available)` —
  a FACTORY returning the async hook. It closes over an absolute monotonic
  deadline rather than calling `anyio.current_effective_deadline()`, because a
  hook may be dispatched by the SDK outside the caller's cancel scope, where
  that call returns `inf` and the guard would silently become a no-op.
  Behaviour per `Bash` tool call:
  1. `tool_input.get("run_in_background") is True` or
     `is_detached(normalized_command)` → `permissionDecision: "deny"`, ledger
     `denied_background += 1`, reason naming the detachment form and telling the
     agent to re-run synchronously.
  2. `command_budget(...) is None` → `deny`, ledger `denied_exhausted += 1`,
     `exhausted = True`, reason: stop, commit what you have, and write the
     refusal marker with `"verification_budget_exhausted": true` if you cannot.
  3. otherwise → `permissionDecision: "allow"` with
     `updatedInput = {**tool_input, "command": wrap_bounded(...),
     "timeout": int(budget_s * 1000)}` (the tool-input `timeout` is
     milliseconds, and is only ever NARROWED — `min` against any caller value).
     Ledger `clamped += 1`, `last_bound_s = budget_s`.
  Non-`Bash` tools return `{}` untouched.
- `build_implementer_agent_options(...)` gains
  `deadline_monotonic: float | None = None` and
  `budget_ledger: CommandBudgetLedger | None = None`. When both are supplied the
  deadline guard is composed via `_compose_hooks` for EVERY work class — the
  defect is generic, per the issue's constraints — alongside
  `_command_audit_hooks()` and, for `ci-remediation`/`mixed`, `_ci_log_guard_hooks()`.
  Omitting them keeps today's behaviour exactly (every existing test and the
  `issue-investigator`/`service-agent` builders are unaffected).
- `validate_budget_contract()` gains a second assertion per work class:
  `envelope >= IMPLEMENTER_TEARDOWN_RESERVE_SECONDS +
  IMPLEMENTER_MIN_COMMAND_BUDGET_SECONDS + IMPLEMENTER_MUTATION_RESERVE_SECONDS`;
  on violation it logs and clamps `IMPLEMENTER_TEARDOWN_RESERVE_SECONDS` down,
  never the ceiling and never the mutation reserve — same policy as the existing
  drain clamp.

### 3. `orchestrator/run_implementer.py` — wire the deadline in, the outcome out

- `_run_implementer_agent(...)` gains `budget_ledger: CommandBudgetLedger |
  None = None`. Immediately before `anyio.fail_after(envelope_s)` it computes
  `deadline = anyio.current_time() + envelope_s` (monotonic, same clock
  `fail_after` uses) and a one-shot `timeout_available = shutil.which("timeout")
  is not None`, logging a loud warning once when absent. Both, plus the ledger,
  go into `build_implementer_agent_options`.
- `review_feedback_one()` creates the ledger before `anyio.run(...)`, passes it
  in, and after the run:
  - commits present → unchanged path (push, `EXIT_OK`), plus
    `print(ledger.describe())` so truncation is visible in the Argo log;
  - no commits, no valid refusal marker, `ledger.exhausted` →
    `ImplementResult.error = f"{VERIFICATION_BUDGET_EXHAUSTED_ERROR_PREFIX}
    {ledger.describe()}"`. The reason is ORCHESTRATOR-derived, not model prose —
    that is the issue's "structured evidence usable by shepherd".
  - a refusal marker carrying `"verification_budget_exhausted": true` maps to
    the same code, so the agent can record the outcome deliberately. This reuses
    `_read_refusal_marker`'s existing validation wholesale; `RefusalMarker`
    gains one boolean field beside `insufficient_evidence`.
- New sentinel `EXIT_VERIFICATION_BUDGET_EXHAUSTED = 51` with prefix
  `VERIFICATION_BUDGET_EXHAUSTED_ERROR_PREFIX = "verification-budget-exhausted:"`,
  added to `_review_feedback_exit_code()`.
- `main()`'s `--refusal-out` ladder gains an `elif code ==
  EXIT_VERIFICATION_BUDGET_EXHAUSTED` arm writing `ledger.as_dict()` (or the
  marker reason) as JSON.
- `implement_one()` (batch mode) gets the same ledger wiring for free — it calls
  the same driver with the default envelope — so the boundary is not
  review-remediation-only.

### 4. `orchestrator/run_shepherd.py` + prompt + ADR

- `_followup_code_sets()` adds `run_implementer.EXIT_VERIFICATION_BUDGET_EXHAUSTED`
  to the **harness** frozenset, with a docstring paragraph stating why: the agent
  ran and was cut short by a platform-imposed bound, so it is blameless like 46
  and 50 and bounded by the same `MAX_HARNESS_FAILURES`. `review_attempts` is
  never charged.
- The `refusal_reason` gate at `run_shepherd.py:2414` extends to
  `| {EXIT_CI_EVIDENCE_INSUFFICIENT, EXIT_VERIFICATION_BUDGET_EXHAUSTED}` so the
  structured reason reaches `FollowupSubprocessError.reason`, the
  `reason_suffix` log line, and the `review-stuck` terminal note.
- `_build_prompt()` ground rules gain two lines for every class: commands are
  bounded by the remaining envelope and may be cut short; backgrounding,
  `nohup`/`setsid`/`disown` and polling loops are BLOCKED, not merely
  discouraged; if verification cannot complete, commit what is proven and say so
  — or write the marker with `"verification_budget_exhausted": true`. The prompt
  states the rule; the hook is the enforcement, exactly as #423 established.
- `docs/adr/011-execution-budget-contract.md` is amended (not superseded) with a
  fourth invariant and a coverage-table row: `Agent-issued Bash command |
  min(IMPLEMENTER_COMMAND_TIMEOUT_SECONDS, remaining - IMPLEMENTER_TEARDOWN_RESERVE_SECONDS),
  OS-enforced | yes (nested)`.

### Why this shape

It mirrors the two boundaries already drawn. #418 moved admission OUTSIDE the
envelope; #423 moved log retrieval outside it and denied the unbounded form
inside. This proposal keeps the work inside (local verification genuinely
belongs to the run) but makes it *derive* its bound from the envelope instead of
having an independent one — the only remaining category the coverage table did
not bound. And it puts enforcement where #423 proved it has to be: a
`PreToolUse` decision taken before the command starts, plus an OS-level bound
that does not depend on the CLI's backgrounding behaviour.

## Alternatives

1. **Widen the `ci-remediation` envelope (or raise
   `IMPLEMENTER_TIMEOUT_CEILING_SECONDS`).** Rejected: the issue forbids it, and
   it is unsound — `go test -race ./...` on a large repo has no ceiling anyone
   can name, so any number just moves the orphan later while making every
   unrelated CI-remediation run hold a claim lease longer
   (`_review_claim_lease_default()` is derived from the ceiling).

2. **Deny only the specific shapes seen in production (`go test -race`,
   trailing `&`, `sleep`-poll loops).** Rejected explicitly by the issue ("do
   not special-case `go test -race` only"), and it is the "exact textual
   spelling instead of command semantics" mistake `_GH_GLOBAL_FLAG`'s comment
   already warns about. The generic boundary is the derived budget; the
   detachment denial is a supporting invariant, not the fix.

3. **Track background shells in `LiveTaskLedger` and drain them.** Rejected:
   `AWAITED_TASK_TYPES` must stay byte-identical to the SDK's
   `DEFERRING_TASK_TYPES` (pinned by `tests/test_subagent_wait.py`), and the
   module docstring explains that a background shell need never reach a terminal
   status — awaiting one hangs by construction. It would also convert the orphan
   into a drain timeout, i.e. re-classify the same loss rather than prevent it.

4. **Shorten the CLI's own Bash tool timeout globally (a low fixed
   `timeout` in `updatedInput`, no deadline math).** Rejected: it is an
   independent bound again — exactly what the issue says must stop — and it
   fails acceptance criterion 8, cancelling short legitimate verifications late
   in a long envelope while still allowing a command launched at t=0 to run past
   the end. It also does not stop `&`.

5. **Kill the whole process group in the `TimeoutError` teardown instead of
   bounding commands.** Rejected as the primary fix: it makes the orphan tidier,
   not rarer. The run still ends at 46 with no PR mutation, which is the outcome
   the issue is about. (The teardown's existing `process.terminate()` stays, as
   the safety net it is.)

## Platform impact

- **Migrations:** none. No schema, no `.status.yaml` field, no GitOps change.
  One new exit code (51) and one optional marker field.
- **Backward compatibility:** `build_implementer_agent_options`'s new parameters
  default to `None`, so every existing caller and test resolves identical
  `ClaudeAgentOptions`. `_run_implementer_agent`'s new parameter defaults to
  `None`. Exit 51 is unknown to an older shepherd, which classifies unknown
  codes as `transient` — retried, never charged, and the deploy order
  (shepherd and implementer ship in the same image) makes the window
  theoretical.
- **Resource impact:** negligible. Two regex passes and one arithmetic
  comparison per `Bash` tool call, plus one `bash -c` layer per command.
  Materially POSITIVE at the fleet level: a CI-remediation tick that today burns
  1020s and produces nothing will end in a bounded outcome in less.
- **Risk — `timeout` absent or `bash` missing in a target repo's toolchain.**
  Mitigation: one-shot `shutil.which("timeout")` probe with a loud warning and
  a tool-input-clamp-only fallback; the detachment denials still hold.
- **Risk — command rewriting breaks a legitimate invocation** (heredocs,
  multi-line scripts, `cd` semantics). Mitigation: `shlex.quote` of the whole
  original string passed to `bash -c`, which preserves cwd and quoting;
  `tests/test_exec_budget.py` pins heredoc, pipeline, `&&`, `2>&1` and
  multi-line cases; `IMPLEMENTER_BOUND_COMMANDS=0` disables wrapping (clamp and
  denials remain) as a break-glass.
- **Risk — premature cancellation of a legitimate long test** (acceptance 8).
  Mitigation: the ceiling is the existing 300s `IMPLEMENTER_COMMAND_TIMEOUT_SECONDS`,
  which already bounds the orchestrator's own commands; anything above it was
  already outside the platform's stated bound. The bound never widens and is
  only reduced as the envelope drains, and the exhausted case is a structured,
  non-charging outcome rather than a lost run.
- **Risk — `updatedInput` not honoured by the pinned SDK/CLI pair.**
  Mitigation: task T8 pins it with a test and an explicit version assertion; the
  documented fallback (deny the unbounded form, hand the agent the
  `timeout`-wrapped command in the deny reason) requires no SDK support.
- **Risk — the guard makes the agent give up too early on a busy runner.**
  Mitigation: `denied_exhausted` and `clamped` counters are in the ledger and in
  the Argo log for every run, so the reserve/floor defaults can be tuned from
  evidence; `MAX_HARNESS_FAILURES` still bounds the retry loop.
</content>
</invoke>
