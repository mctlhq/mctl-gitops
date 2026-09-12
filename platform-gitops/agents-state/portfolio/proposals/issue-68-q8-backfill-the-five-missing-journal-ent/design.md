# Design: issue-68-q8-backfill-the-five-missing-journal-ent

> **Operator amendment, applied before approval (2026-09-12).** The
> deliverable is **six** content files, not five: the five backfilled entries
> described throughout, plus **this cycle's own journal entry**, specified as
> Copy (normative) -> 6 in `requirements.md` and as task 6b in `tasks.md`.
> Every cycle writes its own entry; a backfill that repeats the omission it
> corrects has corrected nothing. Consequently the derived cycle counter is
> **20**, not 19, and `git status --porcelain` must list six added files.
> Where any sentence below says "five files" or "nothing else", read it as
> the five backfilled entries; the sixth is additive and changes nothing else
> about the scope, which remains content files only.

## Current state

**The collection.** `src/content.config.ts` defines `journal` with a `glob`
loader over `./src/content/journal`, pattern
`[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-*.md` and
`generateId: idFromFile` (`entry.replace(/\.md$/, '')`), so the entry id is
the filename without extension and a file whose name does not start with
`YYYY-MM-DD-` is invisible to the build. The schema is a `z.strictObject`, so
an unknown key is a build error, not a warning. Required: `service` (enum
including `portfolio`), `issue` (GitHub URL regex), `proposal_slug`,
`visibility` (`public` | `private`), `title` and `decided` (both
`z.strictObject({ en, ru })`), `issue_opened_at`. Optional: `pr`, `release`
(semver, no `v`), `proposal_approved_at`, `merged_at`, `released_at`,
`deployed_at`. `interventions` has `.default([])`.

Every timestamp goes through the shared `stamp` schema: a string refined by
`isoWithOffset` from `src/lib/journal.ts` and then transformed to a `Date`.
The refinement message states the reason explicitly — quote the value so YAML
does not parse it into a `Date` first, because a `Date` is not a string and
the refinement would reject it before the transform runs.

