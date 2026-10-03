# P8b: Metrics provenance and the no-analytics decision

## Context

The site already renders every number through one snapshot file. `src/pages/index.astro`
and `src/pages/approach.astro` both `import raw from '../data/metrics.json'`, cast it to
the `Metrics` interface in `src/lib/metrics.ts`, and pass values into `Stat.astro`, which
renders them with `formatStat()`. `AGENTS.md` states the rule this enforces: "Every number
shown on the site comes from `src/data/metrics.json`, which carries `generated_at` and a
per-source `collected_at` and `method`. Numbers are never typed into templates or content."

What is missing is the other half. `src/data/metrics.json` today is the P4 placeholder:
every value is `null` and both `method` strings read `"placeholder"`, so every stat tile on
the site renders an em dash. There is no script that produces the file, so the provenance
claim is currently an assertion rather than a reproducible fact, and nothing mechanically
stops a future change from typing a number straight into a template. This proposal adds the
generator (`scripts/snapshot-metrics.mjs`, wired as `npm run metrics`), extends the snapshot
with per-repository figures so `ProjectCard.astro` can show real numbers, adds the grep gate
that keeps typed numbers out of the templates, and records the decision to run no analytics
as ADR-0004 — the ADR that `AGENTS.md` says lands "in the cycle that wires up metrics
provenance".

## User stories

- AS a reader of the site I WANT every number to carry a snapshot date and a stated method
  SO THAT I can tell what the number counts and when it was true.
- AS a reader of a project card I WANT the commit and release counts for that specific
  repository SO THAT the claim in the card's prose is backed by a figure I could re-derive.
- AS the site owner I WANT one command that regenerates the whole snapshot SO THAT
  refreshing the numbers is a re-run rather than an editing session.
- AS a reviewer I WANT a committed script that fails the build on a typed number SO THAT
  the "numbers are never typed" rule is checked by the test suite and not by my attention.
- AS a visitor who cares about privacy I WANT a written, dated decision that the site runs
  no analytics SO THAT the absence of tracking is a stated commitment rather than an
  oversight.

## Acceptance criteria (EARS)

### The generator

- WHEN an operator runs `npm run metrics` THE SYSTEM SHALL execute
  `scripts/snapshot-metrics.mjs` and overwrite `src/data/metrics.json`.
- WHEN `scripts/snapshot-metrics.mjs` writes `src/data/metrics.json` THE SYSTEM SHALL set
  `generated_at` to an ISO 8601 timestamp in UTC ending in `Z`.
- WHEN `scripts/snapshot-metrics.mjs` collects the GitHub source THE SYSTEM SHALL write
  `sources.github` with `collected_at` (ISO 8601, UTC), `method` set exactly to
  `"gh api: repos of org mctlhq plus mashkoffdmitry/pelican-libertex-social; commits and releases per repository via the REST API"`,
  `repos`, `commits`, `releases`, and `per_repo`.
- WHEN `scripts/snapshot-metrics.mjs` computes `sources.github.repos` THE SYSTEM SHALL count
  the repositories of the `mctlhq` organisation plus
  `mashkoffdmitry/pelican-libertex-social`.
- WHEN `scripts/snapshot-metrics.mjs` computes `sources.github.commits` THE SYSTEM SHALL sum
  the default-branch commit count of every counted repository, excluding the upstream history
  of forks.
- WHILE counting commits for `mctlhq/mctl-openclaw` THE SYSTEM SHALL count only commits
  authored by the owner's GitHub identities, so that the upstream history the fork inherited
  is excluded.
- WHEN `scripts/snapshot-metrics.mjs` computes `sources.github.releases` THE SYSTEM SHALL sum,
  over every counted repository, the number of git tags whose name matches `^\d+\.\d+\.\d+$`.
- WHEN `scripts/snapshot-metrics.mjs` writes `sources.github.per_repo` THE SYSTEM SHALL emit
  one entry per counted repository, keyed `"<owner>/<name>"`, each holding `commits`,
  `releases`, `first_commit_at` and `last_commit_at`.
