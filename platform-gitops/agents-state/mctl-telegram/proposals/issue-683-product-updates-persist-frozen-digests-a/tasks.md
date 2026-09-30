# Tasks: issue-683-product-updates-persist-frozen-digests-a

No database migration is needed: `product_update_digests`,
`product_update_publications`, `product_update_entry_owners` and
`broadcast_campaigns.source_digest_*` already exist in `internal/db/db.go`
(sqlite `sqliteSchema()`, postgres `pgSchema()`, and the `addColumnIfMissing`
pass at :435-447). The work is wiring, rendering and two surfaces.

- [ ] 1. Add `ProductUpdateFeedDir` to `internal/config/config.go` — read
  `PRODUCT_UPDATE_FEED_DIR` with the existing `os.Getenv` pattern, defaulting
  to `productupdate.FeedDir` (`docs/product-updates`).
  DoD: `go test ./internal/config/...` passes with a case asserting the
  default and the override; no other config field changes.

- [ ] 2. Ship the feed into the runtime image (depends on 1) — add
  `COPY --from=builder /app/docs/product-updates /srv/product-updates` to the
  runtime stage of `Dockerfile` and set `PRODUCT_UPDATE_FEED_DIR=/srv/product-updates`
  in the `deploy/` values.
  DoD: `docker build` succeeds and `docker run --rm --entrypoint ls <image>
  /srv/product-updates` lists the committed `*.yaml` files.

- [ ] 3. Load the feed once at server start (depends on 1) — in
  `cmd/server/main.go`, call `productupdate.LoadFeed(cfg.ProductUpdateFeedDir)`
  and hold `Feed`, `LatestRelease` and `Err` in a small struct.
  `LatestRelease` is the package-level `version` var (`cmd/server/main.go:57`)
  when `productupdate.ValidRelease(version)` holds, else `""`.
  DoD: a load failure logs once at startup and boots the server unchanged
  (a test asserts `/healthz` still returns 200 with the directory missing);
  the feed is read exactly once per process.

- [ ] 4. Write `internal/productupdate/render.go` (independent of 1-3) —
  `RenderBroadcast(d Digest, feed Feed, docsURL string, limit int) (string, error)`
  and `RenderDocs(feed Feed) []ReleaseGroup`. `RenderBroadcast` re-derives
  each entry's content hash with the same `entryContent`/`hashJSON` helpers
  `FreezeDigest` uses (`internal/productupdate/digest.go:73-95`) and refuses
  unless the rebuilt refs equal `d.SourceRefs` byte for byte. Full form
  (title + summary per entry) when it fits `limit` UTF-16 units, else compact
  (titles only), else an error naming the entry count. `RenderDocs` keeps
  approved, `locale: en` entries, groups by `Evidence.From`, newest release
  first (reuse `parseRelease`, `gate.go:261`), and omits `Provenance`.
  DoD: `go test ./internal/productupdate/...` passes; the package still
  imports nothing from `internal/broadcast`.

- [ ] 5. Carry the source ref through `Prepare` atomically (depends on 4) —
  add `SourceRef *db.CampaignSourceRef` to `broadcast.PrepareRequest`
  (`internal/broadcast/service.go:108-111`), pass it into the
  `db.BroadcastCampaign` literal at `service.go:214`, and widen
  `db.CreateBroadcastCampaign` (`internal/db/broadcast.go:248`) to write
  `source_digest_id`, `source_digest_version`, `source_content_hash` in the
  same INSERT, guarded by the same `EXISTS (... d.id, d.version,
  d.content_hash, d.category = category)` predicate
  `SetBroadcastCampaignSourceRef` uses. Zero rows with a source ref present
  returns `db.ErrCampaignSourceMismatch`.
  DoD: `prepare_broadcast` with no source ref behaves byte-identically to
  today; `broadcast.Store` (service.go:66-72) needs no new method;
  `SetBroadcastCampaignSourceRef` is left in place and still passes its tests.

