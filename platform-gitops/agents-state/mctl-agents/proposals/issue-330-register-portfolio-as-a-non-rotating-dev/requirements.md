# Register `portfolio` as a non-rotating DevLoop service

## Context

`mctlhq/portfolio` is a new repository (static Astro site, tenant `labs`,
service `portfolio`) that is intended to be developed exclusively through the
DevLoop: an issue is labelled `agents:intake`, the poller starts a
`DevLoopWorkflow`, the issue-investigator writes a spec triplet under
`agents-state/portfolio/proposals/<slug>/`, and after approval the Tier 2
implementer opens a PR. None of that can happen today because `portfolio` is
not in `SERVICES` in `config/settings.py`. That list is the single gate for
both entry points: `orchestrator/run_issue_poller.py:160-161,201,218-223`
partitions labelled issues on `ref.repo in SERVICES` and, for anything outside
it, prints `WARN: <repo> is not a known service ... skipping, label kept` and
counts a failure without ever calling `start_dev_loop_workflow`; and
`orchestrator/run_issue_investigator.py:1373-1379` raises
`SystemExit("Repo 'portfolio' is not a known service...")` before any clone or
model call.

The registration is deliberately narrow. `portfolio` must be a valid
investigator/implementer target but must NOT join the proactive
researcher/analyst/spec-writer rotation: `ROTATING_SERVICES` is derived as
`[s for s in SERVICES if s not in NON_ROTATING_SERVICES]`
(`config/settings.py:77`), the rotation reads
`AGENTS_DIR / <service> / CLAUDE.md` plus a `context/` knowledge base
(`orchestrator/run_service_agent.py`), and no `agents/portfolio/` scaffold
exists or is wanted. This is exactly the shape used for `mctl-pairdesk`,
`mctl-academy` and `seerrsense` — the last of which was registered by the
`fix(config): register seerrsense as a known service` commit the issue points
at, and which touched only `config/settings.py`. Adding the name to `SERVICES`
alone would silently enrol it in the rotation and break
`tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services`,
which asserts that the on-disk `agents/[!_]*/...` globs equal
`set(ROTATING_SERVICES)`; adding it to both lists keeps that invariant true.

## User stories

- AS a platform operator I WANT to label an issue on `mctlhq/portfolio` with
  `agents:intake` SO THAT the issue-poller starts a DevLoopWorkflow for it
  instead of leaving the label in place and reporting a failure.
- AS an admin triggering `mctl_trigger_issue` on a `portfolio` issue I WANT the
  investigator to accept the repo SO THAT it produces a spec-driven proposal
  under `agents-state/portfolio/proposals/` rather than exiting with
  "not a known service".
- AS the Tier 2 implementer I WANT `portfolio` accepted by the `--service`
  filter SO THAT an approved `portfolio` proposal can be built with the generic
  implementer sub-agent (`agents/_generic/.claude/agents/implementer.md`).
- AS a maintainer of this repo I WANT the rotation membership asserted by a test
  SO THAT a later edit cannot quietly promote `portfolio` into the proactive
  rotation, which has no scaffold for it and would fail on every run.

## Acceptance criteria (EARS)

- WHEN `config/settings.py` is imported THE SYSTEM SHALL expose `"portfolio"`
  as a member of `SERVICES`.
- WHEN `config/settings.py` is imported THE SYSTEM SHALL expose `"portfolio"`
  as a member of `NON_ROTATING_SERVICES`.
- WHILE `"portfolio"` is in both `SERVICES` and `NON_ROTATING_SERVICES` THE
  SYSTEM SHALL exclude it from the derived `ROTATING_SERVICES` list.
- WHEN `orchestrator.run_issue_investigator.investigate` is called with
  `https://github.com/mctlhq/portfolio/issues/<n>` THE SYSTEM SHALL pass the
  `service not in SERVICES` guard at `run_issue_investigator.py:1373` and
  proceed to slug resolution under `<state_dir>/portfolio/proposals/`.
