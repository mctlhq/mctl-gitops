# spike(devloop): decision-context explainer before human approval

## Context

Issue mctlhq/mctl-agents#670 asks whether DevLoop should add a first-class
"Explainer / Decision Context" artifact at the human approval gate. The
artifact would give the approver grounded context: intent, current behaviour,
invariants, failure modes, evidence, and a short list of places where
line-level review matters. The goal is that approval depends on
understanding, not on reading every generated line. The issue is a spike.
Its deliverable is a measured recommendation (`GO`, `LIMITED GO` or `NO-GO`)
plus, on GO, follow-up issues. It does not ask for a runtime feature.

Today the approver sees only the proposal triplet (`requirements.md`,
`design.md`, `tasks.md`) and the issue comment written by
`orchestrator/run_issue_investigator.py:post_proposal_comment`. The approval
is already bound to exact content: `orchestrator/proposal_state.py:content_digest_of`
hashes `PROPOSAL_DIGEST_FILES`, the `aar_` grant carries that digest as
`artifact_hash`, and `orchestrator/approval_evidence.py` refuses execution
on a mismatch. A decision-context artifact has to fit beside this binding
without weakening it. This spike follows the repository's spike convention
(`docs/spikes/<n>-*.md` with a DRAFT report, fixture-only prototype under
`docs/spikes/<n>/`, guard tests; see #757 and #796). It changes no runtime
path.

## User stories

- AS a DevLoop approver I WANT a grounded decision-context artifact next to
  the proposal SO THAT I can make an informed approve/reject decision
  without reading every low-risk line.
- AS a DevLoop approver I WANT the artifact to name the few files, functions
  and contracts that deserve line-level review SO THAT I spend my scrutiny
  where the risk is.
- AS a platform owner I WANT the artifact bound to the exact proposal digest
  and repository SHA it describes SO THAT a stale explanation is detected
  and never silently reused.
- AS a platform owner I WANT measured cost, latency and reviewer-effort data
  SO THAT the GO / LIMITED GO / NO-GO decision rests on evidence, not
  intuition.
- AS an auditor I WANT a design for correlating the artifact identity with
  the approval decision SO THAT I can later answer "what context did the
  approver see?".

## Acceptance criteria (EARS)

- WHEN the spike PR is opened THE SYSTEM SHALL contain a report
  `docs/spikes/670-decision-context.md` that is either marked
  `STATUS: DRAFT` or carries exactly one decision token from
  `GO`, `LIMITED_GO`, `NO_GO`.
- WHEN the spike PR is opened THE SYSTEM SHALL contain a versioned artifact
  contract (`decision-context/v0`): its required sections, its claim model
  (each claim is `explanatory` or `grounded`), its grounding reference kinds
  and its binding block. The contract SHALL be documented in the report and
  implemented as a stdlib validator in `docs/spikes/670/decision_context.py`.
- WHEN a claim sits in a section marked high-risk (invariants,
  security/authorization/governance impact, failure modes, evidence) THE
  SYSTEM SHALL reject the artifact unless the claim carries at least one
  grounding reference: a repository path pinned to a commit SHA with a line
  range, a proposal file under the bound digest, or an evidence id
  (test name, CI run, `ev-`/`we_` id).
- WHEN the validator is given the artifact plus a current proposal content
  digest and a current target-repository SHA THE SYSTEM SHALL return exactly
  one of `fresh`, `stale` or `unknown`. `stale` SHALL apply when either
  bound value differs. `unknown` SHALL apply when either current value cannot
  be observed. `unknown` SHALL never be reported as `fresh`.
- WHEN the binding block records a proposal digest THE SYSTEM SHALL compute
  it with `orchestrator.proposal_state.content_digest_of`. The spike SHALL
  NOT introduce a second digest framing.
- WHILE the artifact carries a risk classification THE SYSTEM SHALL treat it
  as advisory only. The validator SHALL reject any artifact field that
  claims to skip, lower or satisfy an approval, policy or CI gate.
- WHEN the prototype runs THE SYSTEM SHALL produce one decision-context
  artifact for at least one real high-risk DevLoop proposal: the merged
  mctl-agents#702 proposal (approval semantics / canonical WorkItem
  projection). That artifact SHALL cover retry, timeout/partial execution,
  wrong identity and state changing after approval.
- WHEN the prototype runs THE SYSTEM SHALL also produce one artifact for a
  low-risk proposal, so the two expected review depths can be compared.
- WHEN measurements are recorded THE SYSTEM SHALL report, per artifact:
  generation latency, input/output tokens and cost, artifact bytes, the
  files and context inspected, reviewer time to decision for the current
  path and the experimental path, risks surfaced, whether the review
  pointers matched the paths the merged PR actually changed, and post-merge
  accuracy. Any value not measured SHALL be written `unobserved`, never
  estimated.
- IF the post-implementation comparison finds a claim in the artifact that
  the merged change contradicts THEN THE SYSTEM SHALL record it in the
  report as a "polished-but-wrong" failure instance.
- WHEN the report is finalized THE SYSTEM SHALL answer the issue's ten
  questions and document the failure modes (polished-but-wrong, stale
  context, rubber-stamping, digest-scope confusion). On GO or LIMITED GO it
  SHALL list proposed follow-up issues.
- WHILE this spike is open THE SYSTEM SHALL NOT change `orchestrator/`,
  `config/` or `agents/_manifests/`, and SHALL NOT change
  `PROPOSAL_DIGEST_FILES`, the approval park, or the issue comment. A guard
  test SHALL enforce this.

## Out of scope

- Any runtime change to DevLoop, the investigator, the implementer, the
  shepherd, the approval park, `aar_` grants or the approve CWFT.
- Writing decision-context artifacts into live proposal directories in
  mctl-gitops, or adding them to `PROPOSAL_DIGEST_FILES`.
- A new registered agent, ExecutionProfile or release binding.
- Post-implementation (diff-time) explainers beyond the one retrospective
  accuracy check on #702. A follow-up may build them.
- Using the risk classification to change any gate, or auto-approving.
- Recording the final verdict in the mctlhq/.github SpikeDefinition. The
  issue owner does that (see `orchestrator/spike_issue.py`).

## Open questions

- Reviewer-effort measurement needs a human reviewer who has not already
  read #702. The implementer cannot supply one, so reviewer timings stay
  `unobserved` until an operator run. The report stays `STATUS: DRAFT` until
  then.
- Freshness grounding: should a binding to the target-repository SHA also
  pin the investigator's context snapshot (`cs-` content hash in
  `.status.yaml` `context.content_hash`)? The prototype records it when
  present, but makes freshness depend only on the proposal digest and the
  repository SHA.
- If the answer is GO, where should the artifact live? (a) a fifth file
  inside the digest (approved content), or (b) a separately digested
  sidecar named in the `aar_` grant. The spike recommends; it does not
  decide.
- The issue links the Anthropic code-review post as context. The spike does
  not depend on its content and does not re-verify it.
