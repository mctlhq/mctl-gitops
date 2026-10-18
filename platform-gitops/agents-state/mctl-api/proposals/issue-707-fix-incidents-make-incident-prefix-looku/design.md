# Design: issue-707-fix-incidents-make-incident-prefix-looku

## Current state
Clone read at `8aa7bdf0f45f2686befd4f9a40912ee4ad9b6773`. The issue cites `7f8706a`, and the code described there is unchanged.

- `internal/alerts/store.go` `Store.GetByPrefix`:
  - when `len(prefix) >= 36`, it delegates to `Store.Get` (`WHERE id=$1`);
  - otherwise it runs `SELECT ... FROM alerts WHERE id LIKE $1 ORDER BY created_at DESC LIMIT 1` with `prefix+"%"`;
  - it has no minimum length, does not escape `%`/`_`/`\`, and picks the newest row on ambiguity;
  - errors are wrapped as `fmt.Errorf("alerts store: get by prefix: %w", err)`. The only typed error in the package is `ErrIDConflict`. There is no `ErrNotFound`, and `pgx.ErrNoRows` is not translated.
- `alerts` table: `id TEXT PRIMARY KEY`. Ids are caller-supplied in `CreateIncident` (`internal/api/handlers_alerts.go`, which only requires `a.ID != ""`). Tests use ids such as `argo-run-1` and `argo-wf-trace-1`, so ids are not always UUIDs and can be shorter than 36 or even 8 characters.
- `internal/api/handlers_alerts.go`: `GetIncident` (l.234), `UpdateIncident` (l.270), `AcknowledgeIncident` (l.344) and `ResolveIncident` (l.388) each call `h.opts.AlertStore.GetByPrefix(r.Context(), id)` and map every error to `404 "incident not found: "+id`. Then each one runs the tenant access check, `requireTenantRole` for the mutating ones, and `AlertStore.Update(existing)` (`UPDATE ... WHERE id=$1` using the resolved full id).
- `h.opts.AlertStore` is the concrete `*alerts.Store` (tests build `Handlers{opts: Options{AlertStore: store}}` with `newTestAlertStore`), so there is no interface to update.
- Routes are in `internal/api/router.go` l.526-533. `/incidents/summary` is registered before `/incidents/{id}`.
- MCP: `internal/mcp/server.go`. `mctl_get_incident` (around l.2246), `mctl_acknowledge_incident` (l.2298) and `mctl_resolve_incident` (l.2337) proxy to the REST endpoints with `url.PathEscape(id)` and surface any non-2xx as a tool error. Their `id` description says "full UUID or 8-char prefix".
- Tests: Postgres-backed and gated on `TEST_DATABASE_URL` (`internal/alerts/store_test.go` `newTestStore`/`newAlert`; `internal/api/handlers_alerts_test.go` `newTestAlertStore`). `store_trace_test.go` calls `GetByPrefix(ctx, "argo-wf-trace")`, a 13-character prefix with a single match, and keeps passing.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-api)` returned "service not found: admins/mctl-api". Deployed config not observed.
- `$MCTL_GITOPS_ROOT/services/*/`: no `mctl-api` directory under any tenant (admins, karabu, labs). mctl-api is not deployed as a tenant service from this tree, and its deployed config was not observed. The change is code-only, with no config, env var or schema dependency, so the gap does not affect the design.

## Proposed solution
1. **Typed errors in `internal/alerts`** (`store.go`, next to `ErrIDConflict`):
   - `ErrNotFound = errors.New("alerts store: incident not found")`
   - `ErrPrefixTooShort = errors.New("alerts store: id prefix too short")`
   - `ErrAmbiguousPrefix = errors.New("alerts store: id prefix matches more than one incident")`
   - `const MinPrefixLen = 8`

   `Store.Get` translates `pgx.ErrNoRows` to `ErrNotFound`, wrapped so that `errors.Is` works. The existing callers that compare to nil are unaffected.

