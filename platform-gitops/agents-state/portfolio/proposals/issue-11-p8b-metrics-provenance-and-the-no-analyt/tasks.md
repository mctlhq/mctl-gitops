# Tasks: issue-11-p8b-metrics-provenance-and-the-no-analyt

- [ ] 1. Extend `src/lib/metrics.ts` with the `MetricRepo` interface, `per_repo` on
  `MetricSourceGithub`, `stale` on `MetricSourceMctl`, and the pure helpers `repoKey`
  (`https://github.com/<owner>/<name>` to `<owner>/<name>`, anything else to `null`) and
  `repoMetrics` (returns an all-null `MetricRepo` when `per_repo` is missing or the key is
  absent) — DoD: the module's import list is still empty, `npm run check` passes, and
  `node --test test/metrics.test.ts` still passes unchanged.

- [ ] 2. Extend `metricProblems` in `src/lib/metrics.ts` to validate `sources.github.per_repo`
  (each entry's `commits`/`releases` via the existing `metricValueProblems`, each
  `first_commit_at`/`last_commit_at` via `timestampProblems`, reported under paths such as
  `sources.github.per_repo["mctlhq/mctl-api"].commits`) and `sources.mctl.stale` as a boolean
  (depends on 1) — DoD: a malformed `per_repo` entry and a non-boolean `stale` each produce a
  problem naming their path; a well-formed snapshot produces none.

- [ ] 3. Write `scripts/snapshot-metrics.mjs` with the pure/collection split from `design.md`:
  an exported `buildMetrics({ github, mctl, previous }, now)` that performs no I/O, sorts
  `per_repo` keys, sums the totals and stamps the three timestamps from the injected `now`;
  plus a `main()` that collects (depends on 2) — DoD: `buildMetrics` is importable and
  callable with a fixture and no network; the file follows the house style of
  `scripts/check-dist.mjs` (shebang, header comment stating what it produces and why,
  `ROOT` from `import.meta.url`, problems accumulated and printed together).

- [ ] 4. Implement the GitHub collection in `scripts/snapshot-metrics.mjs`: paginated
  `GET /orgs/mctlhq/repos` plus `GET /repos/mashkoffdmitry/pelican-libertex-social`, filtered
  by a commented `INCLUDE_ARCHIVED = false` constant and sorted by `full_name`; per-repository
  commit counts read from the `rel="last"` page number of a
  `commits?sha={default_branch}&per_page=1` request, with `&author=` per entry of a commented
  `OWNER_IDENTITIES = ['mashkoffdmitry']` constant for `mctlhq/mctl-openclaw` only;
  `first_commit_at`/`last_commit_at` from the first and last pages under the same filter;
  release counts from paginated `tags` filtered by `/^\d+\.\d+\.\d+$/` (depends on 3) — DoD:
  `sources.github.method` is the issue's string character for character; the GitHub half needs
  no credential beyond `GH_TOKEN`; a missing `GH_TOKEN` exits non-zero before any write.

- [ ] 5. Implement the mctl collection in `scripts/snapshot-metrics.mjs`: `devloop_proposals`
  from the GitHub contents API over `platform-gitops/agents-state` in `mctlhq/mctl-gitops`
  (counting `proposals` directories), and `services` from
  `GET https://api.mctl.ai/api/v1/services` with `Authorization: Bearer ${MCTL_TOKEN}`; when
  `MCTL_TOKEN` is absent, skip that call, carry `services` forward from the existing
  `src/data/metrics.json`, and set `stale: true` (`false` otherwise) (depends on 4) — DoD:
  `sources.mctl.method` is the issue's string character for character; a run with `MCTL_TOKEN`
  unset exits zero, preserves the previous `services` value and sets `stale: true`.

- [ ] 6. Wire the write path: bounded retries in a single `ghFetch` helper, all collection
  inside one `try`/`catch` so a failed request exits non-zero without writing a partial file,
  `metricProblems` (imported from `../src/lib/metrics.ts`) run on the assembled object and the
  write refused if it reports anything, and serialisation as
  `JSON.stringify(v, null, 2) + '\n'` with fixed key order (depends on 5) — DoD: forcing a
  request failure leaves `src/data/metrics.json` byte-identical to what it was before the run.

- [ ] 7. Add `"metrics": "node scripts/snapshot-metrics.mjs"` to `package.json` scripts
  (depends on 6) — DoD: `npm run metrics` runs the script; `prebuild` and `build` are
  unchanged and never invoke it.

