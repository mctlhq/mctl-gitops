# Execution-bound action approvals (REST routes and grant rules)

version-status: unverified, see commit SHA (mctl MCP unavailable)

## Context
mctl-api 5962165 lets a scoped agent run token bound to an execution request, read, list, consume and mark executed action approvals, but only its own requests for that execution. The MCP agent receipt gate now also covers agent run tokens. 3487bdb makes a bound DevLoop approve fail when no grant exists. The OpenAPI diff (+18/-10) gives the route rules. Docs tree has `docs/api/index.md` but no action-approvals section.

Only behaviour confirmed by openapi.yaml and commit bodies is proposed. 9de9506 (governance binding) is excluded.

## User stories
- AS a developer integrating an agent I WANT the approval route rules SO THAT I know who may request, consume and execute.
- AS a platform admin I WANT to know a bound DevLoop approve without a grant is refused SO THAT I understand a refusal.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/api/index.md` THE SYSTEM SHALL show an "Action approvals" section listing the request, read, list, consume and execute routes.
- THE SYSTEM SHALL state that a scoped agent run token acts only on its own requests for its own execution, never requests a `mctl-agents-approve` gate, and may only read and mark executed (never consume) that execution's `mctl-agents-approve` grant.
- THE SYSTEM SHALL list `approval_requester_forbidden` (403) and `intent_hash_mismatch` (400), and state that another requester's or execution's request answers 404.
- THE SYSTEM SHALL state that a bound DevLoop approve with no grant is refused (409; 503 without a store).
- IF a reader wants the flow THEN THE SYSTEM SHALL show request -> approve -> consume -> execute with example calls.
- THE SYSTEM SHALL state that governed MCP tool calls from agent run tokens need a receipt bound to the token's execution.

## Out of scope
- 9de9506 governance binding details; exact error code names for 3487bdb beyond the confirmed status codes (TODO).
- Full request/response schemas (link to OpenAPI).