2. **Rewrite `GetByPrefix`** using an exact-first strategy:
   - a. Exact lookup: `Get(ctx, prefix)`. Success returns the row. Any error other than `ErrNotFound` is returned as is. An exact match always wins, which keeps a short or nested caller-supplied id (`argo-run-1` vs `argo-run-10`) addressable. The `len >= 36` shortcut becomes a special case of this step.
   - b. If `len(prefix) < MinPrefixLen`, return `ErrPrefixTooShort`. This covers the empty string.
   - c. Run `SELECT <alertColumns> FROM alerts WHERE id LIKE $1 ESCAPE '\' ORDER BY id LIMIT 2`, where `$1 = escapeLike(prefix) + "%"`. `escapeLike` (unexported) is a `strings.NewReplacer` that turns `\` into `\\`, `%` into `\%` and `_` into `\_`. Collect the rows:
     - 0 rows: `ErrNotFound`;
     - 2 rows: `ErrAmbiguousPrefix`, carrying no ids and no tenant names;
     - 1 row: load evidence and return it.

   `LIMIT 2` is the cheapest query that can tell one match from many. `ORDER BY id` makes results deterministic if this is ever logged, but it does not affect the decision.
   - The doc comment is updated to describe these semantics.

3. **One error mapper in `internal/api/handlers_alerts.go`**: add `writeIncidentLookupError(w, id, err)`. It maps:
   - `ErrPrefixTooShort` to `400 "incident id prefix must be at least 8 characters"`;
   - `ErrNotFound` to `404 "incident not found: "+id`;
   - `ErrAmbiguousPrefix` to `409 "incident id prefix is ambiguous; use a longer prefix or the full id"`;
   - anything else to `500 "failed to look up incident"`, with an `slog.Error` that includes the error.

   All four handlers replace their inline `writeError(w, 404, ...)` with this helper. Because the lookup comes before `requireTenantRole` and `Update`, a failed lookup leaves the incident unchanged.

4. **MCP descriptions** (`internal/mcp/server.go`): update the `id` parameter description on the get, ack and resolve tools to "Incident ID (full ID, or a unique prefix of at least 8 characters; an ambiguous prefix is rejected)". The tool count does not change, so the `server_test.go` count is untouched. The handlers already surface the REST error text.

## Alternatives
- **Restrict the input to the UUID alphabet** (`[0-9a-f-]`) instead of escaping. Dropped because ids are free-form and caller-supplied (`argo-run-1`, which contains other letters), so valid ids would be rejected. Escaping is alphabet-agnostic.
- **Keep `len >= 36` as the only exact path and apply the minimum and ambiguity rules to everything else.** Dropped because a non-UUID id that is a prefix of another (`argo-run-1` / `argo-run-10`), or is shorter than 8 characters, would become impossible to address.
- **Use `strings.HasPrefix` matching in Go after `List`, or `left(id, n) = $1`.** `left()` avoids LIKE escaping but cannot use the primary-key btree for a prefix scan. Listing in Go loads the whole table. Escaped `LIKE ... ESCAPE` with `LIMIT 2` is simpler and bounded.
- **Tenant-scoped matching** (count only incidents the caller may see). It closes the cross-tenant existence signal, but it needs `GetByPrefix` to take the caller's tenants, and admins see everything anyway. Deferred (see Open questions).

## Platform impact
- **Migrations:** none. The query shape changes only.
- **Backward compatibility:**
  - Previously "working" calls with ambiguous or very short prefixes now fail with 409 or 400. That is the intended behaviour change.
  - Full ids and unique prefixes of 8 or more characters behave as before.
  - Clients that matched on 404 for every failure now see 400, 409 or 500 for the non-not-found cases. mctl-telegram and other API consumers that pass 8-character prefixes keep working as long as the prefix is unique.
- **Resources:** an extra exact-match query on the prefix path, which is a primary-key lookup. `LIMIT 2` is negligible.
- **Risks:**
  - (a) Telegram notifications that show 8-character prefixes may become ambiguous for colliding ids. Mitigation: the 409 message tells the user to use a longer prefix.
  - (b) Store errors were previously hidden as 404 and now surface as 500. That is more truthful, and the error is logged.
  - (c) A 409 reveals that a same-prefix incident exists in another tenant. This is low-sensitivity, and it is documented.
