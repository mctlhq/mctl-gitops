# Tasks: incident-89786271

1. [ ] Locate the Argo WorkflowTemplate/CronWorkflow that defines the
       mctl-agents "implement" run-implementer step and confirm the current
       timeout field name and value (expected around ~9500s based on observed
       failure timing).
2. [ ] Reduce that timeout to approximately 1800s (30 minutes), or the
       team's agreed implementer runtime SLA if different.
3. [ ] Verify the change only affects the implement workflow's timeout and
       does not alter resource requests/limits or concurrency settings.
4. [ ] No image tag bump needed — this is a values/manifest-only change.
