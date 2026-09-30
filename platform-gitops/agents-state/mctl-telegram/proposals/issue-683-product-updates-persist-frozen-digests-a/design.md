# Design: issue-683-product-updates-persist-frozen-digests-a

## Current state

### The persistence half of #683 is already merged

Reading the clone (HEAD `4ed00d2`) shows the issue body is partly stale. What
it lists as "missing" exists:

- **Tables.** `internal/db/db.go` declares `product_update_digests`
  (sqlite :823-832, postgres :1093-1102), `product_update_publications`
  (:837-843 / :1103-1109, plus index `idx_product_update_publications_entry`
  :844 / :1110) and `product_update_entry_owners` (:851-854 / :1111-1114).
  The last table's `entry_id TEXT NOT NULL PRIMARY KEY` is what holds
  "one entry, at most one digest id" in the database itself.
- **Campaign source field.** `broadcast_campaigns` carries
  `source_digest_id`, `source_digest_version`, `source_content_hash`
  (sqlite :784-786, postgres :1065-1067) and the additive migration for
  existing databases is `internal/db/db.go:435-447`.
- **Store methods.** `internal/db/product_updates.go` has
  `SaveProductUpdateDigest` (:97), `GetProductUpdateDigest` (:218),
  `PublishedProductUpdateEntries` (:271) and
  `SetBroadcastCampaignSourceRef` (:303), with
  `ErrDigestNotFound`/`ErrDigestConflict`/`ErrDigestEntryPublished`/
  `ErrCampaignSourceRefSet`/`ErrCampaignSourceMismatch` (:30-40) and
  `CampaignSourceRef` (:58-62).
- **Domain layer.** `internal/productupdate/digest.go` has
  `DigestCandidates` (:22) and `FreezeDigest` (:101);
  `internal/productupdate/store.go` has `PersistDigest` (:45) and
  `FreezeNextDigest` (:74).
- **Read-back.** `internal/db/broadcast.go` `campaignColumns` (:268-271)
  selects the three source columns and `scanCampaign` (:277-316) rebuilds
  `BroadcastCampaign.SourceRef` at :292-294.

### What is genuinely missing

1. **No production caller.** `FreezeNextDigest`, `PersistDigest` and
   `SetBroadcastCampaignSourceRef` have zero non-test callers. The only
   production importers of `internal/productupdate` are
   `internal/mcp/descriptors.go` (snapshots only), `cmd/productupdates`
   (the CI gate) and `cmd/tooldiff`.
2. **No renderer.** Nothing turns a `productupdate.Digest` into text.
   `broadcast.Service.Prepare` (`internal/broadcast/service.go:162`) takes
   `PrepareRequest{Selector, Text}` (:108-111) — a caller-supplied body.
3. **The hand-off is not wired and not atomic.** `Prepare` builds a
   `db.BroadcastCampaign` literal (service.go:214-226) that omits
   `SourceRef`, and `CreateBroadcastCampaign` (`internal/db/broadcast.go:248`)
   does not write the `source_digest_*` columns at all. The
   `broadcast.Store` interface (service.go:66-72) does not even expose
   `SetBroadcastCampaignSourceRef`.
4. **The server cannot read the feed.** `productupdate.LoadFeed`
   (`internal/productupdate/feed.go:407`) reads `docs/product-updates` off
   disk, but the runtime stage of `Dockerfile` copies only
   `/mctl-telegram`, `/mctl-telegram-login` and `/mctl-telegram-canary`
   (Dockerfile:29-31). `docs/` is not in the image.
5. **No `latestRelease` at runtime.** `FreezeNextDigest` needs it;
   `cmd/productupdates/main.go` derives it from `git tag --list` plus
   `productupdate.LatestRelease`, which the server has no access to.
6. **No docs/web rendering.** `/docs` (`internal/web/docs.go`) is a single
   embedded static page; `/docs/local-bridge` is embedded markdown
   (`internal/web/localbridge.go`). Nothing renders the feed.
7. **The approver cannot see the source.** `internal/web/broadcasts.go`
   `toRow` (:185) and `internal/mcp/broadcast_tools.go` `summarize` (:106)
   both drop `SourceRef`, so the human approving at
   `/telegram/connect/broadcasts` sees text with no provenance.

### Conventions the change must follow

- **Migrations are declared three times**: the SQLite `CREATE TABLE` in
  `sqliteSchema()` (`internal/db/db.go:584`), the Postgres one in
  `pgSchema()` (:858), and an `addColumnIfMissing` call (:555) inside
  `Migrate` for existing databases. There is no versioned migration table.
