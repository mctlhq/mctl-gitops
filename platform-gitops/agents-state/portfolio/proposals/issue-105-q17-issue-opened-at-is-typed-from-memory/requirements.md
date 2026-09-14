# Q17: issue_opened_at comes from a recorded source

## Context

`issue_opened_at` is the only lifecycle timestamp in a journal entry that a
human or an agent types from memory. Every other stamp (`merged_at`,
`released_at`) is written by `scripts/close-journal.mjs` from verified GitHub
evidence. The field is not decorative: `leadTimeHours()` in
`src/lib/journal.ts` computes `cycleEndTimestamp(entry) - issue_opened_at`,
`src/components/CycleTable.astro` renders that number on `/colophon/` for every
`complete` entry, and `src/pages/colophon/journal/[...slug].astro` renders the
raw stamp and the `formatInterval()` gaps on each entry's detail page. A wrong
value is therefore a wrong published number, and `AGENTS.md` requires every
published number to come from a recorded source.

Checked against the GitHub API, 26 of the 29 committed entries carry exactly
their issue's `created_at`; three do not, and the drift of each was confirmed
during this investigation:

| entry | issue | recorded | issue `created_at` | drift |
|---|---|---|---|---|
| `2026-09-13-q13-link-hit-areas-titles-indexing-and-share-image-alt.md` | portfolio#88 | `2026-09-13T10:52:14Z` | `2026-09-13T10:35:00Z` | +17m 14s |
| `2026-09-13-q14-ten-projects-and-service-links.md` | portfolio#89 | `2026-09-13T12:01:49Z` | `2026-09-13T10:39:03Z` | +1h 22m 46s |
| `2026-09-13-q16-compact-segmented-language-and-theme.md` | portfolio#103 | `2026-09-13T14:00:00Z` | `2026-09-13T21:26:33Z` | -7h 26m 33s (before the issue existed) |

Nothing catches this. `timestampOrderProblems()` only requires the lifecycle
stamps of one entry to be nondecreasing, and all three wrong values still
precede their own entry's later stages. `npm test` and the build stay green.
This proposal keeps the reading the other 26 entries already use -- the field
is the issue's `created_at` -- and stops it being typed from memory: the
proposal carries the recorded instant, the closure script re-resolves it
against the API at the one moment the number becomes publishable, and an
offline collection check catches the class of error that in-repo data alone can
prove.

## User stories

- AS a reader of `/colophon/` I WANT each published lead time to be measured
  from the instant the issue was actually opened SO THAT the number is evidence
  rather than a recollection.
- AS the repository owner I WANT a wrong `issue_opened_at` to be corrected
  automatically before the entry is published SO THAT catching it does not
  depend on someone comparing timestamps by hand.
- AS an implementer writing this cycle's journal entry I WANT the recorded
  instant handed to me in the proposal SO THAT I copy a value instead of
  inventing one.
- AS a contributor I WANT `docs/journal.md` to say what `issue_opened_at` means
  and where it comes from SO THAT the field is not a blank to fill.
- AS a reviewer I WANT the merge gate to stay runnable offline SO THAT a GitHub
  API blip cannot red-build correct code.

## Acceptance criteria (EARS)

Reading of the field

- WHILE any journal entry exists THE SYSTEM SHALL define `issue_opened_at` as
  the `created_at` of the GitHub issue named by that entry's `issue` field,
  copied verbatim to the second, and SHALL apply that one reading to every
  entry.
- WHEN `docs/journal.md` is read THE SYSTEM SHALL state that meaning and that
  source in one sentence, and SHALL name the proposal as where an implementer
  gets the value.

Corrections

- WHEN the three entries listed in the Context table are read after this change
  THE SYSTEM SHALL carry `issue_opened_at: '2026-09-13T10:35:00Z'` for
  `2026-09-13-q13-link-hit-areas-titles-indexing-and-share-image-alt.md`,
  `issue_opened_at: '2026-09-13T10:39:03Z'` for
  `2026-09-13-q14-ten-projects-and-service-links.md`,
  and `issue_opened_at: '2026-09-13T21:26:33Z'` for
  `2026-09-13-q16-compact-segmented-language-and-theme.md`, each single-quoted
  exactly as `test/colophon.test.ts` requires.
- WHILE those three entries are corrected THE SYSTEM SHALL change no other
  field of them: their `status`, `pr`, `release`, `merged_at`, `released_at`,
  `title`, `decided`, `interventions` and markdown body stay byte for byte as
  they are.
- WHEN this cycle's own journal entry is created THE SYSTEM SHALL record
  `issue_opened_at: '2026-09-13T22:07:31Z'`, the `created_at` of
  `https://github.com/mctlhq/portfolio/issues/105`.

Resolution against a recorded source (closure)

