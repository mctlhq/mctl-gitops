# Render frozen product-update digests and prepare broadcasts from them by source_ref

## Context

Issue #683 is the follow-up to #440, slice 2. Reading the clone shows that the
persistence half of #683 has **already landed**: `product_update_digests`,
`product_update_publications` and `product_update_entry_owners` exist in both
dialect schemas (`internal/db/db.go`, sqlite block around the
`CREATE TABLE IF NOT EXISTS product_update_digests` statement and the mirrored
`pgSchema()` block); `broadcast_campaigns` already carries
`source_digest_id`, `source_digest_version` and `source_content_hash`;
`db.SaveProductUpdateDigest`, `db.GetProductUpdateDigest`,
`db.PublishedProductUpdateEntries` and `db.SetBroadcastCampaignSourceRef`
exist in `internal/db/product_updates.go`; and
`productupdate.PersistDigest` / `productupdate.FreezeNextDigest` exist in
`internal/productupdate/store.go`. What is missing is everything that turns
those parts into a flow a human can actually run.

Concretely, four gaps remain. (1) Nothing renders a frozen digest into text:
`broadcast.Service.Prepare` (`internal/broadcast/service.go`) takes a
`PrepareRequest{Selector, Text}` and there is no code anywhere that produces
that `Text` from a `productupdate.Digest`. (2) Nothing calls
`FreezeNextDigest` — it has no non-test caller, and neither does
`SetBroadcastCampaignSourceRef`, so no campaign in production can carry a
`source_ref`. (3) The server process cannot even read the feed:
`productupdate.LoadFeed` reads `docs/product-updates` from the filesystem, and
the runtime stage of the `Dockerfile` copies only the three binaries, never
`docs/`. (4) The feed is not rendered for docs or web — `/docs`
(`internal/web/docs.go`) is a static embedded page. This proposal closes those
four gaps and re-verifies the release gate and the operator daily digest.

## User stories

- **WITHDRAWN (owner decision 2026-09-30): do not implement. See "Correction 2026-09-30" at the end of this file.** AS a broadcast operator I WANT one MCP tool that freezes the next weekly
  digest for a category and returns a broadcast preview SO THAT I can review
  and approve one deduplicated message instead of hand-copying entry text.
- AS a broadcast operator approving on the broadcast page I WANT to see which
  frozen digest (id, version, content hash) a campaign was prepared from SO
  THAT I approve the reviewed text and not something edited after preview.
- AS a release manager I WANT an entry to be carried by at most one digest
  across releases and channels SO THAT clients are never told the same thing
  twice.
- AS a reader of the docs or the website I WANT the approved product-update
  feed rendered as a page SO THAT the same reviewed text serves docs, web and
  Telegram.
- AS a maintainer I WANT the release gate (`go run ./cmd/productupdates gate`
  in `.github/workflows/build.yml`) and the operator daily digest
  (`internal/digest`) to be untouched by this change SO THAT existing flows
  keep working.

## Acceptance criteria (EARS)

### Loading the feed at runtime

- WHEN the server starts THE SYSTEM SHALL load the product-update feed from
  the directory named by `PRODUCT_UPDATE_FEED_DIR` (default
  `productupdate.FeedDir`, i.e. `docs/product-updates`) exactly once, and hold
  the parsed `productupdate.Feed` for the process lifetime.
- IF the feed directory is absent or any entry fails
  `productupdate.LoadFeed` validation THEN THE SYSTEM SHALL log the problem at
  startup, leave the rest of the server fully functional, and refuse every
  digest-freeze request with that error rather than freezing a partial feed.
- WHILE the server is running THE SYSTEM SHALL never re-read the feed from
  disk, so two freezes of the same digest id in one process see identical
  content.
- WHEN the container image is built THE SYSTEM SHALL ship `docs/product-updates`
  into the runtime stage at the path `PRODUCT_UPDATE_FEED_DIR` points to, so
  the feed the image carries is exactly the feed that release reviewed.

### Determining the latest release

- WHEN a freeze needs `latestRelease` THE SYSTEM SHALL use the binary's own
  build version (`main.version`, set from `APP_VERSION` via `-ldflags` in the
  `Dockerfile`) when it satisfies `productupdate.ValidRelease`.
- IF the build version is not a `MAJOR.MINOR.PATCH` release (for example the
  `dev` default) THEN THE SYSTEM SHALL refuse the freeze with an error saying
  the running build cannot tell which release has shipped, and SHALL NOT fall
  back to an empty baseline.

### Rendering a frozen digest

- WHEN asked to render a frozen `productupdate.Digest` for broadcast THE
  SYSTEM SHALL recompute each entry's content hash from the in-memory feed and
  refuse unless the recomputed `SourceRefs` are byte-identical to the digest's
  `SourceRefs`.
