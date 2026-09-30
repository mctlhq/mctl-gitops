# Tasks: issue-430-feat-work-items-read-canonical-workitem

- [ ] 1. Add page-size bounds to `internal/workitems/types.go` — DoD: exported
      `DefaultIntentPageLimit = 50` and `MaxIntentPageLimit = 100` sit in the
      bounds block next to `MaxIntentBytes`/`MaxIntentParamBytes`, with a
      comment saying the handler validates against them and the store clamps.

- [ ] 2. Add `IntentPage` and `Store.Intents` to `internal/workitems/store.go`
      (depends on 1) — DoD: `IntentPage{Intents []Intent; Truncated bool;
      Limit int}` with JSON tags `intents`/`truncated`/`limit`; `Intents(ctx,
      itemID string, afterID int64, limit int) (*IntentPage, error)` placed
      after `getIntent`; clamps `limit` (<=0 → default, >max → max); queries
      `WHERE work_item_id=$1 AND id > $2 ORDER BY id LIMIT $3` with `$3 =
      limit+1` and sets `Truncated` from the extra row, which it drops; scans
      `text` through `*string` and flattens NULL to `""`; normalizes
      `created_at` with `.UTC()`; returns a non-nil empty slice for an unknown
      item, like `Store.Events`; uses `s.pool` with no advisory lock.

- [ ] 3. Add `Store.Intent` to `internal/workitems/store.go` (depends on 2) —
      DoD: `Intent(ctx, itemID, id string) (*Intent, error)` reuses
      `getIntent`'s `id::text=$2` comparison so a non-numeric id is a
      no-match, and maps `pgx.ErrNoRows` to
      `workitems.ErrIntentNotFound` (already defined in
      `execution_requests.go:92`); the private `getIntent` is left unchanged so
      `AppendIntent`'s replay path keeps returning `ErrNotFound`.

- [ ] 4. Add `internal/api/handlers_work_item_intents.go` (depends on 2, 3) —
      DoD: new file with a package comment stating intents are provenance and
      input, never authorization; `writeIntentError` maps
      `workitems.ErrIntentNotFound` to 404 with the existing
      `xrCodeIntentNotFound` constant (reused, not redeclared) and defers to
      `writeWorkItemError`; `ListWorkItemIntents` calls `h.workItemsUser` then
      `h.visibleWorkItem`, parses `after_id` (non-negative int64) and `limit`
      (1..`workitems.MaxIntentPageLimit`) answering 400 `invalid_request`
      otherwise, and writes `{schema_version, intents, truncated, limit}`;
      `GetWorkItemIntent` calls the same two helpers then
      `Store.Intent(item.ID, chi.URLParam(r, "intent_id"))` and writes
      `{schema_version, intent}`; neither writes an audit entry nor logs intent
      text.

- [ ] 5. Route both reads in `internal/api/router.go` (depends on 4) — DoD: in
      the "Work-item reads: side-effect free, outside the write budget" block
      (after the `/work-items/{id}/events` line),
      `r.Get("/work-items/{id}/intents", h.ListWorkItemIntents)` and
      `r.Get("/work-items/{id}/intents/{intent_id}", h.GetWorkItemIntent)`; the
      existing `POST /work-items/{id}/intents` stays in the 20/min write group;
      `go build ./...` and `go vet ./...` pass.

- [ ] 6. Make both routes relay-eligible in
      `internal/api/handlers_surface_identity.go` (depends on 5) — DoD: two
      `surfaceRoutes` entries, `{GET,
      ^/api/v1/work-items/[^/]+/intents$, true}` and `{GET,
      ^/api/v1/work-items/[^/]+/intents/[^/]+$, true}`, with a comment that a
      relayed read runs as the linked human and so inherits that human's
      visibility. (If review answers open question 1 the other way, this task
      is dropped and nothing else changes.)

- [ ] 7. Document both routes in `internal/openapi/openapi.yaml` (depends on 5,
      6) — DoD: a `get` added to the existing
      `/api/v1/work-items/{id}/intents` path item with `after_id` (integer,
      minimum 0) and `limit` (integer, 1..100, default 50) query parameters and
      a 200 schema of `{schema_version, intents: [WorkItemIntent], truncated,
      limit}` plus 400/404; a new `/api/v1/work-items/{id}/intents/{intent_id}`
      path with `get`, 200 `{schema_version, intent}` and a 404 documenting
      both `work_item_not_found` and `intent_not_found`; a new `WorkItemIntent`
      component schema referenced by both; the "Surface Identity" tag
      description's relay-route list extended with the two GETs.

