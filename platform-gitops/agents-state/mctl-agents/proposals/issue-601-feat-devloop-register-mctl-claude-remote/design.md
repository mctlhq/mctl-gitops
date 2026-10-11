# Design: issue-601-feat-devloop-register-mctl-claude-remote

## Current state
- `config/settings.py` defines `SERVICES` (16 entries, ending with `"newton-mcp-gateway"` and a commented-out `"upwork-mcp"`), `NON_ROTATING_SERVICES` (a set of 9 issue-driven services: `mctl-agents`, `mctl-telegram`, `mctl-design`, `mctl-pairdesk`, `mctl-academy`, `seerrsense`, `portfolio`, `.github`, `newton-mcp-gateway`), and derives `ROTATING_SERVICES = [s for s in SERVICES if s not in NON_ROTATING_SERVICES]`. A long comment block above `SERVICES` explains why each non-rotating service is registered.
- `orchestrator/run_issue_poller.py::poll()` splits search results into `service_refs` (`r.repo in SERVICES`) and `other_refs`. Only `service_refs` reach `start_dev_loop_workflow`; others print `WARN: <repo> is not a known service (config/settings.py SERVICES) — skipping, label kept.` and increment `failures`. Dry-run prints `would start/attach` vs `would skip`.
- `orchestrator/run_issue_investigator.py` (~line 3294) also rejects services not in `SERVICES`, pointing at `NON_ROTATING_SERVICES` for scaffold-less repos.
- `orchestrator/run_implementer.py` validates `--service` against `SERVICES`, and `_stage_implementer_agent` (~line 1726) falls back to `agents/_generic/.claude/agents/implementer.md` when `agents/<svc>/.claude/agents/implementer.md` does not exist.
- `orchestrator/run_all.py::_full()` iterates only `ROTATING_SERVICES`.
- `orchestrator/pr_adoption.py` intersects observed repos with `set(SERVICES)`, so registration also makes the repo eligible for PR adoption, same as other non-rotating services.
- Tests: `tests/test_settings.py` pins each non-rotating service with a pair of tests (`test_<svc>_is_a_registered_service`, `test_<svc>_is_non_rotating`) plus invariants (non-rotating subset of SERVICES, no duplicates, no `/` in names). `tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services` asserts `agents/[!_]*` dirs equal `ROTATING_SERVICES`. `tests/test_run_issue_poller.py` covers poll() with a `_ref(repo=...)` helper and `_start_ok_recording` stub, defaulting to `mctl-telegram`.

## Proposed solution
Mirror the `newton-mcp-gateway` registration exactly:

1. `config/settings.py`
   - Append `"mctl-claude-remote"` to `SERVICES` after `"newton-mcp-gateway"` (before the commented `upwork-mcp`).
   - Add `"mctl-claude-remote"` to `NON_ROTATING_SERVICES`.
   - Add a comment paragraph: mctl-claude-remote is issue-driven only (human-labelled `agents:intake`, first target mctlhq/mctl-claude-remote#79); registered so `run_issue_poller.py` dispatches it; no `agents/mctl-claude-remote/` scaffold, so it must not enter `ROTATING_SERVICES` (the rotation reads `AGENTS_DIR / <service> / CLAUDE.md`); the generic implementer sub-agent covers it; no `SHEPHERD_SKIP_SERVICES` entry, so PRs stay shepherd-owned.
2. `tests/test_settings.py`: add `test_mctl_claude_remote_is_a_registered_service` and `test_mctl_claude_remote_is_non_rotating` (in SERVICES, in NON_ROTATING_SERVICES, not in ROTATING_SERVICES).
3. `tests/test_run_issue_poller.py`: add
   - `test_poll_dispatches_mctl_claude_remote` — `_ref(repo="mctl-claude-remote", number=79)`, stubbed `start_dev_loop_workflow` records the URL, `remove_label` records; assert `started == 1`, `failures == 0`, URL dispatched, label removed.
   - `test_poll_dry_run_treats_mctl_claude_remote_as_known` — dry-run with capsys asserts "would start/attach" and not "not a known service", `failures == 0`.
4. Optionally a rotation test asserting `mctl-claude-remote` is absent from `ROTATING_SERVICES` (covered by step 2) — the existing inventory test already guarantees no scaffold dir is added.
5. CHANGELOG is managed by release-please; no manual edit. Use a `feat(devloop):` conventional commit.

No runtime code changes: the poller, investigator, implementer and rotation already behave correctly once the registry contains the name.

## Alternatives
- **Add to `SERVICES` only (rotating).** Rejected: `ROTATING_SERVICES` would include it, `run_all._full()` would run the service-agent against a missing `agents/mctl-claude-remote/CLAUDE.md`, and `test_service_agent_scope_matches_rotating_services` would fail.
- **Create an `agents/mctl-claude-remote/` scaffold and make it rotating.** Rejected by the issue; adds proactive quota spend and maintenance with no stated need.
- **Make the poller accept any `mctlhq/*` repo.** Rejected: removes the deliberate allowlist that keeps mislabelled repos visible to operators, and changes behaviour for every repo — violates "no behavior change for existing services".

## Platform impact
- Migrations: none. Pure config + tests.
- Backward compatibility: existing entries untouched; `ROTATING_SERVICES` unchanged (new name is excluded).
- Side effects of registration: the repo becomes valid for `run_implementer --service`, `run_all --service` single-service mode (would fail without a scaffold — same as other non-rotating services, operator-invoked only), `pr_adoption` scans, mentor services list, and the shepherd's default ownership. These match how `newton-mcp-gateway` behaves.
- Deployment: takes effect when the poller/implementer images are rebuilt from the merged commit.
- Risks: GitHub App may lack access to mctlhq/mctl-claude-remote, making the investigator clone fail; mitigation — failed DevLoop runs are retriable (ALLOW_DUPLICATE_FAILED_ONLY) and visible. Operator-facing MCP enums in mctl-api do not include the name; mitigation — noted as follow-up, not on the DevLoop path.
