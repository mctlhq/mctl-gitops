# Design: issue-195-improve-home-search-snippet-and-bilingua

## Current state

All observations below come from the clone at `a5f91fa` (package version 0.1.53).

- `src/i18n/ui.ts`: the bilingual dictionary. `homeTitle` is
  `{ en: 'Dmitrii Mashkov', ru: 'Dmitrii Mashkov' }`. Its comment explains
  that `<title>` holds one Latin string. `heroName` is the Latin/Cyrillic pair.
  The dictionary has no `homeDescription` key. `contactItems.en` and
  `contactItems.ru` each hold four `{ label, href, text }` entries. The
  Telegram entry is `{ label: 'Telegram', href: 'https://t.me/dmitriimashkov',
  text: '@dmitriimashkov' }` in both languages. The comment above
  `contactHeading` says "href and text are identical across languages by
  design ... only label is rendered as a <Lang> pair".
- `src/pages/index.astro`: renders `<Base title={ui.homeTitle.en}
  description="Platform engineering with AI on proven open source. Dmitrii
  Mashkov builds and runs ...">`, a hard-coded literal. The contact list
  renders `<a href={item.href}><Lang en={item.text} ru={item.text} /></a>`, so
  the RU span reuses the EN text.
- `src/layouts/Base.astro`: takes `title` and `description` props and emits
  one `<title>`, `meta[name=description]`, `og:title`, `og:description`,
  `twitter:title` and `twitter:description` from them. Base also injects
  `homeJsonLd()` when `Astro.url.pathname === '/'` and no `jsonLd` prop is
  given. `OG_IMAGE_ALT` and `og:site_name` are fixed strings. The inline
  `<script is:inline>` is the only executable script, and its hash is in the
  CSP. A `type="application/ld+json"` block is excluded from CSP hashing
  (`src/lib/csp.ts` header comment).
- `src/lib/seo.ts`: `homeJsonLd()` returns `@graph: [Person, WebSite]`.
  Person has `@type`, `name`, `url`, `jobTitle`, `email`, `sameAs` (LinkedIn,
  GitHub, Telegram in that order). WebSite has `@type`, `name`, `url`,
  `inLanguage: 'en'`. The JSDoc says the Person carries "exactly" those
  fields.
- Tests that pin the current values and must change deliberately:
  - `test/ui.test.ts` line ~161: asserts `ui.homeTitle.en/ru === 'Dmitrii Mashkov'`.
  - `test/ui.test.ts` line ~247: `deepEqual`s both `contactItems` arrays and
    asserts `text` is identical across languages for every entry.
  - `test/home.test.ts` line ~95: the "no literal name in template" test
    strips `description="..."` before checking. Its comment calls the
    description out-of-scope prose.
  - `test/home.test.ts` line ~328: asserts the RU span carries
    `ui.contactItems.en[i].text`.
  - `test/home.test.ts` line ~366: parses the built JSON-LD and `deepEqual`s
    the Person key list (six fields).
  - `test/seo.test.ts` lines 68-128: Person keys (six), sameAs order, WebSite
    keys, forbidden fields, purity.
  - `scripts/check-dist.mjs` `HOME_PERSON_KEYS` (line ~302) and
    `checkHomeJsonLd()`. `test/check-dist.test.ts` builds a well-formed
    fixture graph (line ~200) that `checkHomePage` must accept.
- No test today asserts the built `<title>` / description / OG / Twitter
  values of `dist/index.html`.
- `scripts/check-no-metrics.mjs` scans `src/pages`, `src/components`,
  `src/layouts` for two-digit numbers. The new copy contains no digits.
