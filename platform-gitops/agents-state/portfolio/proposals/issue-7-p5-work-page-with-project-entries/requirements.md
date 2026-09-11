# P5: Work page with project entries

## Context

The site currently has one real page (`src/pages/index.astro`) and a `projects`
content collection that holds exactly one project, `mctl-api`, in an `.en.md` /
`.ru.md` pair (`src/content/projects/mctl-api.en.md`,
`src/content/projects/mctl-api.ru.md`). The collection, its Zod schema and its
en/ru parity check already exist in `src/content.config.ts`, but nothing renders
them: there is no `/work/` route, and the only consumer is the development-only
route `src/pages/dev/[check].astro`, which prints collection counts. The home
page and the header already link to work (`href="/work/"` in
`src/pages/index.astro`, `href="/#work"` in `src/components/Nav.astro`), so the
destination is currently a 404 or a dead anchor.

Issue #7 asks for that destination: `/work/` listing fourteen projects in two
groups (Platform, Products), each rendered as a card carrying a one-line
bilingual summary and stack chips, expanding via `<details>` to detail bullets,
links and a placeholder slot for per-repository numbers that P8b will fill. This
matters because the portfolio's whole claim — a platform built the agentic way —
is unverifiable without the inventory of repositories that backs it. It also
has to hold every existing site invariant at once: static output with no client
JavaScript (ADR-0002), `.l.en` / `.l.ru` CSS-driven bilingualism with equal
counts per document (`scripts/check-dist.mjs`), no number typed into a template
(`AGENTS.md`, `src/lib/metrics.ts`), same-origin assets only, and the typography
constraint carried from #4 that `Instrument Serif` must not be used for any
string that has a Russian counterpart.

## User stories

- AS a visitor I WANT a single `/work/` page listing every project in two
  labelled groups SO THAT I can see the full inventory without following
  fourteen GitHub links.
- AS a visitor skimming I WANT each project to show a one-line summary and its
  stack as chips before I expand anything SO THAT I can judge relevance in one
  pass.
- AS a visitor who wants depth I WANT each card to expand to detail bullets and
  links SO THAT I can read the substance without leaving the page.
- AS a Russian-speaking visitor I WANT every summary, detail bullet, group
  heading and plain-word chip in Russian SO THAT the page reads as written
  rather than translated.
- AS a keyboard-only visitor I WANT to reach and toggle every card with Tab plus
  Enter or Space SO THAT the page is usable without a pointer.
- AS the site owner I WANT per-project numbers to come from the metrics snapshot
  and render as an em dash until P8b lands SO THAT no number on the site is
  typed by hand.
- AS a reviewer I WANT the card markup driven entirely by content frontmatter
  SO THAT adding a project is a content change, not a template change.

## Acceptance criteria (EARS)

### Route and grouping

- WHEN `astro build` runs THE SYSTEM SHALL emit `dist/work/index.html` from
  `src/pages/work.astro`, reachable at `/work/` under the project's
  `trailingSlash: 'always'` setting in `astro.config.mjs`.
- WHEN `/work/` renders THE SYSTEM SHALL render exactly fourteen project cards:
  six in the `platform` group and eight in the `product` group.
- WHEN `/work/` renders THE SYSTEM SHALL render the `platform` group before the
  `product` group, each under its own heading, and SHALL order cards inside each
  group by ascending frontmatter `order`.
- WHILE the `projects` collection is the only source of cards THE SYSTEM SHALL
  derive every card's name, summary, stack chips, repository URL and extra links
  from that entry's frontmatter, with no project name, summary, chip label or
  URL written as a literal in `src/pages/work.astro` or
  `src/components/ProjectCard.astro`.
- IF a slug has no `en` entry or no `ru` entry, or the two disagree on `group`,
  `order`, `repo`, `stack` or any `links[].url`, THEN THE SYSTEM SHALL fail the
  build with the message already produced by `checkProjectParity` in
  `src/content.config.ts`.

### Content

- WHEN the content files are added THE SYSTEM SHALL carry these fourteen slugs,
  groups and orders, with `order` taken from the issue's global numbering so
  that each group's orders are contiguous: `platform` — `mctl-api` (1),
  `mctl-gitops` (2), `mctl-agents` (3), `mctl-agent` (4), `mctl-portal` (5),
  `mctl-design` (6); `product` — `mctl-telegram` (7), `seerrsense` (8),
  `mctl-academy` (9), `mctl-loyalty` (10), `mctl-pairdesk` (11),
  `pelican-libertex-social` (12), `pfeifenpatenschaft-backend` (13),
  `mctl-openclaw` (14).
