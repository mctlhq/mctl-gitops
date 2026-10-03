# Tasks: incident-89820765

1. [ ] In mctlhq/mctl-agents, locate the implementer wrapper script/step that produces
   the "assert-attempt" pass/fail signal (search for the message "Neither the primary
   attempt nor the account-2 fallback succeeded").
2. [ ] Add detection for a "stale proposal / already implemented" outcome (implementer
   reports no changes needed because the feature already exists) and treat it as a
   non-fatal terminal state instead of a hard failure.
3. [ ] On that outcome, write the proposal's .status.yaml with status: rejected (or
   superseded) and a note quoting the implementer's finding, instead of leaving the
   workflow to fail into needs-triage.
4. [ ] Verify the fix against both this incident and
   argo-mctl-agents-implement-c36902fb-1789820445 (issue-67, .github repo) — same
   failure pattern.
5. [ ] Confirm existing genuine-failure paths (API errors, timeouts, crashes) still
   correctly fail and reach needs-triage.
