# Tasks: incident-89786722

1. [ ] Check whether incident-89786271's timeout fix has already landed for
       the mctl-agents-implement WorkflowTemplate/CronWorkflow; if so, this
       proposal is satisfied by that same change and needs no separate edit.
2. [ ] Otherwise, locate the Argo WorkflowTemplate/CronWorkflow that defines
       the mctl-agents "implement" run-implementer step and confirm the
       current timeout field name and value (expected around ~9500s based on
       observed failure timing).
3. [ ] Reduce that timeout to approximately 1800s (30 minutes), or the
       team's agreed implementer runtime SLA if different.
4. [ ] Verify the change only affects the implement workflow's timeout and
       does not alter resource requests/limits or concurrency settings.
5. [ ] No image tag bump needed — this is a values/manifest-only change.
