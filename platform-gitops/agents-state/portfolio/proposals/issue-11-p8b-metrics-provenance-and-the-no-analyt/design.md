# Design: issue-11-p8b-metrics-provenance-and-the-no-analyt

## Current state

### The snapshot is consumed but never produced

`src/data/metrics.json` is the P4 placeholder, 18 lines, every value `null`:

```json
{
  "generated_at": null,
  "sources": {
    "github": { "collected_at": null, "method": "placeholder", "repos": null, "commits": null, "releases": null },
    "mctl":   { "collected_at": null, "method": "placeholder", "services": null, "devloop_proposals": null }
  }
}
```

`src/lib/metrics.ts` is a deliberately zero-import module. Its header comment says why:
"no `astro:content`, no `astro/loaders`, no `zod`, and ... no import of a sibling module
either ... This keeps the module importable by plain `node --test`, with no build step, so
`test/metrics.test.ts` can exercise the real logic and **P8b's generator can reuse
`metricProblems` without pulling in Astro**." The module exports `EM_DASH`, `formatStat`,
`snapshotDate`, the `Metrics` / `MetricSourceGithub` / `MetricSourceMctl` interfaces, and
`metricProblems`, which walks the parsed object and returns one string per problem.
`sourceProblems` takes an explicit `metricKeys` list, so unknown keys are currently neither
validated nor rejected.

`src/pages/index.astro` and `src/pages/approach.astro` both do
`import raw from '../data/metrics.json'`, `const metrics = raw as Metrics`, and
`snapshotDate(metrics.generated_at)`. Home renders four `<Stat>` tiles
(`github.repos`, `github.commits`, `github.releases`, `mctl.services`); approach renders
three inside a `<Details>` (`mctl.devloop_proposals`, `mctl.services`, `github.releases`).
`src/components/Stat.astro` renders `formatStat(value)` inside `<span class="stat-value"
data-stat>`. Because every value is `null`, every tile on the live site is an em dash today.

`src/components/ProjectCard.astro` already has the hole this proposal fills:

```astro
<p class="project-metrics">
  <Lang en={ui.workMetricsLabel.en} ru={ui.workMetricsLabel.ru} />{' '}
  <span data-stat><slot name="metrics">{formatStat(null)}</slot></span>
</p>
```

`src/pages/work.astro` renders `<ProjectCard en={entry} ru={ru.get(entry.data.slug)!} />`
and never fills the `metrics` slot, so every card falls through to the em-dash default.

### What already exists around it

- `src/content.config.ts` gives `projects` a `repo` field validated as
  `/^https:\/\/github\.com\/[^\s]+$/`, and `checkProjectParity` requires the `en` and `ru`
  files of a slug to agree on it. Thirteen of the fourteen project slugs carry a `repo`;
  twelve are under `mctlhq/`, one is `mashkoffdmitry/pelican-libertex-social`, and
  `pfeifenpatenschaft-backend` has none.
- `src/lib/adr.ts` exports `ADR_SECTIONS = ['Context', 'Decision', 'Consequences',
  'Drivers', 'Revisit criteria']` and `adrBodyProblems`, which requires the five sections in
  that order, a `class="l ru"` span on every heading, and both an `.l.en` and an `.l.ru`
  block in every section body. `adrLoader()` in `src/content.config.ts` wraps the glob loader
  to run `checkAdrBodies` over the whole store on `astro sync`, `check`, `dev` and `build`,
  and also checks the frontmatter `id` against the four-digit filename prefix.
- `src/content/adr/` holds `0001`, `0002` and `0005`. **0004 is free.**
  `src/pages/colophon/index.astro` builds its ADR table from `getCollection('adr')` sorted by
  `byAdrId`, and `src/pages/colophon/adr/[...slug].astro` emits one page per public entry —
  so a new ADR file needs no page change at all. `scripts/check-dist.mjs`
  (`checkColophonPages`) independently re-scans `src/content/adr` and asserts that every
  public entry got a page.
- `package.json` scripts: `"prebuild": "npm run vendor && npm test"`,
  `"test": "node --test test/journal.test.ts test/adr.test.ts test/metrics.test.ts ..."` —
  ten test files, one `node --test` invocation, no other command. `.github/workflows/build.yml`
  runs `npm ci` then `npm test` on every pull request to `main`.
