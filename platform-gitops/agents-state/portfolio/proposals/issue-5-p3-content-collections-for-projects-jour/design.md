# Design: issue-5-p3-content-collections-for-projects-jour

## Current state

Read in the clone at `HEAD = 1a7abe4` ("Merge pull request #16 ... P2"):

- `src/` contains only `components/{Footer,LangToggle,Nav,ThemeToggle}.astro`,
  `i18n/{Lang.astro,ui.ts}`, `layouts/Base.astro`, `pages/{index,404}.astro`
  and `styles/site.css`. There is **no** `src/content/`, **no**
  `src/content.config.ts`, **no** `src/lib/`, **no** `test/` and no content
  collection anywhere in the project.
- `package.json` declares `astro: ^7.0.0`; `package-lock.json` resolves
  `astro@7.3.2`, whose own dependencies include `zod: ^4.5.4`, resolved to
  `zod@4.6.2`. So the `z` re-exported by `astro:content` is **zod 4**, where
  `z.object().strict()` is deprecated in favour of `z.strictObject()` and the
  string-format helpers moved to `z.iso.*` / top-level functions.
- `package.json` scripts today: `dev`, `prebuild` (→ `vendor`), `build`,
  `preview`, `check` (`astro check`), `vendor`. There is no `test` script and no
  test runner dependency. `devDependencies` are only `@astrojs/check` and
  `typescript`.
- `astro.config.mjs` sets `output: 'static'`, `site:
  'https://dmitriimashkov.com'`, `trailingSlash: 'always'`, and
  `build.inlineStylesheets: 'never'` with a comment explaining that the
  `style-src 'self'` CSP header forbids inlined `<style>`.
- `tsconfig.json` is just `{ "extends": "astro/tsconfigs/strict" }`.
- `src/i18n/Lang.astro` is the bilingual primitive: it renders
  `<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`.
  `src/styles/site.css` implements the switch with
  `:root[data-lang='en'] .l.ru { display: none }` and the mirror rule — a
  class-pair mechanism that works for any element, not only `<span>`.
- `src/layouts/Base.astro` carries the single `is:inline` preference script and
  links five stylesheets, one of which is `/styles/site.css`.
  `scripts/vendor-assets.mjs` copies `src/styles/site.css` to
  `public/styles/site.css` on `prebuild`; `.gitignore` ignores the generated
  copy (the exact ground of two P2 interventions).
- `scripts/csp-hash.mjs` walks `dist/**/*.html`, requires **exactly one**
  distinct inline `<script>` body and fails over 400 bytes. `Dockerfile` runs
  `npm run build && node scripts/csp-hash.mjs` and substitutes the hash into
  `nginx.conf`. Any new client-side script would break the image build, so this
  cycle must add none.
- `.dockerignore` excludes `.astro`, so the image build always performs a cold
  content sync — a loader-side validation cannot be skipped by a warm cache in
  CI.
- `AGENTS.md` already specifies this content model in prose: journal path,
  the five timestamps, `interventions: [{what, why, at}]`, "Lead time and the
  number of interventions are computed at build time, never written by hand",
  `visibility: public | private`, and ADR path `src/content/adr/NNNN-<slug>.md`
  in Nygard form plus Drivers and Revisit criteria. This cycle turns that prose
  into a schema.
- `.github/workflows/claude-review.yml` passes a `conventions` block that
  flags "any user-facing string present in only one of EN/RU" and "any
  client-side script other than the single inline preference script". Both
  constrain the design below.
- `.github/workflows/build.yml` only builds the Docker image on a PR; there is
  no separate `npm test` / `npm run check` job. The new `test` script is
  therefore developer- and reviewer-facing, not yet gated in CI (wiring a CI
  job is a human-owned `.github/**` change under the `AGENTS.md` bootstrap
  boundary, so it is called out in `tasks.md` as a follow-up, not done here).

## Proposed solution

### 1. `src/content.config.ts` — three collections, content-layer `glob` loader

Astro 7 has no legacy collections; each collection declares a loader. All three
use `glob` from `astro/loaders` with an explicit `generateId` that keeps the
filename as the id:

```ts
import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';
import { isoWithOffset, yyyyMmDd } from './lib/journal.ts';
import { checkAdrBodies } from './lib/adr.ts';

const idFromFile = ({ entry }: { entry: string }) => entry.replace(/\.md$/, '');
```

`generateId` matters for `projects`: the default slugifier would fold
`mctl-api.en.md` into an id with the dot removed, which is both unreadable and
a collision risk across future `<slug>.<lang>` pairs. Keeping `mctl-api.en`
verbatim is stable, and P5 will group by frontmatter `slug` + `lang` rather
than by id anyway.