- [ ] 8. Run `npm run metrics` with `GH_TOKEN` and `MCTL_TOKEN` set and commit the resulting
  `src/data/metrics.json`, replacing the P4 placeholder (depends on 7) — DoD: no value in the
  file is `null` that the sources could supply, both `method` strings are the issue's strings,
  both `collected_at` values are present, `stale` is `false`, and `per_repo` has one entry per
  counted repository.

- [ ] 9. Rewrite the `<p class="project-metrics">` block in `src/components/ProjectCard.astro`
  to import `src/data/metrics.json` and `repoMetrics`/`snapshotDate`/`formatStat` from
  `../lib/metrics`, and render `ui.statCommits` / `ui.statReleases` label-value pairs plus
  `ui.statCaptionPrefix` and the snapshot date; drop the now-unused `<slot name="metrics">`
  (depends on 8) — DoD: no new string is added to `src/i18n/ui.ts`; no literal digit appears
  in the file; each card shows its repository's commits and releases, and
  `pfeifenpatenschaft-backend` (no `repo`) shows em dashes; `<Lang>` usage keeps `.l.en` and
  `.l.ru` counts equal.

- [ ] 10. Write `scripts/check-no-metrics.mjs` with the two-tier allowlist from `design.md`:
  `RULES` pattern classifiers (ISO date, year in copy, CSS length, module specifier), each
  carrying its `reason`; `ALLOW` explicit per-file entries, each naming file, permitted values
  and reason, with the `src/components/CycleDiagram.astro` SVG-geometry entry regenerated from
  the tree as it stands after task 9; failure on any unclassified match **and** on any stale
  `ALLOW` file or value that matched nothing (depends on 9) — DoD:
  `node scripts/check-no-metrics.mjs` exits zero on the implemented tree and prints an
  `OK -- N matches, all permitted` summary; introducing a literal `12345` into
  `src/pages/index.astro` makes it exit non-zero naming file, line and matched text.

- [ ] 11. Add `src/content/adr/0004-no-analytics.md` exactly as written in `design.md`
  section 6, including the frontmatter and both language blocks of all five sections — DoD:
  `npm run check` passes (so `adrBodyProblems` returns `[]` and the frontmatter `id: 4`
  matches the filename prefix); `npm run build` emits
  `dist/colophon/adr/0004-no-analytics/index.html`; the colophon ADR table lists it; no page
  or route file is edited to achieve this.

- [ ] 12. Add the journal entry
  `src/content/journal/2026-09-11-metrics-provenance-and-no-analytics.md` using the
  frontmatter in `design.md` section 7, reading `issue_opened_at` from
  `GET /repos/mctlhq/portfolio/issues/11` and quoting it so YAML does not parse it into a
  Date, with an `.l.en` / `.l.ru` body following the existing entries (depends on 11) — DoD:
  `npm run check` passes; `scripts/check-dist.mjs`'s `data-cycle-count` and `data-cycle-row`
  counts rise by one together and the run still exits zero.

- [ ] 13. Change `package.json`'s `test` script to
  `node scripts/check-no-metrics.mjs && node --test <existing ten files> test/metrics-build.test.ts`
  (depends on 10 and the tests below) — DoD: `npm test` runs the gate and all eleven test
  files; a failing gate fails `npm test`; `.github/workflows/build.yml` is not edited, because
  it already runs `npm test`.

## Tests

- [ ] T1. `test/metrics-build.test.ts` — determinism: call the exported `buildMetrics` twice
  with one committed fixture and two different `now` values; assert the two results are
  deep-equal after deleting `generated_at` and both `collected_at`. This is acceptance
  criterion 1 made checkable without a network or a token.

- [ ] T2. `test/metrics-build.test.ts` — carry-forward: `buildMetrics` with `mctl.services`
  absent (the `MCTL_TOKEN`-missing case) and a `previous` snapshot returns the previous
  `services` value with `stale: true`; with a collected value it returns that value with
  `stale: false`.

- [ ] T3. `test/metrics-build.test.ts` — shape and provenance: `buildMetrics` output passes
  `metricProblems` with an empty array, `sources.github.method` and `sources.mctl.method`
  equal the issue's two strings character for character, both `collected_at` values are
  non-null, `sources.github.commits`/`releases` equal the sums of the `per_repo` entries, and
  `per_repo` keys come out sorted.

