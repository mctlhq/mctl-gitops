# Tasks: incident-90035494

1. [ ] Check whether `mctl-gitops/proposals/incident-5ae3a90e` has already
   been implemented (PR merged, or `.status.yaml` shows `merged`). If so,
   this incident needs no further changes -- stop here.
2. [ ] If it has not been implemented yet, apply the same edit described in
   `mctl-gitops/proposals/incident-5ae3a90e/design.md`: remove the
   `labs-mctl-telegram-local-mode-flip-1` one-shot Job block (and its
   preceding comment) from
   `platform-gitops/services/labs/mctl-telegram/values.yaml`.
3. [ ] Do not open a second PR against the same file if incident-5ae3a90e's
   PR is already open -- comment cross-referencing it instead.
