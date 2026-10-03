# Register newton-mcp-gateway as a non-rotating DevLoop service

## Context

`mctlhq/newton-mcp-gateway` is a new private repository (Python/uv MCP server,
tenant `labs`, service `newton-mcp-gateway`) that will be developed entirely
through the DevLoop: epic `mctlhq/newton-mcp-gateway#1`, first issue
`mctlhq/newton-mcp-gateway#2`. Today the pipeline refuses it at both entry
points. `orchestrator/run_issue_poller.py:224-231` prints
`WARN: newton-mcp-gateway is not a known service (config/settings.py SERVICES)
— skipping, label kept` and counts the issue as a failure, and
`orchestrator/run_issue_investigator.py:2458-2464` raises
`SystemExit("Repo 'newton-mcp-gateway' is not a known service. ...")`. Both
gates read the single hand-maintained list `SERVICES` in
`config/settings.py:61-78`.

The fix is the same registration that `seerrsense` (#320), `portfolio` (#331)
and `.github` (#371) already received: append the repo name to `SERVICES` and
to `NON_ROTATING_SERVICES` (`config/settings.py:82-91`), so it becomes a valid
issue-investigator and implementer target without entering
`ROTATING_SERVICES` (derived at `config/settings.py:98`). Non-rotating is
mandatory, not a preference: the proactive rotation reads
`AGENTS_DIR / <service> / CLAUDE.md` (`orchestrator/run_service_agent.py`) and
`newton-mcp-gateway` deliberately has no `agents/newton-mcp-gateway/`
scaffold, so a rotating entry would schedule runs that fail immediately. The
generic implementer fallback at
`agents/_generic/.claude/agents/implementer.md`
(`orchestrator/run_implementer.py:1726-1733`) covers it instead. This matters
because until the entry exists, every `agents:intake` label on that repo sits
untouched — no proposal, no comment, and a poller failure count that hides
real outages.

## User stories

- AS a platform operator I WANT `mctlhq/newton-mcp-gateway` accepted as a
  registered service SO THAT its `agents:intake` issues are dispatched into
  DevLoopWorkflows instead of being skipped with the label kept.
- AS the issue-investigator I WANT `newton-mcp-gateway` present in `SERVICES`
  SO THAT I can write proposals under
  `agents-state/newton-mcp-gateway/proposals/<slug>/` rather than exiting with
  "not a known service".
- AS the Tier 2 implementer I WANT `newton-mcp-gateway` to be an accepted
  `--service` filter value SO THAT approved proposals for that repo are
  eligible for implementation through the generic sub-agent path.
- AS a maintainer of `config/settings.py` I WANT a membership test asserting
  the new service's rotating/non-rotating placement SO THAT a future edit
  cannot silently move it into the rotation that has no scaffold for it.

## Acceptance criteria (EARS)

- WHEN `config/settings.py` is imported THE SYSTEM SHALL expose
  `"newton-mcp-gateway"` as a member of `SERVICES`.
- WHEN `config/settings.py` is imported THE SYSTEM SHALL expose
  `"newton-mcp-gateway"` as a member of `NON_ROTATING_SERVICES`.
- WHILE `"newton-mcp-gateway"` is in `NON_ROTATING_SERVICES` THE SYSTEM SHALL
  exclude it from the derived `ROTATING_SERVICES` list.
- WHEN `orchestrator.run_issue_investigator` is invoked with
  `https://github.com/mctlhq/newton-mcp-gateway/issues/<n>` THE SYSTEM SHALL
  NOT raise `SystemExit("Repo 'newton-mcp-gateway' is not a known service...")`
  and SHALL resolve the proposal directory to
  `<state-dir>/newton-mcp-gateway/proposals/<slug>/`.
- WHEN `orchestrator.run_issue_poller` sees an open `mctlhq/newton-mcp-gateway`
  issue labelled `agents:intake` THE SYSTEM SHALL treat it as a known service,
  start or attach its `dev-loop-mctlhq-newton-mcp-gateway-<n>` workflow, and
  remove the label — instead of printing the "not a known service" warning and
  incrementing the failure count.
- WHEN `orchestrator.run_issue_poller` is invoked with `--dry-run` for such an
  issue THE SYSTEM SHALL print `[dry-run] would start/attach ... and remove
  'agents:intake'` rather than `[dry-run] would skip`.
- WHEN `uv run --locked pytest -q` runs THE SYSTEM SHALL pass the whole suite,
  including the new `tests/test_settings.py` membership assertions and the
  existing `test_non_rotating_services_are_all_registered`,
  `test_services_has_no_duplicates` and
  `test_no_service_name_is_shell_glob_hostile_beyond_a_leading_dot` invariants.
- WHEN `uv run --locked ruff check orchestrator config tests tools` and
  `uv run --locked mypy` run THE SYSTEM SHALL report no new findings
  (`line-length = 120`, `target-version = "py312"`, per `pyproject.toml`).
- WHILE `"newton-mcp-gateway"` is registered THE SYSTEM SHALL leave
  `ROTATING_SERVICES` byte-identical to its current value, so
  `tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services`
  (which asserts the `agents/[!_]*/...` globs equal `set(ROTATING_SERVICES)`)
  continues to pass unchanged.
- IF `docs/agent-inventory.yaml` or `orchestrator/validate_manifest.py`
  required a per-registered-service entry THEN THE SYSTEM SHALL gain a
  `newton-mcp-gateway` entry mirroring `portfolio`; otherwise the file SHALL
  be left untouched. (Investigation finding: no such requirement exists —
  `portfolio`, `seerrsense` and `mctl-pairdesk` appear nowhere in
  `docs/agent-inventory.yaml`; the inventory is keyed per AGENT, not per
  service. The expected outcome is therefore "file untouched".)

## Out of scope

- Agent prompts, context files, or an `agents/newton-mcp-gateway/` directory.
  The generic path (`agents/_generic/.claude/agents/implementer.md`) is used.
- Entry into `ROTATING_SERVICES` or any proactive researcher / analyst /
  spec-writer run for this repo.
- `SHEPHERD_SKIP_SERVICES`, `SHEPHERD_FIX_ONLY_SERVICES`,
  `SHEPHERD_MERGE_APPROVAL_SERVICES` and `NEVER_MERGE_SERVICES`
  (`orchestrator/run_shepherd.py:566-627`). The shepherd owns this repo's PRs
  under the default mode; no per-service entry is added.
- The matching `service` enum change in mctl-api (its own issue; the
  structural fix is `mctlhq/mctl-api#274`). Until it lands, the operator-facing
  MCP tools that carry a hard-coded `service` enum
  (`mctl_trigger_approve`, `mctl_trigger_implementer`,
  `mctl_trigger_reconcile`, `mctl_trigger_shepherd`) will not accept
  `newton-mcp-gateway` as a filter value. The poller and DevLoop paths this
  proposal targets do not go through that enum.
- CronWorkflow / ClusterWorkflowTemplate image tags in mctl-gitops; the
  release pipeline handles the rollout.
- Creating or pre-seeding `agents-state/newton-mcp-gateway/`. The investigator
  creates it with `mkdir(parents=True, exist_ok=True)`
  (`orchestrator/run_issue_investigator.py:1276`, `:2823`).
- Any change to README.md or LLMS.md — neither documents the service registry.

## Open questions

- **GitHub App / token reach into a private repo.** The code change alone
  satisfies acceptance criteria 1, 2 and 4, but criterion 3 (the poller
  actually dispatching) additionally requires that the `GITHUB_TOKEN` the
  poller runs under can see `mctlhq/newton-mcp-gateway` in `gh search issues
  --owner mctlhq` and that the investigator's shallow
  `gh repo clone mctlhq/newton-mcp-gateway`
  (`orchestrator/run_issue_investigator.py:1113-1150`) succeeds. For a new
  private repo that is a GitHub App installation-scope question, not a
  settings.py question. Proceeding on the assumption that the org-level
  installation already covers all `mctlhq` repos (as it does for the other
  private targets); recorded here so the reviewer can confirm rather than
  discover it on the first live run.
- **Comment placement and wording in `config/settings.py`.** The existing
  comment block (lines 9-60) sits above `SERVICES` and explains each
  non-obvious entry, but `mctl-pairdesk` and `seerrsense` have no paragraph at
  all. Proceeding with a new paragraph appended after the `.github` one,
  matching the `portfolio` paragraph's shape, per the issue's explicit
  request.
- **Stale prose in `docs/agent-inventory.yaml:357-362`.** The `run_all` entry
  enumerates `NON_ROTATING_SERVICES` as "(mctl-agents, mctl-telegram,
  mctl-design, mctl-pairdesk)" — already stale by four entries before this
  change. Treated as out of scope (prose only, no test asserts it), but flagged
  so the reviewer can decide whether to fold in a one-line refresh.
