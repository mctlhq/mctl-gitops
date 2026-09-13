# Journal entry lifecycle, historical backfill and release-triggered closure

## Context

Fourteen of the twenty-two public journal entries in
`src/content/journal/` render an em dash for pull request, release and lead
time, although every one of them has a merged implementation PR and a
published release. The cause is the lifecycle, not the fourteen files: a
DevLoop cycle writes its own entry while it is still running, so `pr`,
`release`, `merged_at` and `released_at` are not yet knowable, and nothing
records them afterwards. `src/content.config.ts` makes all four fields
optional, so an entry that is never completed validates forever. Eight
entries were only completed because later cycles backfilled them by hand.

This proposal gives every entry an explicit, schema-validated lifecycle
(`in_progress` / `complete` / `abandoned`), backfills the fourteen verified
merge/release pairs and the two missing approval stamps, shows computed
public totals per status, and adds a release-triggered GitHub Actions
workflow (`.github/workflows/journal-closure.yml` plus
`scripts/close-journal.mjs`) that opens a deterministic closure PR after the
first published stable release that actually contains the implementation
merge commit. The closure PR is published through a metadata-only patch
release, so the static site — built from a release tag, not from `main` —
shows the closed entry without waiting for another DevLoop cycle.
"Complete" records release evidence; it never asserts that a deployment
succeeded.

## User stories

- AS a reader of the public colophon I WANT every shipped cycle to show its
  pull request, release and lead time SO THAT the site's own evidence is not
  contradicted by fourteen rows of em dashes.
- AS a reader I WANT the running cycle to be labelled "in progress" and an
  abandoned cycle labelled "abandoned" with a stated reason SO THAT a blank
  field reads as a known state instead of an omission.
- AS a reader I WANT the colophon to state how many public cycles are
  complete, in progress and abandoned SO THAT I can judge the loop's
  throughput from computed numbers rather than by counting rows.
- AS the repository owner I WANT the schema and the journal loader to reject
  an entry whose evidence contradicts its status, whose timestamps run
  backwards, or a collection with two open cycles SO THAT the one-cycle-at-a-
  time rule is enforced by the build instead of by memory.
- AS the release owner I WANT a closure pull request opened automatically
  after the release that contains the implementation merge commit SO THAT
  closing a cycle costs a review and a patch release, not a new DevLoop
  cycle.
- AS the release owner I WANT closure to fail visibly on ambiguity, API
  failure or conflicting evidence, and to be a no-op on duplicate deliveries
  SO THAT automation never invents or overwrites evidence.

## Acceptance criteria (EARS)

### A. Schema and collection invariants

- WHEN the journal schema in `src/content.config.ts` parses an entry THE
  SYSTEM SHALL require `status: z.enum(['in_progress', 'complete',
  'abandoned'])` on every journal file, public and private.
- THE SYSTEM SHALL accept an optional `abandoned_reason` carrying an `en`
  and a `ru` string, and IF `status` is `abandoned` THEN THE SYSTEM SHALL
  require both strings to contain non-whitespace text (a whitespace-only
  string is rejected).
- IF `status` is `complete` THEN THE SYSTEM SHALL require `pr`, `release`,
  `merged_at` and `released_at`.
- IF `status` is `in_progress` THEN THE SYSTEM SHALL permit `pr` and
  `merged_at` and SHALL forbid `release`, `released_at` and `deployed_at`.
- IF `merged_at` is present on any entry THEN THE SYSTEM SHALL require `pr`.
- IF `status` is `abandoned` THEN THE SYSTEM SHALL require
  `abandoned_reason` and SHALL forbid `merged_at`, `release`, `released_at`
  and `deployed_at`, WHILE still permitting a known unmerged `pr`.
- IF `abandoned_reason` is present on a `complete` or `in_progress` entry
  THEN THE SYSTEM SHALL reject the entry.
- WHEN the schema parses a timestamp THE SYSTEM SHALL validate the real
  value, not only its textual shape: a string that matches the ISO shape but
  denotes no real instant (for example `'2026-02-31T00:00:00Z'`) SHALL be
  rejected.
- WHILE an entry records several lifecycle timestamps THE SYSTEM SHALL
  require them to be nondecreasing in lifecycle order — `issue_opened_at`,
  then optional `proposal_approved_at`, `merged_at`, `released_at`,
  `deployed_at` — skipping absent stages and allowing equal instants.