- [ ] T4. `test/metrics.test.ts` — extend the existing suite: `metricProblems` reports a
  `per_repo` entry with a negative `commits`, a float `releases`, and a `first_commit_at` that
  is not an ISO timestamp with a timezone; and a non-boolean `sources.mctl.stale`. Keep the
  existing assertion that `metricProblems` returns `[]` for the real
  `src/data/metrics.json`, which now exercises the regenerated file.

- [ ] T5. `test/metrics.test.ts` — `repoKey('https://github.com/mctlhq/mctl-api')` is
  `'mctlhq/mctl-api'`, a trailing slash is tolerated, `undefined` and a non-GitHub URL give
  `null`; `repoMetrics` returns the matching entry for a known key and an all-null
  `MetricRepo` for `undefined`, for an unknown key, and for a snapshot with no `per_repo`.

- [ ] T6. `test/projects.test.ts` — every `repo:` value across `src/content/projects/*.en.md`
  resolves through `repoKey` to a key present in `src/data/metrics.json`'s `per_repo`, except
  `pfeifenpatenschaft-backend`, which is asserted to have no `repo` field. This turns
  `per_repo` key drift into a red test rather than a quietly blank card.

- [ ] T7. `test/projects.test.ts` — source-level assertions on
  `src/components/ProjectCard.astro`, in the style of `test/home.test.ts`: it imports
  `../data/metrics.json`, it renders commits and releases only through `formatStat(...)`
  expressions rooted at the `repoMetrics(...)` result, the template after the frontmatter
  fence contains no digit, and it no longer contains `slot name="metrics"`.

- [ ] T8. Self-check of the gate: a test that runs `scripts/check-no-metrics.mjs` against a
  temporary fixture tree containing one permitted match (an ISO date in copy) and one
  forbidden match (a bare `12345`), asserting a non-zero exit whose output names the file,
  the line and `12345`; and a second fixture with an `ALLOW` value that matches nothing,
  asserting the stale-allowance failure.

- [ ] T9. `test/adr.test.ts` needs no change — `adrBodyProblems` is exercised generically and
  `adrLoader` validates `0004-no-analytics.md` on `astro sync`/`check`/`build`. Confirm by
  running `npm run check` and `npm run build` after task 11.

## Reviewer steps (not acceptance criteria)

- [ ] R1. Run `npm run metrics` twice within a minute with both tokens set and confirm the two
  files differ only in `generated_at` and the two `collected_at` values. This is the live form
  of acceptance criterion 1; T1 is its offline proxy, because `npm test` has neither tokens
  nor a guaranteed network.
- [ ] R2. Eyeball the committed `src/data/metrics.json`: in particular the
  `mctlhq/mctl-openclaw` commit count, which is filtered to `OWNER_IDENTITIES` to exclude the
  fork's upstream history, and the `repos` total against the archived-repository choice.
- [ ] R3. Open `/work/` in a browser, switch to Russian, and confirm the per-card commit and
  release figures and the snapshot date read correctly in both languages.

## Rollback

Every change in this cycle is additive or a content replacement in one repository, with no
migration and no deployment side effect — the service is not yet onboarded, so nothing is
running that this can break.

- **Whole cycle.** Revert the merge commit on `main`. `src/data/metrics.json` returns to the
  all-`null` P4 placeholder, every stat tile returns to an em dash, ADR-0004 disappears from
  the colophon (the route and the index are derived from `getCollection('adr')`, so no page
  edit is needed to undo it), and `npm test` returns to the ten-file `node --test` command.
  Nothing external has to be undone: no cron was created, no platform API was touched, no
  gitops value was changed.
- **Just the gate**, if `scripts/check-no-metrics.mjs` proves too noisy in practice: drop the
  `node scripts/check-no-metrics.mjs && ` prefix from `package.json`'s `test` script. The
  script stays committed and runnable by hand; only the build stops failing on it. One-line
  change, no other file affected.
- **Just the numbers**, if a snapshot turns out to be wrong: `git checkout <previous-sha> --
  src/data/metrics.json` and commit. The loader, the gate and ADR-0004 are independent of the
  file's contents, and `repoMetrics` degrades a missing or stale `per_repo` to em dashes
  rather than a build failure, so an older snapshot renders cleanly.
- **Just ADR-0004**: delete `src/content/adr/0004-no-analytics.md`. `0004` is then free again;
  no other file references it by number.