- MCP tools are `func (s *Server) toolX() (mcplib.Tool, mcpserver.ToolHandlerFunc)`
  registered in the list at `internal/mcp/server.go:457`, with scope checks
  via `requireScope(id, "admin:broadcast")` and audit via `s.audit(...)`.
- Web pages are `ui.New(name, html)` templates served through `chromePage`.
- `go fmt`, `go vet`, `golangci-lint`; wrapped errors, no panics; no emoji;
  no logging of message bodies.

## Proposed solution

Five changes, in dependency order.

### 1. Get the feed and the release into the server process

Add to `internal/config/config.go`:

```go
ProductUpdateFeedDir string // PRODUCT_UPDATE_FEED_DIR, default productupdate.FeedDir
```

read with the existing `os.Getenv` pattern alongside `BroadcastApprovalTTL`
(config.go:394).

Add to `Dockerfile` runtime stage, next to the binary copies:

```
COPY --from=builder /app/docs/product-updates /srv/product-updates
```

and set `PRODUCT_UPDATE_FEED_DIR=/srv/product-updates` in the deployment
values (`deploy/`). Local dev and tests keep the `docs/product-updates`
default and need no change.

In `cmd/server/main.go`, after config load, call `productupdate.LoadFeed(cfg.ProductUpdateFeedDir)`
**once** and keep the result. Because `LoadFeed` returns a partial feed with
an error, store both:

```go
type FeedSource struct {
    Feed          productupdate.Feed
    LatestRelease string
    Err           error
}
```

`LatestRelease` is `version` (the `main.version` var, `cmd/server/main.go:57`,
set by `-ldflags "-X main.version=${APP_VERSION}"`, Dockerfile:12) when
`productupdate.ValidRelease(version)` holds, and `""` otherwise. A release
image knows exactly which release it is; a `dev` build honestly does not, and
`FreezeNextDigest` with an empty baseline would treat unshipped entries as
shipped (`Entry.Shipped`, feed.go:358), so the freeze path refuses instead.
`FeedSource.Err` being non-nil, or `LatestRelease` being empty, makes every
freeze refuse with that reason; nothing else in the server depends on it, so
boot is never blocked.

### 2. Render, in `internal/productupdate/render.go`

```go
// RenderBroadcast returns the Telegram body for a frozen digest, built from
// the entries the digest names. It refuses unless the entries reproduce the
// digest's SourceRefs exactly.
func RenderBroadcast(d Digest, feed Feed, docsURL string, limit int) (string, error)

// RenderDocs returns the approved, English feed as an ordered view for the
// docs and web page.
func RenderDocs(feed Feed) []ReleaseGroup
```

`RenderBroadcast` is the crux. It resolves each of `d.SourceRefs` (already
parseable by `Digest.EntryIDs`, store.go:27) to a feed entry, recomputes
`entryContent(e)` and its hash with the *same* unexported helpers
`FreezeDigest` uses (digest.go:73-95), and refuses unless the recomputed
`"<FeedDir>/<id>.yaml@content-sha256:<hex>"` list equals `d.SourceRefs` byte
for byte. That is what makes the text provably the reviewed text rather than
whatever the feed says now — and it is why the renderer lives in
`productupdate`, beside the hashing, and not in `broadcast`.

Two forms, both deterministic from the digest:

- **Full**: a heading naming the category and release, then per entry
  `Title` on one line and `Summary` under it, entries in `SourceRefs` order,
  then one link to `docsURL`.
- **Compact**: the same heading, then `Title` lines only, then the link.

Pick full when its UTF-16 length is within `limit`, else compact, else return
an error naming the entry count. `limit` is passed in by the caller from the
broadcast package's own constant so `productupdate` does not import
`broadcast`. Text is English only (`SupportedLocales` is `["en"]`); titles and
summaries are copied verbatim, never reworded.

`RenderDocs` groups approved, `locale: en` entries by `Evidence.From`, newest
release first (reusing `parseRelease`, gate.go:261), and omits `Provenance`
entirely.

### 3. Make the hand-off atomic

Extend `broadcast.PrepareRequest` (service.go:108-111):

```go
type PrepareRequest struct {
    Selector Selector
    Text     string
    // SourceRef names the frozen product-update digest this body was
    // rendered from; nil for an operator-written campaign.
    SourceRef *db.CampaignSourceRef
}
```

