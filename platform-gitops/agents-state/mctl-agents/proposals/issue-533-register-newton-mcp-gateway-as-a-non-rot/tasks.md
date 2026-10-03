# Tasks: issue-533-register-newton-mcp-gateway-as-a-non-rot

- [ ] 1. Add the explanatory comment paragraph for `newton-mcp-gateway` to
      `config/settings.py`, appended to the existing block after the `.github`
      paragraph (ends line 60) and before `SERVICES = [` (line 61) — DoD: the
      paragraph mirrors the `portfolio` one in shape and states the three
      facts that matter: private Python/uv MCP server in tenant `labs`,
      DevLoop-driven via `agents:intake` issues (epic
      `mctlhq/newton-mcp-gateway#1`); no `agents/newton-mcp-gateway/` scaffold,
      therefore must not enter `ROTATING_SERVICES`; PRs stay shepherd-owned
      (no `SHEPHERD_SKIP_SERVICES` entry). Lines wrap within
      `line-length = 120`.
- [ ] 2. Append `"newton-mcp-gateway",` to `SERVICES` in `config/settings.py`
      (depends on 1) — DoD: inserted after `".github",` and before the
      commented-out `# "upwork-mcp"` entry, so the live entries stay
      contiguous; `python -c "from config.settings import SERVICES;
      print('newton-mcp-gateway' in SERVICES)"` prints `True`.
- [ ] 3. Append `"newton-mcp-gateway",` to the `NON_ROTATING_SERVICES` set in
      `config/settings.py` (depends on 2) — DoD:
      `from config.settings import NON_ROTATING_SERVICES, ROTATING_SERVICES`
      shows the name present in the former and absent from the latter;
      `ROTATING_SERVICES` still evaluates to exactly the 7 repos that have an
      `agents/<svc>/` directory on disk.
- [ ] 4. Add `test_newton_mcp_gateway_is_a_registered_service` and
      `test_newton_mcp_gateway_is_non_rotating` to `tests/test_settings.py`
      (depends on 3) — DoD: both follow the shape of the existing
      `test_dot_github_is_*` pair (lines 35-48), each with a docstring stating
      why the assertion exists; no new imports needed (`SERVICES`,
      `NON_ROTATING_SERVICES`, `ROTATING_SERVICES` are already imported at
      line 11).
- [ ] 5. Verify `docs/agent-inventory.yaml` genuinely needs no entry (depends
      on 3) — DoD: `grep -n "portfolio\|seerrsense\|mctl-pairdesk"
      docs/agent-inventory.yaml` returns nothing, and
      `uv run --locked pytest tests/test_agent_inventory.py -q` is green with
      the file unmodified. If either check fails, add a
      `newton-mcp-gateway` entry mirroring `portfolio` and note it in the PR
      body; otherwise leave the file untouched and say so in the PR body.
- [ ] 6. Run the full local gate (depends on 4, 5) — DoD:
      `uv run --locked pytest -q`,
      `uv run --locked ruff check orchestrator config tests tools` and
      `uv run --locked mypy` (no CLI dirs — `[tool.mypy].files` covers
      `orchestrator`, `config`, `tools`) all pass, matching
      `.github/workflows/pr-validation.yml`.
- [ ] 7. Open the PR against `mctlhq/mctl-agents` (depends on 6) — DoD: the
      diff touches exactly `config/settings.py` and `tests/test_settings.py`
      (plus `docs/agent-inventory.yaml` only if task 5 proved it necessary);
      the body links issue #533, names the `seerrsense` (#320) /
      `portfolio` (#331) / `.github` (#371) precedents, and states explicitly
      that `ROTATING_SERVICES` is unchanged and that
      `SHEPHERD_SKIP_SERVICES` / `NEVER_MERGE_SERVICES` were deliberately not
      touched.

## Tests

- [ ] T1. `tests/test_settings.py::test_newton_mcp_gateway_is_a_registered_service`
      — asserts `"newton-mcp-gateway" in SERVICES`. Fails on the pre-change
      tree, passes after task 2.
- [ ] T2. `tests/test_settings.py::test_newton_mcp_gateway_is_non_rotating`
      — asserts `"newton-mcp-gateway" in NON_ROTATING_SERVICES` and
      `not in ROTATING_SERVICES`. This is the guard against the specific
      regression of registering the service and letting the rotation pick up a
      repo with no scaffold.
- [ ] T3. Existing, must stay green unmodified:
      `test_non_rotating_services_are_all_registered`
      (`set(NON_ROTATING_SERVICES) <= set(SERVICES)` — catches a dangling
      non-rotating entry if task 3 lands without task 2),
      `test_services_has_no_duplicates`, and
      `test_no_service_name_is_shell_glob_hostile_beyond_a_leading_dot`.
- [ ] T4. Existing, must stay green unmodified:
      `tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services`
      — proves the `agents/[!_]*/...` promptSources globs still equal
      `set(ROTATING_SERVICES)`, i.e. that this change did not disturb the
      rotation or any agent's version hash.
- [ ] T5. Manual, post-merge, after the CWFT image rollout — one
      side-effect-free poller preview:
      `python -m orchestrator.run_issue_poller --dry-run` with
      `mctlhq/newton-mcp-gateway#2` labelled `agents:intake`. Expected output
      is `[dry-run] would start/attach dev-loop-mctlhq-newton-mcp-gateway-2
      and remove 'agents:intake'`, NOT `[dry-run] would skip — ... is not a
      known service`. If the issue does not appear in the listing at all, the
      cause is GitHub App / token reach into the private repo, not this
      change (see design.md, "Risk: the private-repo token").
- [ ] T6. Manual, optional, post-merge — confirm the investigator no longer
      exits early for the repo:
      `python -m orchestrator.run_issue_investigator --issue-url
      https://github.com/mctlhq/newton-mcp-gateway/issues/2` must get past
      `run_issue_investigator.py:2458` without raising
      `SystemExit("Repo 'newton-mcp-gateway' is not a known service...")`.
      This spends investigator budget (~$3), so prefer T5 for verification and
      run T6 only when a real proposal for #2 is wanted anyway.

## Rollback

Low-risk and fully reversible in one revert. The change is purely additive to
two in-memory collections; it creates no persistent state, no migration, and
no external resource.

1. `git revert <merge-commit>` on `mctlhq/mctl-agents` `main`, or manually
   drop the two `"newton-mcp-gateway",` entries from `SERVICES` and
   `NON_ROTATING_SERVICES` and the two tests from `tests/test_settings.py`.
   `ROTATING_SERVICES` is derived and needs no separate undo.
2. Once the reverted image rolls out, `run_issue_poller` returns to skipping
   `newton-mcp-gateway` issues with the label kept — the pre-change behaviour,
   with no request silently dropped.
3. Clean up anything the pipeline produced in the interim, if desired: remove
   `platform-gitops/agents-state/newton-mcp-gateway/` from mctl-gitops, and
   close or leave any open `feat/agents-*` PR on the target repo. Neither is
   load-bearing — an orphan state directory is inert once the service is
   unregistered, because `pr_adoption.py` and the implementer both intersect
   discovered work with `set(SERVICES)`.
4. Partial-failure note: if task 2 lands without task 3 (service registered
   but not marked non-rotating), do not revert the whole change — just add the
   `NON_ROTATING_SERVICES` entry. `tests/test_settings.py::T2` and
   `tests/test_agent_inventory.py::T4` both fail loudly in CI before that state
   can reach `main`.
