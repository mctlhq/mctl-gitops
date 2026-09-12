# Design: issue-364-run-implementer-records-a-quota-exhauste

## Current state

### The implementer never inspects the SDK's terminal message

`orchestrator/run_implementer.py:657-680`:

```python
async def _run_implementer_agent(repo_dir: Path, prompt: str, proposal_dir: Path) -> None:
    ...
    with anyio.fail_after(IMPLEMENTER_TIMEOUT_SECONDS):
        async with ClaudeSDKClient(options=options) as client:
            ...
            async for message in client.receive_response():
                print(message)
```

Every message — including `RateLimitEvent` and the terminal `ResultMessage` —
is printed and discarded. The only failure this function can raise is
`ImplementerOperationTimeout`, from the `anyio.fail_after` wrapper.

`implement_one()` then reaches the commit check at
`orchestrator/run_implementer.py:1430-1447`:

```python
        anyio.run(_run_implementer_agent, target, prompt, ref.proposal_dir.resolve())

        # 6. Did the agent actually commit something?
        if not _has_new_commits(target):
            _mark_needs_triage(
                ref, code="no-commits", stage="agent",
                message="implementer produced no commits", attempt=attempt,
            )
            return ImplementResult(ref=ref, pr_url=None, error="implementer produced no commits")
```

`_mark_needs_triage` (`run_implementer.py:1226-1250`) writes
`status: needs-triage` plus `failure: {code, stage, message}`. Per
`README.md:139-145` a `needs-triage` proposal is never retried automatically —
an operator must move it back to `accepted`. So a three-second 429 and a
genuine "the agent decided nothing was needed" produce the same durable record
and the same manual remedy.

The exception ladder below it (`run_implementer.py:1484-1545`) maps
`ImplementerOperationTimeout -> operation-timeout`,
`subprocess.CalledProcessError -> shell-failed`, `SystemExit ->
configuration-error`, and everything else to `unexpected-error`. There is no
429 branch anywhere in the file.

### The investigator already does it correctly

`orchestrator/run_issue_investigator.py:1239-1250` defines
`RateLimitExhaustedError`, whose docstring states the intent explicitly: the
resulting error must be unambiguous to "the CWFT-level OAuth-fallback retry" and
"the account-2 fallback inside the Argo-submitted investigate step". The raise
site (`run_issue_investigator.py:1290-1310`) is inside the same
`async for message in client.receive_response():` loop the implementer has:

```python
            if (
                isinstance(message, ResultMessage)
                and message.is_error
                and message.api_error_status == 429
            ):
                raise RateLimitExhaustedError(...)
```

`investigate()` catches it *before* the generic `Exception` branch
(`run_issue_investigator.py:1869-1876`) and returns
`InvestigateResult(..., rate_limited=True)`; the field's comment
(`run_issue_investigator.py:1320-1327`) records the contract this proposal is
asked to mirror — "lets a caller distinguish 'this account is out of quota'
from 'the agent broke on this issue'". Tests:
`tests/test_run_issue_investigator.py:418-449` (raises on 429, does not raise
on a clean result, does not raise on a 500) and `:588-624`.

### What the SDK actually gives us

`claude-agent-sdk==0.2.136` is pinned (`pyproject.toml:29`, `uv.lock:113-115`).
In `claude_agent_sdk/types.py`:

- `ResultMessage.api_error_status: int | None` (line 1250) — "HTTP status code
  (e.g. 429, 500, 529) of the failing API call when `is_error` is True".
- `RateLimitInfo` (lines 1280-1303) — `status` (`allowed` /`allowed_warning` /
  `rejected`), `resets_at` (Unix ts), `rate_limit_type` (`five_hour`,
  `seven_day`, ...), `overage_status`, `overage_disabled_reason`, `raw`.
- `RateLimitEvent` (lines 1306-1315) wrapping a `RateLimitInfo`, and present in
  the message union (line 1360).

This is exactly the payload quoted in the issue's log excerpt
(`rate_limit_type='seven_day'`, `overage_disabled_reason='out_of_credits'`,
`resets_at=1789509600`). The implementer already receives it; it just throws it
away.

### Surrounding contracts this must not break

