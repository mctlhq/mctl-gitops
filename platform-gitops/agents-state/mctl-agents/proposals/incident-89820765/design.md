# Design: incident-89820765

## Diagnosis
The Argo ClusterWorkflowTemplate `mctl-agents-implement`
(argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml) ran
`orchestrator.run_implementer` against the accepted proposal
mctl-telegram/issue-510-add-self-identification-tool-get-my-iden. Both the
primary attempt and the account-2 fallback attempt completed a full,
successful Claude Agent SDK session and each correctly determined that the
proposal is stale: the requested tool (`get_my_identity`) already exists on
`main` (shipped under issue #540), with semantics that differ from what the
proposal asks for, so implementing it as written would silently change
already-shipped, tested behavior. Both attempts intentionally made no commit
and exited 1 to signal "no commit produced."

The workflow template treats any non-zero exit from `run_implementer.py` as a
failed attempt, regardless of whether the exit reflects a real error or a
deliberate, correct refusal to touch shipped code. Because neither the
primary nor the fallback step reports `Succeeded`, `assert-attempt` fails the
whole workflow, and `notify-telegram` files a generic `workflow_failed`
incident whose canned diagnostic text ("Most often the Claude
five_hour/seven_day usage limit / HTTP 429 on both accounts, or token-2
unset") is not what happened here — both accounts worked correctly and spent
real budget (~$1-2 combined) confirming the same conclusion twice. The
underlying gap is that `run_implementer.py` (and/or the implementer
sub-agent's output contract) has no distinct, machine-readable outcome for
"proposal is already implemented / superseded" that is different from
"implementer errored." A sibling incident with the identical pattern is
argo-mctl-agents-implement-c36902fb-1789820445 (proposal
.github/issue-67-feat-roadmap-control-plane-reconcile-epi), diagnosed
separately as incident-89820445 in this same target service.

## Confidence: LOW
This diagnosis is built entirely from Argo step logs and the SDK transcript;
the actual source of `orchestrator/run_implementer.py` was not available to
verify the current exit-code/status-write logic, so the exact code change
below needs verification against that file before it is applied.

## Proposed Fix
In `orchestrator/run_implementer.py` (mctl-agents repo), distinguish a
deliberate "no gap left to implement" refusal from a genuine implementer
error:
- Detect the refusal outcome (the SDK sub-agent's transcript/scratch file
  already carries a structured signal in at least one observed run: a
  `.implementer-refusal.json` with `{"refused": true, "reason": "..."}` — the
  same convention should be made authoritative for both repos' implementer
  sub-agents instead of relying on free-text detection).
- When refused=true: write `.status.yaml` status as `needs-triage` (or a new
  `superseded` status if the orchestrator's status vocabulary supports
  adding one) carrying the refusal reason in `notes`, and have
  `run_implementer.py` exit 0 for that proposal instead of 1.
- Because the CWFT's `implement-fallback` step only runs
  `when: "{{steps.implement.status}} != Succeeded"`, a primary attempt that
  exits 0 on a refusal will skip the fallback entirely, removing the
  duplicate-cost account-2 re-run for a case where a second opinion cannot
  produce a different, useful answer.
- `assert-attempt` then sees a `Succeeded` primary step and the workflow
  reports success rather than filing a misleading `workflow_failed`
  incident.

## Scope
Minimal: touch only the outcome classification and status/exit-code path in
`orchestrator/run_implementer.py` for the "no gap left to implement" case.
Do not change the CWFT YAML, the proposal-claim mutex, or any other exit
path (genuine implementer errors must keep failing loudly).
