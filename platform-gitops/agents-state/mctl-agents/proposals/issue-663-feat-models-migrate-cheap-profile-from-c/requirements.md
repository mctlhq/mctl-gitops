# Migrate the `cheap` model-policy profile from Claude Haiku 4.5 to Claude Haiku 5.5

## Context
Issue mctlhq/mctl-agents#663 (which replaces #600) asks that the `cheap` profile in
`config/model-policy.yaml` default to `claude-haiku-5-5` instead of
`claude-haiku-4-5`. It also asks for the same change to the `CLAUDE_CHEAP_MODEL`
default in `.env.example`. `CLAUDE_CHEAP_MODEL` stays as the override and rollback
switch. The task-routing safety boundary must not move: `service_agent`,
`mentor_digest` and `review_findings_normalize` stay on `balanced`
(`claude-sonnet-5-5`).

The committed policy currently binds no task to `cheap`. Every task in
`config/model-policy.yaml` `tasks:` resolves to `balanced`. Every agent manifest
under `agents/_manifests/*/agent.yaml` declares `modelPolicy.task` as
`service_agent`, `mentor_digest` or `review_findings_normalize`. So the migration
does not change which model any production agent run uses today. What it changes
is the default that any future mechanical task bound to `cheap` would get. The
proposal therefore puts its weight on keeping the routing boundary, proving that
the model id works through the SDK/CLI path that mctl-agents pins
(`claude-agent-sdk==0.2.163` and its bundled CLI), and recording a small,
reproducible evaluation on a mechanical workload.

## User stories
- AS a platform operator I WANT the `cheap` profile to default to Haiku 5.5 SO THAT future mechanical tasks get the cheaper and newer model without any env plumbing.
- AS a platform operator I WANT `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` to remain a working rollback SO THAT I can revert without a code change.
- AS a reviewer of unattended judgement gates I WANT the Sonnet 5.5 routing of `service_agent`, `mentor_digest` and `review_findings_normalize` to be pinned by a test SO THAT a model migration cannot silently move them back to the cheap tier.
- AS a maintainer auditing cost data I WANT historical Haiku 4.5 usage fixtures and changelog entries preserved SO THAT accounting history is not rewritten.

## Acceptance criteria (EARS)
- WHEN `config/model-policy.yaml` is loaded with no `CLAUDE_CHEAP_MODEL` set THE SYSTEM SHALL resolve profile `cheap` to model `claude-haiku-5-5` with source `policy`.
- WHEN `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` is set THE SYSTEM SHALL resolve a task bound to `cheap` to `claude-haiku-4-5` with source `CLAUDE_CHEAP_MODEL`.
- WHILE the committed `config/model-policy.yaml` is in effect THE SYSTEM SHALL route `service_agent`, `mentor_digest` and `review_findings_normalize` to profile `balanced` with model `claude-sonnet-5-5`.
- WHILE the committed policy is in effect THE SYSTEM SHALL keep `balanced.model` equal to `claude-sonnet-5-5` and `balanced.model_env` equal to `CLAUDE_BALANCED_MODEL`.
- WHEN a developer copies `.env.example` THE SYSTEM SHALL default `CLAUDE_CHEAP_MODEL` to `claude-haiku-5-5`.
- WHEN the opt-in provider smoke check runs with valid Claude credentials THE SYSTEM SHALL complete one bounded `claude_agent_sdk` query with model `claude-haiku-5-5` through the pinned SDK and bundled CLI, and report the model id the result envelope names.
- IF the pinned SDK's bundled CLI rejects or does not recognise `claude-haiku-5-5` THEN THE SYSTEM SHALL fail the smoke check with a non-zero exit, and the migration PR SHALL NOT merge until the SDK pin is raised.
- WHEN the repository is searched for `claude-haiku-4-5` after the change THE SYSTEM SHALL contain only references listed in the checked-in audit as historical: `CHANGELOG.md`, `docs/benchmarks/capability-discovery.md`, `tests/fixtures/model-usage-records.json` and `tests/test_usage_ledger.py`, plus the rollback documentation.
- WHEN the cheap-tier evaluation is recorded THE SYSTEM SHALL record success/correctness, latency, input/output tokens, estimated cost and the malformed structured-output rate for both `claude-haiku-4-5` and `claude-haiku-5-5` on the same fixed inputs.

## Out of scope
- Moving any task (including `service_agent`, `review_findings_normalize` and `mentor_digest`) to `cheap`, or adding a new task bound to `cheap`.
- Changing the `balanced` profile or `CLAUDE_BALANCED_MODEL`.
- Opus routing or escalation.
- Changes to the model-policy schema in `config/model_policy.py`.
- Rewriting historical usage-ledger records, fixtures, changelog entries or benchmark notes.
- Edits to mctl-gitops (the CWFT `cwft-mctl-agents-run.yaml` does not set `CLAUDE_CHEAP_MODEL`; `services/labs/claude-remote` already uses Haiku 5.5 on its own path).

## Open questions
- The CLI version bundled in `claude-agent-sdk==0.2.163` was not observed from this clone. The gitops note on `labs/claude-remote` says Claude Code 2.1.296+ is needed for `claude-haiku-5-5` and that 2.1.280 does not know the id. If the pinned bundle is older, the implementer must raise the SDK pin in `pyproject.toml` / `uv.lock`, which widens the PR. Assumption: check first, and bump only if the smoke check fails.
- No production task uses `cheap`, so "through the mctl-agents execution path" can only be exercised with a synthetic task, not a production agent. Assumption: a dedicated opt-in smoke script that uses `config.model_policy` plus `claude_agent_sdk`, the same pieces that `orchestrator/options.py` and the runners use.
- The live smoke check and the evaluation need real API credentials and spend a small amount (well under $1). CI cannot run them unattended. Assumption: the implementer or an operator runs them by hand and records the results in a checked-in note. CI runs only the offline tests.