- **Exit codes.** `run_implementer.py:150-168` defines
  `EXIT_NO_FOLLOWUP_COMMITS=42`, `EXIT_BRANCH_MISSING_ON_ORIGIN=43`,
  `EXIT_OPERATION_TIMEOUT=44`, `EXIT_BLOCKED_ONLY=45`. The shepherd
  (`run_shepherd.py:1591-1605`) treats exactly {42, 43, 44} as deterministic
  and everything else as transient, where transient means "retry next tick, do
  NOT consume a `review_attempts` slot" (`run_shepherd.py:445-463`).
- **Batch accounting.** `ImplementResult.counts_toward_limit`
  (`run_implementer.py:247`) is read once, at `_implement_refs`
  (`run_implementer.py:1586-1592`). Only two paths opt out today: a blocked
  proposal (`:1329`) and a failed GitHub preflight (`:1343`). A 429 therefore
  consumes the run's single `--max-proposals` slot, which answers the issue's
  open question #2: **the implementer's accounting does not match the
  investigator's contract today.**
- **The in-progress lease.** `implement_one` writes
  `update_status_yaml(ref, "in-progress", attempt=attempt, ...)` at
  `run_implementer.py:1417` *before* the SDK call, with a 130-minute
  `expires_at` (`:1408-1415`). Leaving a 429'd proposal in `in-progress` takes
  it out of `find_accepted_proposals`' selection; the only recovery is the
  shepherd's dead-letter path (`run_shepherd.py:1723-1745`), which requires a
  PR to exist and there is none. So the rollback to `accepted` is not cosmetic.
- **Worker isolation.** `tests/test_worker_isolation.py:33-37` forbids
  `claude_agent_sdk` and `orchestrator.run_implementer` from the
  `orchestrator.temporal.worker` import graph. `run_issue_investigator` IS in
  that graph (via `run_issue_poller`), which is why its SDK imports are
  function-scoped (`run_issue_investigator.py:1252-1262`). Any shared module
  both agents import must therefore be SDK-import-free at module scope.
- **Status file semantics.** `orchestrator/proposal_state.update_status_file`
  preserves every field it is not told to change and removes a field when
  passed `None` (`proposal_state.py:143-183`), and writes atomically via
  rename. Adding a new top-level key is additive and safe for old readers.

## Proposed solution

### 1. New SDK-free module `orchestrator/rate_limit.py`

The gap exists because the same rule is implemented once, in one agent. Put it
in one place both call sites import:

```python
class RateLimitExhaustedError(RuntimeError): ...

@dataclass(frozen=True)
class RateLimitObservation:
    account: str                      # "1" / "2" / "primary" / "secondary" / "unknown"
    rate_limit_type: str | None       # "seven_day", "five_hour", ...
    resets_at: str | None             # RFC 3339 UTC, derived from the Unix ts
    resets_at_epoch: int | None
    overage_disabled_reason: str | None
    detail: str                       # short, credential-free summary

def is_rate_limit_result(message: object) -> bool: ...
def observe_rate_limit_event(message: object) -> RateLimitInfoLike | None: ...
def account_label() -> str: ...
def build_observation(info, *, detail) -> RateLimitObservation: ...
```

`is_rate_limit_result` and `observe_rate_limit_event` are **duck-typed**
(`getattr(message, "api_error_status", None)`, `getattr(message,
"rate_limit_info", None)`) plus a `type(message).__name__` check, so the module
never imports `claude_agent_sdk` and `tests/test_worker_isolation.py` keeps
passing. `account_label()` reads the optional non-secret `CLAUDE_OAUTH_ACCOUNT`
env var, falls back to `"primary"`/`"secondary"` derived from
`auth.detect_auth().env_var`, and returns `"unknown"` when neither is
conclusive. No credential value, prefix or suffix is ever read into a record.

`run_issue_investigator.RateLimitExhaustedError` becomes a re-export of the
shared class (`RateLimitExhaustedError = rate_limit.RateLimitExhaustedError`) so
`tests/test_run_issue_investigator.py:35`'s import and every existing
`except` clause keep working unchanged.

### 2. Detection in `_run_implementer_agent`

Track the most recent `rejected` rate-limit event while streaming, and raise on
the terminal 429 exactly as the investigator does:

```python
            last_info = None
            async for message in client.receive_response():
                print(message)
                info = observe_rate_limit_event(message)
                if info is not None and getattr(info, "status", None) == "rejected":
                    last_info = info
                if is_rate_limit_result(message):
                    raise RateLimitExhaustedError(...)   # carries build_observation(last_info, ...)
```

The event is enrichment only; the terminal `ResultMessage` remains the
authoritative signal, because `allowed_warning` events fire on healthy runs and
a `rejected` event does not by itself end the run.

### 3. Classification in `implement_one`

A new `except RateLimitExhaustedError` branch placed **before** the generic
`Exception` branch (same ordering rule as
`run_issue_investigator.py:1869-1876`), and after `ImplementerOperationTimeout`:

- `update_status_yaml(ref, "accepted", attempt=None, failure=None, rate_limited=<block>)`
  — status rolls back so the next tick re-selects the proposal, the lease is
  dropped so the shepherd's dead-letter logic is not misled, and `failure` is
  explicitly cleared so a stale `no-commits` from an earlier tick cannot be
  mistaken for this one.
- The `rate_limited` block is
  `{code: "rate-limited", account, rate_limit_type, resets_at, resets_at_epoch,
  overage_disabled_reason, since, observed_at, attempt_id, message}`. `since`
  is preserved when an identical block is already on disk, reusing the
  idempotent-write technique of `_mark_blocked`
  (`run_implementer.py:1252-1288`) so a three-day outage produces one GitOps
  commit per distinct observation, not one per tick.
- Returns `ImplementResult(ref=ref, pr_url=None, error="rate limited: ...",
  rate_limited=True, counts_toward_limit=False)`.

Every existing write that already clears `failure`/`blocked` (the
`implemented`, `merged`, `rejected` and `in-progress` writes at
`run_implementer.py:1348-1417`) gains `rate_limited=None`, so the block
disappears as soon as the proposal moves on.

`review_feedback_one` (`run_implementer.py:696-790`) gets the same `except`
branch but writes nothing — the shepherd owns status in that mode — and returns
an error string prefixed `"rate limited:"`.

### 4. Handoff: a distinct exit code and one greppable line

- `EXIT_RATE_LIMITED = 46` next to the existing sentinels
  (`run_implementer.py:150-168`).
- `_review_feedback_exit_code()` maps an error starting with `"rate limited:"`
  to it. It is deliberately **not** added to the shepherd's deterministic set
  (`run_shepherd.py:1596-1601`), so `is_transient` stays true and no
  `review_attempts` slot is consumed — this is the shepherd-side expression of
  the investigator's "never counted toward the budget" contract. A test pins
  that, because the behaviour is currently a default rather than a decision.
- `BatchOutcome` gains a trailing `rate_limited: int = 0` field (same
  backward-compatible pattern used when `blocked` was added,
  `run_implementer.py:250-258`), `_batch_outcome()` classifies it before the
  generic failure branches, and the `=== Summary ===` totals line reports it.
- `main()` exits `EXIT_RATE_LIMITED` when a batch had a rate-limited result and
  no success, and prints one stable stderr line:
  `error: rate-limited: account=<label> type=<seven_day> resets_at=<iso> proposal=<service>/<slug>`.
  The exit stays non-zero, so the CWFT's `implement-fallback` gate — which
  compares Argo step status strings, not exit codes
  (`run_implementer.py:157-168`) — behaves exactly as it does today. The code
  and the line are what mctl-gitops#1206 will key `assert-attempt` on.
- `_implement_refs()` breaks out of the loop on a rate-limited result: an
  exhausted account is workflow-global, the same reasoning the file already
  applies to SDK auth failures (`run_implementer.py:1398-1404`).

### 5. Optional guard: do not re-run into a known-closed window

Before the model call, if the proposal's recorded `rate_limited.resets_at` is
in the future **and** its `account` equals `account_label()`, skip with
`counts_toward_limit=False` and no status write. Fail open in every ambiguous
case (`account: unknown`, unparsable timestamp, missing block). This is what
turns "three days of degraded redundancy" into a bounded, self-describing pause
instead of a tick-by-tick retry loop. It is isolated in its own task so it can
be dropped without affecting the rest.

## Alternatives