- [ ] 6. Add the operator MCP tool (depends on 3, 4, 5) — new
  `internal/mcp/productupdate_tools.go` with
  `toolPrepareProductUpdateDigest`, registered in the builder loop at
  `internal/mcp/server.go:456-461`. Inputs `category`, `digest_id`,
  `version`, plus optional `tiers` / `connected_via` / `active_within_days`;
  deliberately **no `text`**. Keep the literal
  `requireScope(id, "admin:broadcast")` call inline (the
  `portal_allowlist_test.go` derivation reads it statically) and call
  `s.broadcastActor(id)` for the live operator re-check. Order: feed loaded
  and `LatestRelease` known → no non-terminal campaign for this category
  (`ListBroadcastCampaigns` over `prepared`, `approved`, `sending`) →
  `version > 1` requires `GetProductUpdateDigest(id, version-1)` to exist →
  `FreezeNextDigest` → `RenderBroadcast` → `Prepare` with
  `Selector.Category` taken from the digest and `SourceRef` set.
  DoD: result embeds `prepareBroadcastResult` plus `digest_id`,
  `digest_version`, `content_hash`, `entry_ids`, `newly_frozen`; audited via
  `s.audit` like its neighbours; sends nothing and offers no approval path.

- [ ] 7. Regenerate `docs/portal-allowlist.json` (depends on 6) — the file is
  derived from the registered tool set by
  `internal/mcp/portal_allowlist_test.go`; the new tool must appear against
  `admin:broadcast` alongside the four broadcast tools.
  DoD: `go test ./internal/mcp/ -run PortalAllowlist` passes with no diff.

- [ ] 8. Regenerate `docs/tool-descriptors.json` and add the feed entry for
  this change (depends on 6) — adding an MCP tool changes the tool surface,
  so `go run ./cmd/productupdates gate` (`.github/workflows/build.yml:187`)
  will fail until this same pull request carries an **approved**
  `docs/product-updates/<id>.yaml` whose `evidence.from` is the current
  baseline and which claims `{tool: prepare_product_update_digest, change:
  added}`. Set `delivery: next_digest`, `kind: new_tool`, `locale: en`, a
  named human in `provenance.reviewed_by`, and `provenance.assisted_by` if a
  model helped with the wording.
  DoD: `go run ./cmd/productupdates validate` and `... gate` both exit 0 on
  the branch with full history and tags.

- [ ] 9. Show the source ref to the approver (depends on 5) — carry
  `SourceRef` into `broadcastRow` via `toRow`
  (`internal/web/broadcasts.go:185`) and render `digest-id vN sha256:abcd...`
  beside the campaign text in `broadcastTemplate` (:265-303); add the same
  field to `broadcastSummary` via `summarize`
  (`internal/mcp/broadcast_tools.go:106`) so `list_broadcasts` and
  `get_broadcast` expose it.
  DoD: a campaign with no source ref renders and serialises as before (null /
  omitted), not as an empty digest.

- [ ] 10. Add the docs/web page (depends on 3, 4) — new
  `internal/web/productupdates.go` with
  `ProductUpdates(groups []productupdate.ReleaseGroup, loadErr error,
  publicBaseURL string, showManage bool) http.HandlerFunc`, an embedded
  `productupdates.html` rendered through `ui.New` + `chromePage` (same shape
  as `internal/web/docs.go`), mounted at `/docs/product-updates` in
  `cmd/server/main.go` next to the other docs routes (:416-419). Pass
  `publicBaseURL + "/docs/product-updates"` as `docsURL` to
  `RenderBroadcast` in task 6.
  DoD: the page never shows `provenance` fields; with `loadErr != nil` it
  renders a notice and no entries rather than a 500.

- [ ] 11. Document the flow (depends on 6, 10) — extend
  `docs/product-updates/README.md` with the operator steps (freeze and
  prepare via `prepare_product_update_digest`, approve on
  `/telegram/connect/broadcasts`), the recommended digest id convention
  `<category>-<YYYY>-w<WW>`, and the version-bump warning already in
  `FreezeNextDigest`'s doc comment (`internal/productupdate/store.go:66-73`).
  DoD: `go test ./docs/...` passes; no secret, phone number or real Telegram
  identifier appears.

## Tests

- [ ] T1. `RenderBroadcast` refuses a digest whose entry text changed after
  freezing (rebuilt source refs differ) and refuses an entry missing from the
  feed.
- [ ] T2. `RenderBroadcast` is deterministic: the same frozen digest renders
  byte-identically twice, and entries appear in `SourceRefs` order.
