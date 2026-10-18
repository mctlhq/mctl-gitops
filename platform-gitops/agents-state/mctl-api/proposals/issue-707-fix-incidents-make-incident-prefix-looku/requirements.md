# Make incident prefix lookup deterministic and enforce a minimum prefix length

## Context
`alerts.Store.GetByPrefix` (`internal/alerts/store.go`) says it accepts an "ID prefix (minimum 8 chars)", but it enforces no minimum. It escapes nothing in the input. It also resolves a prefix that matches several rows with `ORDER BY created_at DESC LIMIT 1`, which silently picks the newest one. All four incident handlers in `internal/api/handlers_alerts.go` (GET, PATCH, ack, resolve) go through this lookup, and so do the MCP tools that call them (`mctl_get_incident`, `mctl_acknowledge_incident`, `mctl_resolve_incident`). As a result, a mutating call with a short, ambiguous or wildcard id can change an incident the caller never named. This is governance audit finding G14 (follow-up to mctlhq/.github#182).

The fix makes the lookup deterministic. An exact id always wins. Otherwise a prefix must be at least 8 characters, is matched literally, and must match exactly one incident. Each failure has its own typed error, and handlers map each one to a stable HTTP status.

## User stories
- AS a platform operator I WANT an ambiguous incident prefix to be refused SO THAT acking or resolving by short id never touches the wrong incident.
- AS an MCP client (an agent or a human using `mctl_*_incident` tools) I WANT a distinct, stable error for "too short", "not found" and "ambiguous" SO THAT I can retry with a longer id instead of guessing.
- AS a security auditor I WANT `%` and `_` in an id to be matched literally SO THAT the input cannot widen the match.

## Acceptance criteria (EARS)
- WHEN the id equals an existing incident id exactly (any length) THE SYSTEM SHALL return that incident, even if other ids start with it.
- IF there is no exact match AND the id is shorter than 8 characters (including empty) THEN THE SYSTEM SHALL return `alerts.ErrPrefixTooShort`, and the HTTP handlers SHALL respond `400 Bad Request`.
- IF there is no exact match AND the id is at least 8 characters AND no incident id starts with it THEN THE SYSTEM SHALL return `alerts.ErrNotFound`, and the HTTP handlers SHALL respond `404 Not Found`.
- WHEN there is no exact match AND exactly one incident id starts with the id THE SYSTEM SHALL return that incident.
- IF there is no exact match AND two or more incident ids start with the id THEN THE SYSTEM SHALL return `alerts.ErrAmbiguousPrefix` and SHALL NOT pick any of them. The HTTP handlers SHALL respond `409 Conflict`.
- WHILE matching a prefix THE SYSTEM SHALL treat `%`, `_` and `\` in the input as literal characters.
- IF the store returns any other error THEN THE SYSTEM SHALL respond `500 Internal Server Error`, not 404.
- WHEN `PATCH /api/v1/incidents/{id}`, `POST .../ack` or `POST .../resolve` gets an ambiguous, too-short or unmatched id THE SYSTEM SHALL NOT call `Store.Update`, and no incident row SHALL change.
- WHILE serving GET, PATCH, ack and resolve THE SYSTEM SHALL use the same lookup, so all four have the same semantics. The MCP tools inherit them through the REST API.

## Out of scope
- Changing how incident ids are generated, or restricting the id alphabet. Ids are caller-supplied on `POST /api/v1/incidents` (for example `argo-run-1`), so the alphabet is not fixed.
- Tenant-scoping the prefix match (matching only within the tenants the caller can see). See Open questions.
- Adding an MCP tool for PATCH (none exists today).
- Telegram or other notification formats that show 8-character prefixes.

## Open questions
- An exact id match is tried first at any length. This keeps short caller-supplied ids (shorter than 8, or a prefix of another id such as `argo-run-1` vs `argo-run-10`) addressable. The issue only says "shorter than the minimum returns an error". This proposal applies that rule only when there is no exact match. A reviewer should confirm.
- Ambiguity is counted across all tenants, not just the caller's. So a 409 can reveal that some other tenant has an incident with the same prefix. This is a cheap 1-bit signal, and the current code already leaks more through 403-vs-404. Tenant-scoped matching is deferred.
- Status code choices: 400 for too-short, 409 for ambiguous. 422 would also be defensible for both. This proposal picks 400/409 and documents them in the tool descriptions.
- The deployed configuration of mctl-api could not be observed (see design.md). Nothing in this change depends on it.