- WHEN `scripts/snapshot-metrics.mjs` collects the mctl source THE SYSTEM SHALL write
  `sources.mctl` with `collected_at` (ISO 8601, UTC), `method` set exactly to
  `"mctl_list_services via api.mctl.ai and count of platform-gitops/agents-state/*/proposals directories in mctlhq/mctl-gitops"`,
  `services` and `devloop_proposals`.
- WHEN `scripts/snapshot-metrics.mjs` computes `sources.mctl.devloop_proposals` THE SYSTEM
  SHALL read the directory listing of `platform-gitops/agents-state` in `mctlhq/mctl-gitops`
  through the GitHub contents API and count the `proposals` directories beneath it.
- WHEN `scripts/snapshot-metrics.mjs` computes `sources.mctl.services` THE SYSTEM SHALL issue
  `GET https://api.mctl.ai/api/v1/services` authenticated with the `MCTL_TOKEN` environment
  variable.
- IF the `MCTL_TOKEN` environment variable is absent THEN THE SYSTEM SHALL keep the
  `sources.mctl.services` value already present in `src/data/metrics.json`, set
  `sources.mctl.stale` to `true`, and still exit zero.
- IF the `MCTL_TOKEN` environment variable is present and the service count is collected
  THEN THE SYSTEM SHALL set `sources.mctl.stale` to `false`.
- IF the `GH_TOKEN` environment variable is absent THEN THE SYSTEM SHALL exit non-zero
  naming the missing variable, and SHALL NOT overwrite `src/data/metrics.json`.
- WHILE producing the GitHub half of the snapshot THE SYSTEM SHALL require no credential
  other than `GH_TOKEN`.
- WHEN `scripts/snapshot-metrics.mjs` is run twice in succession against unchanged upstream
  state THE SYSTEM SHALL produce two files that differ only in `generated_at` and the two
  `collected_at` values.
- WHEN `scripts/snapshot-metrics.mjs` serialises `src/data/metrics.json` THE SYSTEM SHALL
  emit object keys in a fixed order, `per_repo` entries sorted by key, two-space indentation
  and a trailing newline.
- IF any HTTP request made by `scripts/snapshot-metrics.mjs` fails after its retries THEN
  THE SYSTEM SHALL exit non-zero naming the failing request, and SHALL NOT write a partial
  `src/data/metrics.json`.
- WHEN `scripts/snapshot-metrics.mjs` has assembled the snapshot THE SYSTEM SHALL validate it
  with `metricProblems` from `src/lib/metrics.ts` and exit non-zero, printing every problem,
  if that array is non-empty.

### The committed snapshot and its loader

- WHEN this proposal is implemented THE SYSTEM SHALL commit a `src/data/metrics.json`
  produced by running `scripts/snapshot-metrics.mjs`, replacing the P4 placeholder in which
  every value is `null` and both `method` strings read `"placeholder"`.
- WHILE `src/data/metrics.json` is committed THE SYSTEM SHALL hold non-empty strings in
  `sources.github.method` and `sources.mctl.method`, and a non-null `collected_at` in both
  sources.
- WHEN a component or page needs a number THE SYSTEM SHALL obtain it through
  `src/lib/metrics.ts`, and no component, page or layout shall parse `src/data/metrics.json`
  by any other route.
- WHEN `src/lib/metrics.ts` types the snapshot THE SYSTEM SHALL expose `per_repo` and
  `stale` on the existing `Metrics` interface, and SHALL expose a lookup that maps a
  project's `repo` URL to its `per_repo` entry.
- WHEN `metricProblems` validates a snapshot THE SYSTEM SHALL report a problem for any
  `per_repo` entry whose `commits` or `releases` is neither `null` nor a non-negative
  integer, and for any `first_commit_at` or `last_commit_at` that is neither `null` nor an
  ISO 8601 timestamp with a timezone.