- WHEN `scripts/close-journal.mjs` closes an entry whose `issue` URL names a
  `mctlhq/portfolio` issue THE SYSTEM SHALL resolve that issue's `created_at`
  through the injected GitHub client and write it into the closure pull
  request's `issue_opened_at`, alongside the `pr`, `release`, `merged_at` and
  `released_at` it already writes.
- IF the resolved `created_at` differs from the value recorded in the entry
  THEN THE SYSTEM SHALL log both instants and the entry id before writing the
  corrected value.
- IF the entry's `issue` URL names a repository other than `mctlhq/portfolio`,
  or the issue lookup returns no issue, THEN THE SYSTEM SHALL keep the recorded
  value, log that the stamp was not resolved and why, and SHALL still complete
  the closure.
- WHILE `close-journal.mjs` writes a closure THE SYSTEM SHALL confine the diff
  to `status`, `pr`, `release`, `merged_at`, `released_at` and
  `issue_opened_at`, and SHALL still refuse to write when main or the branch
  differs outside those fields.
- WHEN `npm test` runs THE SYSTEM SHALL exercise the new resolution path
  against the existing injected fake client in `test/journal-closure.test.ts`,
  with no network access and no token.

Offline collection check

- WHILE the journal collection loads THE SYSTEM SHALL require that, among
  entries whose `issue` URLs name the same repository, `issue_opened_at` is
  nondecreasing in issue number; equal instants are permitted.
- IF two entries of the same repository violate that order THEN THE SYSTEM
  SHALL fail `astro sync`, `astro check`, `astro dev` and `astro build` with a
  diagnostic naming both entry ids, both issue numbers and both instants.
- WHILE the check runs THE SYSTEM SHALL make no network request and SHALL
  impose no constraint on the order in which cycles are executed: an entry for
  an older backlog issue may be created and completed after a newer one.
- WHEN an entry's `issue` URL does not match
  `https://github.com/<owner>/<repo>/issues/<number>` THE SYSTEM SHALL skip
  that entry in this check rather than fail.

Carried P3 from the #103 review

- WHEN `src/styles/site.css` is read THE SYSTEM SHALL carry a comment above the
  `.site-nav a, .site-footer a` rule that claims 44px only for the selectors
  that rule covers, and SHALL NOT claim that every interactive element on the
  page is at least 44px tall.

Gate behaviour

- WHILE the pre-merge gate (`.github/workflows/build.yml`) runs THE SYSTEM
  SHALL require no GitHub API call: `npm run build` and `npm test` SHALL pass
  with no network beyond the npm registry install step.

## Out of scope

- Any change to what `leadTimeHours()` computes or to how
  `src/components/CycleTable.astro` or
  `src/pages/colophon/journal/[...slug].astro` render it. The published numbers
  change only because their input is corrected.
- The other lifecycle stamps (`merged_at`, `released_at`, `deployed_at`) and
  the matching, ancestry and release-selection logic of
  `scripts/close-journal.mjs`.
- Re-opening the Q16 header work or the Q18 icon-toggle work; only the stale
  CSS comment is touched.
- A network-dependent required check of any kind, and any new workflow that
  calls the GitHub API.
- Editing `AGENTS.md`. Adding "the issue's `created_at`" as a sixth item of the
  issue contract there, and to the mctl-agents issue-investigator prompt that
  produces proposals, are owner actions recorded below as reviewer steps, not
  acceptance criteria.
- Backfilling a `created_at` for the three entries whose issues live in
  `mctlhq/mctl-api` and `mctlhq/mctl-agents`; all three were verified correct
  during this investigation and need no change.

## Open questions

- The one-cycle-at-a-time rule. At investigation time
  `src/content/journal/2026-09-14-q18-single-icon-button-toggles.md` is
  `status: in_progress`. `checkJournalCollection()` rejects a second
  `in_progress` entry, so this cycle's entry can only be created once the Q18
  entry has been closed by its release, which is the normal sequence. Nothing
  in this proposal changes that rule; recorded here because the implementer
  will hit it if the sequence is broken.
- Scope of the closure correction. As proposed, closure resolves the stamp only
  for the single `in_progress` entry it is closing. Re-resolving every entry on
  every release was rejected as a silent mass-rewrite of published data. A
  future cycle may add an explicit `--recheck-all` dry-run reporting mode; this
  proposal does not.
- The offline check is relative, not absolute. It proves a set of stamps cannot
  all be right; it cannot prove a single stamp is right, and a consistently
  shifted set satisfies it. That is the honest ceiling of what the repository's
  own data supports -- see design.md, "Current state", for the negative finding
  that no in-repo record of an issue's creation time exists.
- The durable fix for the next entry lives partly outside this repository: the
  issue-investigator prompt in `mctlhq/mctl-agents` is what makes every future
  proposal carry the instant. This proposal carries it for cycle #105 and sets
  the precedent; the prompt change is a reviewer step.