- `scripts/vendor-assets.mjs` and `scripts/check-dist.mjs` set the house style for scripts in
  this repo: `#!/usr/bin/env node`, a long header comment stating what the script gates and
  why, `ROOT` resolved from `import.meta.url`, problems accumulated into an array and printed
  all at once, `process.exitCode = 1` rather than `process.exit`.

### The typed-number survey

Running the exact grep from the issue over the three target directories:

```
$ grep -rnoE "\b[0-9]{2,}\b" src/pages src/components src/layouts | wc -l
26
$ grep -rloE "\b[0-9]{2,}\b" src/pages src/components src/layouts
src/components/CycleDiagram.astro
```

**All 26 matches are in one file**, and they fall into exactly two kinds:

1. One match on line 7, `import { ui } from '../i18n/ui';` — the `18` of `i18n`, a
   directory name.
2. Twenty-five SVG geometry values in `buildWide()` / `buildNarrow()` and the `<marker>`
   definition: `112`, `44`, `24`, `160`, `296`, `432`, `568`, `30`, `226`, `12`, `60`, `300`,
   `64`, `40`, `320`, `10`, `2000`, and so on — box widths, column origins, path
   coordinates, a `viewBox` extent, marker dimensions.

`src/pages/404.astro` contains no digit: the string lives in `ui.notFoundTitle`
(`'Not found'` / `'Страница не найдена'`) and `404` appears only in the filename, which the
content grep does not see. `src/i18n/ui.ts` contains zero matches for `\b[0-9]{2,}\b` today —
worth knowing, because the issue scopes the gate to three directories and `ui.ts` is not one
of them.

`CycleDiagram.astro`'s own header comment already anticipates this gate: "Props-less: it
imports only `ui`, never the metrics snapshot and never renders a stat tile, so the
coordinate digits below can never be mistaken for a typed metric."

## Proposed solution

Six changes, in dependency order.

### 1. `scripts/snapshot-metrics.mjs` — split collection from assembly

The script is two layers so that determinism is testable offline, without a network or a
token. `npm test` has neither.

**Pure layer**, exported from the same file:

```js
export function buildMetrics({ github, mctl, previous }, now) -> object
```

