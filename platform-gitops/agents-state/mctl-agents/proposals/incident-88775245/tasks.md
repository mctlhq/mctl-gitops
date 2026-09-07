# Tasks: incident-88775245

1. [ ] Open `config/settings.py` in mctl-agents and locate the `SERVICES` and `NON_ROTATING_SERVICES` lists.
2. [ ] Add `"seerrsense"` to `SERVICES`.
3. [ ] Add `"seerrsense"` to `NON_ROTATING_SERVICES` (it has no `agents/<svc>/` scaffold — it is an externally investigated repo, not a managed platform service).
4. [ ] Verify the change looks correct: no other registration step is implied by the two lists alone (e.g. check whether `SERVICES`/`NON_ROTATING_SERVICES` entries are also expected to appear in a dockerfile/repo mapping elsewhere in the same file).
5. [ ] No image tag bump should be needed for a orchestrator config-only change unless mctl-agents' deploy pipeline requires a version bump to pick up `config/settings.py` changes — confirm and bump if so.