**The fourteen existing entries.** `src/content/journal/` holds fourteen
files, every one of them `visibility: public` — so `journal.length` is 14
today, not the 13 the issue's arithmetic assumes. The fourteenth is
`2026-09-12-q7-polish-wave-findings.md` (issue #52), approved at
`2026-09-12T12:36:04Z`, later than every cycle backfilled here; it had
evidently not landed when the issue was written. See "Platform impact" for
why the derived counter is therefore 20 and why that, neither 18 nor 19, is the value
the gates will demand.
`2026-09-11-p8-production-hardening-accessibility-wc.md` is the
shape this cycle copies: frontmatter only, no body, keys in the order
`service`, `issue`, `proposal_slug`, `visibility`, `title`, `decided`,
`issue_opened_at`, `proposal_approved_at`, with `merged_at`, `released_at`
and `deployed_at` absent. That file is the direct refutation of the belief
that cost the five entries. `2026-09-12-q7-polish-wave-findings.md` is the
other recent entry and additionally writes `interventions: []` explicitly.

**Where the counter comes from.** `src/pages/colophon/index.astro` does
`const journal = publicEntries(await getCollection('journal')).sort(byNewestFirst)`
and `const cycleCount = journal.length`, then renders
`<span data-cycle-count={cycleCount}>{cycleCount}</span>`. There is no
literal anywhere. `test/colophon.test.ts` asserts that the page matches
`/journal\.length/` and binds `data-cycle-count={cycleCount}`, which is what
keeps it that way. `scripts/check-dist.mjs` closes the loop from the other
side: `idsByVisibility(JOURNAL_DIR)` re-reads `src/content/journal/*.md` with
its own `VISIBILITY_RE`, and `checkColophonPages()` fails if
`data-cycle-count`, the `data-cycle-row` occurrence count or the set of
`dist/colophon/journal/<id>/index.html` files disagrees with that independent
scan. `buildSitemapExpectations()` (around line 804) does the same for the
sitemap URL list.

**How an entry renders.** `src/components/CycleTable.astro` maps `entries`
into rows: `isoDate(cycleTimestamp(entry.data))` for the date column, the
service, a link to `/colophon/journal/${entry.id}/` with the bilingual title,
`githubRef(entry.data.issue)`, `pr` or an em dash, `release` or an em dash,
`formatLeadTime(leadTimeHours(entry.data))`, and `interventionCount`.
`src/pages/colophon/journal/[...slug].astro` builds one page per public entry
via `getStaticPaths()`, renders a `<Breadcrumb>`, the bilingual title and
`decided`, a timeline filtered to the timestamps that are present, and the
interventions section. `description` is `clampDescription(data.decided.en)`
(160 characters, cut at a word boundary), so a long `decided` is handled by
existing code.

**How missing end timestamps behave.** `cycleEndTimestamp()` in
`src/lib/journal.ts` returns `deployed_at`, else `released_at`, else `null`;
`leadTimeHours()` returns `null` for that, and `formatLeadTime(null)` is an
em dash rendered inside `<span class="lead-time-missing">` with a
visually-hidden `ui.leadTimeMissing` explanation. `cycleTimestamp()` picks
the latest present stamp in the order deployed / released / merged / approved
/ opened, which for all five backfilled entries is `proposal_approved_at`.
`byNewestFirst` sorts on that, breaking ties on id descending.

**What the gates do and do not scan.** `scripts/check-no-metrics.mjs` walks
`src/pages`, `src/components` and `src/layouts` only — `SCAN_DIRS` is
literally those three — so prose figures in a content file are outside its
reach, as acceptance criterion 6 says and as `2026-09-12-q7-polish-wave-findings.md`
already demonstrates. `scripts/check-links.mjs` opens no socket: it extracts
hrefs from `dist/`, resolves internal ones against the built tree and reports
off-origin ones as skipped by count, so five more GitHub issue links add five
skipped entries and no network dependency. `scripts/check-dist.mjs` check (b)
requires an equal count of `class="l en"` and `class="l ru"` in every built
HTML file; `checkNavigationState()` rejects any `aria-label` mixing Latin and
Cyrillic, with a named exemption for the `.table-scroll` region on
`dist/colophon/index.html`. The 40 KB weight ceiling applies to
`dist/index.html` only, not to the colophon.

## Proposed solution

Add five files under `src/content/journal/` and change nothing else. The
exact bytes are in `requirements.md` under "Copy (normative)"; this section
explains why each property of those files is what it is.

**Filenames.** Each is `YYYY-MM-DD-<slug>.md`, matching the loader glob so
`generateId` yields the id the route and every gate expect. The date prefix
is the UTC date of that entry's `cycleTimestamp`, i.e. of
`proposal_approved_at`, which is also what the Date column prints via
`isoDate(cycleTimestamp(...))`:

| file | `proposal_approved_at` | Date column | prefix |
| --- | --- | --- | --- |
| csp-hash-quoting-and-browser-verified-headers | `2026-09-11T21:23:37Z` | 2026-09-11 | 2026-09-11 |
| content-link-contrast-and-an-offline-link-check | `2026-09-12T00:19:43Z` | 2026-09-12 | 2026-09-12 |
| repository-links-out-of-the-disclosure | `2026-09-12T04:24:45Z` | 2026-09-12 | 2026-09-12 |
| colophon-tables-and-computed-lead-time | `2026-09-12T06:32:13Z` | 2026-09-12 | 2026-09-12 |
| navigation-state-and-accessibility-affordances | `2026-09-12T07:14:28Z` | 2026-09-12 | 2026-09-12 |

Prefix and rendered date agree on all five, so the table never shows a row
whose date contradicts its own URL.

**Frontmatter shape.** Eight keys per file, in the order the existing entries
use. `service: portfolio` and `visibility: public` are written on all five;
the issue shows them only on file 1 because files 2-5 are abbreviated to the
lines that differ, and without `visibility: public` the entry would be
dropped by `publicEntries()` and would produce no page and no row. The three
late timestamps are omitted rather than invented — that omission is the
entire point of this cycle, and `leadTimeHours()` already renders it as a
labelled em dash rather than as a zero. `interventions` is omitted so the
schema default supplies `[]`; `check-dist.mjs` counts `- what:` occurrences
to derive `data-intervention-count`, and an absent key contributes nothing,
leaving that total exactly as it is today. `2026-09-12-q7-polish-wave-findings.md`
writes `interventions: []` explicitly; both forms are equivalent, and the
issue asks for the default, so the key is left out.

**YAML scalar style.** `title` and `decided` values are double-quoted
scalars, as in all fourteen existing entries. Files 3 and 4 contain straight
double quotes inside `decided.en` (`"Details"`, `"not recorded"`,
`"not implemented"`); those are escaped as `\"`, the YAML double-quoted
escape, which preserves the character exactly in the parsed string and
therefore in the rendered page. Timestamps stay single-quoted, which is what
`test/colophon.test.ts` asserts with `assert.match(value, /^'.*'$/)` before
re-testing the unquoted value against `ISO_WITH_OFFSET`. The em dashes,
guillemets and non-breaking-free Cyrillic in the copy are ordinary UTF-8 and
need no escaping.

**Bodies.** None. The file ends at the closing `---`, like every existing
entry; the journal route renders `data.decided` and never `entry.body`.

**Everything downstream is derived.** No template, script or test is touched.
`cycleCount` becomes 20 because `journal.length` is 20; `CycleTable` gains
five `data-cycle-row` rows because it maps over the collection;
`getStaticPaths()` emits five more pages because it maps over
`publicEntries()`; the sitemap gains five URLs because
`@astrojs/sitemap` walks the built routes and `check-dist.mjs` derives the
expected list from the same content directory. The two independent
derivations — the page's `getCollection()` and the script's `readdir()` — can
only agree when the pages really are generated from the files, which is what
makes the counter evidence rather than an assertion. It is also why the
number cannot be pinned by hand: see the counter risk under "Platform
impact".

## Alternatives

**Write the missing timestamps too, reconstructing them from git and the
GitHub API.** Rejected. `merged_at` and `released_at` could plausibly be
recovered for some of the five, but `deployed_at` cannot be recovered at all,
and a partially reconstructed set would make `leadTimeHours()` report a
confident number for a cycle nobody measured. The issue states the values
below are read from GitHub and from the proposals' `.status.yaml`, not
reconstructed, and the schema was built to let an entry say "not recorded"
out loud. Backfilling only what is known is the smaller and more honest
change.

**Add one combined entry covering all five cycles.** Rejected. `AGENTS.md`
requires one entry per DevLoop cycle, and the cycle counter is `journal.length`;
a single merged entry would move the counter from 13 to 14 and misreport the
loop by four, reproducing the defect in a new form. It would also give five
distinct issues one `issue` field, which the schema cannot express.

**Relax or extend the schema so an entry can declare "timestamps not
recorded" explicitly, e.g. a `backfilled: true` flag.** Rejected. The schema
already encodes absence as absence, and `formatLeadTime(null)` plus
`ui.leadTimeMissing` already render and announce it distinctly from a
measured zero — that was the work of cycle 4 in this very wave. Adding a flag
would be a code change in a content-only cycle, would need matching template
and test work, and would introduce a second way to say what the optional
fields already say.

**Delete or privatise an existing entry so the counter lands on the 18 the
issue names.** Rejected, and named here only because the issue's criterion 5
could be misread as asking for it. Editing an existing entry is explicitly
out of scope, `visibility: private` on a real cycle would hide it from the
record, and either move would make the counter agree with a number by
falsifying the thing the number counts. The criterion's binding half is
"derived from `journal.length` — no literal count is introduced anywhere";
the "18" is stale arithmetic from before `2026-09-12-q7-polish-wave-findings.md`
merged.

**Do nothing and start writing entries again from the next cycle.**
Rejected. The counter would stay permanently five short, and the colophon's
claim to be a complete record of the loop would be false in a way no gate
detects — every guard here derives from the files, so a missing file is
invisible to all of them. That is exactly why this backfill has to be a
cycle of its own.

## Platform impact

- **Migrations.** None. No schema change, no data transformation, no
  redirect. Five new static routes appear; nothing existing moves or changes
  URL.
- **Backward compatibility.** Additive only. Every existing journal entry,
  page and permalink is untouched. `data-intervention-count` is unchanged;
  `data-cycle-count` rises by exactly six — 14 to 20 against the tree as it
  stands — which is the intended effect and is verified against an
  independent scan rather than against a literal.
- **Risk: pinning the cycle counter to the issue's stale 18.** The issue was
  written when thirteen entries existed; a fourteenth
  (`2026-09-12-q7-polish-wave-findings.md`) has since merged, so
  `journal.length` after this change is 20. `checkColophonPages()` in
  `scripts/check-dist.mjs` recomputes the expected value from its own
  `readdir()` of `src/content/journal`, so any attempt to make the page read
  18 fails the build, and there is no literal to edit in any case.
  Mitigation: change nothing outside the five new content files, and read
  criterion 5's binding clause as the derivation rather than the digits.
  Flagged as the first open question in `requirements.md` for the approving
  human.
- **Resource impact.** Five more pre-rendered pages and five more table rows.
  `dist/index.html` is unaffected, so the 40 KB ceiling in `check-dist.mjs`
  is not in play. Build time grows by the cost of parsing five small
  markdown files.
- **Risk: a YAML quoting mistake in the two entries with inner double
  quotes.** A naive double-quoted scalar containing an unescaped `"` ends the
  scalar early and produces a parse error or, worse, a truncated string.
  Mitigation: escape as `\"`, and verify by running `npm test` and
  `npm run build` — Zod's `strictObject` and the `min(1)` on each bilingual
  field fail loudly on a mangled value, and task T3 diffs the parsed strings
  against the normative copy.
- **Risk: an unquoted timestamp silently becoming a `Date`.** YAML would
  parse `2026-09-11T21:15:10Z` bare into a timestamp, and `isoWithOffset`
  would then reject a non-string. Mitigation: the values are single-quoted in
  the normative copy, and `test/colophon.test.ts` already fails on any
  timestamp line in any journal file whose value is not single-quoted.
- **Risk: a filename that does not match the loader glob.** A file named
  without the `YYYY-MM-DD-` prefix is silently ignored — no error, just a
  missing entry. Mitigation: `check-dist.mjs` compares the built pages
  against its own `readdir()` of the content directory, so a file present on
  disk but absent from `dist/` is reported as a missing page, not silently
  tolerated.
- **Risk: the copy drifting from the issue.** `AGENTS.md` makes the copy the
  contract. Mitigation: the full EN and RU text for all five entries is
  carried verbatim in `requirements.md`, so the implementer never has to read
  past the approval boundary or invent prose.
- **Security and privacy.** All five entries are `visibility: public` and
  name only public GitHub issues, public proposal slugs and public technical
  detail. No credential, no internal hostname, no third party, consistent
  with the `public` rule in `AGENTS.md`.