`Prepare` copies it into the `db.BroadcastCampaign` literal (service.go:214).
`db.CreateBroadcastCampaign` (`internal/db/broadcast.go:248`) gains the three
columns in the same INSERT, guarded by the same predicate
`SetBroadcastCampaignSourceRef` already uses — written as
`INSERT ... SELECT $1,... WHERE EXISTS (SELECT 1 FROM product_update_digests d
WHERE d.id=$n AND d.version=$n AND d.content_hash=$n AND d.category=$n)` when
a source ref is present, so a campaign is never created naming a digest that
does not exist or whose category disagrees. Zero rows affected with a source
ref present is `ErrCampaignSourceMismatch`.

One insert means there is no window in which a prepared campaign has a
digest-rendered body and a NULL `source_ref`. `SetBroadcastCampaignSourceRef`
is **kept, not deleted**: it is the only way to attribute a campaign prepared
by an older binary, it is already tested
(`internal/db/product_updates_test.go`), and its `source_digest_id IS NULL`
guard means it can never contradict an atomic write.

### 4. The operator entry point

New `internal/mcp/productupdate_tools.go`, tool
`prepare_product_update_digest`, registered in the list at
`internal/mcp/server.go:457`, reached through the same
`WithBroadcast`-gated surface as `prepare_broadcast`:

- Inputs: `category` (required), `digest_id` (required), `version`
  (required, integer), and the same optional audience narrowing as
  `prepare_broadcast` (`tiers`, `connected_via`, `active_within_days`).
  Deliberately **no `text`** — the body comes from the digest.
- Guards, in order: `requireScope(id, "admin:broadcast")`;
  `s.broadcastActor(id)` (which re-checks `IsOperator`); feed loaded and
  `LatestRelease` known; no non-terminal campaign already exists for this
  category (via `ListBroadcastCampaigns(ctx, limit, db.CampaignPrepared,
  db.CampaignApproved, db.CampaignSending)`) — the "one campaign per
  category" owner decision; and, when `version > 1`,
  `GetProductUpdateDigest(ctx, digest_id, version-1)` must not return
  `ErrDigestNotFound`.
- Then: `productupdate.FreezeNextDigest(...)` →
  `productupdate.RenderBroadcast(...)` →
  `s.Broadcast.Prepare(ctx, actor, broadcast.PrepareRequest{Selector:
  broadcast.Selector{Category: string(digest.Category), ...}, Text: body,
  SourceRef: &db.CampaignSourceRef{...}})`.
- Output: the existing `prepareBroadcastResult` plus `digest_id`,
  `digest_version`, `content_hash`, `entry_ids` and `newly_frozen bool`.
  The same "no tool can approve" note as `prepare_broadcast`
  (broadcast_tools.go:199).

Retry is safe end to end: `FreezeNextDigest` excludes the digest's own id
from the published set, so repeating after a lost response returns the same
content hash and writes nothing; the campaign gets a fresh
`bc_`-prefixed id, which the one-campaign-per-category guard then blocks
until the first is approved, cancelled or expired.

The broadcast page (`internal/web/broadcasts.go`) is the second approval and
stays exactly as it is, except that `toRow` (:185) carries `SourceRef` into
`broadcastRow` and the template renders `digest-id v2 sha256:abcd...` beside
the text. `summarize` (`internal/mcp/broadcast_tools.go:106`) gains the same
field so `list_broadcasts` and `get_broadcast` show it.

### 5. Docs and web

New `internal/web/productupdates.go`:

```go
func ProductUpdates(groups []productupdate.ReleaseGroup, loadErr error, publicBaseURL string, showManage bool) http.HandlerFunc
```

rendered with `ui.New("product-updates", productUpdatesHTML)` through
`chromePage`, mounted in `cmd/server/main.go` next to the other docs routes
(:416-419) as `mux.Get("/docs/product-updates", ...)`. It takes the groups
computed from the one loaded feed rather than embedding a second copy, so
docs, web and Telegram all read the same bytes. When `loadErr != nil` the
page renders a notice and no entries. `docsURL` passed to `RenderBroadcast`
is `PublicBaseURL + "/docs/product-updates"`.

## Alternatives

**Embed the feed with `go:embed` instead of copying it into the image.**
Dropped. `go:embed` cannot reach outside its own package —
`internal/web/localbridge.go:19` says exactly this and works around it by
duplicating six markdown files into the package. Duplicating a feed that
grows one file per release would rot immediately, and a `go:generate` step
that copies them adds a build-time failure mode with no compensating benefit
over a `COPY` line. The tradeoff accepted is that a missing `COPY` is a
runtime refusal rather than a compile error; the startup log and the freeze
refusal both name the directory, and a deploy smoke test covers it.

