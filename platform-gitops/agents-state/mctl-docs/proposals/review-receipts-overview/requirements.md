# Manual review receipts (advisory) for admins

version-status: unverified, see commit SHA (mctl MCP unavailable)

## Context
mctl-api 30ae621 (2026-11-06) flips `mctl_submit_review_assertion` to `enabled: true` in `docs/portal-allowlist.json`, so admins can record a manual advisory review receipt from a portal session. The receipt store and routes come from the review-receipts series (857a2b8, 9435c0f). Confirmed from the diff: tool name `mctl_submit_review_assertion`; enabled on the shared portal by owner decision 2026-11-06 (mctl-api#897); refused for service, relayed and surface callers; never satisfies independent assurance.

Not confirmed: production availability (MCP unavailable; the inbox notes gitops accepted the allowlist change the same day via 859422c, but rollout is unverified), and the tool's argument schema (REST body is documented in mctl-api `docs/review-receipts.md` at main, not verified for the MCP tool).

## User stories
- AS a tenant admin I WANT to know the tool exists and what it does SO THAT I can record a manual advisory receipt.
- AS a non-admin I WANT to know I will get a refusal SO THAT I do not retry.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL list `mctl_submit_review_assertion` with a short description.
- THE SYSTEM SHALL state that service, relayed and surface callers are refused and non-admins get a refusal.
- THE SYSTEM SHALL state that a manual receipt is advisory and never satisfies independent assurance.
- WHILE production availability is unverified THE SYSTEM SHALL keep the entry flagged with a review marker and not be merged until confirmed.
- IF the argument schema is not confirmed THEN THE SYSTEM SHALL contain a TODO instead of invented parameters.

## Out of scope
- Worker receipt path (`POST /api/v1/review-receipts`, flagged by `REVIEW_WORKER_INGEST_ENABLED`), gate, tables, capacity operations.
- Portal tool count (79/112 per inbox) - unverified.
