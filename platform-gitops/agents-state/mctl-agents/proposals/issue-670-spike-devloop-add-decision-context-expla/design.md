# Design: issue-670-spike-devloop-add-decision-context-expla

## Current state

What the approver gets today, and what binds the decision:

- `orchestrator/run_issue_investigator.py` writes the proposal triplet into
  the proposal dir in mctl-gitops. It then calls `post_proposal_comment`,
  which comments a gitops link and approval instructions on the issue. Both
  documents describe intent. Neither is a structured, grounded explanation
  of current behaviour, invariants, failure modes or review hot-spots.
  Grounding today is a prompt instruction ("cite real files"), and nothing
  checks it.
- `orchestrator/proposal_state.py`: `PROPOSAL_DIGEST_FILES = ("requirements.md",
  "design.md", "tasks.md", "proposed-content.md")`. `content_digest_of`
  builds a length-prefixed SHA-256 framing. The approve CWFT records it as
  `approval.content_digest`, and `approval_digest_verdict` refuses drift
  before the implementer starts.
- `orchestrator/temporal/activities/delegated_approval.py`:
  `request_devloop_approval` creates the `aar_` ActionApprovalRequest before
  the human is asked, bound to `<service>/<slug>` and to the content digest
  (via `read_proposal_content_digest`). `orchestrator/approval_evidence.py`
  re-reads the grant and requires `artifact_hash == current digest`, a human
  decider, and a single-use `executed` transition.
- `orchestrator/temporal/workflows/dev_loop.py`: investigate, then a bounded
  approval park (`approve` signal carrying `approval_ref`), then implement,
  then shepherd/merge watch. Per the comment text, an edited proposal
  supersedes the pending grant.
- Evidence and identity contracts that a decision context could reference:
  ADR 018 `ExecutionEvidence` (`orchestrator/execution_evidence.py`,
  `ApprovalRef`, `PolicyDecisionRef`), ADR 009 context snapshots
  (`orchestrator/context_snapshot.py`, `cs-` ids, recorded in `.status.yaml`
  `context.content_hash`), decision records (`orchestrator/decision_records.py`,
  mctl-api#701), and ADR 013 human input (a sealed, content-addressed
  artifact in the proposal dir: `human-input/request.json`).
- Spike conventions: `docs/spikes/796-rea-investigation-evidence.md`
  (`STATUS: DRAFT` plus allowed decision tokens, `unobserved` metric cells),
  `docs/spikes/757/` (a stdlib prototype with fixtures) with
  `tests/test_spike_757_attention.py`, and `tests/test_spike_796_report.py`
  (a guard that fails if `orchestrator`, `config` or `agents/_manifests`
  change). `orchestrator/spike_issue.py` makes the implementer emit
  `Refs`, not `Closes`, for a `spike(...)` title, so the owner records the
  verdict.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/issue-investigator-default/profile.yaml`:
  `budgetUsd: 8.00` and `timeoutSeconds: 7200` in the profile. A header
  comment says the effective budget is $3.00 from
  `cwft-mctl-agents-investigate.yaml`. This is the cost envelope to compare
  an explainer pass against.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-702-fix-devloop-a-failed-approval-must-not-p/`:
  the triplet (about 21.5 KB in total) plus `.status.yaml` with
  `status: merged`, `control.requires_human_approval: true` and
  `context.content_hash: sha256:4f1e30ea...`. This is a real, merged,
  approval-semantics proposal, so its implementation can be compared with
  an explainer generated from the proposal alone.
- `$MCTL_GITOPS_ROOT/services/` lists tenants `admins`, `karabu`, `labs`,
  `namax66`. The spike touches no deployed service, so no service config
  was read. The mctl MCP tools were not called: the spike needs no deployed
  runtime state.

## Proposed solution

A fixture-only spike PR in mctl-agents. Nothing in it runs in DevLoop.

### 1. Artifact contract `decision-context/v0`

The artifact is Markdown for the reader, with a fenced YAML front block for
the machine. It is validated by `docs/spikes/670/decision_context.py`
(stdlib plus `yaml`, already a dependency).

```yaml
schema: decision-context/v0
subject: {service: mctl-agents, slug: issue-702-..., issue: mctlhq/mctl-agents#702}
binding:
  proposal_content_digest: sha256:...   # proposal_state.content_digest_of
  target_repo: mctlhq/mctl-agents
  target_repo_sha: <40-hex>             # the tree the explanation reads
  context_snapshot_hash: sha256:...     # optional, from .status.yaml context
  generator: {model: ..., prompt_sha256: ..., generated_at: ...}
risk:
  level: high | medium | low            # advisory only
  areas: [approval-semantics, idempotency, durable-audit, ...]
sections:                               # fixed keys, in issue order
  what_changes / why / how_it_works_today / behaviour_after /
  invariants* / interfaces / security_governance* / failure_modes* /
  evidence* / review_pointers / not_changing
```

Each section is a list of claims: `{text, kind: explanatory|grounded,
refs: [...]}`. A ref is one of:

- `repo:<path>@<sha>#L<a>-L<b>`
- `proposal:<file>` (implicitly under the bound digest)
- `evidence:<test-id|ci-run|ev-...|we_...>`

Validator rules:

- Sections marked `*` are high-scrutiny. Every claim in them must be
  `grounded` with at least one ref.
