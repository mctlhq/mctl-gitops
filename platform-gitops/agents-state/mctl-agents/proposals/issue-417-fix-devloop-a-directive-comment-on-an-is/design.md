# Design: issue-417-fix-devloop-a-directive-comment-on-an-is

## Current state

**Discovery is label-only.** `orchestrator/run_issue_poller.py:93
search_labeled_issues(label)` shells out to
`gh search issues --owner mctlhq --label agents:intake --state open --json url`,
maps each url through `run_issue_investigator.try_parse_issue_url`, drops anything
that is not an `mctlhq` issue url, caps the cycle at `DEFAULT_MAX_ISSUES = 5`
dispatchable issues, then for each ref calls
`orchestrator.temporal.start.start_dev_loop_workflow(ref.url, client=client)` and
`remove_label(ref.url, label)` (line 133). No code path in this module reads issue
comments. `grep -rn 'reinvestigate'` over the clone returns nothing.

**The poll runs on a Temporal schedule.**
`orchestrator/temporal/workflows/issue_poll.py IssuePollWorkflow` executes exactly
one activity, `orchestrator/temporal/activities/issue_poll.py
poll_issues_activity(label, max_issues)`, which is a thin wrapper over
`run_issue_poller.poll(...)`; `docs/temporal-flow.md` records the 15-minute schedule.
This is the only recurring path that can start a `DevLoopWorkflow` without a human.

**The workflow id is the dedup ledger, and it is one-shot per issue.**
`orchestrator/temporal/issue_ref.py:workflow_id_for` returns
`dev-loop-{owner}-{repo}-{number}`; `start.py:start_dev_loop_workflow` starts it with
`id_reuse_policy=ALLOW_DUPLICATE_FAILED_ONLY` and
`id_conflict_policy=USE_EXISTING`. So a repeat start against a RUNNING loop is a
no-op, and a repeat start after a SUCCEEDED loop raises
`WorkflowAlreadyStartedError`, which the poller prints as "already handled"
(run_issue_poller.py:228-236). That is precisely why "ask again" cannot work today
even if someone re-added the label: on the canonical id, the second ask is defined as
already answered.

**Re-investigation itself already works.**
`run_issue_investigator.resolve_slug` (line 891) keys the proposal directory on the
issue NUMBER, reusing an existing `issue-<N>-*` directory whatever the issue is
called today, and raising `ProposalAmbiguityError` when there are two.
`investigate()` (line 1671) refuses only when the existing status is outside
`_OVERWRITABLE_STATUSES = {"proposed"}` (line 189, returning
`InvestigateResult.skipped_reason`), stages the agent's output beside the live
proposal, and `_carry_forward` (line 761) preserves files the rewrite did not touch.
So a second investigation of a `proposed` proposal is a supported, tested operation.

**Comment data is already fetched, and already discarded for triggering.**
`gh_issue_view` (line 917) requests
`--json number,title,body,state,url,comments` and packs each comment into
`IssueData.comments` as `(id, author, created_at, body)` (line 209-220). Only
`orchestrator/context_assembly.py` consumes it, as prompt context. `authorAssociation`
is in gh's response and is currently dropped.

**Acknowledging on the issue is an established move.**
`post_proposal_comment` (line 1137) already runs
`gh issue comment <url> --body ...`, renders the concrete workflow id via
`issue_ref.workflow_id_for`, and links the gitops tree through `_gitops_tree_url`.

**Durable proposal state.** `write_status_yaml` (line 1043) writes the initial
`proposed` payload with `source`/`control` blocks atomically, and its docstring
states the compatibility rule this design depends on: `_status_disagreements`
(line 588) checks only its five named fields and ignores unknown top-level keys, so
an additive block cannot forge an approval or misroute a `Closes` line. The Temporal
worker itself holds no gitops checkout — every durable write goes through an Argo
CWFT under the `mctl-gitops-main-writes` mutex (see `workflows/reconcile.py`
`APPLY_OPERATION = "mctl-agents-reconcile"`).

**The reconcile tick already walks every proposal.**
`orchestrator/temporal/activities/discovery.py _sync_discover_and_project` iterates
`_discover_refs(state_dir, reconcile=True)`, filters on `RECONCILE_INPUT_STATUSES`,
and returns a read-only `ReconcileDiscoveryResult(total_inspected, projections)`.
It is the natural place to notice a request that never became a run.

## Proposed solution

Four additions, all additive; the label path is untouched.

### 1. `orchestrator/directives.py` — pure grammar, no I/O

A dependency-free module so both the poller and the reconcile activity classify the
same way and unit tests need no stubs.

