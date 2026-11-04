# Design: issue-868-feat-mcp-create-workitems-and-append-rea

## Current state

**MCP work-item surface** (`internal/mcp/workitems.go`, mctl-api#341)
- Five tools exist:
  - four reads: `mctl_get_work_item`, `mctl_list_work_item_executions`, `mctl_list_work_item_snapshots`, `mctl_list_work_item_execution_requests`;
  - one write: `mctl_request_work_item_execution`.
- `Server.NewMCPServer` registers them in `internal/mcp/server.go` (lines ~343-347).
- All five go through `Server.workItemCall`, which:
  - forwards `s.effectiveToken(ctx)` as the bearer token;
  - keeps the API's HTTP status, code and details in the tool error;
  - marks a POST that returns 200 with `"replayed": true`.
- Shared helpers:
  - `idArg` / `requiredIDArg` validate ids against `workItemIDPattern` (`^[A-Za-z0-9_-]{1,128}$`), so an id is always exactly one path segment;
  - `workItemSurface = "mcp"` is the label sent as `surface`.

**REST routes** (`internal/api/router.go`)
- Writes, all on the shared 20/min write budget:
  - `POST /work-items` → `Handlers.CreateWorkItem` (line ~751);
  - `POST /work-items/{id}/intents` → `Handlers.AppendWorkItemIntent` (line ~762).
- Reads:
  - `GET /work-items/{id}/intents` → `ListWorkItemIntents` (line ~881);
  - `GET /work-items/{id}/intents/{intent_id}` → `GetWorkItemIntent`.

**`CreateWorkItem`** (`internal/api/handlers_work_items.go`)
- Body: `createWorkItemBody{tenant, visibility, origin_surface, title, external_key, idempotency_key}`.
- Checks, in order:
  1. `user.HasTenantAccess(tenant)`, else 403 `tenant_forbidden`;
  2. `requireWorkItemRole(..., workItemWriteRole=RoleDeveloper, "create")`, else 403 `tenant_role_forbidden`. A viewer is refused here.
- Defaults `visibility` to `tenant`. Defaults `origin_surface` to the relay surface or `"api"`.
- `mutationFor` takes the actor from the token and hashes the body without the key into `RequestHash`. A relayed token that claims a different surface is refused with 400.
- `Store.Create` (`internal/workitems/store.go` ~310) handles replay and dedupe:
  - Same `(tenant, idempotency_key)`, same hash and same actor: returns the stored item. Anything else is `ErrIdempotencyKeyReuse` → 409 `idempotency_key_reused`.
  - Same `external_key`: dedupes onto an open item only when it has the same visibility and is not someone else's private item. Otherwise `ErrExternalKeyInUse` → 409 `external_key_in_use`.
  - Either way the handler answers 200 instead of 201.
- `canSeeWorkItem` is a second check after the store: an item the caller cannot see is never disclosed.

**`AppendWorkItemIntent`**
- Checks visibility first via `visibleWorkItem`: a foreign or another principal's private item answers 404 `work_item_not_found`. Then checks the developer role.
- Body: `intentBody{text, params, surface, idempotency_key}`.
- `IntentInput.validate` (`internal/workitems/inputs.go` ~247) enforces:
  - `text` is required and at most `MaxIntentBytes = 8 << 10`;
  - secret patterns → `ErrSecretInText` → 400 `secret_in_text`;
  - `params` is a JSON object of at most 8 KiB.
- Replay goes through `replayed(...)` with `opIntent`. The handler returns `{schema_version, intent}` with 201 or 200.

**`ListWorkItemIntents`** (`internal/api/handlers_work_item_intents.go`)
- Applies the same visibility check.
- Pages by `after_id`, a non-negative int64, and `limit` from 1 to `MaxIntentPageLimit=100` (default 50).
- Returns `{schema_version, intents, truncated, limit}`.
- `workitems.Intent` has `ID int64`, `Text`, and `TextRedacted bool` (always serialized, `types.go` ~235). A retention-swept intent reads `text: ""` with `text_redacted: true`.

**Tests and policy that pin the tool set**
- `internal/mcp/annotations_test.go` `recordedHints`. The current work-item rows are at lines 53-57. `TestNewMCPServer_ToolCount` in `server_test.go` compares the tool count with `len(recordedHints)`.
- `internal/mcp/portal_allowlist_test.go` `TestPortalAllowlist_CoversEveryRegisteredTool`: every tool needs an entry in `docs/portal-allowlist.json` with a reason. Enabling a non-read tool also needs `mutatingOnPortal`.
- `internal/mcp/agent_receipt_gate.go`: every tool is in `governedAgentTools`, is a read verb (`auth.IsReadTool`), or is in `ungovernedAgentTools`. `mctl_request_work_item_execution` is governed (line 197).
- `docs/portal-allowlist.json` lines 488-511:
  - the four work-item reads are `enabled: true` (owner decision 2026-10-04);
  - `mctl_request_work_item_execution` is `enabled: false`.

**Stale docs** (`docs/work-context-contract.md`)
- Lines 455-459 ("Out of scope") say MCP wrappers for work items are explicit follow-up work. The five tools above already exist.
- Lines 600-601 say "All five tools are off on the shared portal". In fact four reads are enabled and `mctl_request_work_item_execution` is disabled.
- The MCP surface table at lines ~584-590 lists the five tools.

**Deployed state checked:**
- `mctl_list_services(team=admins)` succeeded (complete=true). It lists `mctl-agents-worker*`, `mctl-design`, `mctl-docs`, `mctl-support`, `mctl-web` and `umami`. mctl-api is not a catalogue service of the `admins` tenant, so its deployed config cannot be observed this way.
- `$MCTL_GITOPS_ROOT/services/` (listed `admins/`): no `mctl-api` directory exists under `services/*/`. mctl-api's deployment is not a tenant service in this checkout. Its env and replica settings were not observed, and this design depends on none of them.
- The live portal state was not queried. `docs/portal-allowlist.json` in the clone is the source of truth that gitops vendors byte-identical.

## Proposed solution

Add three handlers to `internal/mcp/workitems.go` that follow the existing pattern exactly, and register them next to the existing five in `NewMCPServer`. There are no REST, store or migration changes.

### `mctl_create_work_item`

**Annotations:** `readOnly=false`, `destructive=false`, `idempotent=true`. Title: "Create a work item".

**Arguments:**

| Argument | Required | Rule |
|---|---|---|
| `tenant` | yes | |
| `title` | yes | Trimmed; non-empty. The store enforces `MaxTitleBytes` (256). |
| `idempotency_key` | yes | Trimmed; a blank key is refused before any call. No default is generated. |
| `visibility` | no | Enum `tenant`, `private`. Omitted when empty, so the REST default applies. |
| `external_key` | no | |

**Body:** `{tenant, title, idempotency_key, origin_surface: workItemSurface}`, plus `visibility` and `external_key` when given. The body never carries an actor, owner or surface argument from the caller.

**Call:** `s.workItemCall(ctx, POST, "/api/v1/work-items", body, "create work item")`.

**Description must state:**
- the actor comes from authentication;
- `tenant` is checked against the caller's own access;
- a viewer is refused;
- a private item is visible only to its creator;
- 409 `external_key_in_use` and `idempotency_key_reused` are possible;
- `"replayed": true` means an existing item was returned, either by the same-key retry or by `external_key` dedupe;
- the returned `wi_` id is what the user passes to another client (no discovery tool exists);
- creating starts no execution.

### `mctl_append_work_item_intent`

**Annotations:** `readOnly=false`, `destructive=false`, `idempotent=true`.

**Arguments:**
- `work_item_id`, required, validated with `requiredIDArg`;
- `text`, required, non-empty. It is not trimmed when sent, because the hash must match exactly what the caller sends;
- `idempotency_key`, required, trimmed, non-empty.

**Body:** `{text, idempotency_key, surface: workItemSurface}`.

**Call:** `POST /api/v1/work-items/{id}/intents`.

**Description must state:**
- the 8 KiB limit;
- `secret_in_text` refusal, so secrets are never stored;
- the retry and conflict semantics;
- an intent is provenance, not approval;
- appending starts no execution.

### `mctl_list_work_item_intents`

**Annotations:** read-only, matching the sibling reads.

**Arguments:**
- `work_item_id`, required;
- `after_id`, optional number: a non-negative integer of at most 2^53;
- `limit`, optional number: an integer from 1 to `workitems.MaxIntentPageLimit`.

Invalid values are refused locally. That mirrors the `expected_state_version` check in `toolRequestWorkItemExecution`.

**Call:** build the query with `url.Values` and call `GET /api/v1/work-items/{id}/intents[?after_id=..&limit=..]`.

**Response:** passed through untouched, with no post-processing of `text`.

**Description must say:**
- oldest first;
- page with `after_id` set to the last `id` returned while `truncated` is true;
- `text_redacted: true` means the text was removed by retention and is unavailable. It is not an empty instruction and must never be reconstructed.

### Registration and policy

- `server.go`: add `srv.AddTool(s.toolCreateWorkItem())`, `s.toolAppendWorkItemIntent()` and `s.toolListWorkItemIntents()`.
- `annotations_test.go` `recordedHints`:
  - three new rows;
  - add `mctl_list_work_item_intents` to the read list at lines ~261-269 if that list enumerates read tools.
- `agent_receipt_gate.go`: add `mctl_create_work_item` and `mctl_append_work_item_intent` to `governedAgentTools`. The list tool is a read verb.
- `docs/portal-allowlist.json`: three entries, all `enabled: false`, each with a specific reason:
  - create opens tenant work under the caller;
  - append stores free text;
  - list exposes raw intent text, which can be sensitive.
  The `mctl_request_work_item_execution` entry and the four enabled reads are not changed. `mutatingOnPortal` is not touched.
- `docs/work-context-contract.md`:
  - Replace the "MCP tool wrappers" out-of-scope bullet with a pointer to the MCP surface section. Keep only the genuinely open items (external_key lookup tool, intent_id/resume via #871).
  - Extend the tool → route table.
  - Replace "All five tools are off..." with an explicit tool | route | portal matrix that links `docs/portal-allowlist.json`.
  - State that none of the three tools starts an execution, and that fulfilment of mcp-origin items depends on mctl-agents#904 and mctl-api#871.
  - Update `internal/openapi/openapi.yaml` only if a contract change is made. None is expected.

### Why this way

- REST already enforces every guard the issue lists, and each MCP call re-runs them under the caller's token. The wrappers stay thin, so a guard cannot drift between surfaces.
- Making `idempotency_key` required in MCP (it is optional in REST) closes the duplicate-write gap the issue names. An MCP client that retries never creates a second item.

## Alternatives

1. **Generate an idempotency key server-side per call when the client omits it.** Dropped. A key generated per attempt makes every retry a new write, which is exactly the duplicate the issue forbids.
2. **Call `internal/workitems.Store` directly from the MCP server instead of over HTTP.** Dropped:
   - it bypasses the handler-level checks (`HasTenantAccess`, `requireWorkItemRole`, `canSeeWorkItem`, relay-surface checks) and the write rate limit;
   - it breaks the invariant from mctl-api#341 that MCP is a surface over the REST contract.
3. **Add `mctl_find_work_item` by `external_key` for automatic discovery.** Dropped from this slice. The issue says automatic lookup needs a separate contract decision. The handoff passes the `wi_` id explicitly.
4. **Enable the read tool on the portal now, like the four existing reads.** Dropped. Raw intent text is more sensitive than state metadata, and the issue makes each exposure an owner decision with disabled as the default.

## Platform impact

- **Migrations:** none. **REST/OpenAPI:** unchanged.
- **Backward compatibility:** purely additive. Three tools are added and the existing tool behavior is unchanged. Clients that cache tool lists will see three more tools on the direct endpoint. The portal does not expose them.
- **Resources:** each call is one HTTP request to the API. Writes share the existing 20/min write budget, so an MCP loop cannot exceed the REST limits.
- **Risks and mitigations:**
  - *Duplicate writes on retry.* The key is required and the REST hash detects a changed body. Tests cover replay and conflict.
  - *Secret leakage.* The store refuses secrets in text before writing. Audit records ids only (`auditWorkItem`). The MCP layer never logs the text.
  - *Cross-tenant disclosure.* Visibility is checked by the API on every call. A foreign or private item answers 404, never 403.
  - *Scoped agent runs reading intent text.* `list_` is a read verb that scoped runs may call (`auth.IsReadTool`). This matches the snapshot read today. It is recorded as an open question.
  - *Misread redaction.* The API serializes `text_redacted` always, and the tool passes it through unchanged. A redaction fixture test pins this.
  - *Dispatcher expectations.* Create and append start nothing. MCP-origin fulfilment is explicitly not claimed (mctl-agents#904, mctl-api#871).

## Open questions

- Should the append tool accept `params`? This proposal says no for now.
- Should the list tool accept an optional `intent_id` (`GET .../intents/{intent_id}`), like sibling tools accept `snapshot_id` and `request_id`? This proposal says no for now.
- Should `replayed: true` be distinguished from an `external_key` dedupe on create? Doing so needs a REST signal, so it is kept as-is and documented.
- Should scoped agent run tokens be able to read raw intents?
- Owner decision on portal exposure for each new tool. The default is disabled.
- The deployed mctl-api config was not observable through tenant service tools or `services/`. It is not needed for this change.
