# Requirements: incident-89787472

## Incident
- ID: argo-mctl-agents-implement-9a41e408-1789787472
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-09-19T03:11:12.430511Z

### Summary
```
implement implement issue-333-feat-human-input-durable-agent-clarifica Failed after 9690.386893s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-9a41e408
```

## Evidence
### Labels
```
(none provided on the incident record)
```

### Log Snippet
onExit (notify-telegram) step log for this run:
```
telegram http=200
incident http=201
```

Argo node timeline for mctl-agents-implement-9a41e408 (from mctl_get_workflow_status), which is the evidence the diagnosis below is based on — Loki does not retain logs for the individual Argo step pods once they are gone, only this onExit summary above:
```
workflow started:              2026-09-19T00:29:38Z
workflow activeDeadlineSeconds: 7200 (deadline = 2026-09-19T02:29:38Z)

step "implement" (run-implementer, primary, oauth account 1)
  started:  2026-09-19T00:29:38Z
  finished: 2026-09-19T02:31:08Z  (~7290s)
  phase:    Failed
  message:  Step exceeded its deadline

step "implement-fallback" (run-implementer, oauth account 2)
  started:  2026-09-19T02:31:08Z   <- already past the 02:29:38Z workflow deadline
  finished: 2026-09-19T02:51:08Z  (20m)
  phase:    Failed
  message:  Step exceeded its deadline

step "commit" (commit-and-push, retry)
  started:  2026-09-19T02:51:08Z   <- also already past the workflow deadline
  finished: 2026-09-19T03:11:08Z  (20m)
  phase:    Failed
  message:  retry exceeded workflow deadline 2026-09-19 02:29:38 +0000 UTC

workflow finished: 2026-09-19T03:11:18Z  (total 9690s)
```

## Acceptance Criteria
- WHEN a proposal's primary run-implementer attempt needs the full
  IMPLEMENTER_TIMEOUT_SECONDS budget and the fallback attempt then triggers,
  THEN the workflow's activeDeadlineSeconds must be large enough to let the
  documented two-attempt design actually complete (or fail promptly) instead
  of continuing to schedule new steps after its own deadline has already
  elapsed.
- WHEN the workflow does fail on deadline THEN it should fail close to the
  declared ceiling, not run ~40 minutes past it doing further doomed steps.
