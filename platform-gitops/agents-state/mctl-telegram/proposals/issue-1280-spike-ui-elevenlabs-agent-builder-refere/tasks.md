# Tasks: issue-1280-spike-ui-elevenlabs-agent-builder-refere

- [ ] 1. Re-pin the report to the current main SHA and re-verify every `path:line` citation in `docs/spikes/assistant-builder-ui-reference.md`. Fix any that drifted, including `internal/config/config.go:498`, which becomes `:499` and `:614` for `ASSISTANT_FORKS_ENABLED` and `:504` for `ManagedRuntimeEnabled`. — DoD: the header names a SHA reachable on main; a reviewer can open each citation at that SHA and find the claimed symbol or text; no reasoning has changed.
- [ ] 2. Add subsection "1.0 Deployed baseline" (depends on 1). — DoD: it names `services/labs/mctl-telegram/values.yaml` and `services/labs/mctl-telegram-preview/values.yaml` and shows production and preview side by side:
  - hosts;
  - `AUTH_MODE`;
  - `AGENT_ENABLED`;
  - `MANAGED_RUNTIME_ENABLED` and `_MAX_ACCOUNTS`;
  - `ASSISTANT_FORKS_ENABLED` as absent, meaning the code default false (`config.go:614`).

  It also states that this is desired gitops state, not observed runtime, and the section 2 status map is updated to match.
- [ ] 3. Close the section 3.1 vendor evidence where network access exists. — DoD: each row carries:
  - URL;
  - retrieval date;
  - a commit SHA for GitHub sources;
  - its label (VENDOR-DOCUMENTED for own fetch, "relayed" if not re-fetched, UNKNOWN if inaccessible).

  The actual-UI column stays UNTESTED. No vendor account or paid access is used.
- [ ] 4. Verify the issue numbers in section 6. — DoD: each row says verified (title, state, date) or unverified. Nothing is presented as verified without a lookup.
- [ ] 5. Move sections 5.4 and 5.5 into section 5, before section 6, and fix the cross-references (depends on 1). — DoD: the heading order is monotonic, the content is otherwise unchanged, and every "see 5.x" reference resolves.
- [ ] 6. Add section 11 "Decision record" and an acceptance cross-walk (depends on 2-5). — DoD:
  - the four verdicts are listed, with ITERATE_CURRENT_UI marked recommended;
  - the owner, date, verdict and conditions fields are blank;
  - a statement blocks implementation until those fields are signed;
  - every acceptance bullet from #1280 and its 2026-11-11 addendum maps to a section, or to "missing: reason".
- [ ] 7. Update section 10 "What is missing" to list only what remains after tasks 3-4 (depends on 3, 4). — DoD: no item that has been closed is still listed, and every remaining gap names what would close it.
- [ ] 8. Open a PR with `docs:` conventional commit(s), "Refs #1280" (not Closes), and merge-commit strategy (depends on 1-7). — DoD: the diff touches only `docs/spikes/assistant-builder-ui-reference.md`, and the PR asks the owner to fill section 11.

## Tests

- [ ] T1. Running `git diff --name-only origin/main` lists only `docs/spikes/assistant-builder-ui-reference.md`.
- [ ] T2. `go test ./docs/...` and `go vet ./...` still pass, because no code changed and the existing doc guard tests are untouched.
- [ ] T3. A citation spot-check shows that at least the cited lines below contain the claimed symbols at the pinned SHA:
  - `cmd/server/main.go`
  - `internal/web/manage_assistant.go`
  - `internal/web/assistants.go`
  - `internal/agent/policy/policy.go`
  - `internal/config/config.go`
  - `internal/assistantinstall/service.go`
- [ ] T4. `git grep -nE '[0-9]{6,}'` over the report finds no real Telegram ids, phones or handles. Any persona used is Alice, Bob, Carol or Dana.
- [ ] T5. The section 11 owner, date and verdict fields are empty in the PR, and the status line still reads PROPOSED.
- [ ] T6. The safety invariants are still present verbatim in meaning:
  - no unsolicited First Message;
  - test mode never sends;
  - configured is not allowed;
  - approve only via the executor path;
  - no prompt or owner notes on the web.

## Rollback

Revert the docs PR with a merge-commit revert. Nothing else depends on the
report: no code, config, deploy or data. The previous merged version of
`docs/spikes/assistant-builder-ui-reference.md` is restored as-is.
