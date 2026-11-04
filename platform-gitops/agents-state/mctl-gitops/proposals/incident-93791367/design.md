# Design: incident-93791367

## Diagnosis
The incident-responder workflow mctl-agents-incidents-1793790900 was marked Failed after 462s, yet its run-orchestrator step ended with "orchestrator exited 0" and handed off 20 proposal files. Only the run-orchestrator and notify-telegram steps are archived, so the failing step is not visible; the most likely candidate is the commit-and-push step failing on its clone-gitops init (exit code 128), the same signature seen in mctl-agents-shepherd-f9979a5a at 11:15-11:17Z, which would also explain why that step has no archived log. This is inference, not confirmed.

## Proposed Fix
Same change as incident-93791038: add a bounded retry with backoff to the clone-gitops step used by the run-shepherd and commit-and-push templates, so a transient git clone failure no longer fails the workflow. Before applying, confirm via the workflow node statuses of mctl-agents-incidents-1793790900 that the failed node is a clone-gitops error; if it is something else, do not apply the retry change for this incident.

## Scope
Minimal. Only the clone-gitops step of the shared workflow templates.

## Confidence: LOW
The failing step of this run is not visible in the archived logs.
