# Tasks: incident-89820445

1. [ ] Check whether proposal incident-89820765 (in this same
   mctl-agents/proposals directory) has already been implemented; if its
   PR is merged, verify it also fixes this case (same file, same code
   path) and close this proposal as a duplicate rather than making a
   second change.
2. [ ] Otherwise: in the mctl-agents repo, read `orchestrator/run_implementer.py`
   and locate where the SDK sub-agent's result is turned into
   `.status.yaml` writes and the process exit code.
3. [ ] Add detection for a deliberate "proposal already implemented /
   nothing to do" refusal outcome (standardize on the
   `.implementer-refusal.json` / `refused: true` + `reason` structured
   signal observed in this run, rather than free-text parsing of the
   transcript).
4. [ ] On a detected refusal: write `.status.yaml` with a status that
   marks the proposal as not retryable as-is (e.g. `needs-triage`) and
   the refusal reason in `notes`; exit 0 instead of 1 for that proposal
   so Argo's `implement-fallback` step (`when:
   "{{steps.implement.status}} != Succeeded"`) does not re-run an
   identical, already-answered question on the account-2 token.
5. [ ] Verify a genuine implementer error (crash, timeout, no result at
   all) still exits non-zero and is still handled by the existing
   fallback/assert/incident path unchanged.
6. [ ] Note in the PR description that the underlying stale accepted
   proposal, .github/issue-67-feat-roadmap-control-plane-reconcile-epi,
   still needs a human or the reconcile tooling to flip its own
   `.status.yaml` away from `accepted`; that is outside this proposal's
   scope (it lives under `.github`'s proposal directory, not
   mctl-agents).
