# Improve home search snippet and bilingual person identity

## Context

Issue mctlhq/portfolio#195 (opened `2026-11-05T22:58:58Z`) asks for a small
change to the existing home page's search snippet and structured identity. The
home `<title>` today is only `Dmitrii Mashkov` (`ui.homeTitle` in
`src/i18n/ui.ts`). Its description is a string literal typed into
`src/pages/index.astro`. The home `Person` JSON-LD node in `src/lib/seo.ts`
knows the person only by the Latin name. Search Console data the issue author
read on 2026-11-05 shows navigational queries in Cyrillic (the person's
Russian name together with "Telegram"). There are very few of them. They
justify an incremental metadata and identity improvement. They do not justify
a claim of uplift or a new landing page.

The change keeps the repository's architecture: static output, English by
default, Russian through the CSS `.l.en` / `.l.ru` toggle, Latin `<title>` in
both dictionary entries (AGENTS.md "Site constraints"), no new script, request,
cookie or dependency. Nothing in this change displays a number on the site.

## Exact copy contract (EN and RU)

This copy is the contract. The implementer must commit it character for
character. Characters that matter: the em dash `—` (U+2014) with a space on
each side, the ampersand `&`, the colon after the Cyrillic name, and the
`@dmitriimashkov` handle.

Home `<title>` / `homeTitle` (Latin in both language entries, as AGENTS.md requires):
- EN: `Dmitrii Mashkov — Platform Engineering & AI`
- RU: `Dmitrii Mashkov — Platform Engineering & AI`

Home description / `homeDescription`:
- EN: `Platform engineering, Kubernetes, GitOps and AI delivery by Dmitrii Mashkov. Explore projects and engineering notes, or get in touch on Telegram.`
- RU: `Дмитрий Машков: платформенная инженерия, Kubernetes, GitOps и AI. Проекты, инженерные заметки и контакт в Telegram.`

The single server-rendered home description uses EN, as the default document
language does. RU is the dictionary translation. This task does not implement
dynamic head metadata or a Russian route. The same EN description feeds the
existing description, OG and Twitter outputs through `src/layouts/Base.astro`.

Descriptive Telegram contact text for the existing home contact link (the `text` of the Telegram entry of `ui.contactItems`):
- EN: `Dmitrii Mashkov on Telegram — @dmitriimashkov`
- RU: `Дмитрий Машков в Telegram — @dmitriimashkov`
- Keep its destination `https://t.me/dmitriimashkov` and the existing `Telegram` service label.

Structured identity:
- Keep `Person.name: Dmitrii Mashkov`.
- Add `Person.alternateName: Дмитрий Машков`.
- Preserve all three existing sameAs URLs, their order, and every other Person/WebSite value.

Journal entry copy (this proposal authors it, because the issue does not
supply it). File `src/content/journal/2026-11-05-q24-home-snippet-in-both-scripts.md`:
- `title.en`: `Q24: One person, two scripts, a clearer home snippet`
- `title.ru`: `Q24: один человек, два алфавита и понятный сниппет главной`
- `seoTitle`: `A clearer home snippet in both scripts — Dmitrii Mashkov`
- `decided.en`: `The home page's search title and description now say what the site is about: platform engineering, Kubernetes, GitOps and AI delivery by Dmitrii Mashkov, with projects, engineering notes and a Telegram contact. The page's structured data now also names the same person in Cyrillic, Дмитрий Машков, so a search in either script points at one person. The Telegram contact link now reads as a phrase in each language instead of a bare handle; its address is unchanged. The title stays in Latin, the description served to search engines stays in English, and no new page, link, script or request was added.`
- `decided.ru`: `Заголовок и описание главной страницы в поисковой выдаче теперь говорят, о чём сайт: платформенная инженерия, Kubernetes, GitOps и AI-доставка от Дмитрия Машкова, с проектами, инженерными заметками и контактом в Telegram. Структурированные данные страницы теперь называют того же человека и кириллицей, Дмитрий Машков, поэтому поиск на любом из двух алфавитов ведёт к одному человеку. Ссылка на Telegram в контактах теперь читается как фраза на каждом языке, а не как голый ник; адрес не изменился. Заголовок остаётся латиницей, описание для поисковиков — на английском, новых страниц, ссылок, скриптов и запросов не добавлено.`