- Journal: `docs/journal.md` defines the lifecycle. Schema is
  `src/content.config.ts` (`journalSchema`), with cross-field rules in
  `src/lib/journal.ts` (`statusEvidenceProblems`: `in_progress` forbids
  `release`, `released_at`, `deployed_at`; `merged_at` implies `pr`).
  `checkJournalCollection` allows at most one `in_progress` entry. Today no
  entry is `in_progress`. The latest entry is
  `2026-10-25-q23-snapshot-releases-merge-themselves.md` (issue #174), so the
  increasing-stamp rule is satisfied by #195. `test/indexing.test.ts`
  requires every entry to declare `indexing:` explicitly.
  `test/title.test.ts` scans journal titles against the 65/75-character
  budget.

Deployed state checked:
- `mctl_get_service_config(team=labs, service=portfolio)`: imageTag `0.1.53`,
  host `labs-portfolio.mctl.ai`, port 80, `base-service`, no database.
- `$MCTL_GITOPS_ROOT/services/labs/portfolio/values.yaml`: `tag: "0.1.53"`,
  ingress hosts `labs-portfolio.mctl.ai` and `dmitriimashkov.com`. This matches
  the canonical `https://dmitriimashkov.com/` used in `homeJsonLd()`.
- The Search Console figures quoted in the issue were not observed by this
  run (no GSC access). They are used only as motivation and appear nowhere on
  the site.

## Proposed solution

1. Dictionary (`src/i18n/ui.ts`)
   - Set `homeTitle` to `{ en: 'Dmitrii Mashkov — Platform Engineering & AI',
     ru: 'Dmitrii Mashkov — Platform Engineering & AI' }`. Keep and lightly
     update the comment: the title is still a single Latin string on both
     sides.
   - Add `homeDescription` directly after `homeTitle`:
     - en: `Platform engineering, Kubernetes, GitOps and AI delivery by Dmitrii Mashkov. Explore projects and engineering notes, or get in touch on Telegram.`
     - ru: `Дмитрий Машков: платформенная инженерия, Kubernetes, GitOps и AI. Проекты, инженерные заметки и контакт в Telegram.`

     A comment states that only `.en` is server-rendered into `<head>` and
     that `.ru` is the dictionary translation (no dynamic head metadata).
   - Change only the `text` of the Telegram entry. In `contactItems.en`, use
     `Dmitrii Mashkov on Telegram — @dmitriimashkov`. In `contactItems.ru`,
     use `Дмитрий Машков в Telegram — @dmitriimashkov`. `label: 'Telegram'`
     and `href` stay as they are, and the other three entries are untouched.
     Update the `contactItems` comment: `href` is identical across languages,
     and `text` is identical except for the Telegram entry, which is
     translated descriptive text.
2. Home page (`src/pages/index.astro`)
   - `description={ui.homeDescription.en}` replaces the literal.
   - In the contact list, `<Lang en={item.text} ru={ui.contactItems.ru[index].text} />`.
     The structure already used for `label` is kept. No new link is added.
3. Structured identity (`src/lib/seo.ts`)
   - In `homeJsonLd()`, add `alternateName: 'Дмитрий Машков'` to the Person
     node immediately after `name`. Update the JSDoc so it says Person has
     exactly seven entries: `@type`, `name`, `alternateName`, `url`,
     `jobTitle`, `email`, `sameAs`. Add a short reason: the Cyrillic name of
     the same person, matching `ui.heroName.ru`, so both scripts resolve to
     one entity (issue #195). WebSite is unchanged.
4. Base layout: no change. It already routes the `title`/`description` props
   into the six head outputs, so a single dictionary value drives all of them.
   Astro escapes `&` as `&amp;` in text and attributes. That is valid and
   decodes to the specified copy.
5. Build-output gate (`scripts/check-dist.mjs`)
   - Add `'alternateName'` to `HOME_PERSON_KEYS` and add an exact-value check
     `person.alternateName !== 'Дмитрий Машков'` → problem naming
     `Person.alternateName`. Update the docstring ("six named fields").
6. Journal: add
   `src/content/journal/2026-11-05-q24-home-snippet-in-both-scripts.md` with
   the frontmatter fields and copy given in requirements.md:
   ```
   service: portfolio
   issue: https://github.com/mctlhq/portfolio/issues/195
   proposal_slug: issue-195-improve-home-search-snippet-and-bilingua
   status: in_progress
   visibility: public
   indexing: noindex
   title: { en, ru }   (from requirements.md)
   seoTitle: "A clearer home snippet in both scripts — Dmitrii Mashkov"
   decided: { en, ru } (from requirements.md)
   issue_opened_at: '2026-11-05T22:58:58Z'
   interventions: []
   ```
   The entry has no `pr`, `merged_at`, `release`, `released_at`,
   `deployed_at` or `proposal_approved_at`, because none is observable at
   commit time. Closure fills them later.

Why this approach: the dictionary is already the single source of every
user-facing string. Putting `homeDescription` there removes the only
duplicated head literal on the home page and lets a test assert the copy
against one value. The Person node is extended rather than duplicated, because
the issue forbids a new Person graph.

## Alternatives

- Render the RU description into `<head>` when the toggle is set, or add a
  `/ru/` route with hreflang. Rejected: explicitly out of scope. It would
  need client script (forbidden beyond the 400-byte preference script) or a
  route the architecture does not have.
- Add a separate visible "Telegram channel" link or keyword line to match
  the observed queries. Rejected: criterion 3 forbids an extra Telegram link
  added for keyword repetition.
- Put the Cyrillic name in `Person.name` and the Latin one in
  `alternateName`, or use an array `name`. Rejected: the issue fixes
  `name: Dmitrii Mashkov`, and the site's default language is English.
- Leave `homeDescription` out of `ui.ts` and only edit the literal in
  `index.astro`. Rejected: criterion 2 requires the metadata to read the
  dictionary.

## Platform impact

- No migrations, no dependency, Dockerfile, nginx, CSP or gitops change. The
  inline-script hash is unaffected (JSON-LD is not hashed, and the preference
  script is untouched).
- `dist/index.html` grows by roughly 150-250 bytes (longer title and
  description in six places, two longer contact spans, one JSON-LD field). It
  stays under the `MAX_INDEX_BYTES` cap in `scripts/check-dist.mjs`, and
  check-dist enforces that.
- Backward compatibility: the canonical URL, routes and `og:image` are
  unchanged. Search engines pick up the new snippet on recrawl. No ranking or
  CTR outcome is claimed.
- Risk: the em dash or ampersand gets mistyped or entity-mangled. Mitigation:
  tests compare decoded built output against the dictionary value, and
  dictionary tests compare against literal copies of the contract.
- Risk: a second `in_progress` journal entry exists by the time of
  implementation. Mitigation: `checkJournalCollection` fails the build, and
  AGENTS.md allows one cycle at a time.
- Deployment happens through the normal release-please → release-deploy path.
  Nothing in this cycle triggers a deploy by hand.