- WHILE rendering THE SYSTEM SHALL emit entries in the digest's `SourceRefs`
  order, in English only, using each entry's reviewed `Title` and `Summary`
  verbatim, never paraphrased or model-generated.
- WHEN the full rendering (title plus summary per entry) fits the broadcast
  text limit enforced by `broadcast.NormalizeText` THE SYSTEM SHALL use it;
  otherwise THE SYSTEM SHALL use the compact rendering (titles only plus one
  link to the docs product-updates page).
- IF even the compact rendering exceeds the limit THEN THE SYSTEM SHALL refuse
  the freeze-and-prepare, naming the entry count, and SHALL NOT truncate or
  reword reviewed text.
- WHEN the same frozen digest is rendered twice THE SYSTEM SHALL produce
  byte-identical text.

### Freezing and preparing, operator present

- **WITHDRAWN (owner decision 2026-09-30): do not implement. See "Correction 2026-09-30" at the end of this file.** The page action replaces it. WHEN a broadcast operator calls the new `prepare_product_update_digest` MCP
  tool with a `category`, a `digest_id` and a `version` THE SYSTEM SHALL
  freeze and persist the digest with `productupdate.FreezeNextDigest`, render
  it, and call `broadcast.Service.Prepare` with the selector category set to
  the digest's category and the campaign's `source_ref` set to
  `(digest_id, version, content_hash)`.
- WHILE a campaign is being prepared from a digest THE SYSTEM SHALL write the
  campaign row and its `source_ref` in a single insert, so no prepared
  campaign can exist with a digest-derived body and no `source_ref`.
- IF the caller supplies a `text` or a `category` that differs from the
  digest's category THEN THE SYSTEM SHALL refuse: a digest campaign's body and
  category come from the digest, never from the caller.
- IF the caller lacks the `admin:broadcast` scope or is not in
  `BroadcastOperators` THEN THE SYSTEM SHALL refuse exactly as
  `prepare_broadcast` does today.
- IF a campaign for the same category is already in the `prepared` or
  `approved` state and has not completed or been cancelled THEN THE SYSTEM
  SHALL refuse, because the owner decision on #440 is one campaign per
  category.
- WHEN the identical `(digest_id, version)` is frozen again after a lost
  response THE SYSTEM SHALL store nothing new, return the same content hash,
  and report that the digest was not newly written.
- IF `version` is greater than 1 and no stored digest exists for
  `(digest_id, version-1)` THEN THE SYSTEM SHALL refuse, so a version number
  cannot be invented.
- WHILE freezing THE SYSTEM SHALL run only in response to an operator request
  and SHALL NOT be scheduled on any timer, because `Prepare` opens a
  30-minute approval window (`broadcast.DefaultApprovalTTL`).

### Immutability of the hand-off

- WHILE a campaign has a `source_ref` THE SYSTEM SHALL refuse any attempt to
  set a different one (`db.ErrCampaignSourceRefSet`) and SHALL refuse a ref
  whose content hash or category does not match the stored digest
  (`db.ErrCampaignSourceMismatch`).
- IF a frozen digest is saved again under the same `(id, version)` with
  different content THEN THE SYSTEM SHALL refuse with
  `db.ErrDigestConflict` and write nothing.
- IF an entry already carried by another digest id would be carried again
  THEN THE SYSTEM SHALL refuse with `db.ErrDigestEntryPublished`.

### Showing the source to the approver

- WHEN the broadcast page lists campaigns THE SYSTEM SHALL show, for each
  campaign with a `source_ref`, the digest id, version and content hash next
  to the text the operator is approving.
- WHEN `list_broadcasts` or `get_broadcast` returns a campaign THE SYSTEM
  SHALL include its `source_ref`, or null for a manual campaign.

### Rendering the feed for docs and web

- WHEN a reader requests `/docs/product-updates` THE SYSTEM SHALL render every
  feed entry with `status: approved` and `locale: en`, including
  `docs_only` entries, grouped by `evidence.from` with the newest release
  first.
- WHILE rendering for docs and web THE SYSTEM SHALL show the entry's reviewed
  title, summary, kind, tools and evidence links, and SHALL NOT show
  `provenance` fields (author, reviewer, assisting model).
- IF the feed failed to load at startup THEN THE SYSTEM SHALL serve the page
  with an explanatory notice rather than a 500, and SHALL NOT serve stale or
  partial entries.

### Existing flows

- WHILE this change is deployed THE SYSTEM SHALL keep
  `go run ./cmd/productupdates gate` behaving exactly as before, with no new
  required input and no change to its exit codes.
