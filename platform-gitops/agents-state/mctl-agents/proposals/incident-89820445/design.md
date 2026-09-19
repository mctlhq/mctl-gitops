# Design: incident-89820445

## Diagnosis
Same root cause as the sibling incident diagnosed as incident-89820765 in
this same target service (argo-mctl-agents-implement-1318e8f2-1789820765,
proposal mctl-telegram/issue-510-add-self-identification-tool-get-my-iden):
the Argo ClusterWorkflowTemplate `mctl-agents-implement`
(argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml) ran
`orchestrator.run_implementer` against the accepted proposal
.github/issue-67-feat-roadmap-control-plane-reconcile-epi. The primary
attempt completed a full, successful Claude Agent SDK session, ran the
target repo's own offline test suite (220 tests, all passing) to confirm,
and correctly determined that every deliverable in tasks.md is already
implemented and merged on `main`. It wrote a structured
`.implementer-refusal.json` (`refused: true`) and intentionally made no
commit, exiting 1 to signal "no commit produced."

Because `run_implementer.py` and the CWFT treat any non-zero exit as a
failed attempt, the account-2 fallback re-ran the identical, already-decided
question at additional Claude budget cost, `assert-attempt` then failed the
whole workflow because neither step reported `Succeeded`, and
`notify-telegram` filed a generic `workflow_failed` incident whose canned
text blames Claude usage limits / an unseeded fallback token — neither of
which happened; both attempts ran to completion and agreed on the same,
correct, non-error conclusion.

## Confidence: LOW
Built from Argo step logs and the SDK transcript only; the actual source of
`orchestrator/run_implementer.py` was not available to verify the current
exit-code/status-write logic, so the code change below needs verification
against that file before it is applied.

## Proposed Fix
Identical fix to incident-89820765's design.md, in the same file
(`orchestrator/run_implementer.py` in the mctl-agents repo): give a
deliberate "nothing left to implement" refusal (the `.implementer-refusal.json`
/ `refused: true` signal observed here) its own non-retryable `.status.yaml`
outcome and a 0 exit code, instead of being indistinguishable from a real
implementer error. This removes the duplicate account-2 fallback run for a
refusal a second run cannot answer differently, and stops
`assert-attempt`/`notify-telegram` from reporting a correct, completed
refusal as a `workflow_failed` incident with a misleading quota/token
diagnosis.

If incident-89820765's proposal is implemented first, this proposal's
implementer should simply confirm the fix already covers this case (same
file, same code path) rather than making a second, conflicting change.

## Scope
Minimal: touch only the outcome classification and status/exit-code path in
`orchestrator/run_implementer.py` for the "no gap left to implement" case.
Do not change the CWFT YAML, the proposal-claim mutex, or any other exit
path (genuine implementer errors must keep failing loudly).