Shared primitives, all regex-based rather than zod's format helpers, so the
schema does not depend on which of zod 4's deprecated/renamed validators
survives a minor bump:

```ts
const githubUrl = z.string().regex(/^https:\/\/github\.com\/[^\s]+$/);
const httpsUrl  = z.string().regex(/^https:\/\/[^\s]+$/);
const semver    = z.string().regex(/^\d+\.\d+\.\d+$/);      // no v prefix, AGENTS.md
const bilingual = z.strictObject({ en: z.string().min(1), ru: z.string().min(1) });
const stamp     = z.string().refine(isoWithOffset, {
  message: 'must be a quoted ISO 8601 timestamp with a timezone, e.g. ' +
           "'2026-09-10T22:44:09Z' -- quote it so YAML does not parse it into a Date",
}).transform((s) => new Date(s));
```

Two decisions inside that snippet:

- **`z.strictObject(...)` instead of `.strict()`.** The issue asks for
  `.strict()`; in zod 4.6.2 that method is the deprecated spelling of exactly
  this. The acceptance criterion — an unknown key such as `lead_time_hours`
  fails the build — is satisfied identically, and the non-deprecated spelling
  will not warn or disappear under Dependabot's next `astro` bump.
- **Timestamps are quoted strings validated by regex, not `z.coerce.date()`.**
  Astro parses frontmatter with a YAML parser that turns an *unquoted*
  `2026-09-10T22:44:09Z` into a JS `Date` before zod ever sees it, discarding
  whether an offset was written. Since the issue requires "ISO 8601 with
  timezone", the offset must still be present when validation happens, so the
  schema insists on a string and the seeds quote every timestamp. A `Date`
  arriving instead produces the message above, which names the fix. The
  validator then `.transform`s to a `Date`, so consumers (P7) get real `Date`
  objects.

The three schemas:

```ts
const projects = defineCollection({
  loader: glob({ pattern: '*.{en,ru}.md', base: './src/content/projects', generateId: idFromFile }),
  schema: z.strictObject({
    slug: z.string().regex(/^[a-z0-9-]+$/),
    lang: z.enum(['en', 'ru']),
    name: z.string().min(1),
    group: z.enum(['platform', 'product']),
    order: z.number().int().nonnegative(),
    repo: githubUrl,
    stack: z.array(z.string().min(1)).min(1),
    summary: z.string().min(1).refine((s) => !s.includes('\n'), 'summary is one line'),
    links: z.array(z.strictObject({ label: z.string().min(1), url: httpsUrl })).optional(),
  }),
});

const journal = defineCollection({
  loader: glob({ pattern: '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-*.md',
                 base: './src/content/journal', generateId: idFromFile }),
  schema: z.strictObject({
    service: z.enum(['portfolio', 'mctl-agents', 'mctl-api']),
    issue: githubUrl,
    proposal_slug: z.string().min(1),
    pr: githubUrl.optional(),
    release: semver.optional(),
    visibility: z.enum(['public', 'private']),
    title: bilingual,
    decided: bilingual,
    issue_opened_at: stamp,
    proposal_approved_at: stamp.optional(),
    merged_at: stamp.optional(),
    released_at: stamp.optional(),
    deployed_at: stamp.optional(),
    interventions: z.array(z.strictObject({
      what: z.string().min(1), why: z.string().min(1), at: stamp,
    })).default([]),
  }),
});

const adr = defineCollection({
  loader: adrLoader(),                       // wrapped glob, see section 3
  schema: z.strictObject({
    id: z.number().int().positive(),
    title: bilingual,
    status: z.enum(['proposed', 'accepted', 'superseded', 'deprecated']),
    date: z.string().regex(yyyyMmDd),
    supersedes: z.number().int().positive().optional(),
    visibility: z.enum(['public', 'private']),
  }),
});

export const collections = { projects, journal, adr };
```

Strictness is what makes the model trustworthy: `lead_time`,
`lead_time_hours` and `manual_interventions` are rejected not by a denylist but
because *no* unknown key is allowed. That is stronger than the issue's wording
and needs no maintenance when the next hand-computed field gets invented.

### 2. `src/lib/journal.ts` — zero-import, node-testable helpers

```ts
export const ISO_WITH_OFFSET =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
export const yyyyMmDd = /^\d{4}-\d{2}-\d{2}$/;
export function isoWithOffset(value: unknown): boolean;

export interface Intervention { what: string; why: string; at: Date | string }
export interface JournalTimes {
  issue_opened_at: Date | string;
  deployed_at?: Date | string | null;
  interventions?: readonly Intervention[];
}

export function leadTimeHours(entry: JournalTimes): number | null;
export function interventionCount(entry: JournalTimes): number;
```