- WHILE `src/lib/metrics.ts` is a module imported by `test/metrics.test.ts` and by
  `scripts/snapshot-metrics.mjs` THE SYSTEM SHALL keep its import list empty, so it stays
  loadable by plain `node --test` and by the generator without a build step.

### What the pages render

- WHEN the home page renders its stat tiles THE SYSTEM SHALL show the real `repos`,
  `commits`, `releases` and `services` values from the snapshot together with the snapshot
  date.
- WHEN the approach page renders its numbers THE SYSTEM SHALL show the real
  `devloop_proposals`, `services` and `releases` values from the snapshot together with the
  snapshot date.
- WHEN `ProjectCard.astro` renders a project whose `repo` frontmatter names a repository
  present in `sources.github.per_repo` THE SYSTEM SHALL show that repository's `commits` and
  `releases` alongside the snapshot date.
- IF a project has no `repo` frontmatter, or its repository has no `per_repo` entry, THEN
  THE SYSTEM SHALL render the em dash that `formatStat(null)` returns rather than omitting
  the row or failing the build.
- WHILE any page renders a metric THE SYSTEM SHALL keep the counts of `class="l en"` and
  `class="l ru"` equal in the emitted HTML, so `scripts/check-dist.mjs` continues to pass.
- WHEN `ProjectCard.astro` labels a metric THE SYSTEM SHALL reuse the existing bilingual
  strings `ui.statCommits`, `ui.statReleases` and `ui.statCaptionPrefix` from
  `src/i18n/ui.ts`, so no number-dependent Russian plural form is required.

### The typed-number gate

- WHEN `npm test` runs THE SYSTEM SHALL execute `scripts/check-no-metrics.mjs` and fail the
  command if that script exits non-zero.
- WHEN `scripts/check-no-metrics.mjs` runs THE SYSTEM SHALL scan every file under
  `src/pages`, `src/components` and `src/layouts` for the pattern `\b[0-9]{2,}\b`.
- IF `scripts/check-no-metrics.mjs` finds a match that is not covered by an allowance
  recorded in the script THEN THE SYSTEM SHALL exit non-zero, naming the file, the line and
  the matched text.
- WHILE `scripts/check-no-metrics.mjs` permits a match THE SYSTEM SHALL carry, inside the
  script itself, the reason that match is allowed — a CSS size, a year in copy, an ISO date,
  SVG diagram geometry, or a module specifier such as `../i18n/ui` — so the justification
  lives in the repository rather than in a pull request description.
- IF an explicit per-file allowance in `scripts/check-no-metrics.mjs` no longer matches
  anything in the scanned tree THEN THE SYSTEM SHALL exit non-zero naming the stale
  allowance, so the allowlist cannot silently outlive the code it excused.
- WHEN `scripts/check-no-metrics.mjs` runs against the tree as implemented THE SYSTEM SHALL
  exit zero, with every allowance accounted for by the SVG geometry and module-specifier
  matches in `src/components/CycleDiagram.astro`.

### ADR-0004

- WHEN this proposal is implemented THE SYSTEM SHALL add
  `src/content/adr/0004-no-analytics.md` with frontmatter `id: 4`, `status: accepted`,
  `visibility: public`, a bilingual `title`, and a `date`.
- WHILE `src/content/adr/0004-no-analytics.md` exists THE SYSTEM SHALL carry the five
  sections `Context`, `Decision`, `Consequences`, `Drivers` and `Revisit criteria`, in that
  order, each heading carrying both a `class="l en"` and a `class="l ru"` span and each
  body carrying both a `class="l en"` and a `class="l ru"` block, so `adrBodyProblems` in
  `src/lib/adr.ts` returns an empty array for it.
- WHEN ADR-0004 states its decision THE SYSTEM SHALL record that the site runs no analytics,
  sets no cookies and loads no third-party beacons, and that visitor counts are not a goal of
  the site.
