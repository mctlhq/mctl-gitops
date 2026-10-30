# Document the read-only agent asset index and preflight tools

## Context
mctl-api commits ba48fc4, 72086aa, 9e1eaa1 (issue-748) added two admin-only, read-only MCP tools: `mctl_list_agent_assets` (merged index of agent assets) and `mctl_get_agent_preflight` (CI-equivalent rule report for an agent and profile). They are not in `docs/mcp/tools-reference.md`.

version-status: unverified, see commit SHA ba48fc4 (both tools appear in the live MCP tool list of this session).

## User stories
- AS a platform admin I WANT to see every agent asset and who references it SO THAT I can judge impact before changing a skill, tool or policy.
- AS a platform admin I WANT a preflight report SO THAT I know whether a binding would pass CI rules.

## Acceptance criteria (EARS)
- WHEN a reader opens the tools reference THE SYSTEM SHALL list both tools with parameters and the admin-only note.
- THE SYSTEM SHALL state that an unavailable source is reported as null, never as empty, and that each source has status `ok` or `unavailable`.
- THE SYSTEM SHALL state that each preflight check is pass, fail or unknown, that unknown is never pass, and that CI (`validate-agent-platform.py`) stays authoritative.
- THE SYSTEM SHALL state that neither tool grants or implies eligibility.
- IF a reader calls preflight THEN THE SYSTEM SHALL show the two argument forms: `environment`, or `definition_version` + `profile` (optional `profile_version`).

## Out of scope
- Registry publish/promote tools; the response schema field by field (no full schema in commits).