- [ ] 8. Document both routes in `docs/work-context-contract.md` (depends on 5,
      6) — DoD: two rows in the REST surface table (`GET
      /api/v1/work-items/{id}/intents` — list intents, ascending `id`,
      `after_id`/`limit`/`truncated`; `GET
      /api/v1/work-items/{id}/intents/{intent_id}` — read one, cross-item id is
      404 `intent_not_found`); the relay-route sentence in "Surface relay
      (mctl-api#350)" extended; the `WorkItemIntent` bullet in "Resource model"
      states that intents are readable by whoever can see the item and remain
      provenance and input, never authorization or approval state; a note that
      a retention-swept intent reads back with `text` empty.

- [ ] 9. Run the full local gate (depends on 1-8) — DoD: `go fmt ./...`,
      `go vet ./...`, `golangci-lint run` and `go test ./...` clean; with
      `TEST_DATABASE_URL` set, `go test ./internal/workitems/...
      ./internal/api/... ./internal/openapi/...` clean; `internal/mcp`
      tool-count test unchanged (no MCP tool added).

## Tests

- [ ] T1. `internal/workitems/store_test.go` (or a new `intents_test.go`):
      append 5 intents to one item, assert `Intents(item, 0, 2)` returns ids 1-2
      in ascending order with `truncated: true`, `Intents(item, 2, 2)` returns
      3-4 with `truncated: true`, and `Intents(item, 4, 2)` returns 5 with
      `truncated: false`.
- [ ] T2. Store: a page exactly as long as the remaining rows reports
      `truncated: false` — the limit+1 probe, not "a full page is truncated".
- [ ] T3. Store: `Intents` on an item with no intents, and on an unknown item
      id, returns a non-nil empty slice and no error (the `Events` contract).
- [ ] T4. Store: `Intent(itemA, idOfIntentOnItemB)` returns
      `workitems.ErrIntentNotFound`; so do an unknown numeric id and a
      non-numeric id such as `"abc"` (no Postgres cast error).
- [ ] T5. Store: an intent whose `text` was set to NULL (simulating the
      retention sweep with a direct `UPDATE work_item_intents SET text=NULL`)
      is returned by both `Intents` and `Intent` with `Text == ""`.
- [ ] T6. Store: `limit <= 0` yields 50 rows at most and `limit > 100` is
      clamped to 100, with `IntentPage.Limit` reporting the effective value.
- [ ] T7. `internal/api/handlers_work_items_test.go`: extend `workItemsRouter`
      with the two GET routes, then assert a caller in the item's tenant reads
      the intents (200, ascending, `schema_version: "workitem/v1"`, and the
      body carries no field beyond the stored `Intent` fields).
- [ ] T8. Handler visibility: a caller with no access to the item's tenant, and
      a caller in the tenant reading another owner's `private` item, both get
      404 with code `work_item_not_found` on both routes — never 403.
- [ ] T9. Handler: `auth.NewServiceUser()` reads both routes successfully
      (the execution platform's read).
- [ ] T10. Handler: cross-item `intent_id` returns 404 with code
      `intent_not_found` (asserting the code string, not just the status).
- [ ] T11. Handler: `limit=0`, `limit=101`, `limit=abc`, `after_id=-1` and
      `after_id=abc` each return 400 with code `invalid_request`; `limit=100`
      and `after_id=0` are accepted.
- [ ] T12. Handler: with `Options.WorkItems == nil` both routes return 503 with
      code `work_items_unavailable` — add `{"GET",
      "/api/v1/work-items/wi_x/intents"}` and `{"GET",
      "/api/v1/work-items/wi_x/intents/1"}` to the existing unconfigured-route
      table in `handlers_work_items_test.go` (line ~153).
- [ ] T13. Handler: an unauthenticated request returns 401 on both routes.
- [ ] T14. `internal/api/handlers_surface_relay_test.go`: a surface principal
      with a valid link reads both routes as the linked human; a surface
      principal with no `X-MCTL-Surface-Actor` gets 403 `relay_required`; a
      revoked link gets 403. (Drop with task 6 if relay is refused in review.)
- [ ] T15. Handler: the read writes nothing — capture `state_version` and the
      event count before and after both reads and assert they are unchanged,
      and assert no audit entry was recorded for the reads.
- [ ] T16. `internal/openapi/embed_test.go`: add
      `"/api/v1/work-items/{id}/intents": {"get", "post"}` and
      `"/api/v1/work-items/{id}/intents/{intent_id}": {"get"}` to
      `TestSpecParses`' routed-and-documented table.

## Rollback

Every change is additive, so rollback is a plain revert of the single PR — no
migration to undo, no data written, no existing response shape changed. If only
the exposure is the problem and the rest is wanted:

1. Remove the two `r.Get` lines from `internal/api/router.go` (task 5). Both
   routes then 404/405 immediately and the store methods become dead code with
   no caller; nothing else in the service touches them.
2. If only relay is the problem, remove the two `surfaceRoutes` entries (task
   6). Surface principals then get 403 `surface_route_not_allowed` before any
   handler runs, while direct callers and the service principal keep the read.
3. If the page size is the problem, lower `MaxIntentPageLimit` (task 1) — one
   constant, and the handler's 400 boundary and the store's clamp move together.

No operator action, redeploy ordering or backfill is required either way: the
work-items store is unchanged, so an older mctl-api image serves the same rows
the moment it is rolled back.
