# Design: incident-93641772

## Confidence: LOW

## Diagnosis
The implementer did not fail on code. It was deliberately blocked by the execution-authorization gate: the proposal .github/issue-300-spike-events-push-github-events-into-exi was marked accepted without a verifiable approval grant (approval_count 0). This is a safety control working as designed, and the follow-on "assert-attempt" and "Failed" status is just the workflow reporting the blocked run (exit 45). The resulting evidence delivery was also refused with evidence_execution_ref_invalid, a secondary symptom of having no execution reference. The incident is about 29 hours old and the workflow already handed the proposal's .status.yaml back.

## Proposed Fix
No gitops change is appropriate. The gate must not be bypassed or weakened. The correct remedy is a human approval of issue 300 through the DevLoop approval path (mctl_approve_dev_loop or the approval flow), after which the proposal can be retried. The implementer should make NO file change for this proposal and should state in its PR or report that it was intentionally not actioned.

## Scope
None. Do not touch authorization policy, approval gates or status files to make this run pass.
