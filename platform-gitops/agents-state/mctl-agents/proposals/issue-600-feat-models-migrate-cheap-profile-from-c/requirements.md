# Migrate the `cheap` model-policy profile from Claude Haiku 4.5 to Claude Haiku 5.5

## Context
Issue mctlhq/mctl-agents#600 asks to make Claude Haiku 5.5 (`claude-haiku-5-5`,
released 2026-10-07) the default implementation of the existing `cheap`
model-policy profile. Today `config/model-policy.yaml` sets
`profiles.cheap.model: claude-haiku-4-5` and `.env.example` sets
`CLAUDE_CHEAP_MODEL=claude-haiku-4-5`. Haiku 5.5 is cheaper and newer, so
mechanical/bounded work routed to `cheap` should use it by default.

The migration must not weaken an existing safety boundary: on 2026-10-01
`mentor_digest` and `review_findings_normalize` were moved off `cheap` to
`balanced` (`claude-sonnet-5-5`) after Haiku 4.5 judgement failures, and
`service_agent` is also `balanced`. As of the clone, **no task in
`config/model-policy.yaml` routes to `cheap`** (all three tasks are
`balanced`), so this change only moves the profile default; it changes no
production task's model. The change keeps `CLAUDE_CHEAP_MODEL` as the rollback
override, adds tests that pin both the new default and the existing routing
boundary, and records a small reproducible cheap-tier before/after evaluation.

## User stories
- AS a platform operator I WANT the `cheap` profile to default to Haiku 5.5 SO THAT any mechanical work routed to it is cheaper and uses the current model.
- AS a platform operator I WANT `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` to restore the old model instantly SO THAT a regression can be rolled back without a code change.
- AS a reviewer of unattended merges I WANT `review_findings_normalize`, `mentor_digest` and `service_agent` to stay on `balanced` SO THAT a model refresh never silently returns judgement gates to the cheap tier.
- AS a maintainer I WANT every `claude-haiku-4-5` reference classified as migrated or historical SO THAT stale defaults do not linger and historical accounting data is not rewritten.

## Acceptance criteria (EARS)
- WHEN `config/model-policy.yaml` is loaded with no `CLAUDE_CHEAP_MODEL` set THE SYSTEM SHALL resolve the `cheap` profile to `claude-haiku-5-5` with `source=policy`.
- WHEN `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` is set THE SYSTEM SHALL resolve the `cheap` profile to `claude-haiku-4-5` with `source=CLAUDE_CHEAP_MODEL`.
- WHILE the committed policy is in effect THE SYSTEM SHALL route `service_agent`, `mentor_digest` and `review_findings_normalize` to the `balanced` profile whose default model is `claude-sonnet-5-5`, enforced by a test against the committed file.
- WHEN a developer copies `.env.example` THE SYSTEM SHALL default `CLAUDE_CHEAP_MODEL` to `claude-haiku-5-5`.
- WHEN the opt-in provider smoke test runs with Anthropic credentials THE SYSTEM SHALL complete one `claude_agent_sdk` request with `model=claude-haiku-5-5` through the same options-building path the orchestrator uses, and SHALL report the model key the SDK returned in `ResultMessage.model_usage`.
- IF credentials are absent THEN THE SYSTEM SHALL skip the smoke test rather than fail the default `pytest` run.
- WHEN the change is proposed THE SYSTEM SHALL include a checked-in benchmark note (`docs/benchmarks/haiku-5-5-cheap-tier.md`) recording, for Haiku 4.5 and Haiku 5.5 on the same mechanical workloads: success/correctness, latency, input/output tokens, estimated cost, and malformed structured-output rate.
- IF a `claude-haiku-4-5` reference is a historical record (CHANGELOG entry, benchmark write-up, recorded usage fixture) THEN THE SYSTEM SHALL leave it unchanged and the audit SHALL list it as historical.

## Out of scope
- Changing the `balanced` profile or its model (`claude-sonnet-5-5`).
- Routing any task (including `service_agent`, `mentor_digest`, `review_findings_normalize`) to `cheap`.
- Adding a `strong`/Opus profile or any escalation policy.
- Changing the model-policy schema (`version: 1`) or `config/model_policy.py` logic.
- Rewriting `tests/fixtures/model-usage-records.json`, the `HAIKU` constant in `tests/test_usage_ledger.py`, `CHANGELOG.md`, or `docs/benchmarks/capability-discovery.md`.
- Changing the Claude Code CLI's own internal small-model side calls (not controlled by this policy).

## Open questions
- Should the policy pin a dated snapshot id (as the usage fixtures do for `claude-haiku-4-5-20251001`) instead of the alias `claude-haiku-5-5`? The issue names the alias and the current policy uses aliases for both profiles, so this proposal uses `claude-haiku-5-5`.
- Since no task currently routes to `cheap`, the "before/after" evaluation cannot be measured on a live production task. This proposal uses a small fixed set of synthetic mechanical workloads (see design). Reviewers may want different workloads.
- `docs/adr/012-model-usage-cost-attribution-contract.md` still says `mentor_digest` and `review_findings_normalize` map to `cheap`. That has been stale since 2026-10-01. This proposal fixes it only with a one-line clarifying note, because it is in the audit scope. Reviewers may prefer a separate PR.