`github` and `mctl` are plain collected data, `previous` is the parsed contents of the
existing `src/data/metrics.json` (used only for the `MCTL_TOKEN`-absent carry-forward), and
`now` is an injected `Date`. `buildMetrics` does no I/O: it shapes the object, sorts
`per_repo` keys with `Array.prototype.sort()` over `Object.keys`, sums the totals, and stamps
the three timestamps from `now` via `toISOString()` (which yields UTC ending in `Z` and
matches `src/lib/metrics.ts`'s `ISO_WITH_OFFSET`). Because `now` is a parameter, a test can
call `buildMetrics` twice with the same fixture and two different `now` values and assert
that everything except the three timestamps is deep-equal — which is acceptance criterion 1
made checkable in `npm test`.

**Collection layer**, run only from `main()`:

- `GH_TOKEN` is required; absent, the script prints the missing variable and sets
  `process.exitCode = 1` **before** touching `src/data/metrics.json`.
- Repositories: `GET /orgs/mctlhq/repos?per_page=100&type=all`, paginated, plus a single
  `GET /repos/mashkoffdmitry/pelican-libertex-social`. Archived repositories are filtered out
  by a named constant `INCLUDE_ARCHIVED = false` with a comment stating the choice (see Open
  questions in `requirements.md`). The list is sorted by `full_name` so downstream iteration
  is stable.
- Commits per repository: `GET /repos/{owner}/{name}/commits?sha={default_branch}&per_page=1`
  and read the page count out of the `Link` header's `rel="last"` URL — one request per
  repository instead of walking every page. For `mctlhq/mctl-openclaw` the same call carries
  `&author=<identity>` for each entry of a named constant
  `OWNER_IDENTITIES = ['mashkoffdmitry']`, and the counts are summed; this is how "excluding
  the upstream history of forks" is implemented for the one fork in the set. A repository
  with no `Link` header has one page, so the count is the length of a `per_page=100` fetch.
- `first_commit_at` / `last_commit_at`: `last_commit_at` is the `commit.committer.date` of
  the first entry on page 1; `first_commit_at` is the last entry of the final page, fetched
  with the page number already known from the `Link` header. Both use the same `author`
  filter as the commit count for `mctl-openclaw`, so the window matches the number.
- Releases per repository: `GET /repos/{owner}/{name}/tags?per_page=100`, paginated, counting
  names matching `/^\d+\.\d+\.\d+$/` — git tags, not the GitHub Releases API, exactly as the
  issue specifies and consistent with `AGENTS.md`'s "semver tags without a `v` prefix".
- `devloop_proposals`: `GET /repos/mctlhq/mctl-gitops/contents/platform-gitops/agents-state`
  lists the per-service directories; for each, a contents call on
  `<service>/proposals` and a count of its `dir` entries. GitHub token only — no `MCTL_TOKEN`.
- `services`: `GET https://api.mctl.ai/api/v1/services` with
  `Authorization: Bearer ${MCTL_TOKEN}`. If `MCTL_TOKEN` is unset, the call is skipped, the
  previous file's `sources.mctl.services` is carried forward, and `stale` is set `true`.
  Otherwise `stale` is `false`.
- Every request goes through one `ghFetch(url)` helper with a bounded retry (three attempts,
  fixed backoff) that throws on a non-2xx it cannot retry. `main()` wraps collection in a
  `try`/`catch`; on throw it prints the failing request and exits non-zero **without
  writing**, so a half-collected snapshot never lands on disk.
- Before writing, `main()` calls `metricProblems` imported from `../src/lib/metrics.ts` and
  refuses to write if it returns anything. Node 24 strips types from a `.ts` import natively,
  which is already how `test/*.test.ts` import these modules, so the `.mjs` script can import
  the `.ts` module directly — and this is exactly the reuse `src/lib/metrics.ts` was written
  for.
- Serialisation: `JSON.stringify(value, null, 2) + '\n'`, with key order fixed by the literal
  in `buildMetrics` and `per_repo` rebuilt from sorted keys.

`package.json` gains `"metrics": "node scripts/snapshot-metrics.mjs"`.

### 2. The snapshot's shape

```json
{
  "generated_at": "2026-09-11T12:00:00Z",
  "sources": {
    "github": {
      "collected_at": "2026-09-11T12:00:00Z",
      "method": "gh api: repos of org mctlhq plus mashkoffdmitry/pelican-libertex-social; commits and releases per repository via the REST API",
      "repos": 0,
      "commits": 0,
      "releases": 0,
      "per_repo": {
        "mctlhq/mctl-api": {
          "commits": 0,
          "releases": 0,
          "first_commit_at": "2026-01-01T00:00:00Z",
          "last_commit_at": "2026-09-10T00:00:00Z"
        }
      }
    },
    "mctl": {
      "collected_at": "2026-09-11T12:00:00Z",
      "method": "mctl_list_services via api.mctl.ai and count of platform-gitops/agents-state/*/proposals directories in mctlhq/mctl-gitops",
      "services": 0,
      "devloop_proposals": 0,
      "stale": false
    }
  }
}
```

Both `method` strings are copied character for character from the issue. The zeros above are
placeholders in this design document only; the committed file carries whatever
`npm run metrics` produces.

### 3. `src/lib/metrics.ts` — extend, keep zero imports

Add to the existing module, without adding an import:

```ts
export interface MetricRepo {
  commits: number | null;
  releases: number | null;
  first_commit_at: string | null;
  last_commit_at: string | null;
}
```

`MetricSourceGithub` gains `per_repo: Record<string, MetricRepo>`; `MetricSourceMctl` gains
`stale: boolean`. `metricProblems` gains a `perRepoProblems` pass reusing the existing
`metricValueProblems` and `timestampProblems` helpers, reporting under paths such as
`sources.github.per_repo["mctlhq/mctl-api"].commits`, and a boolean check for
`sources.mctl.stale`. Two new pure exports:

```ts
/** 'https://github.com/mctlhq/mctl-api' -> 'mctlhq/mctl-api'; anything else -> null. */
export function repoKey(repoUrl: string | undefined): string | null

/** The per_repo entry for a project's repo URL, or an all-null entry. */
export function repoMetrics(metrics: Metrics, repoUrl: string | undefined): MetricRepo
```

`repoMetrics` returning an all-null `MetricRepo` rather than `undefined` is what makes the
`pfeifenpatenschaft-backend` case (no `repo` frontmatter) render em dashes through the
existing `formatStat(null)` path instead of needing a conditional in the template.

### 4. `ProjectCard.astro` — fill its own slot

The component imports the snapshot itself (it is a build-time JSON import; `work.astro`
would otherwise have to thread it through fourteen call sites) and replaces the
`<slot name="metrics">` default:

```astro
import { formatStat, repoMetrics, snapshotDate, type Metrics } from '../lib/metrics';
import rawMetrics from '../data/metrics.json';

const metrics = rawMetrics as Metrics;
const repo = repoMetrics(metrics, en.data.repo);
const date = snapshotDate(metrics.generated_at);
```

rendered as label/value pairs reusing existing bilingual strings, so **no new copy is
required and no Russian number-dependent plural form arises**:

```astro
<p class="project-metrics">
  <Lang en={ui.workMetricsLabel.en} ru={ui.workMetricsLabel.ru} />{' '}
  <span data-stat>
    <Lang en={ui.statCommits.en} ru={ui.statCommits.ru} /> {formatStat(repo.commits)},{' '}
    <Lang en={ui.statReleases.en} ru={ui.statReleases.ru} /> {formatStat(repo.releases)}
  </span>{' '}
  <Lang en={`${ui.statCaptionPrefix.en} ${date}`} ru={`${ui.statCaptionPrefix.ru} ${date}`} />
</p>
```

`ui.statCommits` is `'Commits' / 'Коммиты'`, `ui.statReleases` is `'Releases' / 'Релизы'`,
`ui.statCaptionPrefix` is `'Snapshot' / 'Снимок'` — all already in `src/i18n/ui.ts`. Every
`<Lang>` emits one `.l.en` and one `.l.ru`, so the parity that `scripts/check-dist.mjs`
enforces holds by construction. No literal digit enters the file, so the new grep gate stays
green. The `<slot name="metrics">` is dropped, since nothing ever filled it.

Home and approach pages need **no source change**: they already read every value from the
snapshot, and replacing the placeholder JSON is what turns their em dashes into numbers.

### 5. `scripts/check-no-metrics.mjs` — two-tier allowlist

The script walks `src/pages`, `src/components`, `src/layouts`, applies
`/\b[0-9]{2,}\b/g` line by line, and classifies every match. Two tiers, because the issue's
two demands pull in different directions — "fails on any match that is not a CSS size, a year
in copy or an ISO date" is a set of general kinds, while "every permitted match is listed in
the script with the reason it is allowed" wants a concrete, auditable inventory.

**Tier 1 — `RULES`**: pattern classifiers, each with a `reason`, applied to the matched text
in its line context. `ISO date` (`\d{4}-\d{2}-\d{2}`), `year in copy` (a bare `19xx`/`20xx`),
`CSS length` (the match is immediately followed by `px`, `rem`, `em`, `%`, `vh`, `vw`, `ch`),
`module specifier` (the match lies inside a quoted `import`/`from` path, which is what
catches the `18` of `../i18n/ui`). An unused rule is fine — these are forward-looking kinds
the issue named.

**Tier 2 — `ALLOW`**: explicit per-file entries for anything a rule cannot classify, each
naming the file, the exact permitted values, and the reason:

```js
const ALLOW = [
  {
    file: 'src/components/CycleDiagram.astro',
    values: [10, 12, 24, 30, 40, 44, 60, 64, 112, 160, 226, 296, 300, 320, 432, 568, 2000],
    reason:
      'SVG geometry for the DevLoop cycle diagram: box width/height, column origins, ' +
      'path coordinates, viewBox extent and <marker> dimensions. The component is ' +
      'props-less and never imports src/data/metrics.json, so none of these can be a ' +
      'metric value. See the file header comment.',
  },
];
```

A match is permitted if a `RULES` entry classifies it or an `ALLOW` entry for that file lists
its value. Anything else is a problem, printed as `file:line: matched "NNN" — not permitted`.
**A stale `ALLOW` entry is also a problem**: after the scan, any `ALLOW` file that no longer
exists, or any listed value that matched nothing, fails the run. Without that, the allowlist
would quietly outlive the code it excused and the justification in it would stop being true.
The script prints an `OK -- N matches, all permitted` summary line on success, in the style
of `scripts/check-dist.mjs`.

`package.json` becomes
`"test": "node scripts/check-no-metrics.mjs && node --test test/journal.test.ts ... test/metrics-build.test.ts"`,
so the gate runs in `npm test`, therefore in `prebuild`, therefore in
`.github/workflows/build.yml` — no workflow edit needed.

The exact `values` list above is derived from the survey in **Current state** and must be
regenerated by the implementer from the tree as it stands at implementation time, not copied
blind: if `CycleDiagram.astro` has changed, the stale-entry check will say so.

### 6. `src/content/adr/0004-no-analytics.md`

The full file, to be committed verbatim. `AGENTS.md` requires the proposal to carry the copy
rather than point at it.

````markdown
---
id: 4
title:
  en: "No analytics, no cookies, no third-party beacons"
  ru: "Без аналитики, без cookie, без сторонних маяков"
status: accepted
date: '2026-09-11'
visibility: public
---

## <span class="l en">Context</span><span class="l ru">Контекст</span>

<div class="l en">

The site publishes numbers about its own construction and asks the reader to treat them as verifiable. The reflex that comes with publishing anything on the web is to add an analytics snippet and start counting readers. That question has to be answered deliberately here, because the same page that carries a Content-Security-Policy with no third-party origin, and a build gate that fails on an absolute-URL subresource, cannot quietly load a tracker. Nothing about the purpose of this site depends on knowing who reads it.

</div>

<div class="l ru" lang="ru">

Сайт публикует числа о собственном устройстве и просит читателя считать их проверяемыми. Рефлекс, сопровождающий любую публикацию в вебе, — добавить сниппет аналитики и начать считать читателей. Этот вопрос здесь нужно решить осознанно: та же страница, у которой в Content-Security-Policy нет ни одного стороннего источника, а сборочная проверка падает на подресурсе с абсолютным URL, не может тихо подгрузить трекер. Ничто в назначении этого сайта не зависит от того, кто его читает.

</div>

## <span class="l en">Decision</span><span class="l ru">Решение</span>

<div class="l en">

The site runs no analytics. It sets no cookies, loads no third-party beacons, and issues no request to any origin other than its own. Visitor counts are not a goal of this site. The only numbers it publishes are the ones in src/data/metrics.json, each carrying a collected_at and a method, and each produced by scripts/snapshot-metrics.mjs rather than typed.

</div>

<div class="l ru" lang="ru">

Сайт не использует аналитику. Он не ставит cookie, не загружает сторонние маяки и не обращается ни к одному источнику, кроме собственного. Подсчёт посетителей не является целью этого сайта. Единственные публикуемые им числа — это числа из src/data/metrics.json, каждое со своими collected_at и method, и каждое получено скриптом scripts/snapshot-metrics.mjs, а не набрано вручную.

</div>

## <span class="l en">Consequences</span><span class="l ru">Последствия</span>

<div class="l en">

There is no audience data and there will be none: no page-view totals, no referrer breakdown, no retention curve. A question about traffic can be answered only from the nginx access log of the running container, and only while that log is retained. The Content-Security-Policy stays short, because no third-party origin has to be allowed in script-src, connect-src or img-src. No cookie banner is needed, because there is no cookie to consent to. The zero-third-party-request property stays mechanically checkable: scripts/check-dist.mjs already fails the build on any absolute-URL subresource in dist/.

</div>

<div class="l ru" lang="ru">

Данных об аудитории нет и не будет: ни суммы просмотров, ни разбивки по источникам переходов, ни кривой удержания. Ответить на вопрос о трафике можно только по журналу доступа nginx в работающем контейнере и только пока этот журнал хранится. Content-Security-Policy остаётся коротким, потому что ни один сторонний источник не нужно разрешать в script-src, connect-src или img-src. Баннер согласия на cookie не нужен, потому что нет ни одной cookie, на которую нужно соглашаться. Свойство «ни одного стороннего запроса» остаётся проверяемым механически: scripts/check-dist.mjs уже роняет сборку на любом подресурсе с абсолютным URL в dist/.

</div>

## <span class="l en">Drivers</span><span class="l ru">Движущие факторы</span>

<div class="l en">

Privacy: a reader owes this site no data in exchange for reading it. Zero third-party requests: every byte the browser fetches comes from one origin, which is what makes the vendored design tokens and fonts worth their page weight. A simpler Content-Security-Policy: a policy with no third-party origin in it is one a reviewer can read in full and hold in mind.

</div>

<div class="l ru" lang="ru">

Приватность: читатель ничего не должен этому сайту в обмен на чтение. Ноль сторонних запросов: каждый байт, который получает браузер, приходит из одного источника — ради этого и стоит вес встроенных дизайн-токенов и шрифтов. Более простой Content-Security-Policy: политику, в которой нет ни одного стороннего источника, рецензент может прочитать целиком и удержать в голове.

</div>

## <span class="l en">Revisit criteria</span><span class="l ru">Критерии пересмотра</span>

<div class="l en">

Revisit if a concrete need appears that cannot be answered from the server logs: a specific question, named in advance, whose answer would change a decision about the site. Curiosity about the size of the audience is not such a need.

</div>

<div class="l ru" lang="ru">

Пересмотреть, если появится конкретная потребность, на которую нельзя ответить по журналам сервера: заранее сформулированный вопрос, ответ на который изменил бы решение о сайте. Любопытство относительно размера аудитории такой потребностью не является.

</div>
````

The five headings and their order match `ADR_SECTIONS` in `src/lib/adr.ts` exactly, and the
Russian heading words match those already used in
`src/content/adr/0002-static-astro-no-client-bundles.md`, so `adrBodyProblems` returns `[]`.
Every `<div class="l en">` has its `<div class="l ru" lang="ru">` partner, keeping
`check-dist.mjs`'s parity count even.

### 7. The journal entry

`src/content/journal/2026-09-11-metrics-provenance-and-no-analytics.md`, matching the eight
existing entries and the `journal` schema in `src/content.config.ts`:

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/11
proposal_slug: issue-11-p8b-metrics-provenance-and-the-no-analyt
visibility: public
title:
  en: "Metrics provenance and the no-analytics decision"
  ru: "Происхождение метрик и решение об отказе от аналитики"
decided:
  en: "Every number comes from one generated snapshot carrying a per-source method and collected_at; a committed grep gate fails the build on a number typed into a template; ADR-0004 records that the site runs no analytics."
  ru: "Каждое число берётся из одного сгенерированного снимка с методом и collected_at по каждому источнику; закоммиченная grep-проверка роняет сборку на числе, набранном в шаблоне; ADR-0004 фиксирует, что сайт не использует аналитику."
issue_opened_at: '<created_at of issue 11, quoted, from the GitHub API>'
interventions: []
---
```

`pr`, `release`, `merged_at`, `released_at` and `deployed_at` are `.optional()` in the schema
and are not known while the branch is open, so they are omitted. `issue_opened_at` is
required: the implementer reads it from
`GET /repos/mctlhq/portfolio/issues/11` and quotes it so YAML does not parse it into a Date,
as the schema's error message instructs. A body with `.l.en` / `.l.ru` blocks follows the
shape of the existing entries.

## Alternatives

**Collect through the `mctl` MCP tools and the `gh` CLI instead of `fetch`.** The `method`
string names `mctl_list_services` and `gh api`, which reads like an instruction to shell out.
Dropped: the script has to run under `npm run metrics` on a developer machine and inside a
DevLoop container, and shelling out makes it depend on two binaries being installed and
authenticated in a particular way. The issue itself resolves this by specifying
`GET https://api.mctl.ai/api/v1/services` with `MCTL_TOKEN` and the GitHub contents API —
plain HTTP. The `method` strings stay verbatim because they describe the provenance in the
reader's terms, not the transport.

**Walk every page of every repository's commit list to count commits.** Correct and obvious,
but for the larger repositories it is hundreds of requests per run, which makes a rate-limit
failure the normal case and the run slow enough to discourage re-running. Dropped in favour
of reading the `rel="last"` page number out of the `Link` header on a `per_page=1` request —
one request per repository, same number, and it is what the `Link` header is for.

**Make `npm test` run the real generator to prove determinism.** This is the literal reading
of acceptance criterion 1, and it is the wrong place: `npm test` runs in `prebuild` and in
the Docker build, neither of which has `GH_TOKEN`, `MCTL_TOKEN` or a guaranteed network. It
would turn a pure test suite into a flaky, credentialed one. Dropped in favour of splitting
`buildMetrics` out as a pure function and asserting determinism against a committed fixture,
with the live double-run named as a reviewer step. `AGENTS.md` sanctions exactly this split:
work that genuinely needs an external resource "is a reviewer step named as such, never an
acceptance criterion".

**A line-number-keyed allowlist in `check-no-metrics.mjs`.** Simplest to generate, and it
would satisfy "every permitted match is listed". Dropped: line numbers rot on the first
unrelated edit to `CycleDiagram.astro`, and the failure mode is a red build with a misleading
message. Keying on file plus matched value survives reformatting, and the stale-entry check
keeps it honest.

**Thread the snapshot into `ProjectCard` as a prop from `work.astro`.** More explicit about
the data flow. Dropped: `metrics.json` is a static build-time import with no per-instance
variation, `Stat.astro` already takes the value as a prop while the pages do the importing,
and a prop here would add a required argument to every one of the fourteen call sites in
`work.astro` for no gain in testability.

## Platform impact

**Migrations.** None. `src/data/metrics.json` is a committed build input; the change is a
content replacement plus two added keys (`sources.github.per_repo`, `sources.mctl.stale`).
No database, no ArgoCD values, no chart change. The service is not yet onboarded
(`MCTL_ONBOARDED` gate in `AGENTS.md`), so no deployment behaviour changes.

**Backward compatibility.** `metricProblems` today ignores unknown keys, so an old snapshot
without `per_repo` would validate — but `ProjectCard` would then read `undefined.per_repo`.
`repoMetrics` guards this by returning an all-null `MetricRepo` when `per_repo` is missing or
the key is absent, so an out-of-date snapshot degrades to em dashes rather than a build
crash. `test/metrics.test.ts`'s first assertion —
`metricProblems(realFile)` deep-equals `[]` — keeps working because the regenerated file is
validated by the same function before being written.

**Resource impact.** One extra Node process in `npm test` (`check-no-metrics.mjs`), scanning
roughly twenty small files; negligible. The generator is not in any build path: `prebuild` is
`npm run vendor && npm test`, and `metrics` is a separate manually invoked script, so a
Docker build never reaches for `GH_TOKEN`. Page weight rises slightly on `/work/` (two short
bilingual label/value pairs per card, fourteen cards); `check-dist.mjs`'s 40 KB cap applies
to `dist/index.html` only, which this change does not touch, but the bilingual-parity check
covers every page and will catch an unbalanced `<Lang>`.

**Risks and mitigations.**

- *GitHub rate limiting mid-run.* A partial snapshot would be worse than a stale one.
  Mitigated by collecting everything before writing anything, bounded retries in `ghFetch`,
  and one request per repository for the commit count.
- *`per_repo` key drift.* If a project's `repo` frontmatter names a repository outside the
  counted set, its card silently shows em dashes. Mitigated by `repoMetrics` returning
  all-null (no crash) and by a test asserting that every `repo` in `src/content/projects/*.en.md`
  either resolves to a `per_repo` key or is the known `pfeifenpatenschaft-backend` case —
  so drift is a red test, not a quietly blank card.
- *The allowlist becoming a rubber stamp.* Mitigated by the stale-entry failure: an
  allowance that stops matching fails the run, so the inventory cannot drift away from the
  code.
- *The gate's blind spot.* `src/i18n/ui.ts` holds all user-facing copy and is not scanned,
  so a number typed there would reach the page unchecked. It contains zero `\b[0-9]{2,}\b`
  matches today. Extending the scan is out of scope per the issue; the gap is recorded here
  and in `requirements.md` so a later cycle can close it deliberately.
- *ADR numbering.* `0003` is unused and this proposal takes `0004`, as the issue specifies.
  `adrLoader` cross-checks the frontmatter `id` against the filename prefix, so a mismatch
  fails `astro build` rather than shipping.
