# Design: issue-292-fix-lifecycle-steward-owned-repos-have-n

## Current state

### The shepherd's per-service opt-out is all-or-nothing

`orchestrator/run_shepherd.py` parses the opt-out once at import time:

```python
# orchestrator/run_shepherd.py:316
def _skip_services_from_env() -> frozenset[str]:
    raw = os.environ.get("SHEPHERD_SKIP_SERVICES", "")
    names = frozenset(s for s in raw.replace(",", " ").split() if s)
    unknown = names - set(SERVICES)
    ...
SHEPHERD_SKIP_SERVICES = _skip_services_from_env()   # line 330
```

`_discover_refs` (line 492) applies it before anything else — before
`service_filter`, before the status filter, before the PR lookup:

```python
# orchestrator/run_shepherd.py:518-527
is_skipped = service in SHEPHERD_SKIP_SERVICES
if not reconcile and is_skipped:
    if (service_dir / "proposals").is_dir():
        print(
            f"shepherd: skipping {service} "
            "(SHEPHERD_SKIP_SERVICES; owned by another PR lifecycle)"
        )
    continue
if service_filter and service != service_filter:
    continue
```

Two consequences matter here. First, the skip is total: it removes the
`address-review` stage together with the `merge` stage, because the shepherd
has exactly one gate for both. Second — and this is not obvious from the issue
— the skip is applied *ahead of* `service_filter`, so a **targeted** one-shot
is skipped too. That is precisely the dry-run output quoted in the issue.

### The DevLoop's own in-loop tick is skipped by the same line

ADR-006 §6.1 (`docs/adr/006-dev-loop-merge-deploy-monitor.md`) moved the review
loop into `DevLoopWorkflow` and demoted the cron to a sweeper. The in-loop tick
is `DevLoopWorkflow._shepherd_tick` (`orchestrator/temporal/workflows/dev_loop.py`,
line 976):

```python
tick_params = {"service": service, "slug": slug}
...
tick_result = await _run_cwft("mctl-agents-shepherd", tick_params)
```

It runs the shepherd in targeted mode (`--service`/`--slug`), which
deliberately bypasses `_filter_dev_loop_owned` in `main()` (line ~2250) so the
DevLoop can drive its own proposal. But it does **not** bypass
`SHEPHERD_SKIP_SERVICES`. So for the five skipped repos the DevLoop ticks up to
`SHEPHERD_TICKS_MAX = 12` times (line 146), each tick provisioning a Hetzner
volume, and every one of them prints "skipping ... owned by another PR
lifecycle" and does nothing. The workflow then watches passively until
`MERGE_WATCH_DEADLINE = timedelta(days=14)` (line 126).

Worse, the two drivers cancel each other out. `_watch_pr` sets
`self._shepherd_in_loop = True` as soon as the watch starts (`dev_loop.py`
L1081-1107), and the cron sweeper reads that through mctl-api in
`run_shepherd._dev_loop_owns` (line 124), whose final check is
`payload.get("shepherd_in_loop") is True` (line 184). So for a skipped,
DevLoop-driven proposal: the DevLoop claims ownership, `_filter_dev_loop_owned`
makes the cron stand down, and the DevLoop's own ticks are discarded inside
`_discover_refs`. The proposal is orphaned by both halves at once, silently,
until `MERGE_WATCH_DEADLINE` — 14 days.

Fixing `_discover_refs` therefore repairs both drivers at once, and does so
without touching `dev_loop.py`, the CWFT parameter set
(`{"service", "slug", "agent_image", "agent_version"}` at `dev_loop.py` L992-996)
or the `shepherd_in_loop` ownership protocol.

### The only path from findings to a commit

`decide()` (line 1138) is a pure function returning one of five decisions.
`address-review` fires when `codex_review.findings_p1_p2(at=pr.head_sha)` is
non-empty. `process_one` (line 1549) executes it by calling `apply_followup`
(line 1381), which:

1. normalises the findings into a JSON bundle via the shepherd sub-agent
   (`agents/_shepherd/.claude/agents/shepherd.md`, budget `SHEPHERD_BUDGET_USD`),
2. writes the bundle to a temp file,
3. forks `sys.executable -m orchestrator.run_implementer --service <svc>
   --slug <slug> --review-feedback <path>`,
4. maps sentinel exit codes (`EXIT_NO_FOLLOWUP_COMMITS = 42`,
   `EXIT_BRANCH_MISSING_ON_ORIGIN = 43`, `EXIT_OPERATION_TIMEOUT = 44` in
   `run_implementer.py:128-132`) onto `FollowupSubprocessError(transient=...)`.

On the implementer side, `review_feedback_one` (`run_implementer.py:640`)
clones the sibling repo, asserts `feat/agents-<slug>` exists on origin
(`_branch_exists_on_origin`), checks it out, captures HEAD, runs the sub-agent
with the bundle rendered into the prompt (`_render_review_feedback`), verifies
new commits (`_has_new_commits`), and pushes with no `-u` and no new PR. It
deliberately does not write `.status.yaml` — the shepherd owns status.

`main()` in `run_implementer.py` (line 1505) gates `--review-feedback` on
`--service AND --slug` and on the proposal being in `{implemented,
review-fixing}`. There is no Argo/MCP surface that passes the flag; the only
caller is `apply_followup`.

### Merge, and what is already safe

`merge_pr` (line 1509) runs `gh pr merge --merge --delete-branch
--match-head-commit <SHA>`. It is unconditional `--merge` (no squash), which is
one concrete reason the shepherd must not merge `mctl-telegram`, whose repo
rule is squash-only. `decide()` already refuses to merge outside
`MERGEABLE_STATES = {"CLEAN", "HAS_HOOKS", "UNSTABLE"}` and inside
`SHEPHERD_MERGE_SETTLE_MIN`, but nothing today encodes "this repo's merge
belongs to someone else".

### Supporting machinery already present

- `_update_status_if_changed` (line 1774) writes `.status.yaml` only when a
  field actually changes — the existing answer to gitops commit churn.
- `update_status_file` (`orchestrator/proposal_state.py:115`) accepts arbitrary
  `**fields`, preserves unknown keys, and removes a field when passed `None`.
- Test conventions in `tests/test_run_shepherd.py`: builders `make_pr`,
  `make_finding`, `make_status_yaml`, `make_ref`, `read_status`, and
  `monkeypatch.setattr(run_shepherd, "SHEPHERD_SKIP_SERVICES", frozenset({...}))`
  for the module-level constants (see `test_discover_skips_listed_service`,
  line 245).
- `docs/agent-inventory.yaml` (shepherd entry, line 146) and
  `agents/_manifests/shepherd/agent.yaml` describe the agent; the inventory is
  enforced by `tests/test_agent_inventory.py`.
- `tools/diagram_facts.py` tracks `SHEPHERD_INPUT_STATUSES` /
  `RECONCILE_INPUT_STATUSES` (`_STATUS_SET_RE`, line 69) as diagram facts. This
  design adds no status value, so no drift is produced.

## Proposed solution

Introduce a third per-service mode — **fix-only** — between "full" and
"skip", and a hard in-code never-merge list. Ownership is then split by
*stage* (issue option 2) instead of by repo, and the operator one-shot (issue
option 3) falls out of the same flag.

### 1. Service mode resolution (`orchestrator/run_shepherd.py`)

Factor the existing env parser into a reusable helper and add the new variable:

```python
def _service_set_from_env(var: str) -> frozenset[str]:
    """Comma/whitespace-separated service names; warn on names not in SERVICES."""

SHEPHERD_SKIP_SERVICES = _service_set_from_env("SHEPHERD_SKIP_SERVICES")
SHEPHERD_FIX_ONLY_SERVICES = _service_set_from_env("SHEPHERD_FIX_ONLY_SERVICES")

# Merge is content publication for these repos and is gated on a human
# CODEOWNER by design (config/settings.py). No environment value may grant
# an agent the merge decision for them.
NEVER_MERGE_SERVICES = frozenset({"mctl-academy"})

FULL, FIX_ONLY, SKIP = "full", "fix-only", "skip"

def _service_mode(service: str, *, force_fix_only: bool = False) -> str:
    if service in SHEPHERD_FIX_ONLY_SERVICES:
        return FIX_ONLY                      # wins over SKIP, with a warn at import
    if service in SHEPHERD_SKIP_SERVICES:
        return SKIP
    return FIX_ONLY if force_fix_only or service in NEVER_MERGE_SERVICES else FULL
```

Fix-only deliberately **wins** over skip when both list a service. That makes
the gitops migration order-independent: the CronWorkflow can gain
`SHEPHERD_FIX_ONLY_SERVICES` in one commit and shed the stale
`SHEPHERD_SKIP_SERVICES` entries in a later one without an interval where the
repo is neither owned nor fixed. The overlap emits a one-line `warn:` at import
so the transitional state is visible in every tick's log.

`NEVER_MERGE_SERVICES` collapsing to fix-only rather than skip is intentional:
the constant answers "may an agent merge this?", not "may an agent touch it?".
Academy stays fully skipped because gitops keeps it in
`SHEPHERD_SKIP_SERVICES` and not in the fix-only list, and the skip branch is
checked first for anything not explicitly fix-only.

### 2. Discovery (`_discover_refs`)

Replace the `service in SHEPHERD_SKIP_SERVICES` test with
`_service_mode(service, force_fix_only=fix_only) == SKIP`, carry the resolved
mode onto `ProposalRef` as a new field `mode: str = FULL`, and keep the
existing `shepherd: skipping <svc>` log line for the `SKIP` branch. Reconcile
mode is untouched — it already covers every service.

This single change is what repairs the DevLoop in-loop tick: with
`mctl-telegram` in fix-only, `_shepherd_tick`'s targeted run discovers the
proposal again and the loop resumes.

### 3. Decision (`decide`)

Keep `decide()` pure and add one keyword-only argument:

```python
def decide(pr, codex_review, now=None, *, fix_only: bool = False) -> tuple[str, Any]:
    ...
    return ("defer-merge", None) if fix_only else ("merge", None)
```

Everything above the final `return` is unchanged, so `flip-to-merged`,
`flip-to-rejected`, `wait` and `address-review` behave identically in both
modes. `defer-merge` is a sixth decision name rather than a reuse of `wait`
because the operator log and `_print_summary` must distinguish "nothing to do
yet" from "clean, green, and handed to the steward" — the latter being exactly
the state the issue says is invisible today.

### 4. Execution (`process_one`)

- Thread `fix_only = ref.mode == FIX_ONLY` into the `decide()` call.
- Add a `defer-merge` branch before the `merge` branch:

```python
if decision == "defer-merge":
    print(
        f"info: {ref.service}/{ref.slug} pr={pr.repo}#{pr.number} is "
        "clean and green; merge owned by pr-steward — deferring"
    )
    _update_status_if_changed(ref, ref.status, merge_owner="pr-steward")
    return ShepherdResult(ref=ref, decision="defer-merge",
                          notes="merge owned by pr-steward")
```

  `_update_status_if_changed(ref, ref.status, ...)` re-asserts the *current*
  status and only writes when `merge_owner` is absent or different, so the
  field lands once and subsequent ticks produce no gitops commit.
- Clear the field on the terminal flips: pass `merge_owner=None` alongside
  `review_attempts=None` in the `flip-to-merged`, `flip-to-rejected` and
  `merge` branches (`update_status_file` removes a key when passed `None`).
- Guard the `merge` branch defensively: if `ref.service in NEVER_MERGE_SERVICES`
  or `ref.mode == FIX_ONLY`, log an `error:` and return `defer-merge` instead of
  calling `merge_pr`. This should be unreachable given `decide()`, which is the
  point — it is the belt to `decide()`'s braces.