`leadTimeHours` returns `null` when `deployed_at` is absent, `null` or an empty
string; otherwise `(deployed − opened) / 3_600_000`, unrounded — formatting is
P7's job, and rounding inside the helper would bake a presentation choice into
the data layer. It throws a `RangeError` when either value is unparseable or
when `deployed_at` precedes `issue_opened_at`, because both are data bugs that
should be loud rather than rendered as a negative lead time.

The structural `JournalTimes` interface is deliberate: typing the parameter as
`CollectionEntry<'journal'>['data']` would import the virtual module
`astro:content` and make the module unloadable outside the Astro pipeline,
which would rule out `node --test`. `CollectionEntry<'journal'>['data']`
structurally satisfies `JournalTimes`, so P7 can pass entry data directly with
no cast.

The module has **no imports at all**. Node 24 (the pinned builder base image is
`node:24-alpine@sha256:50c8e8ca…`) strips TypeScript types natively, so
`test/journal.test.ts` can `import { leadTimeHours } from '../src/lib/journal.ts'`
with no build step, no ts-node and no new devDependency.

### 3. `src/lib/adr.ts` plus a wrapped loader — the build-time body check

```ts
export const ADR_SECTIONS = ['Context', 'Decision', 'Consequences',
                             'Drivers', 'Revisit criteria'] as const;
export function adrBodyProblems(id: string, body: string): string[];
export function checkAdrBodies(entries: { id: string; body: string }[]): void;
```

`adrBodyProblems` splits the body on `^##\s` headings and reports, per file:
a missing section, the five sections out of order, and any section whose text
lacks a `class="l en"` or a `class="l ru"` block. `checkAdrBodies` aggregates
every problem across every entry into a single thrown `Error`, so one failing
run tells the implementer about all of them rather than one per iteration.
It also verifies that frontmatter `id` equals the four-digit filename prefix.

The checker runs inside the collection loader, which is what makes it fail
`astro build`:

```ts
function adrLoader() {
  const base = glob({ pattern: '[0-9][0-9][0-9][0-9]-*.md',
                      base: './src/content/adr', generateId: idFromFile });
  return {
    ...base,
    name: 'adr-with-section-check',
    load: async (ctx) => {
      await base.load(ctx);
      checkAdrBodies([...ctx.store.entries()].map(([id, e]) => ({ id, body: e.body ?? '' })));
    },
  };
}
```

Why the loader and not an integration hook: loaders run on `astro sync`,
`astro dev`, `astro check` and `astro build` alike, which is every entry point
a reviewer or CI uses. `astro:build:done` would run after the output is already
written, and no integration hook can call `getCollection`. Validating the whole
`store` (not only the entries this run re-read) keeps the result identical with
a warm `.astro` cache and a cold one — and `.dockerignore` lists `.astro`, so
the image build is always cold anyway.

### 4. Bilingual ADR bodies

The body pattern, which works because a CommonMark HTML block ends at a blank
line, so the markdown between the tags is still parsed as markdown:

```md
## <span class="l en">Context</span><span class="l ru">Контекст</span>

<div class="l en">

English prose, with **markdown** intact.

</div>

<div class="l ru" lang="ru">

Русский текст, с сохранённым **markdown**.

</div>
```

`site.css`'s `:root[data-lang='en'] .l.ru { display: none }` already applies to
a `<div>`, so no CSS changes. The heading carries both spans because
`claude-review.yml` flags any user-facing string present in only one language;
the section checker keys on the English token inside the heading, so the
structural contract and the bilingual contract do not fight.

### 5. Throwaway development page (criterion 2)

`src/pages/dev/[check].astro`, a dynamic route whose `getStaticPaths` is
empty in a production build:

```ts
export function getStaticPaths() {
  return import.meta.env.DEV ? [{ params: { check: 'collections' } }] : [];
}
```

In `astro dev`, `/dev/collections/` renders the three counts from
`getCollection('projects' | 'journal' | 'adr')`. In `astro build` the route
yields zero paths, so nothing is emitted — `dist/` gains no file, and the page
cannot drift into production. (A `_`-prefixed filename would be excluded from
dev as well, which is why this shape is used instead.) Astro logs a warning for
a dynamic route with no paths; if Astro 7 ever promotes that to an error, the
fallback is to keep the page only for the demonstration and delete it before
merge, which still satisfies criterion 2.

### 6. Scripts

```json
"check": "astro sync && astro check",
"test":  "node --test test/journal.test.ts test/adr.test.ts"
```

`astro sync` is named explicitly even though `astro check` syncs too: it makes
the failure legible ("the content validations failed") instead of hiding a
loader throw inside a type-check run. Test files are listed explicitly rather
than passing a directory, so discovery does not depend on the runner's
TypeScript glob defaults.

