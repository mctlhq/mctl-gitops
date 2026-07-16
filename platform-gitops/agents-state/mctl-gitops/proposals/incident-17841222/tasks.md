# Tasks: incident-17841222

1. [ ] Find the Argo WorkflowTemplate / CronWorkflow manifest for the `issue-poll`
       operation (triggered by `mctl-agents-issue-poll`) and inspect its
       `activeDeadlineSeconds` and `synchronization` (mutex) fields.
2. [ ] Set/lower `activeDeadlineSeconds` to ~1800s (30 minutes) so the workflow fails
       fast instead of hanging for hours, unless there is a documented reason
       issue-poll needs longer.
3. [ ] Check whether issue-poll's `synchronization` block references the same mutex
       used by mctl-agents-implement (e.g. `mctl-gitops-main-writes`). If issue-poll
       does not write to the gitops repo, remove that mutex requirement from its
       template.
4. [ ] Verify both changes look correct (deadline reduced, unnecessary mutex removed
       if applicable, no syntax errors in the manifest).
5. [ ] No image tag bump expected — this is a manifest/config-only change. If step 3
       of design.md (a Python-level hang) is later confirmed, open a follow-up
       proposal targeting mctl-agents instead of expanding this one.
