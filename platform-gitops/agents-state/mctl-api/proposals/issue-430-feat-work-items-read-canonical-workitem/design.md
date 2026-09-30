# Design: issue-430-feat-work-items-read-canonical-workitem

## Current state

Storage exists; the read path does not.

- Schema. `internal/workitems/store.go` (schema block, line 59) creates
  `work_item_intents (id BIGSERIAL PRIMARY KEY, work_item_id TEXT REFERENCES
  work_items ON DELETE CASCADE, actor_principal TEXT, surface TEXT, text TEXT
  NULL, params JSONB, created_at TIMESTAMPTZ)` plus
  `CREATE INDEX work_item_intents_item ON work_item_intents (work_item_id, id)`.
  A later migration line (store.go:133) adds
  `actor_principal_id TEXT NOT NULL DEFAULT ''`. `text` is nullable on purpose
  — the retention sweeper drops it and keeps the row
  (`docs/work-context-contract.md`, "Retention and privacy").
- Write. `Store.AppendIntent` (store.go:779) inserts under the item's advisory
  lock, refuses a terminal item, appends the `intent_appended` event carrying
  `{"intent_id": n}` and nothing else, and records idempotency. Its replay
  branch calls the private `getIntent(ctx, q, itemID, id)` (store.go:836),
  which selects `WHERE work_item_id=$1 AND id::text=$2` and maps `pgx.ErrNoRows`
  to `ErrNotFound`.
- Type. `workitems.Intent` (`internal/workitems/types.go:213`) already has the
  exact JSON shape the issue asks for: `id`, `work_item_id`,
  `actor_principal`, `surface,omitempty`, `text`, `params,omitempty`,
  `created_at`. `SchemaVersion` is `workitem/v1`.
- HTTP write. `Handlers.AppendWorkItemIntent`
  (`internal/api/handlers_work_items.go:509`) → `visibleWorkItem` →
  `mutationFor` → `AppendIntent`, answering
  `{schema_version, intent}`.
- Reads today. Every work-item read follows the same three lines:
  `workItemsUser` (503 `work_items_unavailable` when `opts.WorkItems == nil`,
  401 without a user), then `visibleWorkItem` (loads `{id}`, turns an invisible
  item into `workitems.ErrNotFound`, so 404 `work_item_not_found` and never
  403), then one store call and `writeJSON`. See `GetWorkItem`,
  `ListWorkItemExecutions`, `ListWorkItemEvents`
  (handlers_work_items.go:400/540/700), `ListWorkItemSnapshots`,
  `GetWorkItemSnapshot` (`internal/api/handlers_work_item_snapshots.go`) and
  `ListExecutionRequests` / `GetExecutionRequest`
  (`internal/api/handlers_execution_requests.go:208/228`).
- Visibility. `canSeeWorkItem` (handlers_work_items.go:88): admin sees
  everything; otherwise `HasTenantAccess(item.Tenant)` and either
  `visibility == tenant` or `owner_principal == principalOf(user)`. The
  platform service principal is `auth.NewServiceUser()` with
  `Groups: ["admins"]` (`internal/auth/oidc.go:148`), so it is already admitted
  by the `IsAdmin()` branch — which is why it can already read executions and
  snapshots. No new special case is needed for it.
- Routing. `internal/api/router.go:550` starts the "Work-item reads:
  side-effect free, outside the write budget" block (lines 551-560); mutations
  sit in the 20/min write group at lines 473-494.
- Relay. `surfaceRoutes` in `internal/api/handlers_surface_identity.go` (line
  ~80) is the allowlist a surface principal may call, with `relay: true`
  meaning "run as the linked human". It currently lists
  `GET /api/v1/work-items/[^/]+`, `POST .../intents`, `POST .../surface-refs`
  and `GET|POST .../execution-requests[/{request_id}]`.
- Error codes. `intent_not_found` already exists as `xrCodeIntentNotFound`
  (handlers_execution_requests.go:43), returned when
  `POST /work-items/{id}/execution-requests` names an `intent_id` of another
  item — `workitems.ErrIntentNotFound`
  (`internal/workitems/execution_requests.go:92`), raised by the `SELECT
  EXISTS (... FROM work_item_intents WHERE work_item_id=$1 AND id=$2)` probe at
  execution_requests.go:359. `writeWorkItemError` does not map it; only
  `writeExecutionRequestError` does.