### 7. Seed data — the verified table

Sources: `gh issue view` / `gh pr view` / `gh api repos/*/releases` for GitHub
facts; `platform-gitops/agents-state/<service>/proposals/<slug>/.status.yaml`
for `proposal_slug` and approval time; `gh api
repos/mctlhq/mctl-gitops/commits` for the image-bump commit used as
`deployed_at`. Note that P1's `.status.yaml` records `merged_at:
2026-09-11T00:21:13Z` — that is the shepherd's *observation* time; the GitHub
API reports the actual merge at `00:11:53Z`, and the issue says to fill
timestamps from GitHub, so the GitHub value is used.

| file | `service` | `issue` | `proposal_slug` | `pr` | `release` |
|---|---|---|---|---|---|
| `2026-09-10-register-portfolio-as-a-devloop-service.md` | `mctl-agents` | `https://github.com/mctlhq/mctl-agents/issues/330` | `issue-330-register-portfolio-as-a-non-rotating-dev` | `https://github.com/mctlhq/mctl-agents/pull/331` | `1.41.0` |
| `2026-09-10-add-portfolio-to-the-devloop-service-enums.md` | `mctl-api` | `https://github.com/mctlhq/mctl-api/issues/281` | `issue-281-add-portfolio-to-the-devloop-service-enu` | `https://github.com/mctlhq/mctl-api/pull/282` | `4.41.0` |
| `2026-09-10-astro-static-skeleton-and-nginx-image.md` | `portfolio` | `https://github.com/mctlhq/portfolio/issues/3` | `issue-3-p1-astro-static-skeleton-nginx-image-and` | `https://github.com/mctlhq/portfolio/pull/12` | `0.1.0` |
| `2026-09-10-base-layout-vendored-tokens-and-fonts.md` | `portfolio` | `https://github.com/mctlhq/portfolio/issues/4` | `issue-4-p2-base-layout-with-vendored-design-toke` | `https://github.com/mctlhq/portfolio/pull/16` | `0.1.1` |

| file | `issue_opened_at` | `proposal_approved_at` | `merged_at` | `released_at` | `deployed_at` |
|---|---|---|---|---|---|
| `…register-portfolio…` | `'2026-09-10T22:44:09Z'` | `'2026-09-10T22:49:52Z'` | `'2026-09-10T23:21:47Z'` | `'2026-09-10T23:26:13Z'` | `'2026-09-10T23:28:11Z'` |
| `…service-enums…` | `'2026-09-10T22:44:11Z'` | `'2026-09-10T22:49:04Z'` | `'2026-09-10T23:21:47Z'` | `'2026-09-10T23:26:18Z'` | `'2026-09-10T23:28:21Z'` |
| `…astro-static-skeleton…` | `'2026-09-10T22:45:31Z'` | `'2026-09-10T23:38:32Z'` | `'2026-09-11T00:11:53Z'` | `'2026-09-11T00:17:50Z'` | *(unset)* |
| `…base-layout…` | `'2026-09-10T22:45:33Z'` | `'2026-09-11T00:36:16Z'` | `'2026-09-11T01:39:35Z'` | `'2026-09-11T01:42:36Z'` | *(unset)* |

All four filenames use the UTC date of `issue_opened_at`, so all four are
`2026-09-10-*`. `visibility: public` on all four.

### 8. Seed interventions, with the anchor for each `at`

On **both** R-round entries (`…register-portfolio…` and `…service-enums…`),
in this order:

1. `at: '2026-09-10T23:12:30Z'` — anchor: the APPROVED review submitted on
   `mctl-api#282` that the re-request produced.
   `what: "re-requested the Claude review on mctl-api#282"`,
   `why: "the first run posted its verdict as a comment without submitting a formal review, so the approval gate never cleared"`.
2. `at: '2026-09-10T23:21:47Z'` — anchor: the merge of the PR the hand-run
   shepherd merged.
   `what: "triggered the shepherd by hand"`,
   `why: "the shepherd cron only runs 07:00-21:00 UTC and both PRs were ready at 23:00 UTC"`.

On the **P1** entry (`…astro-static-skeleton…`):

1. `at: '2026-09-10T22:43:00Z'` — anchor: commit `chore: bootstrap repository
   wiring` (mashkovd).
   `what: "manual bootstrap commit of README, AGENTS.md, workflows, release-please config and Dependabot"`,
   `why: "ADR-0001 bootstrap boundary: a DevLoop cycle cannot run in a repository that has no review gate"`.
2. `at: '2026-09-10T23:49:32Z'` — anchor: the dismissed `claude[bot]` review on
   `portfolio#12`, the outcome of the re-request.
   `what: "re-requested the Claude review on portfolio#12"`,
   `why: "the review-fixing loop had deadlocked: the reviewer flagged the EN-only 404 string and the implementer correctly refused to fix what the spec defers"`.