```python
DIRECTIVE_MENTION = "@MCTL"          # single constant; see open question
RECOGNISED_VERBS = frozenset({"reinvestigate"})
ACK_MARKER = "<!-- mctl-directive-ack: {comment_id} -->"

@dataclass(frozen=True)
class Directive:
    comment_id: str
    author: str
    author_association: str
    created_at: str
    verb: str | None        # None => mention present, verb unrecognised
    raw_first_line: str

def parse_directive(comment) -> Directive | None: ...
def answered_comment_ids(comments) -> frozenset[str]: ...
def is_authorized(d: Directive) -> bool: ...
```

`parse_directive` recognises the mention only at the start of the comment's first
non-blank line (case-insensitive), normalises the next token (lowercase, strip
punctuation, drop internal hyphens so `re-investigate` == `reinvestigate`), and
returns `verb=None` when the token is not in `RECOGNISED_VERBS`. A mention deeper in
the body is prose, not an instruction. `is_authorized` requires
`author_association in {"OWNER", "MEMBER", "COLLABORATOR"}` and a login not ending in
`[bot]` — this is the budget gate, since an accepted directive costs a full
investigation.

`answered_comment_ids` scans the same comment list for `ACK_MARKER` occurrences. The
bot's own replies are therefore the ledger: no new storage, and it rides the
`gh issue view --json comments` call the dispatcher already makes.

### 2. `IssueData` carries association, additively

`gh_issue_view` gains `authorAssociation` to its `--json comments` request and a new
field `IssueData.comment_records: tuple[IssueComment, ...] = ()` alongside the
existing 4-tuple `comments`. The 4-tuple stays exactly as it is, so
`context_assembly.collect_issue_comments` needs no change.

### 3. `orchestrator/run_directive_poller.py` — a second pass on the same tick

New module rather than surgery inside `run_issue_poller.poll`, so the label path's
existing test suite (`tests/test_run_issue_poller.py`) keeps asserting unchanged
behaviour.

```python
async def poll_directives(
    *, dry_run: bool = False, max_directives: int = DEFAULT_MAX_DIRECTIVES
) -> DirectivePollResult: ...
```

Per cycle:

1. **Candidates.** `gh search issues --owner mctlhq --state open --match comments
   --json url --limit 100 -- "@MCTL"`, filtered through `try_parse_issue_url`. Same
   shape and same 100-row cap warning as `search_labeled_issues`.
2. **Per issue, one `gh_issue_view`.** Parse every comment; keep directives that are
   authorized and whose `comment_id` is not in `answered_comment_ids(...)`.
3. **Classify, then answer.** Exactly one of:
   - unrecognised verb -> reply listing `RECOGNISED_VERBS`;
   - repo not in `config.settings.SERVICES` -> reply naming the repo;
   - no proposal directory -> reply pointing at the `agents:intake` label;
   - more than one `issue-<N>-*` directory -> reply naming both;
   - proposal status outside `_OVERWRITABLE_STATUSES` -> reply naming the status;
   - a prior directive run for this issue still RUNNING -> reply naming it;
   - otherwise **dispatch**.
   Every branch posts a reply carrying `ACK_MARKER.format(comment_id=...)`. There is
   no silent branch: that is the defect.
4. **Proposal lookup without a gitops checkout.** Read
   `agents-state/<service>/proposals/<slug>/.status.yaml` from `mctlhq/mctl-gitops`
   through the GitHub contents API, reusing the helper behind
   `orchestrator/temporal/activities/proposals.py find_proposal_slug` (the existing
   precedent for "the worker needs gitops state and has no checkout").
5. **Dispatch.** `start_dev_loop_workflow(issue.url, client=client,
   workflow_id=workflow_id_for_directive(url, comment_id))`. The id override is a new
   optional keyword on the existing function; policies stay
   `ALLOW_DUPLICATE_FAILED_ONLY` + `USE_EXISTING`.
   `issue_ref.workflow_id_for_directive` returns
   `dev-loop-{owner}-{repo}-{number}-d{sha256(comment_id)[:8]}`. A distinct id is
   *required*, not cosmetic: on the canonical id a completed loop rejects every
   restart (`WorkflowAlreadyStartedError`), which is exactly the "second ask does
   nothing" behaviour being fixed. Keying on the comment id makes Temporal's own id
   reuse the run-level dedup, so a retried tick, a crash between start and reply, or
   a duplicated search hit all converge on one run.
   `WorkflowAlreadyStartedError` here means "this directive already ran" -> still post
   the reply, do not start again, mirroring run_issue_poller.py:228.