- WHEN any of the above refinements fails THE SYSTEM SHALL fail Astro
  validation (`astro sync`, `astro check`, `astro dev`, `astro build`) with a
  diagnostic naming the offending entry, the field and the violation.
- WHEN the journal collection finishes loading THE SYSTEM SHALL enforce, in a
  journal loader wrapper following the existing `adrLoader()` /
  `projectsLoader()` pattern in `src/content.config.ts`, that at most one
  entry across all public and private entries has `status: in_progress`;
  zero in-progress entries SHALL be valid.
- THE SYSTEM SHALL NOT impose any newest-by-`issue_opened_at` restriction:
  a backlog issue may be executed after a newer issue (issue #52, opened
  2026-09-11, ran after issue #65, opened 2026-09-12), and issue age SHALL
  NOT be used as a lifecycle guard. The existing display sort
  (`byNewestFirst` over `cycleTimestamp`) SHALL be retained unchanged.
- WHILE evidence is missing, a PR is open, a deployment failed or a GitHub
  API call failed THE SYSTEM SHALL NOT mark a cycle abandoned; abandonment
  SHALL require an explicit cancellation decision recorded with a reason in
  both languages through the normal proposal/PR process.

### B. Library (`src/lib/journal.ts`)

- THE SYSTEM SHALL export a journal status type, `isComplete(data)` and
  `statusCounts(entries)` returning `{ complete, in_progress, abandoned }`.
- WHEN `statusCounts` is called THE SYSTEM SHALL accept journal data objects
  (the same shape `totalInterventions` accepts), not collection wrappers,
  and SHALL return zeros for an empty input.
- IF an entry's status is not `complete` THEN `leadTimeHours()` SHALL return
  `null`.
- WHILE an entry is `complete` THE SYSTEM SHALL preserve the existing
  `deployed_at`-then-`released_at` precedence, the unrounded hours
  computation, the exact-zero result for identical instants, and the
  `RangeError` behaviour for a reversed pair or an unparseable timestamp.
- THE SYSTEM SHALL keep `src/lib/journal.ts` free of runtime imports (no
  `astro:content`, no `astro/loaders`, no `zod`), so `node --test` can import
  it directly.
- THE SYSTEM SHALL keep intervention counts derived from the recorded
  `interventions` array (`interventionCount`, `totalInterventions`),
  unchanged.

### C. UI and exact copy

- THE SYSTEM SHALL insert a **Status** column between *Title* and *Issue* in
  `src/components/CycleTable.astro`, making the column order: Date, Service,
  Title, Status, Issue, Pull request, Release, Lead time (h), Interventions.
- WHEN the viewport is below 600px THE SYSTEM SHALL hide *Service* and
  *Pull request* — columns 2 and 6 after the insertion — in
  `src/styles/site.css`, and `test/a11y.test.ts` SHALL be updated from
  columns 2 and 5 to columns 2 and 6.
- THE SYSTEM SHALL retain the accessible horizontal scrolling affordance
  (`.table-scroll` with `role="region"` and `tabindex="0"`, the scroll hint
  and the `::after` fade); the whole table need not fit within 390px.
- THE SYSTEM SHALL place a **Status** row first in the `journal-meta`
  definition list of `src/pages/colophon/journal/[...slug].astro`.
- IF an entry is `abandoned` THEN the detail page SHALL render its reason
  paragraph, in both languages, beneath a heading using
  `journalAbandonedHeading`, placed under the `journal-meta` list.
- WHILE an entry is `in_progress` THE SYSTEM SHALL use `leadTimeMissing` as
  the lead-time explanation in both the table and the detail page; WHILE an
  entry is `abandoned` THE SYSTEM SHALL use `leadTimeAbandoned` in both.
- THE SYSTEM SHALL render known PR links, including for `in_progress`
  entries, and SHALL keep the em dash for absent `pr` and `release` values.
- WHEN `src/pages/colophon/index.astro` computes totals THE SYSTEM SHALL
  derive the total cycle count, all three status counts and the intervention
  total from the same public-only collection
  (`publicEntries(await getCollection('journal'))`).
- WHILE an entry is `visibility: private` THE SYSTEM SHALL still validate it
  but SHALL NOT give it a public row, a detail page, or any contribution to
  any public total.
- THE SYSTEM SHALL render all five counts, including zero values, inside
  spans carrying `data-cycle-count`, `data-complete-count`,
  `data-in-progress-count`, `data-abandoned-count` and
  `data-intervention-count`.
- THE SYSTEM SHALL compose the totals sentence from these counts and the
  `ui` strings, with the colon, commas and semicolon as template
  punctuation. During implementation the sentence reads, illustratively:

  EN: `23 public cycles: 22 complete, 1 in progress, 0 abandoned; 21 manual interventions in total`

  RU: `23 публичных циклов: 22 завершённых, 1 в работе, 0 прерванных; 21 ручных вмешательств всего`

  After closure the computed complete/in-progress counts change. These
  numbers are illustrative and SHALL NOT be written as literals or template
  literals anywhere in the source.
- THE SYSTEM SHALL add exactly these keys to `src/i18n/ui.ts`, with exactly
  these values:

  - `cycleColStatus`: EN `Status` — RU `Статус`
  - `journalStatusLabel`: EN `Status` — RU `Статус`
  - `statusComplete`: EN `complete` — RU `завершён`
  - `statusInProgress`: EN `in progress` — RU `в работе`
  - `statusAbandoned`: EN `abandoned` — RU `прерван`
  - `colophonTotalComplete`: EN `complete` — RU `завершённых`
  - `colophonTotalInProgress`: EN `in progress` — RU `в работе`
  - `colophonTotalAbandoned`: EN `abandoned` — RU `прерванных`
  - `leadTimeAbandoned`: EN `not measured: this cycle was abandoned` — RU `не измерено: этот цикл был прерван`
  - `journalAbandonedHeading`: EN `Why this cycle was abandoned` — RU `Почему этот цикл был прерван`

- THE SYSTEM SHALL leave the existing `colophonTotalCycles`,
  `colophonTotalInterventions` and `leadTimeMissing` values unchanged.

### D. Backfill

- THE SYSTEM SHALL set `status: complete` on the eight entries that already
  carry `pr`, `release`, `merged_at` and `released_at` — issues 281, 330, 3,
  4, 8, 5, 6, 7, i.e. the files
  `2026-09-10-add-portfolio-to-the-devloop-service-enums.md`,
  `2026-09-10-register-portfolio-as-a-devloop-service.md`,
  `2026-09-10-astro-static-skeleton-and-nginx-image.md`,
  `2026-09-10-base-layout-vendored-tokens-and-fonts.md`,
  `2026-09-11-approach-page.md`,
  `2026-09-11-content-collections.md`,
  `2026-09-11-home-page.md` and
  `2026-09-11-work-page.md`.
- THE SYSTEM SHALL backfill the fourteen remaining entries with exactly
  these values and set `status: complete` on each (source: GitHub REST
  `pulls` `merged_at` and `releases` `published_at`, collected 2026-09-13;
  same convention as the eight entries above; every file below is
  `src/content/journal/<file>.md`):

| issue | file | `pr` | `merged_at` | `release` | `released_at` |
|---|---|---|---|---|---|
| 11 | 2026-09-11-metrics-provenance-and-no-analytics | https://github.com/mctlhq/portfolio/pull/36 | 2026-09-11T12:36:26Z | 0.1.7 | 2026-09-11T12:38:49Z |
| 10 | 2026-09-11-p8-production-hardening-accessibility-wc | https://github.com/mctlhq/portfolio/pull/38 | 2026-09-11T13:24:25Z | 0.1.8 | 2026-09-11T13:26:35Z |
| 27 | 2026-09-11-hero-name-in-the-reader-s-script | https://github.com/mctlhq/portfolio/pull/40 | 2026-09-11T14:09:24Z | 0.1.9 | 2026-09-11T14:11:40Z |
| 42 | 2026-09-11-production-cutover | https://github.com/mctlhq/portfolio/pull/43 | 2026-09-11T17:05:16Z | 0.1.10 | 2026-09-11T17:07:39Z |
| 45 | 2026-09-11-csp-hash-quoting-and-browser-verified-headers | https://github.com/mctlhq/portfolio/pull/51 | 2026-09-11T21:59:44Z | 0.1.11 | 2026-09-11T22:02:01Z |
| 55 | 2026-09-12-content-link-contrast-and-an-offline-link-check | https://github.com/mctlhq/portfolio/pull/56 | 2026-09-12T04:10:35Z | 0.1.12 | 2026-09-12T04:13:25Z |
| 47 | 2026-09-12-repository-links-out-of-the-disclosure | https://github.com/mctlhq/portfolio/pull/58 | 2026-09-12T06:21:10Z | 0.1.13 | 2026-09-12T06:23:31Z |
| 48 | 2026-09-12-colophon-tables-and-computed-lead-time | https://github.com/mctlhq/portfolio/pull/60 | 2026-09-12T07:00:05Z | 0.1.14 | 2026-09-12T07:02:38Z |
| 49 | 2026-09-12-navigation-state-and-accessibility-affordances | https://github.com/mctlhq/portfolio/pull/62 | 2026-09-12T07:56:41Z | 0.1.15 | 2026-09-12T07:59:14Z |
| 65 | 2026-09-12-share-image-font-preload-cache-lifetime | https://github.com/mctlhq/portfolio/pull/66 | 2026-09-12T12:26:11Z | 0.1.16 | 2026-09-12T12:28:58Z |
| 52 | 2026-09-12-q7-polish-wave-findings | https://github.com/mctlhq/portfolio/pull/69 | 2026-09-12T13:42:40Z | 0.1.17 | 2026-09-12T13:45:35Z |
| 68 | 2026-09-12-backfilling-five-omitted-journal-entries | https://github.com/mctlhq/portfolio/pull/72 | 2026-09-12T15:51:08Z | 0.1.18 | 2026-09-12T15:53:06Z |
| 71 | 2026-09-12-q9-six-review-findings | https://github.com/mctlhq/portfolio/pull/74 | 2026-09-12T17:34:48Z | 0.1.19 | 2026-09-12T17:37:14Z |
| 75 | 2026-09-12-symlink-safe-check-no-metrics-entry-guard | https://github.com/mctlhq/portfolio/pull/77 | 2026-09-12T19:37:37Z | 0.1.20 | 2026-09-12T19:40:48Z |

  Timestamps are written single-quoted, exactly as the existing entries write
  them, e.g. `merged_at: '2026-09-11T12:36:26Z'`.

- THE SYSTEM SHALL add the two missing approval stamps (source:
  `approval.approved_at` in
  `platform-gitops/agents-state/portfolio/proposals/<slug>/.status.yaml` in
  `mctlhq/mctl-gitops`):
  - issue 11 (`2026-09-11-metrics-provenance-and-no-analytics.md`):
    `proposal_approved_at: '2026-09-11T11:15:37Z'`
  - issue 75 (`2026-09-12-symlink-safe-check-no-metrics-entry-guard.md`):
    `proposal_approved_at: '2026-09-12T19:03:02Z'`
- THE SYSTEM SHALL NOT backfill `deployed_at`: no portfolio entry has it, no
  per-release deployment evidence was collected, and lead time falls back to
  `released_at`. IT SHALL NOT be invented.
- THE SYSTEM SHALL preserve the existing evidence of the two
  cross-repository entries (mctl-api #281, mctl-agents #330), including
  their `deployed_at` values.

### E. Release closure and publication

- THE SYSTEM SHALL follow the finite sequence: implementation PR → original
  stable release R → closure PR → metadata-only patch release R2 →
  deployment of R2.
- WHEN this cycle's implementation PR is written THE SYSTEM SHALL add this
  cycle's own journal entry with `status: in_progress` and no invented
  evidence (no `pr`, `release`, `merged_at`, `released_at`, `deployed_at`).
- THE SYSTEM SHALL add `.github/workflows/journal-closure.yml`, triggered by
  `release` with type `published`, filtering out drafts and prereleases, and
  additionally by `workflow_dispatch` taking a required release-tag input for
  recovery.
- THE SYSTEM SHALL reuse the existing GitHub App authentication pattern
  (`actions/create-github-app-token` pinned by SHA, as in
  `.github/workflows/release-please.yml`) so that generated PRs run the
  normal checks, SHALL scope the write credentials to the `portfolio`
  repository, and SHALL serialize closure runs for this repository with a
  `concurrency` group. The workflow SHALL link `docs/journal.md`.
- THE SYSTEM SHALL put matching and update logic in
  `scripts/close-journal.mjs`, with an injectable boundary around GitHub
  requests so the logic is testable offline with no network access.
- WHEN the script runs THE SYSTEM SHALL resolve the event or manual tag to a
  published, non-draft, non-prerelease release in `portfolio`.
- WHEN resolving the journal entry and its implementation PR THE SYSTEM
  SHALL, if the entry already records a `pr`, validate that PR; otherwise it
  SHALL identify the unique merged implementation PR that introduced that
  journal entry file and verify its issue association.
- THE SYSTEM SHALL verify that the implementation PR's merge commit is an
  ancestor of the release tag's resolved commit, and SHALL NOT infer
  inclusion from publication or merge timestamps, SHALL NOT take the latest
  release blindly, and SHALL NOT use a release PR as the implementation PR.
- THE SYSTEM SHALL choose the earliest published stable release that
  contains the implementation merge commit, and IF the first eligible
  release is ambiguous THEN THE SYSTEM SHALL fail with diagnostics rather
  than guess.
- THE SYSTEM SHALL update only `service: portfolio` entries, SHALL preserve
  the cross-repository historical entries, and SHALL match against the
  current `main` state so that rerunning an older event cannot revert a
  completed entry.
- WHEN an entry is eligible for closure THE SYSTEM SHALL set `pr`,
  `merged_at`, `release` and `released_at` from the verified GitHub evidence
  and switch `status` to `complete`, WHERE `release` and `released_at`
  always refer to R and never to R2.
- THE SYSTEM SHALL NOT set `deployed_at` without separate verified
  deployment evidence; this workflow leaves it unfilled.
- THE SYSTEM SHALL create or reuse a deterministic branch and pull request
  identified by the journal entry, WHERE the diff changes only that entry's
  lifecycle status and evidence fields, and SHALL use the commit and PR title
  `fix(journal): close cycle <issue-number>` so release-please proposes a
  patch release.
- THE SYSTEM SHALL NOT manufacture a new journal entry, a manual-intervention
  record or any count for routine closure or release mechanics; actual manual
  interventions are recorded through the established journal process.
- WHEN a delivery is duplicated or retried THE SYSTEM SHALL NOT create
  duplicate PRs or duplicate commits.
- IF an existing closure PR, or `main`, already contains conflicting evidence
  or unrelated edits THEN THE SYSTEM SHALL report the conflict and stop
  without overwriting it.
- IF a GitHub API call fails, matching is ambiguous or evidence is invalid
  THEN THE SYSTEM SHALL fail visibly and preserve existing data.
- THE SYSTEM SHALL provide a dry-run mode that reports the intended match and
  diff and performs no writes.
- WHEN a valid release has no newly eligible `in_progress` portfolio entry
  THE SYSTEM SHALL succeed as a no-op; in particular R2 sees the
  already-complete entry and produces no closure PR, commit or further
  release.
- THE SYSTEM SHALL treat closure and release PRs as follow-through for the
  original cycle, never as additional DevLoop cycles.
- THE SYSTEM SHALL NOT bypass approvals, merge arbitrary pull requests,
  overwrite tags or images, deploy a different commit under R's tag, or
  change the shared deployment workflow.

### F. Documentation

- THE SYSTEM SHALL create `docs/journal.md` containing exactly this text:

````markdown
# Journal lifecycle

One entry per DevLoop cycle, `src/content/journal/YYYY-MM-DD-<slug>.md`.
Every entry carries `status`.

- A cycle creates its own entry with `status: in_progress`. Record a known
  implementation PR and merge time when available; do not invent evidence.
  An in-progress entry has no release, release time or deployment time.
- After the first published stable release containing the implementation
  merge commit, the journal-closure workflow opens a closure PR. It records
  `pr`, `merged_at`, `release` and `released_at` from verified GitHub evidence
  and sets `status: complete`.
- The release owner merges the closure PR and the resulting metadata-only
  patch release through the normal CI, review and merge-commit gates, then
  verifies deployment. This publishes the closed entry without waiting for
  another DevLoop cycle.
- The entry continues to identify the original implementation release, not
  the metadata patch release. Complete means release evidence is recorded;
  it does not assert successful deployment. Record `deployed_at` only when
  separate deployment evidence is available.
- Closure and release PRs are follow-through for the original cycle, not
  additional DevLoop cycles. They create no extra journal entries. A release
  with no newly eligible open entry is a no-op, so the metadata patch release
  does not start another closure or release.
- At most one entry is `in_progress`, including private entries; zero is valid.
  Issue opening dates do not determine execution order. Finish or explicitly
  abandon the previous cycle before starting another.
- Mark a cycle `abandoned` only after an explicit cancellation decision,
  through the normal proposal and PR process, with a non-blank reason in
  both languages. A known unmerged PR may remain recorded. An abandoned
  entry has no merge, release or deployment evidence. Missing evidence,
  an open PR, failed deployment or an API error is not abandonment.
- The schema validates status evidence and timestamp order. The journal loader
  validates the collection-wide open-entry limit. Private entries are
  validated but never rendered or included in public totals.

## Recovery

Inspect a failed closure run and its diagnostics before changing data.
Use the journal-closure workflow's manual dispatch with the original stable
release tag to retry after the failure is resolved. Repeated delivery reuses
the existing closure PR or makes no change when the entry is already complete.
Resolve ambiguous PR/release matches or conflicting evidence through review;
do not guess, overwrite unrelated edits or change a completed entry's release.
If closure or deployment is pending, the release owner finishes that work as
part of the original cycle and verifies the public colophon and detail page.

Lead time and intervention counts are computed at build time, never typed.
Routine closure and release mechanics add no manufactured interventions;
actual manual interventions follow the existing journal recording rules.
````

- THE SYSTEM SHALL add a concise link to `docs/journal.md` from `README.md`.
- THE SYSTEM SHALL NOT modify `AGENTS.md` or the reserved release/review
  workflows (`.github/workflows/release-please.yml`,
  `.github/workflows/claude-review.yml`, `.github/dependabot.yml`).

### G. Tests (implementer-verifiable)

- WHEN the test suite runs THE SYSTEM SHALL prove that the actual Astro
  journal schema requires `status`, accepts valid examples of all three
  states, and rejects: each missing required field per status, each
  forbidden field per status, a whitespace-only abandonment reason, an
  invalid date, and a reversed lifecycle timestamp pair — asserting on
  diagnostics that identify the entry, the field and the violation.
- THE SYSTEM SHALL exercise the real journal schema and loader through
  isolated Astro builds driven from fixture content trees: two open entries
  fail (including a public/private pair), zero open entries pass, and one
  open entry belonging to an older backlog issue passes.
- WHEN an invalid-entry fixture fails THE SYSTEM SHALL assert it failed
  because of the intended schema diagnostic, not an unrelated build error.
- THE SYSTEM SHALL prove the production schema/loader wiring as well as the
  helpers: removing the collection guard makes the corresponding negative
  integration test fail, and the mutation/reproduction evidence lives in a
  committed test or document, never in a pull request description.
- WHILE this migration is in place THE SYSTEM SHALL assert that every journal
  file carries a status, that every `complete` entry carries all four
  evidence fields, and that at most one entry is `in_progress`; at the
  implementation-PR checkpoint the 22 historical entries are complete, this
  cycle's new entry is in progress and none is abandoned. These checkpoint
  numbers SHALL NOT become permanent hard-coded assertions that block future
  cycles.
- THE SYSTEM SHALL assert that all fourteen backfill rows and both approval
  stamps above are present verbatim, that no historical `deployed_at` is
  invented, and that the cross-repository entries retain their evidence.
- THE SYSTEM SHALL test the closure script offline with fixtures covering:
  correct entry/implementation-PR/release association; merge ancestry,
  including a merge not contained in a candidate release; earliest-containing
  release selection; duplicate events; an already-completed entry;
  missing, draft and prerelease releases; API failures; ambiguous matches;
  conflicting or unrelated edits; and absence of any write on failures and
  dry runs.
- THE SYSTEM SHALL test the finite sequence R → closure PR → R2 → no-op:
  the closure diff changes only allowed lifecycle fields, preserves R as the
  entry's release, creates no extra journal entry, and a retry reuses the
  same PR without an additional commit when the intended content is
  unchanged. The workflow trigger and its draft/prerelease filter, the
  recovery input and the script invocation SHALL be tested.
- THE SYSTEM SHALL have behaviour tests for `statusCounts`, `isComplete` and
  status-aware lead time, including empty inputs, all three statuses, a zero
  lead time, and release/deployment precedence; public-only counts and the
  exclusion of private entries from rendered rows and pages SHALL be tested
  with mixed fixtures.
- THE SYSTEM SHALL assert on built markup that it contains the five computed
  totals including zero values, all status labels, the table Status column,
  the first detail Status row, and the correct in-progress and abandoned
  lead-time explanations in both views; known in-progress PR links render.
  An abandoned fixture SHALL be used rather than fictional production
  history.
- THE SYSTEM SHALL assert that the narrow-viewport hiding targets columns 2
  and 6, that all supplied UI keys carry the exact EN/RU values above, that
  `docs/journal.md` matches section F byte for byte, and that `README.md` and
  the closure workflow link it.
- THE SYSTEM SHALL list every new test file explicitly in the enumerated
  `test` script in `package.json`, and SHALL NOT recursively invoke
  `npm run build` from `npm test`: isolated integration builds invoke Astro
  directly.
- WHEN the normal gates run THE SYSTEM SHALL pass `npm run vendor && npm test`,
  `npm run build` and `node scripts/check-links.mjs`.

## Release-owner and reviewer completion steps (not implementer criteria)

These depend on post-merge events. No implementer commit can prove them, and
none of them is an acceptance criterion for the implementation PR.

1. Finish the original release R, inspect the generated closure PR and merge
   it through the normal gates. Complete and deploy the metadata-only patch
   release R2 with the existing release process. No next DevLoop cycle is
   needed.
2. Verify that the deployed colophon and this cycle's detail page show
   `complete` and retain R as their evidence. With no intervening cycle the
   final checkpoint is 23 complete, zero in progress and zero abandoned.
   Check the actual intervention total rather than assuming the illustrative
   21.
3. Confirm that R2's closure run is a no-op, with no extra closure PR or
   release. A pending closure PR or a failed deployment leaves this issue's
   end-to-end completion pending.
4. At 390px, in both EN and RU, verify readable status values and totals, no
   clipped text, and usable keyboard-accessible horizontal table scrolling.

## Out of scope

- Historical deployment timestamp backfill: no such evidence has been
  collected, and `deployed_at` is not invented for any entry.
- Changes to `AGENTS.md`, the reserved release/review workflows
  (`release-please.yml`, `claude-review.yml`, `dependabot.yml`), shared
  platform workflows or deployment infrastructure.
- Client-side GitHub requests, a live journal API, or any network dependency
  in the normal content build. GitHub access belongs to the closure workflow;
  committed evidence feeds the static build.
- Overwriting release tags or images, bypassing PR/review gates, automatic
  approval of proposals, or automatic merging of arbitrary release PRs.
- Automatic abandonment based on missing evidence or unsuccessful runs.
- Changes to journal titles, navigation, or hiding, collapsing or paginating
  the cycles table beyond preserving its existing narrow-screen column
  hiding.

## Open questions

- The issue does not say whether `abandoned_reason` is permitted on a
  `complete` or `in_progress` entry. Interpretation taken: it is forbidden
  there, because a reason without an abandonment is evidence of a wrong
  status; this is stated as an explicit criterion above.
- The issue numbers its scope items D.8/D.9/D.10 while section C already has
  an item 8; this proposal treats the backfill items by content, not by
  number, and keeps them under section D.
- This cycle's entry needs `issue_opened_at`. Issue #79 was opened at
  `2026-09-13T05:29:22Z` (GitHub REST `issues`, read in the investigation
  clone); the implementer uses that value and omits `proposal_approved_at`,
  which it cannot verify from the repository. The closure workflow does not
  backfill approval stamps.
- The issue does not fix the filename of this cycle's entry. Interpretation:
  `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`,
  following the existing `YYYY-MM-DD-<slug>.md` convention.
- Whether `astro build`'s error output names the exact zod `path` for every
  refinement is Astro's behaviour, not ours; the tests assert on the entry
  id, field name and message text the implementation itself emits, which is
  under our control.