3. `at: '2026-09-11T00:09:44Z'` — anchor: the human APPROVED review on
   `portfolio#12`, which the rewritten description unblocked.
   `what: "rewrote the pull request description to state the three deferrals"`,
   `why: "task 12 of the approved proposal required it and the implementer cannot edit a PR body, which left the review gate reading a documented deferral as an oversight"`.

On the **P2** entry (`…base-layout…`):

1. `at: '2026-09-11T01:14:05Z'` — anchor: commit `fix: record every platform
   binding in the lockfile, drop the dead stylesheet` (mashkovd, on PR #16).
   `what: "regenerated package-lock.json by hand with npm install --package-lock-only"`,
   `why: "npm install on the implementer's linux/x64 pod pruned every other platform's native binding out of the lockfile, so npm ci in the Dockerfile refused the tree with EUSAGE and the build check could never go green; the shepherd passes the implementer only findings raised by review bots, so the diagnosis posted on the PR never reached it"`.
2. `at: '2026-09-11T01:14:05Z'` — same commit, which also removed the file.
   `what: "deleted src/styles/site.css by hand"`,
   `why: "byte-identical dead copy of public/styles/site.css that nothing imported; raised in human review on the PR, which the shepherd does not read"`.
3. `at: '2026-09-11T01:15:27Z'` — anchor: commit `fix: restore
   src/styles/site.css and gitignore the copy it generates`.
   `what: "deleted src/styles/site.css, broke the build, then restored it and gitignored the generated public/styles/site.css instead"`,
   `why: "the deletion was my error -- scripts/vendor-assets.mjs copies that file from prebuild and I had searched only the source tree for references, not the build scripts; the underlying smell was real, in that the generated copy was committed without being ignored"`.
4. `at: '2026-09-11T01:16:45Z'` — anchor: merge of `portfolio#17`.
   `what: "added the --package-lock-only rule to AGENTS.md (PR #17)"`,
   `why: "the implementer always runs on linux/x64, so the same failure would recur on any future bump of a package shipping native bindings"`.

So `interventionCount` yields 2, 2, 3, 4 and `leadTimeHours` yields
≈0.734, ≈0.736, `null`, `null` — both branches of the helper are exercised by
real data, not only by fixtures.

### 9. Seed copy (EN and RU), supplied here so the implementer translates nothing

**Journal `title` / `decided`:**

- `…register-portfolio…` — title en `Register portfolio as a non-rotating
  DevLoop service`; ru `Регистрация portfolio как сервиса DevLoop вне
  ротации`. decided en `mctl-agents now treats portfolio as a first-class
  DevLoop service, so its issues are investigated on demand instead of waiting
  for the weekly rotation.`; ru `mctl-agents теперь считает portfolio
  полноценным сервисом DevLoop, поэтому его задачи исследуются по запросу, а не
  ждут недельной ротации.`
- `…service-enums…` — title en `Add portfolio to the DevLoop service enums`;
  ru `Добавление portfolio в перечисления сервисов DevLoop`. decided en `The
  platform API accepts portfolio everywhere a DevLoop service name is taken, so
  triggers and proposals for this repository validate.`; ru `API платформы
  принимает portfolio везде, где ожидается имя сервиса DevLoop, поэтому
  триггеры и предложения для этого репозитория проходят валидацию.`
- `…astro-static-skeleton…` — title en `Astro static skeleton, nginx image and
  health endpoints`; ru `Статический каркас Astro, образ nginx и проверки
  состояния`. decided en `The site builds to static HTML served by nginx from
  digest-pinned base images, with /healthz and /readyz returning 200, which
  fixes the deployment shape for every later cycle.`; ru `Сайт собирается в
  статический HTML и отдаётся nginx из базовых образов, закреплённых по
  digest, а /healthz и /readyz отвечают 200 — это задаёт форму развёртывания
  для всех последующих циклов.`
- `…base-layout…` — title en `Base layout with vendored design tokens and
  fonts`; ru `Базовый макет с встроенными в сборку токенами дизайна и
  шрифтами`. decided en `Design tokens and fonts are vendored at build time and
  the bilingual switch is CSS-driven, so the page makes zero third-party
  requests and stays usable without JavaScript.`; ru `Токены дизайна и шрифты
  встраиваются во время сборки, а переключение языка выполняется средствами
  CSS, поэтому страница не делает сторонних запросов и остаётся рабочей без
  JavaScript.`

**ADR headings:** `Context`/`Контекст`, `Decision`/`Решение`,
`Consequences`/`Последствия`, `Drivers`/`Движущие факторы`,
`Revisit criteria`/`Критерии пересмотра`.

**ADR-0001 `bootstrap-boundary`** — title en `Bootstrap boundary: humans wire,
the DevLoop builds`; ru `Граница начальной настройки: человек делает обвязку,
DevLoop — всё остальное`.

- Context en: `This repository exists to be evidence that the mctl DevLoop can
  build and run a real site. Every file a human writes weakens that evidence —
  and a repository with no review gate cannot host a DevLoop cycle at all, so
  some human wiring is unavoidable.`
  ru: `Этот репозиторий существует как доказательство того, что mctl DevLoop
  способен построить и поддерживать настоящий сайт. Каждый файл, написанный
  человеком, ослабляет это доказательство, но репозиторий без шлюза проверки
  вообще не может вместить цикл DevLoop, поэтому часть обвязки приходится
  делать руками.`
- Decision en: `Humans create and edit only the wiring: the repository itself,
  README.md, AGENTS.md, LICENSE, .gitignore, .github/**, the release-please
  configuration and manifest, repository settings, secrets, labels and the
  branch ruleset. Every other file — the Astro project, Dockerfile, nginx.conf,
  content, journal, ADRs, scripts — arrives through a DevLoop cycle, and every
  deployment action goes through the mctl MCP tools.`
  ru: `Человек создаёт и правит только обвязку: сам репозиторий, README.md,
  AGENTS.md, LICENSE, .gitignore, .github/**, конфигурацию и манифест
  release-please, настройки репозитория, секреты, метки и правила ветвления.
  Все остальные файлы — проект Astro, Dockerfile, nginx.conf, контент, журнал,
  ADR, скрипты — появляются через цикл DevLoop, а любое действие по
  развёртыванию выполняется инструментами mctl MCP.`
- Consequences en: `A trivial fix waits for a full cycle, and any human edit
  outside the wiring list is a manual intervention that must be recorded in the
  journal entry of the next cycle. In exchange the repository history is itself
  the claim the site makes.`
  ru: `Тривиальная правка ждёт полного цикла, а любая правка человека вне
  списка обвязки считается ручным вмешательством и обязательно фиксируется в
  записи журнала следующего цикла. Взамен история репозитория сама становится
  утверждением, которое делает сайт.`
- Drivers en: `The site must be evidence, not a claim.`
  ru: `Сайт должен быть доказательством, а не заявлением.`
- Revisit criteria en: `Revisit if a trivial change takes more than two working
  days end to end.`
  ru: `Пересмотреть, если тривиальное изменение проходит путь от задачи до
  продакшена дольше двух рабочих дней.`

**ADR-0002 `static-astro-no-client-bundles`** — title en `Static Astro output,
no client-side bundles`; ru `Статическая сборка Astro без клиентских бандлов`.

- Context en: `The site is a portfolio and a work journal: text, links and a
  handful of numbers read from a build-time snapshot. Nothing on it needs a
  client-side framework, and every kilobyte of JavaScript is a cost paid by
  every reader.`
  ru: `Сайт — это портфолио и рабочий журнал: текст, ссылки и несколько чисел
  из снимка, собранного во время сборки. Ничему здесь не нужен клиентский
  фреймворк, а каждый килобайт JavaScript оплачивает каждый читатель.`
- Decision en: `Astro builds with output: 'static' and nginx serves the result.
  The only JavaScript shipped is one inline preference script of at most 400
  bytes in the document head, whose SHA-256 is listed in the
  Content-Security-Policy. The bilingual switch is CSS-driven through .l.en /
  .l.ru pairs, so English renders immediately and the site stays fully usable
  with JavaScript disabled.`
  ru: `Astro собирается с output: 'static', результат отдаёт nginx.
  Единственный отправляемый JavaScript — один встроенный скрипт настроек не
  больше 400 байт в head документа, чей SHA-256 перечислен в
  Content-Security-Policy. Переключение языка выполняется средствами CSS через
  пары .l.en / .l.ru, поэтому английский рендерится сразу, а сайт остаётся
  полностью рабочим с отключённым JavaScript.`
- Consequences en: `Both language variants are present in every document, which
  costs page weight; an interactive feature is impossible until this decision is
  revisited; dist/ contains no .js file and exactly one inline script, which
  scripts/csp-hash.mjs enforces at image build time.`
  ru: `Оба языковых варианта присутствуют в каждом документе, что увеличивает
  вес страницы; интерактивная функциональность невозможна, пока решение не
  пересмотрено; в dist/ нет ни одного файла .js и есть ровно один встроенный
  скрипт — это проверяет scripts/csp-hash.mjs при сборке образа.`
- Drivers en: `A reader on a slow mobile connection must get the text
  immediately, and a static artifact is trivially cacheable and trivially
  auditable.`
  ru: `Читатель на медленном мобильном соединении должен получить текст сразу,
  а статический артефакт легко кешируется и легко проверяется.`
- Revisit criteria en: `Revisit if a feature genuinely needs client-side code,
  or if the Lighthouse mobile performance score drops below 95.`
  ru: `Пересмотреть, если какая-то функция действительно потребует клиентского
  кода или если оценка Lighthouse mobile performance опустится ниже 95.`

**ADR-0005 `self-contained-runtime-assets`** — title en `Self-contained runtime
assets: tokens and fonts vendored at build time`; ru `Самодостаточные ресурсы
времени выполнения: токены и шрифты встраиваются в сборку`.

- Context en: `Design tokens come from @mctlhq/css and the three typefaces —
  Onest, Instrument Serif, JetBrains Mono, all under the SIL Open Font License
  — from pinned @fontsource packages. Loading either from a third-party origin
  at runtime would hand every reader's IP address to that origin and make the
  page depend on its availability.`
  ru: `Токены дизайна берутся из @mctlhq/css, а три гарнитуры — Onest,
  Instrument Serif, JetBrains Mono, все под лицензией SIL Open Font License —
  из закреплённых пакетов @fontsource. Загрузка любого из этих ресурсов со
  сторонней площадки во время выполнения раскрыла бы ей IP-адрес каждого
  читателя и поставила бы страницу в зависимость от её доступности.`
- Decision en: `scripts/vendor-assets.mjs fetches tokens and fonts at build
  time, verifies them against pinned SHA-256 digests, and commits them under
  public/assets/ together with their licences; the site serves them from its own
  origin and the Content-Security-Policy names no external origin.`
  ru: `scripts/vendor-assets.mjs получает токены и шрифты во время сборки,
  сверяет их с закреплёнными SHA-256, и кладёт их в public/assets/ вместе с
  лицензиями; сайт отдаёт их со своего же домена, а Content-Security-Policy не
  упоминает ни одной внешней площадки.`
- Consequences en: `A design system release reaches the site only through a
  reviewed re-pin of the digests, and the repository carries the vendored bytes.
  In exchange the production page makes zero third-party requests and the build
  succeeds offline from the committed tree.`
  ru: `Новая версия дизайн-системы попадает на сайт только через
  отрецензированное обновление закреплённых хешей, а сами файлы лежат в
  репозитории. Взамен продакшен-страница не делает ни одного стороннего
  запроса, а сборка проходит без сети из уже зафиксированного дерева.`
- Drivers en: `No third-party request and no cookie is a promise the page has
  to keep byte for byte, not in prose.`
  ru: `Отсутствие сторонних запросов и cookie — обещание, которое страница
  обязана выполнять побайтово, а не на словах.`
- Revisit criteria en: `Revisit if the design system publishes a version the
  site must follow within days.`
  ru: `Пересмотреть, если дизайн-система выпустит версию, за которой сайту
  нужно последовать в течение дней.`

**Project pair `mctl-api`** (`group: platform`, `order: 1`,
`repo: https://github.com/mctlhq/mctl-api`,
`stack: ['Go', 'chi', 'PostgreSQL', 'Temporal', 'Argo Workflows', 'Vault']`,
`links: [{ label: 'Docs' / 'Документация', url: 'https://docs.mctl.ai' }]`):

- `mctl-api.en.md` — name `mctl-api`, summary `The control-plane API behind the
  mctl platform: tenants, services, domains, incidents and the DevLoop.` Body:
  one paragraph explaining that it exposes the platform as both a REST API and
  an MCP server, so that an agent and a human drive the same operations, with
  every change landing as a GitOps commit rather than a direct cluster write.
- `mctl-api.ru.md` — name `mctl-api`, summary `API управляющего слоя платформы
  mctl: команды, сервисы, домены, инциденты и DevLoop.` Body: the same
  paragraph in Russian. `name` stays untranslated: it is an identifier.

`stack` entries stay untranslated in both files for the same reason. No numeric
metric appears in either file — metrics join by `repo` in P8b.

## Alternatives

1. **Put the ADR body check in an Astro integration (`astro:build:done`) or a
   standalone `scripts/check-adr.mjs` run from `npm run check`.** Dropped: the
   integration hook fires after `dist/` is written, so the build "fails" with a
   published artifact already on disk, and neither hook can call
   `getCollection`. A standalone script would have to re-implement frontmatter
   and body splitting, duplicating the loader, and — critically — it would not
   make `astro build` itself fail, which acceptance criterion 1 requires. The
   wrapped loader satisfies the criterion with one implementation that also
   runs on `astro dev` and `astro check`.
2. **Denylist `lead_time`, `lead_time_hours` and `manual_interventions`
   explicitly with a `.refine` on a non-strict object.** Dropped: it enumerates
   today's mistakes and silently admits tomorrow's. `z.strictObject` rejects all
   three as a consequence of rejecting everything unknown, and needs no upkeep.
   The issue's `.strict()` wording is honoured in substance; only the
   non-deprecated zod-4 spelling differs, which is noted in `tasks.md` so a
   reviewer does not read it as a deviation.
3. **`z.coerce.date()` for the timestamps, as Astro's own content examples
   do.** Dropped: it accepts an unquoted YAML timestamp, by which point the
   offset is already gone, so "ISO 8601 with timezone" becomes unenforceable.
   The string-plus-regex-plus-transform route enforces the offset at the only
   moment it still exists and still hands `Date` objects to consumers.
4. **One bilingual project file per slug with `title: { en, ru }`, matching the
   journal and ADR shape.** Dropped: the issue fixes `<slug>.en.md` /
   `<slug>.ru.md` with a per-file `lang`, and the project *body* is a long
   expanded description rendered inside `<details>` — far easier to author and
   review as two monolingual markdown bodies than as one file of interleaved
   `.l.en` / `.l.ru` blocks. Journal and ADR bodies are short enough that the
   interleaved form costs little.

## Platform impact

- **Migrations:** none. Three new directories under `src/content/`, a new
  `src/content.config.ts`, a new `src/lib/`, a new `test/`, one new
  `src/pages/dev/[check].astro`, and two new `package.json` scripts (`test`,
  and `check` extended to `astro sync && astro check`). No existing file's
  behaviour changes; `astro.config.mjs`, `Base.astro`, `site.css`,
  `nginx.conf`, `Dockerfile`, `scripts/*` and `src/i18n/ui.ts` are untouched.
  `.astro/` (already gitignored) gains the content data store.
- **Backward compatibility:** nothing consumes the collections yet, so the
  schemas can still be tightened in P5/P7 without a content migration. The
  first real constraint this cycle imposes on the future is the *filenames* of
  the four journal entries and three ADRs, and the reserved ADR numbers 0003 and
  0004.
- **Resource impact:** `dist/` gains nothing (no route renders content, and the
  dev page emits no page), so image size, page weight and the CSP are
  unchanged. `scripts/csp-hash.mjs` continues to see exactly one inline script.
  Build time grows by the content sync of nine small markdown files —
  milliseconds. No new runtime dependency and no new devDependency:
  `node --test` is built in and `zod` arrives transitively through `astro`.
- **Risk: `astro build` does not fail as required** (the loader wrapper proves
  not to be invoked, e.g. because a warm `.astro` store short-circuits the
  load). Mitigation: the PR must demonstrate the three failure modes from
  acceptance criterion 1 with temporary fixtures after `rm -rf .astro` *and*
  with a warm cache, and the demonstration output goes into the PR description
  before the fixtures are removed.
- **Risk: `node --test` cannot load a `.ts` file** on the developer's Node
  version, or `astro check` rejects the `../src/lib/journal.ts` import
  extension. Mitigation: the builder image is `node:24-alpine`, where type
  stripping is on by default; if `astro check` objects, add
  `"allowImportingTsExtensions": true` (and, if the checker asks for it,
  `"erasableSyntaxOnly": true`) to `tsconfig.json`, which is implementer-owned.
  Keeping both lib modules import-free and syntax-plain is what makes this a
  one-line fix rather than a toolchain change.
- **Risk: a reviewer reads `z.strictObject` as not implementing `.strict()`, or
  reads the bilingual ADR headings as a deviation from the issue.** Mitigation:
  both are argued in this document and flagged in `requirements.md`'s open
  questions; the implementer repeats both in the PR description.
- **Risk: a seeded timestamp is wrong and quietly becomes "evidence".**
  Mitigation: every value in sections 7 and 8 carries its source or anchor, the
  two cases where the anchor is an inference (the PR-description rewrite, the
  review re-requests) are called out, and the implementer copies the table
  rather than re-deriving it.
- **Risk: a `public` journal entry leaks something.** Mitigation: the four
  entries contain only public repository URLs, public release versions,
  timestamps and the intervention prose quoted from the issue; no credential, no
  internal hostname, no third party. A reviewer checks `visibility` against
  `AGENTS.md`'s rule as part of the gate.
- **CI note:** `.github/workflows/build.yml` builds the Docker image, which runs
  `npm run build`, so the ADR body check and every schema *do* gate the PR
  today. `npm test` and `npm run check` are not yet a CI job; adding one is a
  `.github/**` change reserved to humans by the bootstrap boundary, so it is
  listed as a follow-up rather than attempted here.
