# Design: issue-417-fix-devloop-a-directive-comment-on-an-is

## Current state

### Intake is label-only and comment-blind

`orchestrator/run_issue_poller.py` is the entire automatic intake surface.
`search_labeled_issues()` (lines 93-130) shells out to

```
gh search issues --owner mctlhq --label agents:intake --state open --limit 100 --json url
```

It requests `--json url` and nothing else — no title, no `updatedAt`, and no
comments. `poll()` (lines 138-262) filters the result to `config/settings.py
SERVICES`, applies `--max-issues` (default 5), calls
`start_dev_loop_workflow(ref.url, client=client)` per issue, and then
`remove_label()` (lines 133-135, `gh issue edit <url> --remove-label`).

`poll()` is reached three ways, all converging on the same function:
`python -m orchestrator.run_issue_poller`, the Temporal activity
`poll_issues_activity` in `orchestrator/temporal/activities/issue_poll.py:19`,
and in production the `IssuePollWorkflow` schedule registered in
`orchestrator/temporal/worker.py:271-316` — `every=15m, offset=7m,
overlap=SKIP`, schedule id `issue-poll-mctl-agents-schedule`. The old Argo
`cronworkflow-mctl-agents-issue-poll.yaml` is suspended.

Nothing on that path reads a comment. Grepping the clone for `@MCTL`,
`reinvestigate` or `directive` returns exactly one hit — the prompt-hardening
sentence at `orchestrator/run_issue_investigator.py:1290`, which tells the model
to treat issue text as data and ignore directives inside it. That is the issue's
claim, confirmed.

### The label is not a repeatable gesture either

`orchestrator/temporal/start.py:30-72` is the single place the workflow-ID
scheme and dedup policy live:

```python
return await client.start_workflow(
    DevLoopWorkflow.run,
    IssueRef(issue_url=issue_url),
    id=workflow_id_for(issue_url),          # dev-loop-{owner}-{repo}-{issue}
    task_queue=TASK_QUEUE,
    id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
    id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
)
```

So re-adding `agents:intake` to ask again resolves to one of two silences:

- the loop is RUNNING (for an un-approved proposal it is parked at
  `await workflow.wait_condition(lambda: self._approved)`,
  `orchestrator/temporal/workflows/dev_loop.py:908`) — `USE_EXISTING` returns the
  existing handle and nothing new happens;
- the loop SUCCEEDED — `ALLOW_DUPLICATE_FAILED_ONLY` raises
  `WorkflowAlreadyStartedError`, which `run_issue_poller.py:228-236` deliberately
  logs as `OK (already handled)` and then strips the label again.

Only a FAILED prior run restarts. This is why #395's two later requests produced
nothing even in principle: the gesture the docs point at cannot express "do it
again".

### Re-investigation itself already works — it just has no trigger

`run_issue_investigator.investigate()` is built for repeat runs.
`resolve_slug()` (line 891) reuses an existing `issue-<N>-*` directory whatever
the issue is called today, and the idempotency guard at lines 1697-1704 permits a
rewrite exactly when the status is overwritable:

```python
_OVERWRITABLE_STATUSES = {"proposed"}     # line 189
...
if existing and existing_status not in _OVERWRITABLE_STATUSES:
    reason = (f"proposal {service}/{slug} already at status "
              f"'{existing_status}' — refusing to overwrite in-flight work")
```

The agent writes into a staging directory and the publish is a two-rename swap,
so a re-investigation that fails leaves the previous proposal intact. Both of
#395's landed rewrites went through this path — driven by out-of-band
`mctl_trigger_issue` dispatches, not by the comments they appear to answer.

### There is no comment-reply or marker-comment machinery

`post_proposal_comment()` (`run_issue_investigator.py:1137-1173`) is the only
issue-comment writer, and it posts unconditionally:

```python
_run(["gh", "issue", "comment", issue_url, "--body", body])
```

called once from `investigate()` (lines 2166-2176) inside a non-fatal
`except subprocess.CalledProcessError` wrapper. No HTML-comment marker exists
anywhere in the repo, and no code asks "have I already replied to this?". The
nearest precedent is on the PR side: `run_shepherd.py:1682-1755` reads PR issue
comments and matches a bot marker string (`No P1/P2 findings`) as evidence, and
`run_shepherd.py:1195-1198` discovers a PR by finding the marker
`agents-state/{service}/proposals/{slug}/` in its body.

### Reconcile walks every proposal but cannot see this condition