### 5. Never-merge guard in `merge_pr`

`merge_pr` takes the `PRSnapshot`, which carries `repo` (`mctlhq/<svc>`), so
the guard needs no new parameter:

```python
service = pr.repo.split("/")[-1]
if service in NEVER_MERGE_SERVICES:
    print(f"error: refusing to merge {pr.repo}#{pr.number}: "
          f"{service} merges are gated on a human CODEOWNER")
    return (False, None)
```

Two independent checks (`decide()` and `merge_pr`) are what makes "Academy's
PRs stay unmergeable by an agent" a property of the code rather than of the
environment. It is also cheap to test directly.

### 6. CLI (`main`)

Add `--fix-only` (`action="store_true"`):

- rejected with exit 2 when combined with `--reconcile` (reconcile never merges
  or fixes, so the combination is a user error worth naming);
- passed into `_discover_refs(..., fix_only=args.fix_only)` and forwarded to
  `process_one`, where it forces `ref.mode = FIX_ONLY` for every ref in the run;
- documented in the module docstring's `Env:`/`Usage:` block alongside
  `SHEPHERD_FIX_ONLY_SERVICES`.

This is the operator one-shot the issue asks for in option 3, in a stronger
form than a `--review-feedback` passthrough on `mctl_trigger_implementer`: the
operator does not have to author a findings bundle, because the shepherd reads
the live review and builds it.

```bash
python -m orchestrator.run_shepherd \
    --service mctl-telegram --slug issue-481-idempotency-key-scope --fix-only
```

Budget accounting in `main()`'s loop already charges `per_call_estimate` on
`address-review`; `defer-merge` costs nothing and is not charged.

### 7. Documentation and companion changes

- `README.md` "Tier 3 — PR shepherd": document the three modes, the new
  decision, and the `--fix-only` one-shot; update the quoted `decide()` pseudo
  code.
- `docs/agent-inventory.yaml` shepherd entry: note that merge is conditional on
  service mode and that `mctl-academy` is never mergeable by an agent.
- `docs/adr/006-dev-loop-merge-deploy-monitor.md`: an addendum noting that
  `SHEPHERD_SKIP_SERVICES` no longer implies "no in-loop review fixing", so the
  sweeper/in-loop split described in §6.1 now applies to steward-owned repos
  too.
- **mctl-gitops (out of repo, documented for the operator):** in
  `cronworkflow-mctl-agents-shepherd.yaml` and `cwft-mctl-agents-shepherd.yaml`,
  set `SHEPHERD_FIX_ONLY_SERVICES: "mctl-design,mctl-telegram,mctl-gitops,mctl-pairdesk"`
  and reduce `SHEPHERD_SKIP_SERVICES` to `"mctl-academy"`. Both files need it:
  the CWFT env is what the DevLoop's in-loop tick inherits.
- **mctl-api (out of repo, optional follow-up):** add a `fix_only` boolean to
  the `mctl-agents-shepherd` operation so `mctl_trigger_shepherd` can pass
  `--fix-only`. Not required — the env-driven mode already covers the
  steady state, and an admin can submit the CWFT directly.

## Alternatives

**Option 1 — give the pr-steward the review-fix step.** Most faithful to
"steward owns ONLY what the shepherd skips", but it means reimplementing
`apply_followup` + `review_feedback_one` in the claude-remote runtime: an
8 Gi Argo step that clones a sibling repo and may run `go build` does not
belong in a headless `claude -p` pod, and the sentinel-exit-code contract
(`EXIT_NO_FOLLOWUP_COMMITS`/`43`/`44`) plus the `review_attempts` cap would have
to be duplicated and kept in sync across two repos and two languages. Dropped:
the cost is a second implementation of the highest-risk code path on the
platform.