**A. Keep `needs-triage`, just change the code to `rate-limited`.** The
literal reading of the issue's first bullet, and the smallest diff. Dropped:
`needs-triage` is a terminal, operator-gated state (`README.md:139-145`), so
every quota blip would require a human to move a blameless proposal back to
`accepted`. Consequence #1 in the issue is precisely that triage is pointed at
the wrong object; parking the proposal in the triage queue keeps that cost while
only relabelling it. Recording the distinct cause *and* leaving the proposal
runnable satisfies the same bullet and the "not counted against the budget"
bullet together.

**B. Detect the limit by matching the assistant text
("You've hit your weekly limit").** No new plumbing, works even on CLI versions
that predate `api_error_status`. Dropped: it is a user-facing, localisable,
model-authored string; the investigator deliberately keys on the structured
field instead, and a text match would also fire on an agent that merely
*quoted* the phrase while implementing this very issue.

**C. Call `auth.rotate_to_secondary_auth()` and retry in-process.** The
function already exists (`orchestrator/auth.py:84-98`) and has no caller.
Dropped: it duplicates the CWFT fallback leg, would run two real SDK sessions
inside one pod against the "at most one accepted proposal per run" policy
(`_max_proposals_error`, `run_implementer.py:1618-1630`), and in the measured
incident the fallback account was the exhausted one — the retry would have
burned a second session to learn the same thing.

**D. Emit a Prometheus metric or push an incident from the implementer pod.**
Closest to the issue's "ideally a metric or alert". Dropped from this proposal:
the implementer is a short-lived Argo pod with no scrape target (the only
Prometheus wiring in the repo is the long-lived Temporal worker,
`orchestrator/temporal/worker.py:402-418`), so it would need a pushgateway that
does not exist. The exit code plus `.status.yaml` block is the durable
substrate an alert can be built on later, and the alert itself belongs with the
CWFT work in mctl-gitops#1206.

## Platform impact

**Migrations.** None. `rate_limited` is a new optional top-level key in
`.status.yaml`; `update_status_file` preserves unknown fields
(`proposal_state.py:143-183`) and every existing reader keys on `status`,
`failure`, `pr`, `attempt` or `blocked`. No proposal status value is added, so
`docs/diagrams/archify/facts.yaml`'s `reconcile_input_statuses` /
`shepherd_input_statuses` and `tests/test_diagram_facts.py` are untouched.

**Backward compatibility.** Rate-limited proposals stay `accepted`, a status
already in `SHEPHERD_INPUT_STATUSES`' complement and in reconcile's input set,
so no controller sees a state it does not handle. `EXIT_RATE_LIMITED = 46` is
new; the shepherd's `deterministic_codes` set is explicit
(`run_shepherd.py:1596-1601`), so an unknown code is already handled as
transient. `RateLimitExhaustedError` remains importable from
`orchestrator.run_issue_investigator`.

**Resource impact.** Negligible: one extra `getattr` per streamed message, one
extra small YAML write on a failure path that already writes.

**Risks and mitigations.**

- *A quota outage produces a GitOps commit every tick.* Mitigated by the
  idempotent-write rule (unchanged `code`/`account`/`rate_limit_type`/
  `resets_at` writes nothing), copied from `_mark_blocked`, and further by the
  §5 guard.
- *A proposal that keeps failing on 429 never reaches a human.* It stays
  `accepted` with a durable, timestamped block naming the account and reset
  time, is visible in the batch summary and in the exit code, and — unlike
  today — is not silently mislabelled. If the condition outlives the recorded
  `resets_at`, the block's `since` shows how long it has persisted.
- *The account label is wrong or absent.* Everything degrades to
  `account: unknown`: the record is still more informative than `no-commits`,
  and the §5 skip guard explicitly does not fire, so no work is withheld on a
  bad label.
- *Work committed locally before a mid-run 429 is discarded.* Unchanged from
  today's behaviour for any exception; the temp clone is still retained for
  post-mortem because `pr_url` is None (`run_implementer.py:1547-1553`).
  Pushing a half-finished implementation would be worse than re-running.
- *False positives on a non-429 error.* The classifier requires `is_error` AND
  `api_error_status == 429`, and a regression test mirrors
  `tests/test_run_issue_investigator.py:438-449` for the 500 case.
- *Secret leakage.* The record carries an ordinal account label and SDK-supplied
  limit metadata only; a test asserts no token-shaped value reaches
  `.status.yaml`.