**Freeze from the CLI (`cmd/productupdates freeze --dsn ...`) and let the
operator tool only prepare from an already-stored digest.** Dropped. It
sidesteps the feed-in-the-image problem and gives the freeze real git tags,
but it splits one operator action across a shell with database credentials
and an MCP client, and it breaks the invariant the issue states plainly:
freezing and `Prepare` run together while an operator is present, because
`Prepare` opens a 30-minute window (`DefaultApprovalTTL`,
`internal/broadcast/service.go:18`). A digest frozen days earlier from a
different feed revision is exactly the drift the content hash exists to
prevent.

**Keep the two-step hand-off: `Prepare`, then
`SetBroadcastCampaignSourceRef`.** Dropped as the primary path. It needs no
change to `CreateBroadcastCampaign`, but a crash between the two leaves a
prepared campaign carrying digest text with a NULL `source_ref`, and its
approval-window clock is already running. The page would then show reviewed
digest text with no provenance — the precise failure the `source_ref` was
added to prevent. The function is retained for repair, not used for the
normal flow.

**Let the caller pass `text` and merely attach a `source_ref`.** Dropped.
It reintroduces the hand-copying the issue is trying to remove and makes the
content hash a decoration: the stored digest and the delivered body could
disagree with nothing to catch it. Refusing `text` on the digest tool is what
makes the hash meaningful.

## Platform impact

**Migrations.** None. Every table and column this proposal relies on is
already in `sqliteSchema()`, `pgSchema()` and the `addColumnIfMissing` pass
(`internal/db/db.go:435-447`). The only schema-adjacent change is widening
`CreateBroadcastCampaign`'s INSERT to the three existing columns, which is
purely additive and NULL for manual campaigns.

**Backward compatibility.** `PrepareRequest.SourceRef` is a new nil-able
field, so `prepare_broadcast` and every existing caller behave unchanged.
Campaigns created before this change keep `source_ref` NULL and render as
"manual" on the page and in the MCP results. `broadcast.Store` gains no new
method (the source ref rides on `CreateBroadcastCampaign`, which is already
in the interface at service.go:66-72), so no test double outside
`internal/broadcast` needs updating.

**Resource impact.** One extra directory read at boot (a handful of small
YAML files). The feed is held in memory for the process lifetime — kilobytes.
No new goroutines, no timers, no extra queries on the delivery path. Freezing
is operator-driven and rare; `SaveProductUpdateDigest`'s Postgres
`SHARE ROW EXCLUSIVE` table lock (product_updates.go:117) is held for
milliseconds, as its comment states.

**Risks and mitigations.**

- *A feed entry is edited after a digest was frozen.* `RenderBroadcast`
  recomputes the content hashes and refuses; the digest is not silently
  re-rendered from the new text.
- *Digest id reused for a version that was already sent.* `FreezeNextDigest`'s
  doc comment (store.go:66-73) warns that this reopens its entries as
  candidates. Mitigated by refusing `version > 1` without `version-1` stored,
  and by naming the issue in the tool description; the operator still owns
  what a "correction" means.
- *Image shipped without the feed directory.* Startup logs the load failure
  and every freeze refuses with it; a deploy smoke test
  (`internal/web/deploy_smoke_test.go` is the existing precedent) asserts the
  docs page lists at least one entry.
- *A digest too large for one Telegram message.* Full-then-compact-then-refuse.
  The refusal names the entry count; the operator's remedy is a pull request
  marking surplus entries `docs_only`. Recorded as an open question.
- *Two operators freeze concurrently.* `product_update_entry_owners`'
  primary key refuses the second (`ErrDigestEntryPublished`) regardless of
  whether the Postgres table lock was taken; the one-campaign-per-category
  guard refuses the second prepare.
- *Consent leakage across categories.* `FreezeDigest` already refuses a mixed
  category (digest.go:120-121), and the tool sets the selector category from
  the digest rather than from the caller, so an opt-in `product_updates`
  digest cannot be sent under `security` consent.

**Unaffected flows, to be re-verified.**
`go run ./cmd/productupdates gate` (`.github/workflows/build.yml:187`) reads
the feed from the working tree and is untouched. `digest.StartDailyDigest`
(`internal/digest/digest.go`) is the operator new-client summary and shares
no code or table with product updates. Release-please
(`.github/workflows/release-please.yml`) is untouched; the only new coupling
is that `APP_VERSION` must continue to be the release tag, which it already
is (Dockerfile:12).