6. **Bounds.** At most `max_directives` (default 3) dispatches per cycle; the rest are
   logged and answered next tick. `DIRECTIVE_TRIGGER_ENABLED=false` short-circuits the
   whole pass. Per-issue failures are counted, never fatal — identical to the label
   pass.

Wiring: new activity `poll_directives_activity` in
`orchestrator/temporal/activities/issue_poll.py`, registered in `worker.py`'s
`short_activities` list (lines 462-483) and executed by `IssuePollWorkflow` after
`poll_issues_activity` on the existing `issue-poll-mctl-agents-schedule`
(every 15 minutes, offset 7 minutes, `overlap=SKIP`, `worker.py:271-314`). That
schedule starts the workflow with a bare `IssuePollWorkflowInput()`, so the new
knob must carry a working default: `IssuePollWorkflowInput` gains
`max_directives: int = 3`; the result gains
`directives_started`/`directives_answered`/`directives_failed`. Adding a step to a
running workflow's history is guarded with `workflow.patched("directive-poll")`, the
pattern `dev_loop.py` already uses for `atomic-approve`.

### 4. Requester provenance and the reconcile backstop

**Provenance.** `DevLoopWorkflow`'s `IssueRef` gains optional
`requested_by` / `directive_comment_url` / `directive_comment_id`; they are forwarded
into `investigate_params` (dev_loop.py:893) as CWFT parameters, surfaced as
`--requested-by` / `--directive-comment-url` / `--directive-comment-id` on
`run_issue_investigator.main()`, and written by `write_status_yaml` as an additive
top-level `request:` block. Additive is load-bearing: `_status_disagreements`
(line 588) reads only its five named fields, so this block cannot affect approval or
the implementer's `Closes` line. Defaults are empty everywhere, so the label path
produces a byte-identical payload to today.

**Backstop.** `ReconcileDiscoveryResult` gains
`unactioned_directives: list[UnactionedDirective]`. For proposals whose
`source.type == github_issue` and whose status is in `_OVERWRITABLE_STATUSES`, the
sweep fetches the issue's comments and reports any directive whose `created_at` is
after `.status.yaml updated_at` and whose id is absent from
`answered_comment_ids(...)`. Read-only, capped (`RECONCILE_DIRECTIVE_SCAN_LIMIT`,
default 25 issues per tick, over-cap logged), and it writes nothing — it is the
report that the #395 silence lacked. The field defaults to `[]` so results recorded
before the change still deserialize.

**Docs, and the two that are test-enforced.** A new `docs/directives.md` states the
grammar, the authorization rule, and every refusal message verbatim.
`docs/agent-inventory.yaml` must gain the new trigger on the `issue-investigator`
entry (its `triggeredBy` currently lists only `mctl_trigger_issue` and
`run_issue_poller.py (agents:intake label)`), because `tests/test_agent_inventory.py`
asserts the inventory stays true; `docs/diagrams/archify/facts.yaml` is enforced the
same way by `tests/test_diagram_facts.py`. `docs/temporal-flow.md` and `README.md`
gain the second trigger edge into `DevLoopWorkflow`.

### Prior art this follows

`run_shepherd.py:1691-1695` already scans comments for a trigger phrase
(`"@claude review" in body.lower()`, newest-first) and filters authors against
`GATING_BOTS` (line 122) — same shape, different surface. `directives.py` is the
issue-side equivalent, extracted as a pure module so both consumers share one
grammar. Conventions from `CONTRIBUTING.md` apply: English only, no emoji, plain
`warn:`/`info:`/`error:` log prefixes, conventional commits, `ruff` (line-length
120, `S` rules on, per-call `# noqa: S603` at subprocess sites) and `mypy` clean.

One interaction worth naming: `context_assembly.collect_issue_comments` (line 438)
has no author filter, so the bot's own acknowledgement becomes a
`github-issue-comment` candidate on the next investigation. That is harmless — it is
classified `trust_tier="untrusted"` like every other comment, and
`ISSUE_INVESTIGATOR_CONTEXT_MODE` defaults to `off` — but the marker format is
deliberately an HTML comment so it renders as nothing in the issue UI and reads as
inert text in a prompt.

## Alternatives