## User stories

- AS a person searching for Dmitrii Mashkov by name in Latin or Cyrillic I WANT the home result to show a title and description that say what he does SO THAT I can recognise the right result and click it.
- AS a search engine building a knowledge entry I WANT the home Person node to carry both the Latin name and the Cyrillic alternate name SO THAT both spellings resolve to one person.
- AS a reader of the home page in either language I WANT the Telegram contact link to say whose Telegram it is, in my language SO THAT the link is self-describing.
- AS the repository owner I WANT the change to keep the static, bilingual, zero-tracking architecture and the journal lifecycle SO THAT the DevLoop record stays verifiable.

## Acceptance criteria (EARS)

These reproduce the issue's six criteria. Each EARS line below is tagged with
the issue criterion it covers.

Issue criterion 1. Built home HTML has exactly one title, description, OG
title/description and Twitter title/description carrying the specified default
EN copy. The title dictionary entries match the exact copy above and stay Latin.
- WHEN the site is built THE SYSTEM SHALL emit in `dist/index.html` exactly one `<title>` element whose decoded text is `Dmitrii Mashkov — Platform Engineering & AI`.
- WHEN the site is built THE SYSTEM SHALL emit in `dist/index.html` exactly one `<meta name="description">`, exactly one `<meta property="og:description">` and exactly one `<meta name="twitter:description">`, each with decoded `content` equal to the EN `homeDescription`.
- WHEN the site is built THE SYSTEM SHALL emit in `dist/index.html` exactly one `<meta property="og:title">` and exactly one `<meta name="twitter:title">`, each with decoded `content` equal to `Dmitrii Mashkov — Platform Engineering & AI`.
- THE SYSTEM SHALL hold `ui.homeTitle.en` and `ui.homeTitle.ru` both equal to `Dmitrii Mashkov — Platform Engineering & AI`, with no Cyrillic character in either.

Issue criterion 2. Both descriptions and both translated contact strings are
committed character for character in the dictionary. Home metadata reads the
dictionary instead of duplicating a string literal.
- THE SYSTEM SHALL hold `ui.homeDescription.en` and `ui.homeDescription.ru` in `src/i18n/ui.ts` exactly equal to the EN and RU description copy above.
- THE SYSTEM SHALL hold the Telegram entry of `ui.contactItems.en` with `text` exactly `Dmitrii Mashkov on Telegram — @dmitriimashkov`, and the Telegram entry of `ui.contactItems.ru` with `text` exactly `Дмитрий Машков в Telegram — @dmitriimashkov`.
- THE SYSTEM SHALL pass the home description to `Base` from `src/pages/index.astro` as `description={ui.homeDescription.en}`. No description string literal may remain in that template.

Issue criterion 3. The existing home Telegram contact renders the specified
EN/RU text using the current `.l.en` / `.l.ru` mechanism and retains its URL
and service label. No extra Telegram link is added solely for keyword
repetition.
- WHEN the home page is built THE SYSTEM SHALL render the existing Telegram contact `<a href="https://t.me/dmitriimashkov">` containing `<span class="l en">Dmitrii Mashkov on Telegram — @dmitriimashkov</span>` and `<span class="l ru" lang="ru">Дмитрий Машков в Telegram — @dmitriimashkov</span>` through `src/i18n/Lang.astro`.
- WHILE the Telegram contact is rendered THE SYSTEM SHALL keep its label `Telegram` in both languages and its `href` `https://t.me/dmitriimashkov`, identical across languages.
- THE SYSTEM SHALL keep exactly one `<a>` on `dist/index.html` whose `href` is `https://t.me/dmitriimashkov`, and keep the Email, LinkedIn and GitHub contact entries unchanged in label, href and text.