**Option 3 alone — expose `--review-feedback` on `mctl_trigger_implementer`.**
Smallest change, but it leaves the loop manual: an operator must notice the
stall, read the review, author a bundle JSON in the shepherd's schema, and
trigger. It does not close the DevLoop hole at all, and it puts a raw
"push arbitrary feedback to a PR branch" verb on the MCP surface. This design
supersedes it: `--fix-only --service --slug` gives the operator the same
one-call fix with the bundle built from the live review, and the same code path
runs unattended.

**A `.status.yaml`-driven owner field instead of an env list.** Record
`merge_owner: pr-steward` on the proposal at investigation time and have the
shepherd read it. Rejected as the *gate*: ownership is a property of the
repository, not of an individual proposal, so it would be re-derived and
re-written per proposal with an obvious drift failure mode, and a hand-edited
file could grant an agent merge rights on Academy. `merge_owner` survives here
only as an output projection, never as an input.

**Reuse `wait` for the deferred merge.** No new decision name, no
`_print_summary` change. Rejected because the issue's core complaint is
invisibility: `wait` already covers five genuinely different situations, and
folding "handed off to the steward" into it would leave the stall exactly as
unobservable as it is today.

## Platform impact

**Migrations.** None in the data model. `merge_owner` is a new optional
`.status.yaml` field; every writer goes through `update_status_file`, which
preserves unknown keys, so older readers and in-flight proposals are
unaffected. No status vocabulary change, so `docs/diagrams/archify/facts.yaml`
and `tests/test_diagram_facts.py` see no drift.

**Backward compatibility.** With `SHEPHERD_FIX_ONLY_SERVICES` unset and
`--fix-only` absent, `_service_mode` returns `FULL` or `SKIP` exactly as today
for every service except `mctl-academy`, which resolves to `SKIP` via the
unchanged `SHEPHERD_SKIP_SERVICES` entry. The only behavioural change with an
empty environment is the `merge_pr` never-merge guard, which can only fire for
Academy — a service that is skipped anyway.

**Resource impact.** Four repositories re-enter the shepherd's normal
discovery. Each `address-review` tick costs one SDK normalisation call (capped
by `SHEPHERD_BUDGET_USD`, default 5.00, charged in `main()`'s loop) plus one
implementer subprocess with `IMPLEMENTER_TIMEOUT_SECONDS = 900`. The
`MAX_REVIEW_ATTEMPTS = 3` cap bounds this at three fix cycles per proposal
before `review-stuck`. In-loop DevLoop ticks are bounded by
`SHEPHERD_TICKS_MAX = 12` at `SHEPHERD_TICK_EVERY_POLLS = 8` polls
(~4 h cadence) and become *useful* rather than no-ops, so the volume-provision
cost per tick is now paid for something.

**Risks and mitigations.**

- *An agent merges a steward-owned PR, bypassing squash-only or branch
  protection.* Mitigated by two independent gates (`decide()` returns
  `defer-merge`; `merge_pr` refuses `NEVER_MERGE_SERVICES`) plus a third
  defensive check in `process_one`'s merge branch, each covered by a test.
- *Misconfigured env re-enables merge on Academy.* Structurally impossible:
  `NEVER_MERGE_SERVICES` is a code constant read by `decide()` and `merge_pr`,
  not an env var.
- *Steward merges while the implementer is mid-push.* The implementer's
  `_branch_exists_on_origin` check returns exit 43, classified deterministic,
  consuming one `review_attempts` slot; the next tick observes `merged` and
  flips to terminal, clearing `merge_owner` and `review_attempts`. Worst case
  is one wasted slot, not a wedged proposal.
- *Shepherd and steward both comment on the PR.* The shepherd's only comment is
  `trigger_review`'s `@claude review` after a successful fix push, which is
  best-effort and already tolerant of failure. No merge conflict is possible
  because the steward never pushes commits.
- *gitops commit churn from `merge_owner`.* Written through
  `_update_status_if_changed`, so exactly one commit per proposal, then silence.
- *Rollout ordering.* Fix-only winning over skip makes the two gitops commits
  independent; and even a single-commit rollout that only adds
  `SHEPHERD_FIX_ONLY_SERVICES` is already correct.
