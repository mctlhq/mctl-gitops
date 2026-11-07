# Agent scopes and scoped run tokens in Authorization

version-status: unverified, see commit SHA (mctl MCP unavailable; prod rollout of mctl-api not confirmed)

## Context
mctl-api added a new `implement` agent scope (352f9f5) with a `mctl-agents-implement` run-token exchange template, applied the intents-route deny to every agent scope (48578a0), and restricted action-approval access to scoped run tokens only (0196447, df43377). These change what integrators holding agent run tokens can reach. The docs tree (context/docs-tree.md, 2026-04-27) has `docs/security/authorization.md` but nothing on agent scopes.

The audience is narrow: these are mostly agent-platform internals (mctl-agents#717 S4/S5). The proposal documents only what commit bodies and the in-repo `docs/implement-agent-scope.md` confirm.

## User stories
- AS a platform admin I WANT to know which routes the `implement` scope reaches SO THAT I can review what an implementer run can do.
- AS a developer integrating agent tokens I WANT to know that approval routes need a scoped run token bound to an execution SO THAT I do not rely on unscoped tokens.
- AS a security reviewer I WANT to know that the intents route is denied to all agent scopes SO THAT I can verify the boundary.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/security/authorization.md` THE SYSTEM SHALL show an "Agent scopes and run tokens" section describing the `implement` scope and its routes.
- WHEN a reader looks for the `mctl-agents-implement` template THE SYSTEM SHALL state that a run without an `execution_id` is refused at exchange with `workflow_without_execution`.
- THE SYSTEM SHALL state that every agent scope is denied the work-item intents route.
- THE SYSTEM SHALL state that only a scoped run token gets approval access; an unscoped token bound to an execution does not.
- IF a reader wants the exchange endpoint THEN THE SYSTEM SHALL show `POST /api/v1/agent-run-tokens/exchange`.
- WHILE prod rollout is unconfirmed THE SYSTEM SHALL carry a review marker for the maintainer to confirm before publishing.

## Out of scope
- Investigate/review scope details beyond what is referenced.
- 9de9506 (human decision bound to a grant): needs author clarification.
- Exchange request/response body shape (not in commits; TODO).