`ReconcileWorkflow` (`orchestrator/temporal/workflows/reconcile.py:76`) runs
every 15 minutes at offset 3 and calls `discover_and_project`
(`activities/discovery.py:122`), which in production reads every `.status.yaml`
on mctl-gitops main via `gitops_state.list_proposal_refs()`. That returns
`ProposalStateRef(service, slug, status, pr_url)` — `_read_blob` extracts only
those two values from the YAML, so the tick has no `updated_at` to compare a
comment against, and never looks at the issue at all.

### Reference: what #395 actually looks like on disk

`.status.yaml` carries no `service`, `slug` or `requester` field — those are the
directory path. The requester equivalent is the `source` block written by
`write_status_yaml` (`run_issue_investigator.py:1043-1128`):

```yaml
status: proposed
updated_at: '2026-09-19T15:18:29Z'
updated_by: mctl-agents[bot]
source: {type: github_issue, repo: mctlhq/mctl-agents, issue: 395, url: ...}
control: {requires_human_approval: true}
```

`orchestrator/proposal_state.py:145` `update_status_file()` is the shared
read-merge-write for every later transition; it preserves unknown fields, so a
new block can be added without touching other writers.

## Proposed solution

Three additions, in dependency order. Each is independently useful; together they
close both halves of the silence.

### 1. `orchestrator/directives.py` — pure parsing, closed vocabulary

A new dependency-free module so the recognition rule is a pure function that can
be exhaustively tested without `gh`, Temporal or a clone. It exports:

```python
MENTION_TOKENS = ("@mctl", "@mctl-agents", "@mctl-agents[bot]")
VERBS = {"reinvestigate": Verb.REINVESTIGATE}
BOT_LOGINS = frozenset({"mctl-agents[bot]", "mctl-app"})
PRIVILEGED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

@dataclass(frozen=True)
class Directive:
    comment_id: str
    author: str
    created_at: str
    verb: str | None          # None == mention present, verb unrecognised
    authorized: bool

def parse_comment(comment) -> Directive | None   # None == not a directive at all
def parse_comments(comments) -> list[Directive]
```

Three rules carry the security posture, mirroring the one already stated in
`run_issue_investigator.py:1287-1294`:

- Only the verb is read, and only from `VERBS`. The rest of the comment body is
  never forwarded into a prompt, a shell argument or a CWFT parameter. The
  commenter cannot steer the investigator by writing instructions — they can
  only select one of a fixed set of actions.
- A comment whose author is in `BOT_LOGINS` is not a directive. Without this the
  acknowledgement posted in step 2 would be re-read as a request on the next
  tick.
- Only the GitHub login is propagated onward, and only after matching
  `^[A-Za-z0-9-]{1,39}$`.

A mention with no matching verb yields `Directive(verb=None)` rather than `None`.
That distinction is the whole difference between "unrecognised instruction, here
is a reply" and the silence this issue is about.

### 2. `orchestrator/run_issue_directive_poller.py` — the trigger

A second scan, structurally parallel to `run_issue_poller.poll()` and sharing
its `_run`, its per-issue failure tolerance and its cap discipline:

```python
async def scan(dry_run: bool = False, max_directives: int = DEFAULT_MAX_DIRECTIVES) -> DirectiveScanResult
```

**Discovery is driven by the proposal set, not by GitHub search.** For each
non-terminal proposal from `gitops_state.list_proposal_refs()`, the slug's
`issue-<N>-` prefix plus the service name reconstruct the issue URL, and one
`gh issue view --json number,url,state,comments` per candidate yields the
comments. Two reasons over `gh search issues --match comments "@MCTL"`: search
is index-lagged, and an indexing delay here would reintroduce exactly the
silence being fixed; and the issue's own framing ("the reconcile tick already
walks every proposal") points at the proposal set as the authoritative
enumeration. The cost is one `gh issue view` per live proposal per tick —
against the 5000/hour limit that is the same order as the arithmetic already
recorded in `worker.py:284-291` for the label search.

**Dedup is an acknowledgement marker comment, not a gitops write.** After acting
on a directive the scan posts a reply ending in a machine-readable trailer:

```
<!-- mctl-directive-ack: <comment_node_id> -->
```

