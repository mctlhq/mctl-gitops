# Design: issue-105-q17-issue-opened-at-is-typed-from-memory

## Current state

**Where the value is consumed.** `src/lib/journal.ts` is an import-free module
(`node --test` runs it directly). `leadTimeHours(entry)` returns `null` unless
`isComplete(entry)`, then computes
`cycleEndTimestamp(entry).getTime() - toDate(entry.issue_opened_at).getTime()`
over 3,600,000, throwing `RangeError` if the end precedes the open.
`src/components/CycleTable.astro:41` calls it per row and renders
`formatLeadTime(leadTime)` on `/colophon/`.
`src/pages/colophon/journal/[...slug].astro:25` puts `data.issue_opened_at`
first in the entry's stamp list, so the raw value is user-visible even while
the entry is `in_progress`, and the `formatInterval()` gaps below it are
measured from it.

**Where it is validated.** `src/content.config.ts` types the field as `stamp`:
`isRealTimestamp` (ISO-with-offset shape plus real calendar fields) then
`.transform(s => new Date(s))`. The `.superRefine` maps
`journalEntryProblems()` onto `ctx.addIssue`. That is
`statusEvidenceProblems()` (status <-> evidence fields) plus
`timestampOrderProblems()`, which only requires the five lifecycle stamps of
one entry to be nondecreasing. All three wrong values sit before their own
entry's `merged_at`, so nothing fires. `journalLoader()` wraps the glob loader
and runs one collection-wide pass, `checkJournalCollection()`, which enforces
the at-most-one-`in_progress` rule and nothing else.

**Where the other stamps come from.** `scripts/close-journal.mjs` resolves the
implementation PR, verifies its merge commit is an ancestor of the release tag,
picks the earliest containing stable release, and calls `applyClosure()` to
write exactly `CLOSURE_FIELDS = ['status','pr','release','merged_at','released_at']`.
`closureDiffProblems()` proves the diff is confined to those keys.
Every API call goes through one injectable seam, `createGitHubClient()`, so
`run()` is exercised offline in `test/journal-closure.test.ts` against
`makeFakeGithub()`. The workflow `.github/workflows/journal-closure.yml` runs it
on `release: published` and on `workflow_dispatch` with a tag, under a GitHub
App token minted with `repositories: portfolio`, `permission-contents: write`,
`permission-pull-requests: write`. It is not a pull-request check: the required
gate is `.github/workflows/build.yml`, which runs `npm ci`, `npm run build`
(`prebuild` = `npm run vendor && npm test`), a `git diff --exit-code` on the
vendored tree, `scripts/check-links.mjs`, and a Docker build with
`scripts/check-headers.mjs`. None of those calls the GitHub API.

**Is there an in-repo record of when an issue was opened?** No. This was
checked, and the negative answer is a finding rather than a gap:
`src/data/metrics.json` records `generated_at`, a per-source `collected_at` and
`method`, and per-repository commit and release counts with
`first_commit_at` / `last_commit_at` -- no issue data at all, and
`scripts/snapshot-metrics.mjs` never fetches issues. `CHANGELOG.md` and
`.release-please-manifest.json` record releases. Git history records commit
times, which are not issue-creation times. The proposal directory that would
carry the investigator's reading lives in `mctlhq/mctl-gitops`, not here. So
the entry's own `issue_opened_at` is today the *only* record in this repository
of when its issue was opened, which is exactly why nothing could check it.

**The measured state of the data.** Every one of the 29 committed entries was
compared against its issue's `created_at` during this investigation. 26 agree
to the second, including the three entries whose issues live in other
repositories (`mctl-api#281`, `mctl-agents#330`, and `portfolio` for the rest).
Three disagree, exactly the three named in the issue, with exactly the
corrections the issue names. Recomputed published lead times, all `complete`
entries with no `deployed_at` (so end = `released_at`):