- Pagination precedent. `internal/evidence/read.go` has
  `ListResult{Evidence, Truncated, Limit}` with a clamped `Limit` and the
  comment "a clipped page must never read as a complete one";
  `internal/mcp/lifecycle.go:321` keeps `truncated` strictly about the store's
  page. `Store.List` (store.go:927) clamps with `defaultListLimit`/
  `maxListLimit` (inputs.go:121); the handler `ListWorkItems`
  (handlers_work_items.go:414) refuses an out-of-range `limit` with 400
  `invalid_request`. No work-item route uses `after_id` yet — this is the first.

## Proposed solution

Four small, additive pieces. No migration, no write path, no new dependency.

### 1. Store reads — `internal/workitems/store.go`, beside `AppendIntent`

Two exported methods, placed immediately after `AppendIntent`/`getIntent` so
that everything touching `work_item_intents` stays in one place:

```go
// IntentPage is a bounded page of intents, oldest first. Truncated is part
// of the answer: a clipped page must never read as a complete one.
type IntentPage struct {
    Intents   []Intent `json:"intents"`
    Truncated bool     `json:"truncated"`
    Limit     int      `json:"limit"`
}

// Intents returns a page of the item's intents with id > afterID, ascending.
// No authorization: the caller checks visibility, as Events does.
func (s *Store) Intents(ctx context.Context, itemID string, afterID int64, limit int) (*IntentPage, error)

// Intent returns one intent of itemID. An id of another item, or no id at
// all, is ErrIntentNotFound — never ErrNotFound, which means the work item.
func (s *Store) Intent(ctx context.Context, itemID, id string) (*Intent, error)
```

- `Intents` clamps `limit` to `DefaultIntentPageLimit` (50) when `<= 0` and to
  `MaxIntentPageLimit` (100) when above, mirroring `Store.List`. Both constants
  go in the bounds block of `types.go` next to `MaxIntentBytes`, exported so the
  handler can validate against the same numbers.
- Query: `SELECT id, work_item_id, actor_principal, surface, text, params,
  created_at FROM work_item_intents WHERE work_item_id=$1 AND id > $2 ORDER BY
  id LIMIT $3` with `$3 = limit+1`. If `limit+1` rows come back, drop the extra
  and set `Truncated = true`. Fetching one row more than the page makes
  `truncated` exact, so a full last page is not reported as truncated and a
  paginating caller is never sent after a page that does not exist
  (the trap `internal/mcp/lifecycle.go:326` documents). The existing
  `work_item_intents_item (work_item_id, id)` index serves this scan directly —
  no new index.
- `text` is scanned into `*string` and flattened to `""` when NULL, exactly as
  `getIntent` and `AppendIntent` already do, so a retention-swept row still
  reads. The read also sets a new response field `text_redacted` (true exactly
  when the column was NULL). The field is additive, and existing `Intent` JSON
  consumers ignore it. Without it, a swept row and a genuinely empty text are
  indistinguishable, which is the "could not observe" vs. "observed absent"
  confusion AGENTS.md forbids. `created_at` is normalized with `.UTC()`, as everywhere else.
