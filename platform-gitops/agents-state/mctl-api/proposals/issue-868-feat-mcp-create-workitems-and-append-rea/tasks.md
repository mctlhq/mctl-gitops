# Tasks: issue-868-feat-mcp-create-workitems-and-append-rea

- [ ] 1. Add `toolCreateWorkItem` to `internal/mcp/workitems.go`.
  - Required args: `tenant`, `title`, `idempotency_key`. Optional: `visibility` (enum `tenant`/`private`), `external_key`.
  - Body sent: `origin_surface: workItemSurface`, plus the arguments given. No actor or surface argument is accepted.
  - Call: `workItemCall(POST, "/api/v1/work-items")`.
  - The description covers: actor from auth, tenant check, viewer refusal, 409 codes, replay meaning, passing `wi_` explicitly, and no execution started.
  - DoD: blank or missing key, blank title, or a bad visibility returns a tool error with no HTTP call. A valid call sends exactly the documented body.
- [ ] 2. Add `toolAppendWorkItemIntent`.
  - Required args: `work_item_id` (via `requiredIDArg`), `text`, `idempotency_key`.
  - Body sent: `{text, idempotency_key, surface: "mcp"}`.
  - Call: `POST /api/v1/work-items/{id}/intents`.
  - The description covers: 8 KiB, `secret_in_text`, retry and conflict, provenance not approval, no execution.
  - DoD: missing text or key, or a bad id, fails locally. The text is forwarded byte-for-byte, with no trimming or truncation.
- [ ] 3. Add `toolListWorkItemIntents`.
  - Args: `work_item_id`, optional `after_id` (a non-negative integer of at most 2^53), optional `limit` (1 to `workitems.MaxIntentPageLimit`).
  - Call: `GET .../intents` with the query built by `url.Values`.
  - Read-only annotations. The description explains `text_redacted` as unavailable content.
  - DoD: invalid paging fails locally. The response is passed through unchanged.
- [ ] 4. Register the three tools in `Server.NewMCPServer` (`internal/mcp/server.go`), next to the existing work-item tools. (Depends on 1-3.)
  - DoD: the tools appear on the direct MCP endpoint.
- [ ] 5. Update `recordedHints` in `internal/mcp/annotations_test.go` (and the read-tool list near line 261, if applicable). (Depends on 4.)
  - Create and append: `{readOnly:false, destructive:false, idempotent:true}`. List: `{readOnly:true, destructive:false, idempotent:false}`.
  - DoD: `TestNewMCPServer_ToolCount` and the annotation tests pass.
- [ ] 6. Add `mctl_create_work_item` and `mctl_append_work_item_intent` to `governedAgentTools` in `internal/mcp/agent_receipt_gate.go`. (Depends on 4.)
  - DoD: the governed/ungoverned coverage test passes.
- [ ] 7. Add three `enabled: false` entries with specific reasons to `docs/portal-allowlist.json`. (Depends on 4.)
  - Leave the `mctl_request_work_item_execution` entry and the four enabled reads unchanged. `mutatingOnPortal` is not modified.
  - DoD: `TestPortalAllowlist_CoversEveryRegisteredTool` passes, and `git diff` shows no change to existing entries.
- [ ] 8. Correct `docs/work-context-contract.md`.
  - Out-of-scope bullet at lines 455-459: wrappers are not all future work. Keep only the external_key lookup tool and the #871 items as follow-up.
  - Extend the MCP surface table.
  - Replace lines 600-601 with an exact tool | route | portal matrix linked to `docs/portal-allowlist.json`: four reads enabled, `mctl_request_work_item_execution` disabled, three new tools disabled.
  - State that create, append and list start no execution, and that mcp-origin fulfilment needs mctl-agents#904 and mctl-api#871.
  - DoD: the doc matches `portal-allowlist.json` entry for entry.
- [ ] 9. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. Run a manual mutation pass on the guards (see T12). (Depends on 1-8.)
  - DoD: all green, and every listed mutation is killed by at least one test.

## Tests

All tests go in `internal/mcp/workitems_test.go` unless noted, and use the existing httptest server pattern.

- [ ] T1. Create sends `POST /api/v1/work-items` with `tenant`, `title`, `idempotency_key` and `origin_surface:"mcp"`.
  - `visibility` and `external_key` are sent only when given.
  - Unknown identity-like arguments (`actor`, `owner_principal`, `surface`) are not forwarded.
  - The caller's token is forwarded (extend `TestWorkItemToolsForwardTheCallersToken`).
- [ ] T2. Create refuses locally, without calling the API, on a missing or blank `idempotency_key`, a missing title or tenant, or `visibility:"public"`.
- [ ] T3. A create that returns 200 gets `"replayed": true`. A 409 `external_key_in_use` and a 409 `idempotency_key_reused` keep status, code and details. A 403 `tenant_role_forbidden` (viewer) and a 403 `tenant_forbidden` (unauthorized tenant claim) are surfaced verbatim.
- [ ] T4. Append sends exactly `{text, idempotency_key, surface:"mcp"}`.
  - The text is forwarded byte-identical, including leading or trailing whitespace and an 8 KiB + 1 byte payload (no local truncation).
  - Missing text, missing key, or a bad `work_item_id` fails without a call.
- [ ] T5. Append surfaces the API errors: 400 `secret_in_text`, 400 `invalid_request` (oversize), 409 `idempotency_key_reused`, 404 `work_item_not_found`, and 403 `tenant_role_forbidden`. A 200 is marked `replayed`.
- [ ] T6. List builds `?after_id=&limit=` correctly, omits them when absent, and refuses negative, fractional or non-numeric `after_id`, and `limit` of 0 or 101, with no call.
- [ ] T7. List passes a redaction fixture through unchanged: an intent with `"text":""`, `"text_redacted":true` keeps both fields.
- [ ] T8. Add the three tools to `TestWorkItemToolsRefuseIDsThatAreNotOneSegment` (`..`, `a/b`) and to the typed-refusal test.
- [ ] T9. No tool calls `/execution-requests`, `/executions` or `/resume`. Assert the recorded request paths across a create, append and list sequence.
- [ ] T10. Add a REST-level test in `internal/api` (`handlers_work_items_test.go`, `tenant_role_work_items_test.go`), only where coverage is missing, covering:
  - viewer refused on create and on intent append;
  - another principal's private item → 404 on append and on list intents;
  - same key and same body on append → 200 with the same intent id;
  - same key and a changed body → 409;
  - list paging over more than `limit` intents with `truncated`;
  - `origin_surface:"mcp"` stored on create.
- [ ] T11. The existing suites pass with the new tools: `TestNewMCPServer_ToolCount`, the annotations tests, `TestPortalAllowlist_CoversEveryRegisteredTool`, the agent receipt gate coverage test, and `TestReadToolsAreRecordedReadOnly`.
- [ ] T12. Mutation pass. Each of these mutations must be killed by a failing test:
  - drop the key-required check;
  - drop `origin_surface`/`surface:"mcp"`;
  - flip the list tool's `readOnly`;
  - enable any new allowlist entry;
  - trim or truncate the text;
  - drop the `limit` bound.

## Rollback

The change is additive and has no data migration.
- To roll back, revert the PR, or deploy the previous mctl-api image.
- The three tools disappear from the direct MCP endpoint. Their portal entries were never enabled, so portal users are unaffected.
- WorkItems and intents created through MCP stay valid REST data (`origin_surface: "mcp"`, `surface: "mcp"`), readable by the existing REST routes and the existing `mctl_get_work_item`.
- If only the docs are wrong, revert just `docs/work-context-contract.md`.