| entry | published now | after correction |
|---|---|---|
| q13 (#88) | `0.9` | `1.1` |
| q14 (#89) | `0.7` | `2.1` |
| q16 (#103) | `8.3` | `0.9` |

**The carried P3.** `src/styles/site.css:603` reads "Tap targets: every
interactive element on the page is at least 44px tall at any viewport width,
per the 360px acceptance criterion" above the `.site-nav a, .site-footer a`
rule. It is false twice over: the standalone-link rule below it sets 24px
(issue #88), and the header controls are a fixed 32px box -- now `.icon-toggle`
after Q18 replaced Q16's `.toggle-group` segmented pill (`site.css:190-204`).
`docs/accessibility-checklist.md:21` was already corrected and describes the
real state; `test/a11y.test.ts` enforces `MIN_TARGET_PX = 24` over eleven
`TARGET_SELECTORS`, so 24px is the actual floor the repository asserts.

## Proposed solution

One reading, applied everywhere: **`issue_opened_at` is the `created_at` of the
GitHub issue the entry's `issue` field names, verbatim to the second.** That is
already the reading of 26 of 29 entries, it is the only reading under which the
lead time measures what `/colophon/` claims it measures, and it is the only one
of the three readings currently in the data that has a recorded source. Three
layers make it hold, each in the place where it can hold without a network
dependency in the merge gate.

### Layer 1 -- the contract carries the fact (issue's option 1)

The investigator reads the issue through the API, so it can inline the instant.
This proposal does: issue #105 was created at `2026-09-13T22:07:31Z`, and
`requirements.md` makes copying that value into this cycle's own entry an
acceptance criterion. The same habit that makes a proposal carry user-visible
copy character for character now carries this one value.

Two supporting changes land in the repository:

- `docs/journal.md` gains the definition sentence and names the proposal as the
  source an implementer copies from, so the field stops being a blank. The doc
  is pinned byte for byte by `EXPECTED_DOCS` in `test/journal-workflow.test.ts`,
  so that constant moves with it, and a new targeted assertion pins the
  *meaning* (the sentence must name `issue_opened_at` and the issue's
  `created_at`) so a future rewrite cannot drop the definition by pasting new
  text into the byte-for-byte constant.
- Adding a sixth item to the `AGENTS.md` issue contract, and to the
  issue-investigator prompt in `mctlhq/mctl-agents`, is a reviewer step. The
  bootstrap boundary (ADR-0001) lists `AGENTS.md` among the files humans edit,
  and the prompt is in another repository; neither is an implementer commit.

### Layer 2 -- resolution against the recorded source, at the moment of publication

`leadTimeHours()` returns a number only for a `complete` entry, and an entry
becomes `complete` through `scripts/close-journal.mjs`. That script already
holds a GitHub token, already runs off the merge gate, and already writes four
stamps from recorded evidence. So the resolution belongs there:

- a pure helper `entryIssueRef(data)` parses the entry's `issue` URL into
  `{ owner, repo, number }` -- the existing `entryIssueNumber()` returns only
  the number, and the client's `REPO` constant is hardcoded to
  `mctlhq/portfolio`, so resolving `mctl-api#281` with it would silently fetch
  `portfolio#281`. That trap is the reason this helper exists;
- `createGitHubClient()` gains `getIssue(number)` (`GET /repos/{repo}/issues/{n}`,
  which already returns `{status: 404, json: null}` rather than throwing);
- `run()` resolves `created_at` only when `entryIssueRef()` names
  `mctlhq/portfolio` -- the App token is scoped `repositories: portfolio`, so a
  cross-repo lookup would 404 by construction -- and adds it to the `evidence`
  object. A different value is logged with both instants before it is written;
  an unresolvable one (other repository, or 404) is logged as an explicit
  non-resolution and the recorded value is kept. Closure never fails on it: a
  merged, released cycle must still close;
- `CLOSURE_FIELDS` gains `issue_opened_at`, and `applyClosure()` writes it the
  same way it writes the others, quoted, in place.

The effect is that the published number is always computed from an instant the
API confirmed, at the exact moment it becomes publishable, with no new network
dependency anywhere in the pre-merge gate. `test/journal-closure.test.ts`
proves it offline: `makeFakeGithub()` gains an `issue` fixture and the new
cases assert the corrected write, the drift log, the cross-repo skip and the
404 skip.

### Layer 3 -- the offline check the repository's own data supports (issue's option 2)

There is no in-repo value to resolve a single stamp against (see "Current
state"). There is, however, one real invariant over the set: **within one
repository, GitHub issue numbers increase with creation time.** So for entries
whose `issue` URLs name the same repository, `issue_opened_at` must be
nondecreasing in issue number. This needs no network and no new data -- only
the `issue` URLs and stamps already committed.

- `src/lib/journal.ts` gains `issueRef(url)` (returns `{repo, number}` or
  `null`) and `issueStampOrderProblems(entries)`, returning a problem per
  violating adjacent pair, naming both ids, both issue numbers and both
  instants; plus `checkIssueStampOrder(entries)`, which throws the aggregated
  list, mirroring `checkJournalCollection()`.
- `journalLoader()` in `src/content.config.ts` calls it immediately after
  `checkJournalCollection()`, so it runs on `astro sync`, `check`, `dev` and
  `build` alike and cannot be bypassed.
- Equal instants pass (GitHub `created_at` has one-second granularity and two
  issues can share a second). Entries whose URL does not parse are skipped.
- It constrains nothing about execution order. `docs/journal.md` already states
  "Issue opening dates do not determine execution order", and
  `test/journal-build.test.ts` has a fixture asserting a newer issue may run
  first; this check compares a stamp to its own issue number, never to another
  entry's position in the cycle sequence, so that fixture stays green.

Verified against the data: all four existing fixture sets in
`test/journal-build.test.ts` satisfy it unchanged, all 29 committed entries
satisfy it once the three corrections land, and today it fails on exactly one
pair -- `#98` at `18:51:12Z` followed by `#103` at `14:00:00Z`. That is the
value the issue calls impossible, and it is the one the network could not have
been needed to catch.

### The data corrections

The three stamps are set to their issues' `created_at`. Nothing else in those
three files changes.

### The carried P3

The comment above `.site-nav a, .site-footer a` is narrowed to those two
selectors and states the real floor: the standalone-link rule is 24px, the
header's `.icon-toggle` is a fixed 32px, and 24px is what `test/a11y.test.ts`
enforces. `src/styles` is not in `SCAN_DIRS` of `scripts/check-no-metrics.mjs`,
so pixel figures in this comment are not a gate concern.

## Alternatives

1. **A build-time check that fetches each issue's `created_at` and fails on
   drift.** Rejected, and the issue rules it out directly: it would put the
   GitHub API on the critical path of `.github/workflows/build.yml`, turning an
   API blip or a rate limit into a red build on correct code. It also cannot
   run on a developer machine or in the Docker build, neither of which has a
   token -- the same reason `scripts/snapshot-metrics.mjs` is explicitly kept
   out of `prebuild`.
2. **A separate informational, non-gating workflow that reports drift.**
   Priced and dropped. It would add a workflow, a token and an App-permission
   surface to produce an annotation nobody is required to read, and Layer 2
   already logs precisely that drift at the moment it matters, inside a run a
   human reviews. If a future cycle wants early reporting, the cheapest form is
   a `--recheck-all --dry-run` mode on the script that already exists, not a
   new workflow.
3. **Widening the closure App token to every repository that can own a journal
   issue.** Rejected: it enlarges a write-capable token's blast radius to fix
   three historical entries that are already correct. Skipping the resolution
   for non-`portfolio` issues, with an explicit log line, costs nothing and
   keeps the token scoped.
4. **A "no round timestamp" heuristic (reject `issue_opened_at` ending
   `:00:00`).** It would have caught `#103` and nothing else -- `#88` and `#89`
   drift by non-round amounts. It is a smell test, not a resolution against a
   source, and it red-builds a correct entry roughly once in 3,600 whenever an
   issue is genuinely opened on the minute. The issue-number monotonicity check
   catches the same entry for a real reason, so the heuristic buys nothing.
5. **Redefining the field as "the proposal attempt's start time"** (the reading
   `#89` accidentally encodes). Rejected: no such instant is recorded anywhere
   in this repository either, so it would move the problem rather than solve
   it, and it would make `/colophon/`'s lead time measure the loop's own
   latency rather than the cycle's, silently changing the meaning of every
   published number.

## Platform impact

**Migrations.** None. No schema field is added, renamed or removed;
`issue_opened_at` keeps its `stamp` type. Three data values change and three
published numbers change with them (`0.9 -> 1.1`, `0.7 -> 2.1`, `8.3 -> 0.9`).
No test pins a lead-time literal, so no expected-value fixture moves.

**Backward compatibility.** All 29 existing entries satisfy the new loader
check after the three corrections; the four fixture sets in
`test/journal-build.test.ts` satisfy it as they stand. `applyClosure()` writing
a sixth field is invisible to already-`complete` entries, which the script
never selects.

**Resource impact.** One additional GitHub API GET per closure run, which
happens once per release. The merge gate is unchanged and still runs with no
API access.

**Risks and mitigations.**

- *Widening `CLOSURE_FIELDS` weakens conflict detection for `issue_opened_at`:*
  `closureDiffProblems()` strips allowed keys from both sides, so a hand edit to
  that field on main would no longer be reported as a conflict. Mitigated by
  the mandatory log line naming both instants whenever the resolved value
  differs, and by the closure PR itself being a reviewed diff.
- *A correction could invert an entry's own lifecycle order* (a resolved
  `created_at` later than `merged_at`), making the closure PR fail the schema.
  This is the correct outcome -- it means the other stamps or the `issue` link
  are wrong -- and `docs/journal.md`'s Recovery section already routes
  conflicting evidence through review rather than a guess.
- *A correction could break the new monotonicity check on the closure PR.* Also
  correct: it means a neighbouring entry's stamp is wrong. The diagnostic names
  both entries, so the fix is mechanical.
- *The offline check is relative.* It cannot validate an isolated entry and a
  uniformly shifted set would satisfy it. Layer 2 is what makes each published
  value absolute; Layer 3 is the strongest statement the repository's own data
  can support, and `requirements.md` records that limit rather than implying
  more.
- *Cross-repository entries keep an unresolved stamp.* All three were verified
  correct during this investigation, and the script logs every skip, so the
  gap is visible rather than assumed away.
