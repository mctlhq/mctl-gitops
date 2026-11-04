# MCP tools to create WorkItems and append/read intents for manual cross-client handoff

## Context

Issue mctlhq/mctl-api#868 (parent epic mctlhq/.github#281) asks for three thin MCP
wrappers over REST routes that already exist: `mctl_create_work_item`
(`POST /api/v1/work-items`), `mctl_append_work_item_intent`
(`POST /api/v1/work-items/{id}/intents`) and `mctl_list_work_item_intents`
(`GET /api/v1/work-items/{id}/intents`). Today the MCP surface in
`internal/mcp/workitems.go` can read a WorkItem and request an execution, but it
cannot open a WorkItem or record what was asked for. So a person cannot start
work in one MCP client (Claude) and pick it up in another (Codex) under the same
authenticated principal.

The slice adds no storage model and starts no execution. Authorization, tenant
visibility, the 8 KiB intent limit, secret refusal, idempotency and redaction
stay in the REST handlers and `internal/workitems`. The MCP tools only forward
the caller's own token and keep the API's typed refusals intact. The direct MCP
endpoint registers all three tools. The shared Cloudflare portal lists all three
as disabled until the owner decides otherwise. The slice also corrects two stale
statements in `docs/work-context-contract.md`.

## User stories

- AS an authenticated mctl user in Claude I WANT to create a WorkItem in my tenant and append my intent text SO THAT I can hand the work to another client by its `wi_` id.
- AS the same user in Codex I WANT to list the intents of that `wi_` id SO THAT I can read what was asked without retyping it.
- AS a client retrying after a network failure I WANT a repeated call with the same idempotency key to return the original result SO THAT a retry never creates a duplicate item or intent.
- AS a platform owner I WANT every new tool to stay disabled on the shared portal by default SO THAT exposure is an explicit owner decision.
- AS a reader of `docs/work-context-contract.md` I WANT the MCP section and the portal statement to match the code SO THAT nobody relies on a wrong exposure claim.

## Acceptance criteria (EARS)

### Create
- WHEN `mctl_create_work_item` is called with `title`, `tenant`, `idempotency_key` and optionally `visibility` and `external_key` THE SYSTEM SHALL send `POST /api/v1/work-items` with those fields, `origin_surface: "mcp"` and the caller's own bearer token, and return the API's response body.
- IF `idempotency_key` is missing or blank THEN THE SYSTEM SHALL return a tool error without calling the API.
- IF `visibility` is given and is not `tenant` or `private` THEN THE SYSTEM SHALL return a tool error without calling the API.
- WHEN `visibility` is omitted THE SYSTEM SHALL omit it from the body, so the REST default (`tenant`) applies.
- THE SYSTEM SHALL NOT accept or forward any actor, owner, principal, requested_by or surface argument. Who acts is resolved by the API from the token.
- IF the API answers 409 `external_key_in_use` or 409 `idempotency_key_reused` THEN THE SYSTEM SHALL return a tool error that keeps the HTTP status, the code and the details.
- WHEN the API answers 200 (not 201) to the create THE SYSTEM SHALL return the body with `"replayed": true`, as `workItemCall` already does for every POST.
- IF the caller has no access to the named tenant THEN THE SYSTEM SHALL surface the API's 403 `tenant_forbidden`. A tenant argument never overrides authentication.
- IF the caller's tenant role is below developer (for example viewer) THEN THE SYSTEM SHALL surface the API's 403 `tenant_role_forbidden`, and no item SHALL be created.

### Append intent
- WHEN `mctl_append_work_item_intent` is called with `work_item_id`, `text` and `idempotency_key` THE SYSTEM SHALL send `POST /api/v1/work-items/{id}/intents` with `text`, `surface: "mcp"` and `idempotency_key`, and return the API's response.
- IF `idempotency_key` or `text` is missing or blank THEN THE SYSTEM SHALL return a tool error without calling the API.
- IF `work_item_id` does not match `workItemIDPattern` THEN THE SYSTEM SHALL return a tool error without calling the API.
- IF `text` is larger than 8 KiB (`workitems.MaxIntentBytes`) THEN THE SYSTEM SHALL return the API's 400 refusal. The MCP layer SHALL NOT truncate the text.
- IF the text contains a secret-shaped value THEN THE SYSTEM SHALL return the API's 400 `secret_in_text` refusal, and the text SHALL NOT be stored.
- WHEN the same key and body are sent again THE SYSTEM SHALL return the original intent, marked `"replayed": true`.
- IF the same key is reused with a different body THEN THE SYSTEM SHALL return the API's 409 `idempotency_key_reused`.
- IF the caller's tenant role is viewer THEN THE SYSTEM SHALL surface 403 `tenant_role_forbidden`, and no intent SHALL be appended.
- IF the item is private to another principal or belongs to a foreign tenant THEN THE SYSTEM SHALL surface the API's 404 `work_item_not_found`.

