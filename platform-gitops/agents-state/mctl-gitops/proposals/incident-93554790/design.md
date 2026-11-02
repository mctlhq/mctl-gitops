# Design: incident-93554790

## Diagnosis
The implement workflow for mctl-gitops/issue-2211-spike-can-stable-ottl-in-the-opentelemet was refused by the execution-authorization gate: "approved with no verifiable approval grant" (approval_count 0). The proposal's .status.yaml says accepted, but no matching approval grant exists in the approval store, so the implementer exited 45 (blocked) and the follow-up evidence upload was rejected with evidence_execution_ref_invalid. This gate is working as designed; it is not a fault to be bypassed.

## Proposed Fix
No configuration or code change is indicated. The correct remedy is for a human admin to approve the proposal through the dev-loop approval path (mctl_approve_dev_loop for a DevLoopWorkflow, or mctl_trigger_approve with the reviewed content digest), which creates a verifiable grant. Do not weaken or disable the authorization check, and do not hand-edit .status.yaml to work around it.

## Confidence: LOW
Only the implementer log was available; the approval-store state for this proposal was not inspected. Verify that the grant is really missing before acting.

## Scope
Minimal. If no code or config defect is confirmed, make no file changes.