Issue criterion 4. The existing home JSON-LD graph still has Person then
WebSite, with the exact Cyrillic alternateName added only to Person. Existing
sameAs URLs and all other fields are unchanged. Existing schema assertions are
adapted for this deliberate seventh field. Forbidden-field and purity coverage
is retained.
- WHEN `homeJsonLd()` is called THE SYSTEM SHALL return a `@graph` of exactly two nodes, `Person` then `WebSite`.
- THE SYSTEM SHALL give the `Person` node exactly the keys `@type`, `name`, `alternateName`, `url`, `jobTitle`, `email`, `sameAs`, with `name` `Dmitrii Mashkov` and `alternateName` `Дмитрий Машков`. `url`, `jobTitle`, `email` and the ordered three-entry `sameAs` stay unchanged.
- THE SYSTEM SHALL leave the `WebSite` node with exactly `@type`, `name`, `url`, `inLanguage` and their current values, and no `alternateName`.
- IF `dist/index.html`'s Person node lacks `alternateName` or carries any other value THEN `scripts/check-dist.mjs` SHALL report a problem naming `Person.alternateName` or the Person key list.
- THE SYSTEM SHALL retain the existing forbidden-field test (`worksFor`, `address`, `alumniOf`, `telephone`, `potentialAction`) and the purity/fresh-object test in `test/seo.test.ts`.

Issue criterion 5. Existing and relevant updated checks pass (`npm test`,
production build and the repository's build-output checks). The built output is
verified for the copy and structured identity changes. No new client script,
cookie, third-party subresource, analytics, dependency or external browser
request is introduced.
- WHEN `npm test`, `npm run build` and `node scripts/check-dist.mjs` run THE SYSTEM SHALL pass them all.
- THE SYSTEM SHALL leave `package.json` dependencies and `package-lock.json` unchanged, add no `<script>` other than the existing inline preference script and the JSON-LD data block, and leave the CSP inline-script hash unchanged.
- THE SYSTEM SHALL add no new external `src`/`href` subresource, cookie or analytics code.

Issue criterion 6. Add the cycle journal entry using the repository's lifecycle
contract. Do not fabricate future merge/release/deployment timestamps. Use the
existing supported pending-state representation until closure.
- THE SYSTEM SHALL add `src/content/journal/2026-11-05-q24-home-snippet-in-both-scripts.md` with `status: in_progress`, `issue: https://github.com/mctlhq/portfolio/issues/195`, `proposal_slug: issue-195-improve-home-search-snippet-and-bilingua`, `issue_opened_at: '2026-11-05T22:58:58Z'`, `visibility: public`, `indexing: noindex`, `interventions: []` and the journal copy above.
- IF a merge, release, release time, deployment time, approval time or PR number is not known at commit time THEN THE SYSTEM SHALL omit that field rather than invent it. `release`, `released_at` and `deployed_at` are always absent from an `in_progress` entry, per `docs/journal.md` and `statusEvidenceProblems` in `src/lib/journal.ts`.
- WHILE this entry is `in_progress` THE SYSTEM SHALL have no other journal entry in `in_progress`.

## Out of scope

Reproduced from the issue:
- New language routes or hreflang.
- Changing the Latin-title policy.
- Dynamic metadata after a language toggle.
- New landing pages.
- Changes to job history, capabilities, numbers, projects or contact destinations.
- A new Person graph.
- Analytics or cookies.
- Changing indexing decisions for journal/ADR pages.
- Infrastructure or DNS.
- Changing the release process.
- Guarantees about ranking or CTR.

Also from the issue's "Expected files": do not modify AGENTS.md, reserved
workflow files, ADR-0004, package dependencies, or deployment configuration.
Implied by the above: `og:image:alt` / `OG_IMAGE_ALT` in `Base.astro`,
`public/og.svg` and `og:site_name` stay unchanged.

## Open questions

- The issue supplies no journal-entry copy. This proposal authors the title,
  `seoTitle` and `decided` text above, both languages. The reviewer should
  check that copy before approval.
- `indexing: noindex` for the new entry follows the convention of every entry
  after 2026-09-13 (all later entries, Q23 included, are `noindex`). It does not change any existing entry's indexing.
- Whether `proposal_approved_at` and `pr` go in the entry: the implementer
  cannot observe either, so both are omitted. The journal-closure workflow
  records `pr`/`merged_at`/`release`/`released_at` later. This is the
  "supported pending-state representation" the issue refers to.
- Lifting the "contactItems text identical across languages" invariant in
  `test/ui.test.ts` for the Telegram entry is required by criterion 3. The
  invariant stays for the other three entries and for every `href`.