- WHEN ADR-0004 states its drivers THE SYSTEM SHALL name privacy, zero third-party requests
  and a simpler Content-Security-Policy.
- WHEN ADR-0004 states its revisit criteria THE SYSTEM SHALL name a concrete need that cannot
  be answered from server logs.
- WHEN the colophon index renders THE SYSTEM SHALL list ADR-0004 in its ADR table and emit
  `dist/colophon/adr/0004-no-analytics/index.html`, both by way of the existing
  `getCollection('adr')` call in `src/pages/colophon/index.astro` and the existing
  `src/pages/colophon/adr/[...slug].astro` route, with no change to either file.

### Journal

- WHEN this cycle is implemented THE SYSTEM SHALL add one journal entry under
  `src/content/journal/` naming issue 11 and this proposal slug, as `AGENTS.md` requires one
  entry per DevLoop cycle.

## Out of scope

- Scheduling `scripts/snapshot-metrics.mjs`. It is run inside a DevLoop cycle when the
  numbers need refreshing; no cron, no GitHub Actions schedule, no workflow trigger is added.
- Any change to the platform API. `GET https://api.mctl.ai/api/v1/services` is consumed as it
  exists today.
- Editing `AGENTS.md`. It is human-owned.
- Editing `.github/workflows/claude-review.yml`, `.github/workflows/release-please.yml` or
  `.github/dependabot.yml`, which `AGENTS.md` reserves to humans.
- Adding analytics, telemetry or any measurement of visitors. ADR-0004 records the decision
  not to; it does not introduce a mechanism to be switched on later.
- Extending the typed-number scan beyond `src/pages`, `src/components` and `src/layouts`.
  `src/i18n/ui.ts` and `src/content/**` are not scanned by this gate.
- Changing `scripts/check-dist.mjs`, `scripts/csp-hash.mjs` or `scripts/vendor-assets.mjs`.
- Backfilling historical snapshots. `src/data/metrics.json` holds one current snapshot, not
  a time series.

## Open questions

- **Which identities count as "the owner's identities" for `mctl-openclaw`?** The issue says
  to count only the owner's commits there but does not enumerate the identities. Proceeding
  with a named constant in the script holding the GitHub login `mashkoffdmitry`, passed as
  the `author` parameter to the commits endpoint, and documented in a comment so a second
  identity can be added as a one-line change. A reviewer should confirm the resulting
  `mctlhq/mctl-openclaw` commit count looks right.
- **Does `repos` include archived and private repositories?** The issue says "repos of org
  mctlhq" without qualification. Proceeding with every non-archived repository the `GH_TOKEN`
  can enumerate, plus the one external repository, with the choice stated in a comment. If
  the owner wants archived repositories counted, that is a one-constant change.
- **"Identical numbers" in acceptance criterion 1 versus the timestamps.** Two runs a minute
  apart necessarily differ in `generated_at` and `collected_at`. Read as: every value that is
  not a timestamp is identical. The offline determinism test asserts exactly that.
- **`stale: false` when the token is present.** The issue only specifies setting
  `stale: true` when `MCTL_TOKEN` is missing. Proceeding with an always-present boolean so
  the file's shape is stable and `metricProblems` can validate it; a reviewer who prefers the
  key absent on the happy path should say so.
- **When `MCTL_TOKEN` is missing, is `devloop_proposals` still refreshed?** It is read through
  the GitHub API and needs no mctl credential. Proceeding with: `devloop_proposals` is
  collected fresh, `services` carries forward, `collected_at` is updated, and `stale: true`
  flags that the source is partly carried forward.
- **Should the journal entry be part of this cycle's diff?** The issue's file list omits it,
  but `AGENTS.md` requires one entry per cycle and the eight existing entries follow that
  rule. Proceeding with adding one; if the reviewer intends the journal entry to land
  separately, drop task 11.
