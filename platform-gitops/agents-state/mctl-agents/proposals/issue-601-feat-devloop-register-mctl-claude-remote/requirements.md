# Register mctl-claude-remote as a non-rotating, issue-driven DevLoop target

## Context
The issue poller (`orchestrator/run_issue_poller.py`) only dispatches
`agents:intake` issues whose repository name is in
`config.settings.SERVICES`; any other repo is logged as "not a known service",
counted as a failure, and keeps its label. `mctlhq/mctl-claude-remote` is not
in that list, so labelling mctlhq/mctl-claude-remote#79 with `agents:intake`
today would be ignored.

The issue asks to register `mctl-claude-remote` the same way `portfolio`,
`.github` and `newton-mcp-gateway` are registered: present in `SERVICES`,
present in `NON_ROTATING_SERVICES` (so it never enters `ROTATING_SERVICES`
and the proactive researcher/analyst/spec-writer rotation), with no
`agents/mctl-claude-remote/` scaffold, relying on the generic implementer
sub-agent (`agents/_generic/.claude/agents/implementer.md`).

## User stories
- AS a platform operator I WANT to label a mctl-claude-remote issue with `agents:intake` SO THAT the DevLoop investigates and implements it like any other registered repo.
- AS a platform operator I WANT mctl-claude-remote kept out of the proactive rotation SO THAT the weekly run does not fail on a missing `agents/mctl-claude-remote/` scaffold or spend quota on an unscaffolded repo.
- AS a maintainer of mctl-agents I WANT tests that pin this registration SO THAT a later edit cannot silently drop the repo or move it into rotation.

## Acceptance criteria (EARS)
- THE SYSTEM SHALL list `"mctl-claude-remote"` exactly once in `config.settings.SERVICES`.
- THE SYSTEM SHALL list `"mctl-claude-remote"` in `config.settings.NON_ROTATING_SERVICES`.
- WHILE `mctl-claude-remote` is in `NON_ROTATING_SERVICES` THE SYSTEM SHALL exclude it from `ROTATING_SERVICES`, and therefore from the `_full()` rotation in `orchestrator/run_all.py`.
- WHEN `run_issue_poller.poll()` finds an `agents:intake` issue in `mctlhq/mctl-claude-remote` THE SYSTEM SHALL call `start_dev_loop_workflow` with that issue URL and remove the label on success, and not log it as an unknown service.
- WHEN `run_issue_poller.poll(dry_run=True)` finds such an issue THE SYSTEM SHALL print the "would start/attach" line and count no failure.
- WHEN the Tier 2 implementer stages an implementer for a `mctl-claude-remote` proposal THE SYSTEM SHALL use the generic fallback `agents/_generic/.claude/agents/implementer.md` (existing `_stage_implementer_agent` behaviour), with no per-service scaffold.
- IF an `agents/mctl-claude-remote/` directory were added THEN `tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services` SHALL fail; this proposal therefore SHALL NOT create one.
- WHILE this change is applied THE SYSTEM SHALL leave `ROTATING_SERVICES` and the poller routing for every previously registered service unchanged.
- THE SYSTEM SHALL document in the `config/settings.py` comment block that `mctl-claude-remote` is issue-driven, has no scaffold, and uses the generic implementer.

## Out of scope
- Creating an `agents/mctl-claude-remote/` proactive-rotation scaffold.
- Shepherd policy changes (`SHEPHERD_SKIP_SERVICES` / `SHEPHERD_FIX_ONLY_SERVICES` / `SHEPHERD_MERGE_APPROVAL_SERVICES` are env-driven from the mctl-gitops CronWorkflow, not this repo). With no entry the repo's PRs are shepherd-owned by default, like `newton-mcp-gateway`.
- Service enums hard-coded outside this repo (e.g. the `service` enum of the mctl-api MCP tools `mctl_trigger_approve`, `mctl_trigger_implementer`, `mctl_trigger_shepherd`, `mctl_trigger_reconcile`). The DevLoop poller path does not use them.
- GitHub App installation / repo access for mctlhq/mctl-claude-remote (assumed in place, as for other mctlhq org repos).
- Actually labelling mctlhq/mctl-claude-remote#79 (follow-up after merge).

## Open questions
- Should mctl-claude-remote PRs stay shepherd-owned (the default, as for `newton-mcp-gateway`) or move to pr-steward/skip-list like `mctl-design` / `mctl-academy`? This proposal assumes the default (no change); a different policy is a separate mctl-gitops change.
- Should the mctl-api MCP tool `service` enums be extended to include `mctl-claude-remote` so operators can target it with `mctl_trigger_implementer` etc.? Not needed for the DevLoop path; recorded as a possible follow-up in mctl-api.