- WHEN the content files are added THE SYSTEM SHALL use the EN and RU summaries
  and the stack chip lists exactly as given in issue #7, including replacing the
  existing `summary` and `stack` of `mctl-api` with the issue's wording
  (`Go`, `chi`, `mcp-go`, `OAuth 2.0 PKCE`, `OpenAPI`) while keeping its
  `order: 1`, its `group: platform` and its existing `Docs` link to
  `https://docs.mctl.ai`.
- WHEN a project's `repo` is set THE SYSTEM SHALL use
  `https://github.com/mctlhq/<slug>`, except `pelican-libertex-social`, which
  SHALL use `https://github.com/mashkoffdmitry/pelican-libertex-social`.
- WHEN the ten projects for which issue #7 supplies detail bullets are authored
  (`mctl-api`, `mctl-gitops`, `mctl-agents`, `mctl-agent`, `mctl-portal`,
  `mctl-design`, `mctl-telegram`, `seerrsense`, `mctl-academy`,
  `mctl-openclaw`) THE SYSTEM SHALL put those bullets, verbatim per language, in
  the markdown body of the matching `.en.md` and `.ru.md` file, one bullet per
  list item, with the same number of bullets in both languages.
- WHEN `mctl-openclaw` is authored THE SYSTEM SHALL state in its detail bullets
  that repository totals reflect the upstream project and that the owner's
  contribution is the fork layer and the deployment pipeline, in both languages.
- IF issue #7 supplies no detail bullets for a project (`mctl-loyalty`,
  `mctl-pairdesk`, `pelican-libertex-social`,
  `pfeifenpatenschaft-backend`) THEN THE SYSTEM SHALL leave that entry's
  markdown body empty and SHALL NOT invent prose for it; the card's expanded
  region then carries only its links and its metrics placeholder.
- WHILE no issue text exists for a user-facing string THE SYSTEM SHALL NOT
  author one, per the issue contract in `AGENTS.md`.

### Bilingualism

- WHEN any user-facing string is rendered THE SYSTEM SHALL render it as an
  `.l.en` / `.l.ru` pair, with the Russian element also carrying `lang="ru"`, as
  `src/i18n/Lang.astro` already does.
- WHEN `scripts/check-dist.mjs` walks `dist/` THE SYSTEM SHALL show an equal
  count of `class="l en"` and `class="l ru"` in `dist/work/index.html`, as in
  every other emitted document.
- WHEN `src/i18n/ui.ts` is extended THE SYSTEM SHALL add the page title, the
  group headings (`Platform` / `Платформа`, `Products` / `Продукты`), the
  repository link label and the metrics-pending label as `{ en, ru }` entries in
  the existing `ui` object.
- WHEN a stack chip is a plain word or phrase rather than a language, tool or
  product name (`design tokens`, `upstream fork`) THE SYSTEM SHALL render its
  Russian form from a chip dictionary exported by `src/i18n/ui.ts`, keyed by the
  canonical English chip string stored in frontmatter.
- IF a chip string has no entry in that dictionary THEN THE SYSTEM SHALL render
  the frontmatter string unchanged in both languages, so that language, tool and
  product names stay untranslated.
- WHILE `stack` must stay byte-identical between an entry's `.en.md` and
  `.ru.md` (enforced by `checkProjectParity`) THE SYSTEM SHALL keep the English
  chip string as the canonical value in both files.

### Typography

- WHILE any string has a Russian counterpart THE SYSTEM SHALL NOT set it in
  `Instrument Serif`; no rule added for the work page SHALL use
  `var(--font-editorial)`.
- WHEN a group heading, a summary or a detail bullet is rendered THE SYSTEM
  SHALL set it in Onest (`var(--font-display)`), and WHEN a project name or a
  stack chip is rendered THE SYSTEM SHALL set it in JetBrains Mono
  (`var(--font-mono)`), both identical across languages.

### Interaction, accessibility and output

- WHEN a card is rendered THE SYSTEM SHALL render it as a native `<details>`
  with a `<summary>` holding the project name, the one-line summary and the
  stack chips, and the expandable region holding the detail bullets, the links
  and the metrics placeholder.
- WHEN a visitor tabs through `/work/` THE SYSTEM SHALL give focus to every
  card's `<summary>` and SHALL toggle it on both Enter and Space, with no
  `tabindex` attribute authored and no interactive element (`<a>`, `<button>`)
  placed inside a `<summary>`.
- WHILE `/work/` is open THE SYSTEM SHALL keep every `<summary>` at least 44px
  tall at any viewport width, matching the existing `.block > summary` rule in
  `src/styles/site.css`.