A directive is actionable iff no comment on the issue carries an ack trailer for
its comment id. This makes the durable dedup record and the human-facing
acknowledgement the same artifact, which is the right shape here for three
reasons: the reply is required by the acceptance criteria anyway; GitHub is
already authoritative for issue state; and the Temporal worker has no gitops
checkout and no deploy key (the invariant whose violation OOMKilled the incident
responder, #179), so a `.status.yaml`-based marker would have to queue behind
the `mctl-gitops-main-writes` mutex through an mctl-api operation for every
single tick. Two identical directives posted as two comments have two comment
ids, so they produce two runs — one per request, which is what the issue asks
for. The same comment observed on ten consecutive ticks produces one.

Ordering matters: the ack is posted **after** a successful submit and carries
the returned workflow name. If the submit fails, no ack is written, the reply
says the dispatch failed, and the next tick retries — the same "leave the marker
off so it retries" discipline `run_issue_poller` applies to the label.

**Dispatch.** For a recognised, authorized `reinvestigate` on a proposal at a
status in `_OVERWRITABLE_STATUSES`, the scan submits the mctl-api operation
`mctl-agents-investigate` (the same operation `DevLoopWorkflow` submits at
`dev_loop.py:898`) with `issue_url`, the resolved `slug`, and
`requested_by=<login>`. It deliberately does **not** start or signal a
DevLoopWorkflow:

- the workflow id is already taken, and both `USE_EXISTING` and
  `WorkflowAlreadyStartedError` are no-ops as shown above;
- a loop parked at `wait_condition(self._approved)` must stay parked. The
  re-investigation rewrites the proposal in place (same slug, `proposed` ->
  `proposed`), and when the human later signals approve, the loop implements the
  **rewritten** proposal. That is precisely the semantics the #395 commenter
  wanted, and it is achieved by not disturbing the workflow at all.

Every non-dispatch outcome is a reply, not a silence: no proposal directory
(point at `agents:intake`), status not overwritable (name the status), ambiguous
`issue-<N>-*` directories (name them), unauthorized author, unrecognised verb.

**Recording the requester.** `requested_by` and the requesting comment URL ride
the CWFT parameters into the investigator, which extends `write_status_yaml`'s
payload with a `request` block alongside the existing `source` block:

```yaml
request:
  by: mashkovd
  comment: https://github.com/mctlhq/mctl-agents/issues/395#issuecomment-...
  received_at: '2026-09-19T15:37:00Z'
```

`update_status_file()` preserves unknown fields, so no other writer needs to
change.

**Wiring.** The scan is invoked from the existing `IssuePollWorkflow` tick as a
second activity after `poll_issues_activity` — same 15-minute schedule, same
offset, no new Temporal schedule, no new mutex contention, and no change to the
label path. `IssuePollWorkflow.run` gains the second `execute_activity` behind
`workflow.patched("directive-scan")` so in-flight and replayed executions keep
their recorded command stream.

### 3. Reconcile reports a directive that never became a run

Belt-and-braces for the case where step 2 itself is broken, down, or
capped-out — the condition the issue explicitly asks to surface.

`gitops_state._read_blob` / `ProposalStateRef` gain `updated_at` (it is already
in the YAML being parsed; this is a field extraction, not a fetch).
`discover_and_project` then reports, alongside `projections`, a
`stale_directives: list[StaleDirective]` naming each proposal whose issue
carries a directive-shaped comment newer than the proposal's `updated_at` with
no matching ack. `ReconcileWorkflowResult` gains the field (defaulted to `None`,
so results recorded before it existed still deserialize — the same discipline
`applied` and `lifecycle` already use), and the workflow logs it.

Report-only, behind `workflow.patched("directive-staleness")`. Reconcile does not
dispatch: acting is step 2's job, and a reconcile tick that started SDK runs
would be a second, racing trigger for the same request.

### Documentation

`agents/_manifests/issue-investigator/agent.yaml` lists its triggers explicitly:

```yaml
  triggers:
    - mctl_trigger_issue (MCP, admin-only)
    - orchestrator/run_issue_poller.py (agents:intake label)
```

The new trigger is added there and in `docs/agent-inventory.yaml` (machine-checked
by `tests/test_agent_inventory.py` and `tests/test_manifest.py`), and the verb
vocabulary is documented in `README.md` so `@MCTL reinvestigate` is a documented
gesture rather than folklore.

## Alternatives

**A GitHub Actions `issue_comment` workflow.** The obvious shape, and the one the
issue's "Proposed fix" reaches for first. Dropped as the primary mechanism for a
concrete reason: the workflow file would live in `mctlhq/mctl-agents`, but the
pipeline serves fourteen repos listed in `config/settings.py SERVICES`. A
per-repo `issue_comment` handler means fourteen copies to keep in sync, each
needing an mctl-api credential in that repo's Actions secrets. The existing
`issue_comment` precedent in this repo — `.github/workflows/claude-review.yml` —
works because it delegates to an org-level reusable workflow, which is a
different and heavier piece of infrastructure than this change needs. A poller
covers every service with one code path and no per-repo secrets. The Actions
route stays available later as a latency optimization layered on top of a
mechanism that already works.

**A `reinvestigate` signal on `DevLoopWorkflow`.** Architecturally tidy: add
`@workflow.signal def reinvestigate(...)` beside the existing `approve` handler
(`dev_loop.py:868-881`) and have the approval park re-submit the investigate CWFT
when it fires. Dropped as the primary path on coverage and blast radius. It only
helps an issue whose loop is currently RUNNING — a SUCCEEDED loop, a FAILED one,
or an issue that never had a loop (like #395, whose events show zero `labeled`
events for its entire life) gets nothing, which is the same silence in a new
place. It cannot answer an unrecognised directive at all, because there is no
workflow to receive it. And it means surgery inside the one `wait_condition` the
approval gate depends on, gated by another `workflow.patched` marker, on a 2676-line
workflow with a 192 KB replay suite. Worth revisiting once the comment path has
earned trust; not the thing to build first.

**Make the label the repeatable gesture instead** — have the poller re-dispatch
on a re-added `agents:intake`. Dropped because it cannot be made to work without
changing the workflow-ID scheme: `ALLOW_DUPLICATE_FAILED_ONLY` exists so a FAILED
run stays restartable (codex P1 on #241), and loosening it to
`ALLOW_DUPLICATE` would let a mass-relabel event re-run completed loops. Minting
a per-request workflow id (`dev-loop-...-{n}-r2`) would fork the durable identity
every other component keys off — `find_proposal_slug`, `detect_orphans`,
`list_active_dev_loop_ids` and the lifecycle store all assume one loop id per
issue.

**Write the dedup marker into `.status.yaml` rather than as an ack comment.**
Rejected on the worker's own constraint: no gitops checkout, no deploy key, so
every marker write becomes an mctl-api operation queued behind the shared
`mctl-gitops-main-writes` mutex — a gitops commit per observed comment, on a
15-minute tick, to record something GitHub already knows. The requester still
lands in `.status.yaml`, but as an output of the run, not as a precondition of
starting it.

## Platform impact

**Migrations.** None. No schema change, no data migration. The `request` block in
`.status.yaml` is additive and optional; `update_status_file()` already preserves
fields it does not set, and every reader tolerates unknown keys.

**Backward compatibility.** The label path is untouched — `search_labeled_issues`,
`remove_label` and the `agents:intake` semantics keep their exact behaviour, and
the new scan never touches labels. Proposals with no ack comments behave as
before. `ReconcileWorkflowResult.stale_directives` and
`ProposalStateRef.updated_at` are defaulted so previously recorded activity
results still deserialize. Both workflow changes sit behind `workflow.patched`
markers (`directive-scan`, `directive-staleness`) so in-flight and replayed
executions keep their recorded command stream; `tests/test_workflow_replay.py`
with the fixtures under `tests/fixtures/histories/` is the check on that.

**Resource impact.** GitHub reads grow by roughly one `gh issue view` per
non-terminal proposal per 15-minute tick. At ~50 live proposals that is ~4800
requests/day against a 5000/hour limit — the same order as the arithmetic already
recorded for the label search in `worker.py:284-291`. SDK spend is the real cost
and is bounded three ways: the per-tick `--max-directives` cap (default 3), the
one-run-per-comment-id ack marker, and the `_OVERWRITABLE_STATUSES` guard, which
refuses to re-investigate anything an implementer owns.

**Risks and mitigations.**

- *Prompt injection via a directive comment.* Comment bodies are untrusted text
  written by arbitrary GitHub users. Mitigation: only a verb from a closed
  vocabulary is read; no byte of the body reaches a prompt, a shell argument or a
  CWFT parameter. The only propagated field is the GitHub login, validated
  against `^[A-Za-z0-9-]{1,39}$`.
- *Unprivileged dispatch.* Anyone can comment on a public issue, and a directive
  starts a paid SDK run. Mitigation: act only on `authorAssociation` in
  {OWNER, MEMBER, COLLABORATOR}; everyone else gets an explicit refusal reply,
  which is still not silence.
- *Acknowledgement loop.* A bot reply containing `@MCTL` could be read as a new
  directive. Mitigation, belt and braces: bot-authored comments are never
  directives, and an acked comment id is never actionable again.
- *Racing an implementer.* A re-investigation that clobbered an accepted proposal
  would destroy in-flight work. Mitigation: the scan checks the status before
  dispatching, and `investigate()`'s own guard at lines 1697-1704 plus the
  `_ProposalAdvanced` check inside the publish block refuse the write
  independently — two guards, neither relying on the other.
- *Comment-read failures blinding the scan.* Mitigation: a failure on one issue
  is logged and the scan continues, matching `poll()`'s per-issue tolerance; the
  tick exits non-zero only on a global failure.
- *The ack marker being the only dedup record.* If GitHub is unreachable the scan
  cannot read acks — but it also cannot post replies or read comments, so it
  dispatches nothing. The failure mode is "no directives handled this tick",
  not "every directive handled twice".