### List intents
- WHEN `mctl_list_work_item_intents` is called with `work_item_id` and optionally `after_id` and `limit` THE SYSTEM SHALL send `GET /api/v1/work-items/{id}/intents?after_id=&limit=` and return the page as the API returns it: `intents`, `truncated` and `limit`.
- IF `after_id` is not a non-negative integer, or `limit` is not an integer from 1 to 100 (`workitems.MaxIntentPageLimit`), THEN THE SYSTEM SHALL return a tool error without calling the API.
- WHEN an intent has `text_redacted: true` THE SYSTEM SHALL return it unchanged: empty `text` plus `text_redacted: true`. The tool description SHALL state that this means the text is unavailable, not an empty instruction, and that clients must not reconstruct it.
- IF the item is private to another principal or belongs to a foreign tenant THEN THE SYSTEM SHALL surface 404 `work_item_not_found`, exactly as for an id that does not exist.

### Cross-cutting
- WHILE any of the three tools runs THE SYSTEM SHALL NOT create an execution request, an execution or a snapshot.
- THE SYSTEM SHALL register all three tools on the direct MCP endpoint (`Server.NewMCPServer` in `internal/mcp/server.go`).
- THE SYSTEM SHALL list all three tools in `docs/portal-allowlist.json` with `enabled: false` and a specific reason. `mctl_request_work_item_execution` SHALL stay disabled. The four existing work-item reads SHALL keep their current entries.
- THE SYSTEM SHALL record the three tools in `recordedHints` (`internal/mcp/annotations_test.go`):
  - create and append as `readOnly: false, destructive: false, idempotent: true`;
  - list as `readOnly: true, destructive: false, idempotent: false`.
  `TestNewMCPServer_ToolCount` SHALL pass.
- THE SYSTEM SHALL add `mctl_create_work_item` and `mctl_append_work_item_intent` to `governedAgentTools` (`internal/mcp/agent_receipt_gate.go`). They are not read verbs.
- THE SYSTEM SHALL update `docs/work-context-contract.md`:
  - the "Out of scope" bullet (current-main lines 455-459) that calls MCP wrappers future work;
  - the MCP surface table, adding the three tools;
  - the statement "All five tools are off on the shared portal" (lines 600-601), replaced with the exact matrix: four reads enabled, `mctl_request_work_item_execution` disabled, the three new tools disabled. The matrix SHALL link `docs/portal-allowlist.json`.

## Out of scope

- Any new REST route, storage table, migration or change to `internal/workitems` validation.
- `intent_id` on execution requests and execution resume (mctl-api#871).
- Fulfilment of MCP-origin items by the dispatcher (mctl-agents#904 and mctl-api#871). This slice does not fix it and does not claim to.
- An MCP lookup or discovery tool by `external_key`, or listing WorkItems over MCP.
- Enabling any of the new tools, or `mctl_request_work_item_execution`, on the shared portal (owner decision, mctlhq/.github#237).
- The retention sweeper (mctl-api#353). Tests use redaction fixtures.
- The live Claude-to-Codex authentication proof (mctl-agents#909). This slice provides the tools that proof exercises.
- Intent `params` over MCP (see Open questions).

## Open questions

- `params`: REST accepts an optional JSON object of up to 8 KiB. The issue lists only text. This proposal leaves `params` out of the MCP append tool to keep the contract minimal. Adding it later is backward compatible.
- Single-intent read: REST has `GET /work-items/{id}/intents/{intent_id}`. This proposal does not add an optional `intent_id` to the list tool, because the issue names only the paged list. The sibling list tools do take such an id, so the reviewer may want it added.
- `"replayed": true` on create: the API also answers 200 when `external_key` dedupes onto an existing open item, not only on a key replay. `workItemCall` marks both cases `replayed`. This proposal keeps that behavior and says so in the tool description. A distinct marker would need a REST change.
- Scoped agent run tokens: `auth.IsReadTool` admits `list_` tools, so a scoped agent run could read raw intent text through `mctl_list_work_item_intents`. This matches the snapshot read tools, which can already carry issue text. Confirm this is acceptable, or add the tool to an agent-scope exclusion.
- Portal exposure of each new tool, including the raw-intent read, is an owner decision. The default is disabled.