- WHEN JavaScript is disabled THE SYSTEM SHALL render `/work/` fully usable in
  English, with cards expandable and all links live.
- WHEN `astro build` completes THE SYSTEM SHALL produce no `.js` file anywhere
  under `dist/`, and `/work/` SHALL request no cross-origin subresource: every
  stylesheet, font and asset reference resolves under the site origin.
- WHEN `scripts/check-dist.mjs` runs THE SYSTEM SHALL additionally assert that
  `dist/work/index.html` exists and contains exactly fourteen project cards,
  failing the image build otherwise.

### Metrics

- WHILE `src/data/metrics.json` carries no `per_repo` data THE SYSTEM SHALL
  render each card's per-repository metric placeholder as the em dash exported
  as `EM_DASH` by `src/lib/metrics.ts`, obtained through `formatStat(null)`.
- WHEN a number is shown on the work page THE SYSTEM SHALL read it from the
  metrics snapshot; no digit SHALL be typed into `src/pages/work.astro`,
  `src/components/ProjectCard.astro` or any project's frontmatter or body.
- WHEN P8b later supplies `per_repo` data THE SYSTEM SHALL accept it through the
  card's named metrics slot without a change to the card's public props.

### Verification

- WHEN the pull request is opened THE SYSTEM SHALL include in its description
  the output of a link-checking script run over the built `dist/`, listing every
  distinct absolute and site-relative URL on `/work/` with its HTTP status.
- IF any URL on `/work/` returns a status other than 200 THEN THE SYSTEM SHALL
  report it in the pull-request description, named, rather than silently
  dropping or rewriting the link.
- WHEN `npm test` runs THE SYSTEM SHALL execute the new grouping and work-page
  tests, which are listed explicitly in the `test` script of `package.json`.

## Out of scope

- Per-project numeric metrics and the `per_repo` shape of
  `src/data/metrics.json` — that is P8b. This proposal adds only the slot and
  the em-dash placeholder, and changes neither `src/data/metrics.json` nor
  `metricProblems` in `src/lib/metrics.ts`.
- Screenshots, logos and any image asset for a project.
- Per-project detail pages or routes under `/work/<slug>/`.
- The approach page (`/approach/`) and the colophon page (`/colophon/`), and the
  `/#approach` header link that still points at the home page.
- Search, tag filtering, sorting controls or any other interactive affordance,
  which ADR-0002 forbids while it stands.
- Rewiring the footer `Release` source, adding analytics, or touching
  `nginx.conf`, the CSP or the vendored asset set.
- Any change to `.github/workflows/claude-review.yml`,
  `.github/workflows/release-please.yml` or `.github/dependabot.yml`, reserved
  to humans by `AGENTS.md`.

## Open questions

1. Four projects (`mctl-loyalty`, `mctl-pairdesk`, `pelican-libertex-social`,
   `pfeifenpatenschaft-backend`) are given a summary but no detail bullets,
   while acceptance criterion 2 of the issue reads "Every card has EN and RU
   summary and details". Proceeding with the reading that criterion 2 is a
   bilingual-parity requirement, not an instruction to author missing copy: no
   prose is invented, those four bodies stay empty, and their expanded region
   carries links plus the metrics placeholder. If the reviewer wants prose
   there, it has to arrive as issue copy in a follow-up.
2. The issue does not say whether the fourteen repositories are all public.
   Criterion 3 ("every link returns HTTP 200") fails for any private or
   non-existent repository. Proceeding by treating the issue's URLs as the
   source of truth and reporting each non-200 by name in the pull-request
   description, leaving the make-public-or-drop decision to the human gate.
3. `src/components/Nav.astro` links Work to `/#work`, an anchor deleted from the
   home page in #6 (`test/home.test.ts` asserts `id="work"` is gone). The issue
   does not list `Nav.astro` among the files expected to change. Proceeding with
   the minimal one-line fix to `/work/`, because the page this proposal adds is
   otherwise unreachable from the header; flagged here for the reviewer in case
   it should be split out.
4. The issue specifies `self-healing` → `самовосстановление` as the example of a
   translatable chip word, but that string appears only in detail prose, not in
   any stack list. The only plain-word chips in the fourteen stacks are
   `design tokens` and `upstream fork`. Proceeding by seeding the chip
   dictionary with those two and leaving it open for later additions.
5. The issue says numbers "render as an em dash until then" without naming which
   numbers. Proceeding with a single unlabelled em-dash placeholder per card,
   behind a named slot, so P8b chooses the labels and the metric set.