- `Intents` returns an empty, non-nil slice for an unknown item — the same
  contract `Events` documents ("An unknown id answers an empty list, not
  ErrNotFound, so the caller Gets the item first"). The handler has already
  Got the item through `visibleWorkItem`, so no existence check is duplicated.
- `Intent` reuses `getIntent`'s `id::text=$2` comparison so a non-numeric path
  parameter is simply no match instead of a Postgres cast error, and maps
  `pgx.ErrNoRows` to `ErrIntentNotFound`. `getIntent` keeps returning
  `ErrNotFound` for the replay path it serves, so no existing behaviour moves.
- Both methods use `s.pool` directly (no `withTx`, no advisory lock): they are
  reads, like `Events`, `Executions` and `Snapshots`.

### 2. HTTP handlers — new `internal/api/handlers_work_item_intents.go`

A new file, following `handlers_work_item_snapshots.go`'s precedent of keeping
one resource's handlers together:

```go
func (h *Handlers) ListWorkItemIntents(w http.ResponseWriter, r *http.Request)
func (h *Handlers) GetWorkItemIntent(w http.ResponseWriter, r *http.Request)
```

Both are the canonical three lines: `h.workItemsUser`, `h.visibleWorkItem`,
then the store call. That single reuse is what delivers the issue's visibility
requirement — 503 when unconfigured, 401 unauthenticated, 404 (never 403) for
an item the caller cannot see, and service-principal access via the existing
`IsAdmin()` branch — with no new authorization code to get wrong.

- `ListWorkItemIntents` parses `after_id` and `limit` from `r.URL.Query()` with
  `strconv.ParseInt`/`Atoi`, answering 400 `invalid_request` on a non-integer,
  a negative `after_id`, or a `limit` outside 1..`workitems.MaxIntentPageLimit`
  — the wording style of `ListWorkItems`' limit check. Response:
  `{"schema_version": workitems.SchemaVersion, "intents": [...],
  "truncated": bool, "limit": n}`, built as a `map[string]any` like every other
  work-item read.
- `GetWorkItemIntent` passes `chi.URLParam(r, "intent_id")` to `Store.Intent`.
- A small `writeIntentError(w, err)` maps `workitems.ErrIntentNotFound` to
  404 with the existing `xrCodeIntentNotFound` constant ("intent_not_found")
  and defers everything else to `writeWorkItemError`. This is the same shape as
  `writeSnapshotError`. The constant is reused, not redeclared: it lives in the
  same `api` package, and reusing it guarantees a client sees the same code it
  already gets from `POST .../execution-requests`.
- No audit entry, matching every other work-item read, so intent text can never
  reach an audit row.

### 3. Routing and relay

- `internal/api/router.go`: two lines in the read block after
  `r.Get("/work-items/{id}/events", ...)`:
  `r.Get("/work-items/{id}/intents", h.ListWorkItemIntents)` and
  `r.Get("/work-items/{id}/intents/{intent_id}", h.GetWorkItemIntent)`. The
  existing `POST /work-items/{id}/intents` stays in the write group; chi
  registers method-specific handlers, so the same pattern in two groups is fine
  — `GET|POST /work-items/{id}/execution-requests` is already split that way.
- `internal/api/handlers_surface_identity.go`: two `surfaceRoutes` entries,
  `{GET, ^/api/v1/work-items/[^/]+/intents$, true}` and
  `{GET, ^/api/v1/work-items/[^/]+/intents/[^/]+$, true}`, so the routes are
  relay-eligible as the issue states. Relay resolution is unchanged and
  happens once, in `surfacePrincipalGate`; a relayed read runs as the linked
  human and therefore gets that human's visibility.

### 4. Contract

- `internal/openapi/openapi.yaml`: add `get` to the existing
  `/api/v1/work-items/{id}/intents` path item (alongside its `post`) with
  `after_id` and `limit` query parameters and a response schema carrying
  `schema_version`, `intents`, `truncated`, `limit`; add a new
  `/api/v1/work-items/{id}/intents/{intent_id}` path with `get`. Introduce a
  `WorkItemIntent` component schema (`id`, `work_item_id`, `actor_principal`,
  `surface`, `text`, `params`, `created_at`) so both responses reference one
  definition. Extend the "Surface Identity" tag description's relay-route list
  with the two GETs.
- `docs/work-context-contract.md`: add the two routes to the REST surface table
  (line ~380), append them to the relay-route sentence in "Surface relay
  (mctl-api#350)" (line ~492), and state under `WorkItemIntent` (line ~105)
  that intents are readable by whoever can see the item, in ascending `id`
  order with `after_id`/`limit`/`truncated`, and that they remain provenance
  and input — never authorization or approval state.

## Alternatives

1. **Extend the `intent_appended` event, or `GET /work-items/{id}`, to carry
   intent text.** No new route, and the execution platform already reads both.
   Dropped: the contract is explicit that history records the intent id only
   and never copies text (`AppendIntent`'s comment, store.go:819, and
   "Retention and privacy"), and `work_item_events` rows are not covered by the
   intent-text retention sweep — text copied there would outlive the sweep.
   Widening `GET /work-items/{id}` would also make every poll of the item view
   ship unbounded intent text to callers that only wanted `state_version`.

2. **Return the intent inline on the execution-request read
   (`GET /work-items/{id}/execution-requests/{request_id}`), embedded next to
   `intent_id`.** Tempting: it is exactly where the resuming platform looks.
   Dropped: it resolves only intents that an execution request happens to
   name, so C2 assembly still could not read the item's other intents; it
   changes an existing response shape (a compatibility risk for current
   clients) and couples two resources whose retention differs — a swept intent
   would turn into a half-empty embedded object inside an execution request.

3. **Offset pagination (`offset`/`limit`) or no pagination at all (return every
   intent, like `Events` and `Executions` do).** Simpler, and consistent with
   the neighbouring list routes. Dropped: the issue specifies `after_id` and
   `truncated`, and it is the right choice here — intents are append-only with a
   monotonic `BIGSERIAL`, so a keyset read is stable under concurrent appends
   (an offset page silently shifts), it is index-covered by
   `work_item_intents_item`, and an unbounded list of 8 KiB texts is a response
   size nobody bounds. `Events`/`Executions` stay as they are; this route does
   not have to match their (bounded-by-nature) shape.

4. **A `GET /intents/{intent_id}` route not nested under the work item.**
   Dropped: the intent id would then be the only thing standing between a
   caller and another tenant's intent, and enforcing visibility would require a
   reverse lookup to the item anyway. Nesting makes `visibleWorkItem` the single
   gate and makes the cross-item 404 fall out of the query.

## Platform impact

- **Migrations: none.** No DDL, no new index, no column. `work_item_intents`
  and its `(work_item_id, id)` index are used as they stand.
- **Backward compatibility: additive only.** Two new GET routes, one new
  component schema, two new exported store methods, two new exported constants.
  No existing response shape, error code or status changes. `getIntent` keeps
  its current error mapping, so `AppendIntent`'s replay path is untouched. No
  MCP tool is added or removed, so `internal/mcp/server_test.go`'s tool count
  expectation (CLAUDE.md) stays valid.
- **Resource impact: negligible.** Each list is one index-covered range scan of
  at most 101 rows; each get is one primary-key-adjacent lookup. Both sit in
  the read block, outside the 20/min write budget, and inherit the surface
  aggregate limit and the 30s timeout already applied to the authenticated
  group. Worst-case response is ~100 x (8 KiB text + 8 KiB params) ≈ 1.6 MB;
  if a reviewer wants that smaller, lowering `MaxIntentPageLimit` is a
  one-constant change.
- **Risk: exposing user-written text to a caller who should not see it.**
  Mitigation: no new authorization logic exists to diverge — the routes go
  through the same `visibleWorkItem`/`canSeeWorkItem` pair as the existing
  reads, and the tests assert 404-not-403 for a foreign-tenant item and for
  another owner's `private` item. A relayed read runs as the linked human
  (`surfacePrincipalGate`), never as the surface principal and never as admin.
- **Risk: `intent_not_found` vs `work_item_not_found` confusion.** A client that
  cannot tell "the item is gone" from "that intent is not this item's" would
  retry the wrong thing. Mitigation: the distinct code, reusing the constant
  `POST .../execution-requests` already returns, plus an explicit cross-item
  test.
- **Risk: a clipped page read as complete.** C2 assembly that silently drops
  the newest intent would produce a wrong context snapshot. Mitigation: the
  limit+1 probe makes `truncated` exact, and a test asserts `truncated: false`
  on a page exactly as long as the limit.
- **Risk: intent text in logs.** Mitigation: no audit entry is written for
  these reads (matching the other work-item reads), and no handler logs the
  intent; only `slog.Error("work-items store error", ...)` on a store failure,
  which carries no row content.
- **Retention interaction.** A swept intent (`text` NULL) is returned as
  `text: ""` with `text_redacted: true` rather than erroring, so a caller assembling context from an old
  item degrades instead of failing; the row's provenance (`actor_principal`,
  `surface`, `created_at`) survives.
- **Operational note.** With no store configured (`WORK_ITEMS_DB_URL` and
  `AUDIT_DB_URL` unset, or `WORK_ITEMS_DISABLED`) both routes answer 503
  `work_items_unavailable`, never an empty list — an execution platform must
  not read "no intents" from "no store".
