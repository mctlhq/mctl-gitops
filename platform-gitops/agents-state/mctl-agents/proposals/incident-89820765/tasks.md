# Tasks: incident-89820765

1. [ ] In the mctl-agents repo, read `orchestrator/run_implementer.py` and
   locate where the SDK sub-agent's result is turned into
   `.status.yaml` writes and the process exit code.
2. [ ] Add detection for a deliberate "proposal already implemented /
   nothing to do" refusal outcome (standardize on a structured signal,
   e.g. a `refused: true` / `reason` object, rather than free-text
   parsing of the transcript).
3. [ ] On a detected refusal: write `.status.yaml` with a status that marks
   the proposal as not retryable as-is (e.g. `needs-triage`) and the
   refusal reason in `notes`; exit 0 instead of 1 for that proposal so
   Argo's `implement-fallback` step (`when:
   "{{steps.implement.status}} != Succeeded"`) does not re-run an
   identical, already-answered question on the account-2 token.
4. [ ] Verify a genuine implementer error (crash, timeout, no result at
   all) still exits non-zero and is still handled by the existing
   fallback/assert/incident path unchanged.
5. [ ] Add/update a unit test in mctl-agents covering the refusal path
   (exit code 0, `.status.yaml` content) alongside the existing
   error-path test(s).
6. [ ] Note in the PR description that the two stale accepted proposals
   observed triggering this bug —
   mctl-telegram/issue-510-add-self-identification-tool-get-my-iden and
   .github/issue-67-feat-roadmap-control-plane-reconcile-epi — still need
   a human or the reconcile tooling to flip their own `.status.yaml`
   away from `accepted`; that is outside this proposal's scope (it lives
   under those services' proposal directories, not mctl-agents).