- WHEN `orchestrator.run_issue_poller.poll` finds an open `mctlhq/portfolio`
  issue carrying the `agents:intake` label THE SYSTEM SHALL classify it as a
  known-service ref and call `start_dev_loop_workflow` for it (subject to
  `--max-issues`), instead of printing the "not a known service" warning and
  incrementing `failures`.
- WHEN `orchestrator.run_all` or `orchestrator.run_service_agent` fans out over
  `ROTATING_SERVICES` THE SYSTEM SHALL NOT schedule a service-agent run for
  `portfolio`.
- IF an approved `portfolio` proposal reaches `_stage_implementer_agent` and no
  `agents/portfolio/.claude/agents/implementer.md` exists THEN THE SYSTEM SHALL
  fall back to `agents/_generic/.claude/agents/implementer.md`
  (`run_implementer.py:387-411`) rather than raising `SystemExit`.
- WHEN `uv run --locked pytest -q` runs THE SYSTEM SHALL pass, including the new
  membership test and the pre-existing
  `tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services`.
- WHEN `uv run --locked ruff check orchestrator config tests tools` and
  `uv run --locked mypy` run (as in `.github/workflows/pr-validation.yml:257,264`)
  THE SYSTEM SHALL report no new findings.
- IF `docs/agent-inventory.yaml` or `orchestrator/validate_manifest.py` required
  a per-registered-service entry THEN THE SYSTEM SHALL add a `portfolio` entry
  mirroring `seerrsense`; the inventory is keyed by AGENT, not by service, and
  contains no `seerrsense` entry, so no inventory change is expected.

## Out of scope

- Any `agents/portfolio/` scaffold: no `CLAUDE.md`, no `context/`, no
  per-service `.claude/agents/{researcher,analyst,spec-writer,implementer}.md`.
  The generic implementer path is used.
- Adding `portfolio` to `ROTATING_SERVICES` or to the proactive R&D rotation in
  any form.
- The matching service enum change in `mctlhq/mctl-api` (the MCP
  `mctl_trigger_implementer` / `mctl_trigger_approve` / `mctl_trigger_reconcile`
  service enums); the structural fix is tracked as `mctlhq/mctl-api#274`.
- Any change to CronWorkflows or CWFT image tags in `mctl-gitops`; the release
  pipeline rolls the new image out.
- Creating `platform-gitops/agents-state/portfolio/` by hand — the investigator
  creates the service and proposal directories itself
  (`run_issue_investigator.py:270`, `:989`, `:1569` all use
  `mkdir(parents=True, exist_ok=True)`).
- Onboarding the `portfolio` service on the mctl platform itself (tenant `labs`
  deployment, ingress, domain).

## Open questions

- Should `portfolio` be added to `SHEPHERD_SKIP_SERVICES`? That set is built
  from an env var in the gitops CronWorkflow (`run_shepherd.py:317-330`), not
  from this repo, and `mctl-design` is the only current member. The issue is
  silent, so this proposal assumes the default: the shepherd DOES drive
  `portfolio` PRs to merge, matching `seerrsense`/`mctl-pairdesk`. If a
  pr-steward owns `portfolio` PRs instead, that is a follow-up gitops change,
  not a code change here.
- Until `mctl-api#274` lands, MCP-triggered operations that take a `service`
  enum (`mctl_trigger_implementer`, `mctl_trigger_approve`) will reject
  `portfolio` server-side, exactly as they do for `seerrsense` today. The
  unfiltered forms (no `service` argument) and the Temporal DevLoop path are
  unaffected. Proceeding on that basis, per the issue's "out of scope".
- Whether `portfolio`'s repo will carry its own `CLAUDE.md`. It is read at
  runtime by both agents via `setting_sources=["project"]` and is declared in
  `docs/agent-inventory.yaml` as a `runtimeContextInputs` entry, so nothing in
  this repo needs to change either way. Recorded, not blocking.