- [ ] T3. `RenderBroadcast` picks the full form under the limit, the compact
  form over it, and errors when even compact overflows — the error names the
  entry count and no reviewed text is truncated.
- [ ] T4. `CreateBroadcastCampaign` with a source ref writes all three columns
  in one insert; with a ref naming a nonexistent digest, a wrong content hash,
  or a category that differs from the campaign's, it writes nothing and
  returns `ErrCampaignSourceMismatch`. Run against both SQLite and Postgres,
  matching `internal/db/product_updates_test.go`.
- [ ] T5. `prepare_product_update_digest` end to end on a seeded feed: freezes,
  persists, prepares, and the resulting campaign read back through
  `GetBroadcastCampaign` carries the expected `SourceRef`.
- [ ] T6. Called twice with the same `(digest_id, version)`, the second call
  reports `newly_frozen: false`, stores no new digest row, and is refused by
  the one-campaign-per-category guard while the first campaign is still
  `prepared`.
- [ ] T7. Dedupe across digests: an entry carried by `digest-a` is not offered
  to `digest-b` (`PublishedProductUpdateEntries` / `DigestCandidates`), and
  saving `digest-b` with it anyway returns `ErrDigestEntryPublished`.
- [ ] T8. Refusals: caller without `admin:broadcast`; caller with the scope but
  not in `BroadcastOperators`; a `category` that disagrees with the digest's;
  a supplied `text`; `version: 2` with no stored version 1; an empty
  `LatestRelease` (a `dev` build); a feed that failed to load.
- [ ] T9. Consent safety: a `product_updates` digest always prepares with
  selector category `product_updates`, never `maintenance` or `security`, and
  `FreezeDigest` still refuses a mixed-category entry set.
- [ ] T10. Web: the broadcast page shows the digest id, version and content
  hash for a sourced campaign and shows nothing extra for a manual one;
  approval still requires `oauth.ConnectClientID`, the operator check and a
  same-origin POST.
- [ ] T11. Docs page: lists approved `en` entries including `docs_only`,
  groups by release newest first, omits `provenance`, and renders a notice
  (not a 500) when the feed failed to load.
- [ ] T12. Regression: `go run ./cmd/productupdates validate` and `gate` are
  unchanged in behaviour and exit codes; `internal/digest` tests
  (`run_digest_test.go`, `reachability_test.go`) still pass untouched;
  `prepare_broadcast` with no source ref produces a campaign with a NULL
  `source_ref`.
- [ ] T13. Boot: the server starts, serves `/healthz`, and serves every
  existing route when `PRODUCT_UPDATE_FEED_DIR` points at a missing or
  invalid directory.

## Rollback

Nothing here is destructive and there is no schema change to undo, so
rollback is a redeploy of the previous image tag. Specifically:

1. **Immediate.** Revert the merge commit and redeploy. The three
   product-update tables and the three `broadcast_campaigns.source_*` columns
   stay — they predate this change and the old binary simply never writes or
   reads them (`CreateBroadcastCampaign` leaves them NULL, `scanCampaign`
   tolerates NULL). Never drop them: `product_update_entry_owners` is the
   dedupe record, and dropping it would let already-sent entries be sent
   again.
2. **In-flight campaigns.** A campaign prepared from a digest and not yet
   approved simply expires after `DefaultApprovalTTL` (30 minutes) via
   `ExpireBroadcastCampaigns`, or can be cancelled with the existing
   `cancel_broadcast` tool or the page's cancel button. An already-approved
   campaign keeps delivering under the unchanged worker; its stored
   `source_ref` becomes inert data.
3. **Stored digests.** A digest frozen before the rollback keeps its entries
   marked published, so those entries stay out of future digests. That is the
   correct behaviour if the broadcast went out. If it did **not** go out and
   the entries must be re-offered, delete the rows for that digest id from
   `product_update_entry_owners`, then `product_update_publications`, then
   `product_update_digests`, in that order, in one transaction — an operator
   action, deliberately not automated.
4. **Partial rollback.** Task 10 (the docs page) and task 9 (showing the
   source ref) are independent of the freeze path and can be reverted alone.
   Reverting task 2 (the `COPY` line) alone disables freezing while leaving
   the rest of the server healthy, which is the safest kill switch if the
   feed itself turns out to be the problem.
