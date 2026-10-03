# Design: issue-79-q11-every-cycle-s-journal-entry-is-born

## Current state

Baseline: `main` at `41dc0238ff3aeeb1f6d7d091c6514416dce77790`, package version
`0.1.20`, Astro 7, no client bundles, static output.

**Schema.** `src/content.config.ts` defines three collections. The `journal`
collection uses a bare `glob({ pattern: '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-*.md',
base: './src/content/journal', generateId: idFromFile })` loader and a
`z.strictObject({...})` schema whose `pr`, `release`, `merged_at`,
`released_at` and `deployed_at` fields are all `.optional()`. Timestamps go
through a shared `const stamp = z.string().refine(isoWithOffset, {...})
.transform((s) => new Date(s))`, so only the textual shape is checked — a
string such as `'2026-02-31T00:00:00Z'` passes the regex and becomes an
`Invalid Date`. There is no cross-field refinement and no collection-wide
check for the journal.

The other two collections already show the pattern this proposal follows for
collection-wide invariants: `projectsLoader()` wraps the base glob loader and
calls `checkProjectParity(ctx.store.entries()...)` after `base.load(ctx)`;
`adrLoader()` does the same with `checkAdrBodies(...)` from `src/lib/adr.ts`.
Both throw `Error('<Collection> validation failed:\n- ...')`, and the header
comment on `adrLoader()` explains why the loader, not an
`astro:build:done` hook, is the right place: the loader runs on `astro sync`,
`astro check`, `astro dev` and `astro build` alike.

**Library.** `src/lib/journal.ts` is deliberately import-free (its own header
says so) so `node --test test/journal.test.ts` can import it with no build
step. It exports `ISO_WITH_OFFSET`, `isoWithOffset`, `cycleEndTimestamp`
(`deployed_at` then `released_at`, else `null`), `leadTimeHours` (unrounded
hours, `RangeError` on a reversed pair or an unparseable value),
`interventionCount`, `totalInterventions`, `cycleTimestamp`, `byNewestFirst`,
`isoDate`, `isoStamp`, `formatLeadTime` (em dash for `null`, one decimal
otherwise), `formatStamp`, `intervalMinutes`, `formatInterval` and
`githubRef`. `src/lib/content.ts` provides `isPublic` / `publicEntries`.

**UI.** `src/components/CycleTable.astro` renders eight columns — Date,
Service, Title, Issue, Pull request, Release, Lead time (h), Interventions —
inside `.table-scroll` (`role="region"`, `tabindex="0"`, aria-label built from
`ui.cycleTableCaption`). A `null` lead time renders
`<span class="lead-time-missing">—</span>` plus a `.visually-hidden`
`ui.leadTimeMissing` explanation. `src/pages/colophon/index.astro` builds
`const journal = publicEntries(await getCollection('journal')).sort(byNewestFirst)`,
`cycleCount = journal.length`, `interventionsTotal = totalInterventions(
journal.map((entry) => entry.data))` and renders them in
`<span data-cycle-count={cycleCount}>` / `<span data-intervention-count={...}>`.
`src/pages/colophon/journal/[...slug].astro` builds `getStaticPaths` from
`publicEntries`, renders a `dl.journal-meta` (Service, Issue, Pull request,
Release, Lead time), the decided paragraph, a timeline built from the five
timestamps with `formatStamp`/`formatInterval`, and the interventions list.
`src/styles/site.css` hides `table.cycles` columns 2 and 5 inside
`@media (max-width: 599px)` (line 608) and declares the `.table-scroll::after`
fade in the earlier 599px block (line 530).