- WHILE this change is deployed THE SYSTEM SHALL leave
  `digest.StartDailyDigest` (the operator daily new-client summary) untouched:
  it is a different digest and shares no code with product updates.

## Out of scope

- Localisation. `productupdate.SupportedLocales` is `["en"]` and v1 is English
  only (owner decision on #440).
- Any automatic or scheduled freezing, sending or approving. Approval stays a
  human action on the broadcast page; no tool can approve.
- Enforcing reviewer != author. The owner decided not to enforce it.
- New notification categories, consent changes, or changes to
  `internal/broadcast/policy.go` eligibility rules.
- Changing the delivery worker (`internal/broadcast/worker.go`) or the
  `broadcast_deliveries` schema.
- Immediate (non-digest) single-entry campaigns. Those keep using
  `prepare_broadcast` with operator-written text and no `source_ref`.
- A docs-site generator. The docs rendering is a page served by
  `internal/web`, consistent with `/docs` and `/docs/local-bridge` today.
- Deleting `db.SetBroadcastCampaignSourceRef`. It is kept as the only way to
  attribute a campaign prepared by an older binary.

## Open questions

- **Digest id convention.** The issue does not say how a digest id is chosen.
  Proceeding with an operator-supplied id validated by the existing
  `idPattern`, and recommending `<category>-<YYYY>-w<WW>` in the feed README.
- **Oversized digest policy.** The issue does not say what happens when a
  week's approved entries exceed the 4096 UTF-16 unit broadcast limit.
  Proceeding with full-then-compact-then-refuse as specified above; the
  operator's remedy is to mark surplus entries `docs_only` in a follow-up pull
  request.
- **Docs page scope.** Whether the docs page should list only entries a digest
  actually carried, or every approved entry. Proceeding with every approved
  entry, because docs is not a consent domain and `docs_only` entries exist
  precisely to be rendered and never sent.
- **Feed delivery into the image.** Copying `docs/product-updates` into the
  runtime stage is proposed over `go:embed` because `go:embed` cannot reach
  outside its package — `internal/web/localbridge.go` says exactly this and
  works around it by duplicating files, which would rot for a growing feed.
  A reviewer may prefer a generated embed instead; see design.md.
- **`version` bump semantics.** `FreezeNextDigest`'s doc comment warns that
  version N+1 of the same id also picks up entries approved since, and that
  reusing an already-sent id reopens its entries. The refusal on a missing
  `version-1` is this proposal's guard; whether a correction must be limited
  to the earlier entry set is left to the operator, as that comment already
  states.

## Correction 2026-09-30 (owner decision): the operator entry point is the broadcasts page, not an MCP tool

The owner decided on #683 (issue comment, 2026-09-30) that v1 of the digest to
broadcast handoff goes through the **existing broadcasts page**, and that **no
new MCP mutation tool** is added. The user story and every criterion above that
names `prepare_product_update_digest` are replaced by the following. Everything
else in this document stands: feed loading, `latestRelease`, rendering, the
single-insert `source_ref`, one campaign per category, English only, the docs
page, and the untouched release gate and daily digest.

- AS a broadcast operator on `/telegram/connect/broadcasts` I WANT a "Prepare
  from digest" action that freezes the next digest for a category and prepares
  its campaign SO THAT I review and then approve one deduplicated message on
  the same page, without hand-copying entry text.
- WHEN an operator submits the page's prepare-from-digest form (`category`,
  `digest_id`, `version`, and the optional audience narrowing the page already
  offers) THE SYSTEM SHALL freeze and persist the digest with
  `productupdate.FreezeNextDigest`, render it, and call
  `broadcast.Service.Prepare` with the selector category taken from the digest
  and `source_ref` set to `(digest_id, version, content_hash)`, in the single
  insert described above.
- WHILE handling that form THE SYSTEM SHALL apply exactly the guards the page
  already applies to its approve and cancel actions: `admin:broadcast` scope,
  `IsOperator`, and a same-origin POST. A caller that fails any of them is
  refused as those actions refuse today.
- IF the form carries a `text` field, or a `category` that differs from the
  digest's category, THEN THE SYSTEM SHALL refuse. A digest campaign's body and
  category come from the digest.
- WHEN the action succeeds THE SYSTEM SHALL show the prepared campaign on the
  same page with its digest id, version and content hash. Preparing never
  approves: approval stays a separate, explicit action on the page.
- THE SYSTEM SHALL NOT add any MCP tool that freezes, prepares, approves or
  sends a digest campaign. The read-only `list_broadcasts` and `get_broadcast`
  may expose `source_ref`, since they mutate nothing.
- No timer, schedule or background job freezes a digest or calls `Prepare`.
  The action runs only on an operator's request, because `Prepare` opens the
  30-minute approval window.