- `review_pointers` entries must each carry a `repo:` ref and a `why`.
- A `repo:` ref's SHA must equal `binding.target_repo_sha`.
- `failure_modes` on a `risk.level: high` artifact must include `retry`,
  `timeout_partial`, `wrong_identity` and `state_after_approval` (each
  present, or marked `not_applicable` with a grounded reason).
- Unknown keys are rejected, as in ADR 013 and ADR 018.
- Keys such as `skip_review`, `auto_approve`, `satisfies_gate` or
  `waive_*`, anywhere in the document, are rejected. This is invariant 1:
  the explainer is not authority.
- An optional `ref_resolver` callback checks that each `repo:` path and line
  range exists at that SHA in a local clone. The tests use a fixture
  resolver.

`freshness(artifact, current_digest, current_sha) -> "fresh" | "stale" | "unknown"`
returns `unknown` when either current value is None, and `stale` on any
mismatch. It never infers `fresh` from a missing value. This is the same
rule as `approval_evidence`: uncertainty is never authorization.

### 2. Generation harness

`docs/spikes/670/explain.md` is the explainer prompt: grounded,
on-demand-focus aware (`focus: authz | persistence | retry | migration |
execution-path`). `docs/spikes/670/run_explainer.sh` documents the operator
command: Claude Agent SDK, read-only tools (`Read`, `Glob`, `Grep`), a clone
of the target repo checked out at the bound SHA, and the proposal dir. It
writes the artifact plus a `measurements.json` (latency, tokens, cost,
files read). The explainer runs as a separate read-only pass, not inside
the investigator. This is option B below: a separate pass can be
re-generated when stale without re-investigating, and it reads the code
instead of only restating the investigator's prose.

### 3. Experiment

- High-risk subject: mctl-agents#702. Generate from the proposal triplet
  with the repo pinned at the pre-implementation SHA (the merge-base of the
  #702 PR). Then compare against the merged PR diff:
  - review-pointer recall/precision against the files and functions the PR
    changed;
  - contradicted claims, recorded as polished-but-wrong;
  - `freshness()` against the post-merge SHA, which must report `stale`.
- Low-risk subject: one merged docs/presentation proposal, selected at
  implementation time from `agents-state/*/proposals` with
  `status: merged` and no `control.requires_human_approval`.
- Committed fixtures: the two generated artifacts, plus hand-written
  negative fixtures (ungrounded high-risk claim, SHA-mismatched ref, unknown
  key, gate-waiver key, missing failure mode).

### 4. Report `docs/spikes/670-decision-context.md`

- `STATUS: DRAFT` until the operator measurement run. Allowed tokens:
  `GO`, `LIMITED_GO`, `NO_GO`.
- Measurement table: every column from the issue, `unobserved` where not
  measured.
- Answers to Q1 to Q10. The spike's hypotheses, to be confirmed or refuted
  by the run:
  - Q1: after proposal, before the approval park.
  - Q2: a dedicated read-only pass.
  - Q3: repo at pinned SHA plus proposal digest plus evidence ids.
  - Q4: digest and SHA binding with `freshness()`.
  - Q5: correlate by putting the artifact digest beside the proposal digest
    in the grant, in a follow-up, not by adding it to
    `PROPOSAL_DIGEST_FILES`, because that would make approving the
    explanation part of approving the change.
  - Q9: grounded-claim enforcement plus retrospective contradiction count.
- Failure-mode section and a comparison with the current flow.
- On GO or LIMITED GO: a follow-up epic outline (proposal-time explainer
  activity, grant correlation in mctl-api, post-implementation drift check,
  on-demand slice explainer).

## Alternatives

- **A. Have the investigator write a fourth proposal file now.** Cheapest,
  with no extra pass. Dropped as the spike's arm because it restates the
  same model's prose (the issue's "not merely restate previous model
  prose"). It would also change the approved-content digest or sit outside
  it ambiguously, and it changes a runtime path before any evidence exists.
  The report still records it as a candidate integration point.
- **B. Build the explainer as a DevLoop activity/agent directly (no
  spike).** Dropped. The issue's disposition is P2/BACKLOG and asks to
  prototype on one real approval before adding a new agent or epic. A
  registered agent needs registry, profile and binding work (ADR 007) that
  a NO-GO would waste.
- **C. Reuse the ADR 018 ExecutionEvidence envelope as the artifact.**
  Dropped as the artifact itself. ExecutionEvidence is a sealed join of
  canonical ids with no prose by design. The decision context references
  it (`evidence:` refs) instead of extending it.

## Platform impact

- No migrations, no runtime or deployed-state change, no manifest, profile
  or binding change. The guard test enforces that `orchestrator/`,
  `config/` and `agents/_manifests/` are unchanged.
- Cost: one operator measurement run, about two explainer passes at about
  investigator scale (the effective investigator budget is $3.00 per run per
  the profile comment), plus reviewer time. All of it is outside cron.
- Risk: fixtures generated from a merged proposal could leak nothing
  sensitive. They cite public repo paths only, and committed fixtures hold
  no tokens or transcripts (size-capped as in the #796 guard).
- Risk: polished artifacts could bias a future reviewer. Mitigation: the
  artifacts live only under `docs/spikes/670/` and are never attached to a
  live proposal.
- The PR must say `Refs #670`, not `Closes`. `spike_issue` already
  enforces this for the `spike(` title.