**A GitHub Actions `issue_comment` workflow, as the issue literally proposes.**
Dropped as the primary mechanism. `mctl-agents`' own `.github/workflows/` cannot
observe comments on `mctl-telegram`, `mctl-web`, `portfolio`, or the other twelve
entries of `SERVICES` — it would need a workflow and a secret installed in every
repo, and GitHub runners cannot reach the in-cluster Temporal frontend, so each one
would have to call mctl-api's REST surface instead. That is a fifteen-repo rollout
plus a new credential distribution problem for a latency win over a tick the label
path already accepts. Kept as a clean follow-up: one reusable workflow in
`mctlhq/.github` that POSTs to mctl-api, with this poller as the backstop that makes
a missing installation visible instead of silent.

**Re-arm the `agents:intake` label instead of reading comments.** Dropped. The
mechanism is exactly the one that fails: after a successful loop,
`ALLOW_DUPLICATE_FAILED_ONLY` turns the re-labelled dispatch into
`WorkflowAlreadyStartedError`, printed as "already handled" and then the label is
removed — nothing runs and nothing says so, which is #417 restated. It also
contradicts the acceptance criterion forbidding label side-effects.

**Signal the existing `DevLoopWorkflow` with a `reinvestigate` signal**, beside the
existing `approve` signal (dev_loop.py:868). Dropped. A signal needs a live
execution, and the failure class here is re-requests arriving after the loop
finished — the #395 comments at 15:37 and 17:16 came after the 15:19 commit. It also
puts a second full investigate/approve/implement cycle inside one execution's
history, complicating the ADR-010 lifecycle claim (`dev_loop.py:459 LifecycleClaim`)
that assumes one entity phase per execution.

**Store the dedup ledger in `.status.yaml` rather than in the bot's reply.** Dropped.
The Temporal worker cannot commit to gitops — every durable write goes through an
Argo CWFT under the `mctl-gitops-main-writes` mutex — so the dispatcher would have to
submit a workflow just to record that it is about to submit a workflow. The reply is
already required by the acceptance criteria, already durable, and already fetched by
the same `gh issue view` call.

## Platform impact

**Migrations.** None. New module plus additive fields. `.status.yaml` gains an
optional `request` block that every existing reader ignores by construction;
`IssueData` gains a defaulted field; `ReconcileDiscoveryResult` and
`IssuePollWorkflowInput`/result gain defaulted fields so historical Temporal payloads
still deserialize.

**Backward compatibility.** The `agents:intake` path, `remove_label`,
`workflow_id_for`, and the canonical `dev-loop-{owner}-{repo}-{number}` id are
unchanged. `tests/test_run_issue_poller.py` should pass untouched — treat any
required edit to it as a signal that the label path was disturbed.

**Cross-repo risk: directive-suffixed workflow ids.** mctl-api's `mctl_get_dev_loop`
derives the workflow id from the issue url, so it will not find a `-d<hash>` run and
will answer 404 ("no loop for this issue") while one is live. Mitigations: the reply
names the exact id (and the approve route takes a `workflow_id` path parameter, so
approving a directive run already works); `docs/directives.md` states it; and the
follow-up is a one-line change in mctl-api to accept an explicit id. Same caveat for
ADR-010 ownership rows keyed by `devloop-workflow` owner ids — the refusal branch
("a prior directive run is still RUNNING", checked via the existing visibility
helper `activities/visibility.py list_active_dev_loop_ids`) keeps two live loops for
one issue from contending in the first place.

**Resource and budget impact.** An accepted directive costs one full investigation
(~$3 of subscription quota) plus a clone. Three gates bound it: the authorization
check (`OWNER`/`MEMBER`/`COLLABORATOR` only), `max_directives` per cycle (default 3),
and the "prior run still RUNNING" refusal. The added GitHub API traffic is one
`gh search` plus one `gh issue view` per candidate issue per tick; the reconcile
backstop is capped at 25 issues per tick.

**Security.** The directive body is untrusted input from an arbitrary GitHub user.
Only the leading mention and the single following token are ever interpreted; no
text from the comment is forwarded as an instruction. Comment text that reaches the
prompt does so through the existing context-assembly path, which already applies
`_neutralize_prompt_tags` (run_issue_investigator.py:1181). The authorization gate is
what stops a drive-by commenter from spending agent budget, and replies to
unauthorized directives are off by default so the bot cannot be used as an
amplifier.

**Risks.** (1) GitHub comment-search indexing lag can delay a directive by minutes —
accepted, and the reconcile backstop reports anything the search never surfaced.
(2) A reply that fails after a successful start would re-run on the next tick if the
ledger were the only guard; it is not — the comment-derived workflow id makes the
restart a no-op and only the reply is retried. (3) A malformed or hand-edited
`.status.yaml` in gitops makes the precondition unreadable; that branch replies "could
not read the proposal's status" rather than dispatching blind.