**Content.** 22 journal files, all `visibility: public`. Eight carry
`pr`/`release`/`merged_at`/`released_at` (issues 281, 330, 3, 4, 8, 5, 6, 7);
the two cross-repository ones (mctl-api #281, mctl-agents #330) additionally
carry `deployed_at`. The other fourteen carry only `issue_opened_at` and
(twelve of them) `proposal_approved_at`; issues 11 and 75 lack the approval
stamp.

**Workflows and scripts.** `.github/workflows/release-please.yml` (reserved)
mints a token with `actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0`,
`owner: mctlhq`, `repositories: portfolio`, `permission-contents: write`,
`permission-pull-requests: write`, and explains that a PR opened with an App
token raises `pull_request` events so the release PR gets CI and the Claude
review; after a release it dispatches `release-deploy.yaml` in `mctl-gitops`
with the tag. `.github/workflows/build.yml` (not reserved) runs
`npm ci`, `npm run build` (whose `prebuild` is `npm run vendor && npm test`),
a vendored-tree `git diff --exit-code`, and `node scripts/check-links.mjs`.

Scripts follow a consistent shape: pure exported functions plus a `main()`
behind `isEntryPoint()` in the hybrid `import.meta.main` /
`realpathSync(process.argv[1])` form (`scripts/check-links.mjs`,
`scripts/check-no-metrics.mjs`, `scripts/snapshot-metrics.mjs`), a shape that
`test/entry-point.test.ts` derives by scanning `scripts/*.mjs` and enforces.
Tests that must exercise a script end to end copy it into a temp tree and
`spawnSync` it there (`test/metrics-build.test.ts`, `test/check-dist.test.ts`,
`test/vendor-assets.test.ts`). `scripts/check-no-metrics.mjs` scans only
`src/pages`, `src/components`, `src/layouts` for two-or-more-digit literals,
plus a version-shaped matcher over `src/content/projects` bodies — journal
frontmatter is deliberately out of both scans.

`package.json`'s `test` script enumerates all 29 test files explicitly.

## Proposed solution

### 1. Status in the schema, invariants in refinements (`src/content.config.ts`)

Add to the journal `strictObject`:

- `status: z.enum(['in_progress', 'complete', 'abandoned'])` (required),
- `abandoned_reason: nonBlankBilingual.optional()`, where
  `const nonBlank = z.string().refine((s) => s.trim().length > 0, 'must contain non-whitespace text')`
  and `nonBlankBilingual = z.strictObject({ en: nonBlank, ru: nonBlank })`
  (the existing `bilingual` uses `.min(1)`, which accepts `'   '`).

Harden `stamp` so it validates the instant, not only the shape: keep the
regex check, and add a second predicate that `Date.parse(value)` is not
`NaN`, via a new import-free helper `isRealTimestamp(value)` in
`src/lib/journal.ts` (regex plus `Number.isNaN` check). The existing
`isoWithOffset` stays exported and unchanged — `test/colophon.test.ts` and
`test/journal.test.ts` both use `ISO_WITH_OFFSET`.

Attach cross-field rules with `.superRefine((data, ctx) => ...)` on the
journal object, emitting one `ctx.addIssue({ code: 'custom', path: [field],
message })` per violation so Astro's own "**<entry id>** frontmatter does not
match collection schema" output names the field:

- `complete` → `pr`, `release`, `merged_at`, `released_at` all present;
- `in_progress` → `release`, `released_at`, `deployed_at` absent;
- `abandoned` → `abandoned_reason` present; `merged_at`, `release`,
  `released_at`, `deployed_at` absent; `pr` allowed;
- any status → `merged_at` present implies `pr` present;
- `abandoned_reason` present implies `status === 'abandoned'`;
- lifecycle order: walk `[issue_opened_at, proposal_approved_at, merged_at,
  released_at, deployed_at]`, drop absent stages, and require each surviving
  pair to be nondecreasing (`<=`), reporting the later field's name and both
  instants.

The refinement predicate itself is written as an import-free exported
function in `src/lib/journal.ts` — `journalEntryProblems(data): string[]`
(plus a small `statusEvidenceProblems`/`timestampOrderProblems` split if that
reads better) — and `content.config.ts` only maps its problems onto
`ctx.addIssue`. That keeps the logic unit-testable by `node --test` while the
*enforcement* lives in the real schema, which is what the integration builds
prove.

`.superRefine` turns the schema into a `ZodEffects`; Astro's content layer
calls `schema.safeParseAsync` through `parseData`, so this works, and the
integration fixtures below are what proves it rather than an assumption.

### 2. Collection guard in a journal loader wrapper

Add `journalLoader()` next to `projectsLoader()` and `adrLoader()`, with the
same shape: wrap the existing glob loader, `await base.load(ctx)`, then call
`checkJournalCollection(ctx.store.entries().map(([id, entry]) => ({ id, data:
entry.data as JournalCollectionEntry })))`. `checkJournalCollection` lives in
`src/lib/journal.ts`, is import-free, counts entries with
`status === 'in_progress'` across **all** entries (public and private) and
throws `Error('Journal validation failed:\n- two entries are in_progress:
<id>, <id> ...')` when the count exceeds one. Zero is valid. No ordering rule
is added: `#52` (opened 2026-09-11) ran after `#65` (opened 2026-09-12), and
`byNewestFirst`/`cycleTimestamp` keep the display sort exactly as today.

### 3. Library additions (`src/lib/journal.ts`)

```ts
export type JournalStatus = 'in_progress' | 'complete' | 'abandoned';
export interface JournalStatusData { status: JournalStatus }
export function isComplete(data: JournalStatusData): boolean
export function statusCounts(entries: readonly JournalStatusData[]):
  { complete: number; in_progress: number; abandoned: number }
```

`statusCounts` takes data objects (like `totalInterventions`), starts from
`{ complete: 0, in_progress: 0, abandoned: 0 }` so every key is present for an
empty input, and increments by status. `leadTimeHours` gains `status` on its
parameter type and returns `null` immediately unless `isComplete(entry)`;
everything after that — `cycleEndTimestamp` precedence, unrounded hours,
exact `0`, `RangeError` on reversal or unparseable input — is untouched.
`cycleEndTimestamp` stays status-agnostic (it is a timestamp helper, and
`cycleTimestamp`/`byNewestFirst` still need to date an open entry).
Existing fixtures in `test/journal.test.ts` gain an explicit
`status: 'complete'` (or `'in_progress'` for the null cases), which is the
"update existing timestamp fixtures for the explicit status contract" the
issue asks for.

### 4. UI

`src/i18n/ui.ts` gains the ten keys listed in requirements section C, values
copied character for character; the three existing keys are untouched.
`test/ui.test.ts` already enforces that every key has non-empty `en` and `ru`
of the same kind.

`CycleTable.astro`: a `Status` header (`ui.cycleColStatus`) and cell between
Title and Issue, so the column order becomes Date, Service, Title, Status,
Issue, Pull request, Release, Lead time, Interventions. The cell renders a
`statusLabel[entry.data.status]` lookup — the same `as const` map shape the
colophon already uses for `adrStatusLabel` — through `<Lang>`. The lead-time
cell branches on status: `complete` renders `formatLeadTime(leadTime)`,
`in_progress` renders the em dash plus `.visually-hidden ui.leadTimeMissing`,
`abandoned` renders the em dash plus `.visually-hidden ui.leadTimeAbandoned`.
The `lead-time-missing` class and `ui.leadTimeMissing` reference are kept, so
the existing `test/colophon.test.ts` assertions still hold. PR and release
cells keep `entry.data.pr ? <a …> : EM_DASH` / `entry.data.release ?? EM_DASH`,
which already renders an in-progress entry's known PR link.

`src/pages/colophon/journal/[...slug].astro`: a `Status` row
(`ui.journalStatusLabel` + the same label map) becomes the first `dt`/`dd`
pair in `dl.journal-meta`; the lead-time `dd` branches exactly as the table
does; after the `dl`, an `{data.status === 'abandoned' && data.abandoned_reason
&& (…)}` block renders an `<h2>` from `ui.journalAbandonedHeading` and a
`<p class="journal-abandoned">` with the bilingual reason.

`src/pages/colophon/index.astro`: `const counts = statusCounts(journal.map(
(entry) => entry.data))` from the same public-only, already-sorted collection
used for the table and `totalInterventions`. The totals paragraph renders five
spans — `data-cycle-count`, `data-complete-count`, `data-in-progress-count`,
`data-abandoned-count`, `data-intervention-count` — with `:`/`,`/`;` as
template punctuation and the words from `ui.colophonTotalCycles`,
`colophonTotalComplete`, `colophonTotalInProgress`, `colophonTotalAbandoned`,
`colophonTotalInterventions`. Zero counts render as `0`, never as a hidden
branch, because `statusCounts` always returns all three keys and the template
has no conditional around them. No number is typed: `scripts/check-no-metrics.mjs`
scans `src/pages` for `\b[0-9]{2,}\b` and would catch a regression.

`src/styles/site.css`: the `@media (max-width: 599px)` block changes
`table.cycles th/td:nth-child(5)` to `:nth-child(6)` (Service stays column 2,
Pull request moves from 5 to 6 once Status is inserted at 4). The
`.table-scroll` region, its hint and the `::after` fade are untouched, so
horizontal scrolling remains the narrow-screen affordance; a
`.journal-abandoned` colour/spacing rule is added next to `.journal-meta`.
`test/a11y.test.ts`'s "hides table.cycles columns 2 and 5" test is updated to
2 and 6 (name and assertions).

### 5. Backfill

Each of the 22 existing files gains `status: complete`, placed on its own
frontmatter line (convention: after `visibility`, before `title`, so status
reads next to visibility). The fourteen open entries additionally receive the
`pr`, `merged_at`, `release`, `released_at` values from the table in
requirements section D, written single-quoted like every existing timestamp,
and issues 11 and 75 receive their `proposal_approved_at` stamps. No
`deployed_at` is added anywhere; the two cross-repository entries keep the
`deployed_at` values they already have. This cycle's own entry,
`src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`, is
created with `status: in_progress`, `issue_opened_at: '2026-09-13T05:29:22Z'`,
`proposal_slug: issue-79-q11-every-cycle-s-journal-entry-is-born`,
`interventions: []`, bilingual `title`/`decided`, and no evidence fields.
After this commit the schema sees 22 complete entries and exactly one
`in_progress`, satisfying the loader guard.

Backfilled values are also asserted verbatim by a committed test, so a later
edit that "corrects" one of them fails loudly.

### 6. Closure: workflow plus script

`.github/workflows/journal-closure.yml`

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      tag: { description: 'Stable release tag to close against', required: true }
```

with a top-level `permissions: contents: read`, a job-level
`if: github.event_name == 'workflow_dispatch' || (github.event.release.draft
== false && github.event.release.prerelease == false)`, and
`concurrency: { group: journal-closure-${{ github.repository }},
cancel-in-progress: false }` so deliveries serialize instead of racing. The
job checks out `main` with `fetch-depth: 0` (ancestry needs real history),
sets up Node 24, mints a token with the same pinned
`actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0`,
`owner: mctlhq`, `repositories: portfolio`, `permission-contents: write`,
`permission-pull-requests: write` — so the closure PR raises `pull_request`
events and gets build + Claude review like any other PR — and runs
`node scripts/close-journal.mjs --tag "$TAG"` with
`TAG: ${{ github.event.release.tag_name || inputs.tag }}`. A header comment
links `docs/journal.md`.

`scripts/close-journal.mjs` keeps every GitHub call behind one injectable
object so the logic is exercised offline:

```js
export function createGitHubClient({ token, repo, fetchImpl = fetch }) { … }
export async function run({ tag, github, repoRoot, dryRun = false, log }) { … }
```

`run` is a pure orchestration over the client's methods
(`getReleaseByTag`, `listStableReleases`, `resolveTagCommit`,
`isAncestor(commit, tagCommit)`, `getPullRequest`, `findPullsIntroducingFile`,
`getFileOnMain`, `findOpenPull`, `createOrUpdateBranchFile`, `createPull`),
and the tests inject a fake client built from fixtures. Exported pure helpers
carry the decisions that deserve direct tests:
`parseFrontmatter(source)`, `entryIssueNumber(data)`,
`selectClosableEntry(entries)` (portfolio service, `status: in_progress`),
`earliestContainingRelease(releases, contains)` (sorted by `published_at`,
stable only, ambiguity → throw with both candidates named),
`applyClosure(source, evidence)` (returns the new file text; sets `status:
complete` and inserts/updates only `pr`, `merged_at`, `release`,
`released_at`), `closureDiffProblems(before, after)` (rejects any change
outside those five fields), and `branchName(issueNumber)` →
`fix/journal-close-<issue-number>`. Commit and PR title:
`fix(journal): close cycle <issue-number>`, so release-please proposes a
patch release.

Decision order in `run`:

1. resolve `tag` → release; reject draft/prerelease/missing with a diagnostic;
2. read the journal directory from the checked-out `main` state, select the
   single `service: portfolio`, `status: in_progress` entry; none → exit 0 as
   a no-op (this is the R2 case, where the entry is already `complete`);
3. resolve the implementation PR: if the entry records `pr`, fetch and
   validate it (merged, belongs to `mctlhq/portfolio`, references the entry's
   issue); otherwise find the merged PRs that introduced that journal file
   and require exactly one whose issue association matches — a release PR
   (`release-please--branches--main…`) is excluded by the file-introduction
   test itself, since a release PR touches `CHANGELOG.md`/`package.json`, not
   the journal entry;
4. verify `isAncestor(mergeCommitSha, resolveTagCommit(tag))`; not contained →
   exit 0 as a no-op for this release (a later release will contain it),
   with a log line saying so;
5. among stable published releases, pick the earliest whose resolved commit
   contains the merge commit; if two candidates tie on `published_at`, fail
   with both named;
6. compute the new file text; if `main`'s current copy already equals it, or
   the entry is already `complete`, exit 0 with no write; if the deterministic
   branch already exists, compare its blob — equal → reuse the existing PR
   with no new commit; different in the five allowed fields only → update;
   different anywhere else, or `main` carries conflicting evidence → report
   the conflict and exit non-zero without writing;
7. `--dry-run` prints the intended match and unified diff and returns before
   any write.

Failure modes (API error, ambiguity, invalid evidence) throw with the entry
id, the field and the offending values; nothing is written on a throw because
every write happens in step 6 after all verification.

### 7. Documentation

`docs/journal.md` is created with the exact text in requirements section F,
alongside the existing `docs/link-check.md`, `docs/accessibility-checklist.md`
and `docs/hardening-notes.md`. `README.md` gains one concise line linking it
(README is a human-editable file under the bootstrap boundary, but the
boundary restricts *humans* to a list of files, not the implementer, and
`AGENTS.md` explicitly requires the implementer to write everything else;
adding a link line is within this proposal and is the only README change).

### 8. Tests

Four new files, each added to the enumerated `test` script in `package.json`:

- `test/journal-status.test.ts` — `statusCounts` (empty, all statuses,
  zeros present), `isComplete`, status-aware `leadTimeHours` (null for
  in-progress and abandoned even with timestamps present, zero lead time,
  deployed-over-released precedence, `RangeError` cases), `journalEntryProblems`
  and `checkJournalCollection` unit behaviour, plus source-level assertions
  over the committed content: every file has `status`, every `complete` entry
  carries the four evidence fields, at most one `in_progress`, the fourteen
  backfill rows and the two approval stamps verbatim, no invented
  `deployed_at`, cross-repository evidence intact.
- `test/journal-build.test.ts` — isolated Astro builds. A helper copies
  `src/` (replacing `src/content/journal` with the fixture set), symlinks
  `node_modules` and `public/`, writes a minimal `astro.config.mjs`, and
  spawns `node node_modules/astro/astro.js build` in the temp root
  (`npm run build` is never invoked from `npm test`, per the issue and
  because `prebuild` would recurse). Cases: valid examples of all three
  statuses build; each missing/forbidden-field violation, a whitespace-only
  abandonment reason, an invalid date and a reversed timestamp pair fail with
  the intended diagnostic (asserted by entry id + field + message, and by the
  absence of unrelated error text); two open entries fail including a
  public/private pair; zero open entries pass; one open entry on an older
  backlog issue passes. The rendered-markup assertions live here too: the
  five `data-*` totals including zeros, all status labels, the table Status
  column, the first detail Status row, in-progress and abandoned lead-time
  explanations in both views, an in-progress PR link, and a private fixture
  entry with no row and no detail page. One case copies `content.config.ts`
  with the `journalLoader` guard call removed and asserts the two-open-entry
  fixture then *builds* — committed mutation evidence that the guard, not
  something else, is what fails that test.
- `test/journal-closure.test.ts` — `scripts/close-journal.mjs` against a fake
  client: correct entry/PR/release association; merge not contained in a
  candidate release; earliest-containing selection; duplicate delivery;
  already-complete entry; missing/draft/prerelease release; API failure;
  ambiguous PR match and ambiguous release tie; conflicting evidence and
  unrelated edits on the branch; dry run. Every failure/dry-run case asserts
  the fake client recorded zero write calls. The R → closure PR → R2 → no-op
  sequence is one ordered test over one fake repository state, asserting the
  diff touches only the five fields, `release` stays R, no journal file is
  added, and the retry reuses the branch/PR with no second commit.
- `test/journal-workflow.test.ts` — YAML and docs: `release: types:
  [published]`, the draft/prerelease filter, the required `workflow_dispatch`
  input, the concurrency group, the pinned App-token action with
  `repositories: portfolio`, the `node scripts/close-journal.mjs` invocation,
  the `docs/journal.md` link; `docs/journal.md` equals the exact text (stored
  as the expected string in the test); `README.md` links it.

Existing files updated: `test/journal.test.ts` (fixtures gain `status`),
`test/a11y.test.ts` (columns 2 and 6), `test/colophon.test.ts` (required
frontmatter keys now include `status`; the new UI references),
`test/ui.test.ts` (exact values for the ten new keys can also live here next
to the existing `heroName` assertions).

## Alternatives

1. **Close the entry in the next DevLoop cycle (status quo, formalised).**
   Rejected: it is exactly the defect. The last shipped cycle stays "running"
   forever when no further work happens, and eight of the current entries
   exist only because later cycles happened to backfill them.

2. **Close on merge to `main` (a `push`/`pull_request: closed` trigger)
   instead of on `release: published`.** Rejected: the site is built from a
   release tag by the centralized `release-deploy` dispatch in
   `release-please.yml`, so a commit on `main` alone changes nothing the
   public sees, and at merge time the release that will contain the merge is
   not yet known — `release`/`released_at` would have to be invented or left
   blank, which is the same hole one step later.

3. **Validate the lifecycle in a standalone `npm test` script (a
   `scripts/check-journal.mjs` gate) rather than in the schema and loader.**
   Rejected: `astro dev`/`astro check`/`astro build` would still accept a
   contradictory entry, and the failure would arrive from a grep-style gate
   rather than from the collection that owns the data. The issue explicitly
   requires enforcement in the actual journal schema; the loader wrapper is
   the project's own established place for collection-wide rules
   (`checkProjectParity`, `checkAdrBodies`).

4. **Have the closure script call `gh` from the workflow, or `fetch` inline
   with no injectable boundary.** Rejected: the acceptance criteria demand
   offline fixture tests for ancestry, ambiguity, duplicate delivery and API
   failure. `scripts/snapshot-metrics.mjs` already shows the seam this repo
   prefers — a pure `buildMetrics({github, mctl, previous}, now)` behind the
   network layer, tested from fixtures in `test/metrics-build.test.ts`.

5. **Derive counts client-side or from a live journal API.** Rejected by the
   site constraints in `AGENTS.md`: zero third-party browser requests, no
   client bundles, every number computed at build time from committed data.

## Platform impact

- **Migration.** All 22 existing journal files change (one added line each,
  fourteen with four more), and one new entry is added. `status` is required,
  so any journal file created after this lands without a status fails the
  build — which is the point, and `docs/journal.md` documents it.
- **Backward compatibility.** No public URL, route, title or navigation
  changes. The cycles table gains a column; narrow screens keep two hidden
  columns and the existing scroll affordance. Existing frontmatter keys and
  their meanings are unchanged; `deployed_at` remains optional and unfilled.
- **Build/runtime cost.** The schema refinements and the loader pass are O(n)
  over 23 entries. The isolated-build integration tests are the real cost:
  each spawns an Astro build over a fixture tree. Mitigation: share one
  fixture-tree factory, symlink `node_modules`/`public` rather than copying,
  keep the fixture page set minimal for the pure schema cases, and reserve
  the full-site copy for the markup-rendering cases. `npm test` stays a
  single `node --test` invocation with no recursive `npm run build`.
- **Risks.**
  - *`.superRefine` on a collection schema.* If Astro's content layer were to
    reject a `ZodEffects` schema, every fixture build fails loudly in
    `test/journal-build.test.ts` on the very first valid case, not silently.
    Fallback if that happens: express the same rules as a discriminated union
    on `status` (three `z.strictObject` branches plus the ordering check),
    which stays inside the schema as the issue requires.
  - *Closure automation writing wrong evidence.* Mitigated by verification
    order (ancestry before selection, selection before write), by the
    conflict check against `main`, by the allowed-field diff guard, by
    dry-run, and by the fact that the workflow only opens a PR — the release
    owner still merges it through CI, review and a merge commit.
  - *Duplicate release deliveries.* Mitigated by the deterministic branch and
    PR, the concurrency group, and the "already complete → no-op" path that
    makes R2 (the metadata patch release) produce nothing.
  - *App token scope.* Scoped to `mctlhq/portfolio` with contents and
    pull-requests write only, mirroring the release workflow; no access to
    `mctl-gitops` and no ability to merge or approve.
  - *Column count on narrow screens.* Nine columns with two hidden leaves
    seven at 390px; the table already scrolls horizontally inside a focusable
    region, and the reviewer step covers the visual check in both languages.
