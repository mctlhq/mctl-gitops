# Design: issue-98-q15-conversion-first-home-role-history-c

## Current state

Everything below was read in a clone of `mctlhq/portfolio` at `249feed`.

**Home page.** `src/pages/index.astro` renders, in this order:
`<h1 class="hero-name">` (a `<Lang>` pair on `ui.heroName`), `<p class="thesis">`,
`<p class="subline">`, `<section class="stats">` with four `<Stat>` components
whose `value=` props are all rooted at `metrics.sources.*` plus a
`.stat-caption`, a `<span id="ctas-label" class="visually-hidden">` followed by
`<nav class="ctas" aria-labelledby="ctas-label">` with two `.cta` links
(`/work/`, `/colophon/`), and three `<Details>` blocks bound to
`ui.detailsRunSummary`, `ui.detailsWorkSummary` and `ui.detailsContactSummary`
(the last one `open`, holding a GitHub link and a `mailto:` link).

**Copy.** `src/i18n/ui.ts` is a single `as const` dictionary of `{ en, ru }`
entries (strings or string arrays), plus two separate exports
(`stackChipRu`, `stackChipUntranslated`) that are deliberately *not* `ui` keys
because `test/ui.test.ts` requires every `ui` value to be an `{ en, ru }` pair.
`src/i18n/Lang.astro` renders
`<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`;
`src/styles/site.css` hides the non-selected half with
`:root[data-lang='en'] .l.ru { display: none }` and its mirror. Block-level
`.l.en` / `.l.ru` containers are already used (`<ul class="l en">` in
`index.astro` and `approach.astro`, `<div class="l en">` in
`ProjectCard.astro`), so a block container is an established pattern, not a new
one.

**Layout and structured data.** `src/layouts/Base.astro` already accepts an
optional `jsonLd` prop and emits
`<script type="application/ld+json" set:html={JSON.stringify(jsonLd).replace(/</g,'\\u003c')}>`
when it is truthy. Only `src/pages/colophon/journal/[...slug].astro` and
`src/pages/colophon/adr/[...slug].astro` pass it, both via
`breadcrumbJsonLd()` from `src/lib/seo.ts` (a zero-import module, so
`test/seo.test.ts` can exercise it under plain `node --test`).
`src/lib/csp.ts`'s `INLINE_SCRIPT_RE` excludes
`type="application/ld+json"`, which is why a data block never enters the CSP
hash — proven by `test/csp.test.ts` T5 and relied on by both
`scripts/csp-hash.mjs` and `scripts/check-headers.mjs`.

**Styles.** `src/styles/site.css` declares `.hero-name`, `.thesis`,
`.subline`, `.stats`/`.stat*`, `.ctas` (flex, wrap, `--mctl-space-4` gap),
`.cta` (inline-flex, `min-block-size: 44px`, bordered, `--surface-fg`),
`.cta:hover` (`--accent` text and border), the visited pin
`.cta:visited:not(:hover) { color: var(--surface-fg) }`, the `.block`
disclosure family, and content-link rules `main a`, `main a:visited:not(:hover)`
and `main a:hover`. The one existing accent-filled affordance is
`.toggle-group button[aria-pressed='true'] { background: var(--accent); color: var(--accent-fg); border-color: var(--accent) }`.
The print block hides `.ctas` and force-expands `.block` bodies.

**Gates that constrain this change.**
- `scripts/check-dist.mjs` runs inside the `Dockerfile` build
  (`RUN npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs`).
  Its `checkHomePage()` asserts the bilingual hero `<h1>`, `<title>` exactly
  `Dmitrii Mashkov` with no Cyrillic, **exactly one `<details open>`** and
  **exactly three `<summary><h2`** on `dist/index.html`; `checkJsonLd()` is
  applied only under `colophon/journal/` and `colophon/adr/`;
  `MAX_INDEX_BYTES` is `40 * 1024`.
- `test/home.test.ts` asserts: exactly three `<Details` tags, all with
  `heading`, exactly one with `open` bound to `ui.detailsContactSummary`;
  `href="/work/"` and `href="/colophon/"` both present; no digit anywhere in
  the rendered template once `h1`-`h6` tag names are stripped; the hero `<h1>`
  shape; and `.hero-name`'s font resolution.
- `test/ui.test.ts` requires every `ui` entry to be `{ en, ru }` of the same
  kind, and for arrays requires **every item to be a non-empty string**.
- `test/a11y.test.ts` enforces `min-block-size >= 24px` for a fixed
  `TARGET_SELECTORS` list (including `.cta`) and forbids any `animation:` or
  `transition:` declaration.
- `scripts/check-contrast.mjs` validates a fixed pair list: `surface-fg`,
  `surface-fg-muted`, `accent` over `surface-bg`/`surface-elevated`, and
  `accent-fg` over `accent` (plus the `main a` link colours).
  `surface-fg` over `accent` is **not** in that list.
- `scripts/check-no-metrics.mjs` scans `src/pages`, `src/components`,
  `src/layouts` for any 2+ digit number; `src/i18n` and `src/lib` are not
  scanned, and `src/content/projects` gets a separate version-number gate.
- `scripts/check-links.mjs` opens no socket (`test/links.test.ts` asserts the
  source contains none of `fetch(`, `node:http`, `setTimeout`, `retry`, ...);
  `docs/link-check.md` records why external checking is out of scope) and
  reports off-origin and `mailto:` hrefs as skipped, by count and listed.
- `test/projects.test.ts` carries an `EXPECTED_LINKS` table whose
  `mctl-loyalty` row currently names `https://labs-mctl-loyalty.mctl.ai` and is
  matched against the raw frontmatter of both language files.
- `docs/journal.md` and the journal schema in `src/content.config.ts`: at most
  one `in_progress` entry collection-wide; no entry is `in_progress` today
  (the last cycle, `2026-09-13-q14-...`, is `complete`).

## Proposed solution

### 1. Copy (`src/i18n/ui.ts`)

Add, in the home-page region of the dictionary and next to the existing hero
and CTA keys: `heroEyebrow`, `ctaContact`, `aboutHeading`, `aboutParagraphs`
(3 strings per language), `capabilitiesHeading`, `capabilityItems` (3
`{ term, body }` objects per language), `contactHeading`, `contactIntro`,
`contactItems` (4 `{ label, href, text }` objects per language). Remove
`detailsContactSummary`, whose only consumer disappears. All values are the
verbatim strings in `requirements.md` sections A-D.

`capabilityItems` and `contactItems` are the first `ui` entries whose array
items are objects. `test/ui.test.ts` grows one branch: when an item is a plain
object, require the `en` and `ru` objects at the same index to have the same
key set and a non-empty string at every leaf, keeping the existing "same kind"
and "same length" assertions. This preserves the parity guarantee rather than
weakening it.

For `contactItems`, `href` and `text` are identical across languages by
construction; a test asserts that equality so a future edit cannot desync the
two arrays into two different destinations.

### 2. Page structure (`src/pages/index.astro`)

Rendered order after this change:

```
<p class="eyebrow">            <Lang heroEyebrow>
<h1 class="hero-name">         <Lang heroName>          (unchanged)
<p class="thesis">             <Lang heroThesis>        (unchanged)
<p class="subline">            <Lang heroSubline>       (unchanged)
<span id="ctas-label" ...>     <Lang ctasLabel>         (moved with the nav)
<nav class="ctas" ...>         a.cta.cta-primary -> #contact  (ctaContact)
                               a.cta             -> /work/    (ctaWork)
<section id="about">           h2 aboutHeading + 3 <p> per language
<section id="capabilities">    h2 capabilitiesHeading + 3x (h3 term + p body)
<section class="stats">        unchanged (four <Stat>, .stat-caption)
<Details detailsRunSummary>    unchanged
<Details detailsWorkSummary>   unchanged
<section id="contact">         h2 contactHeading + p contactIntro + ul of 4 links
```

The CTA block moves above `.stats` (see `requirements.md` open question 1); the
`<nav class="ctas">` element, its class and its `aria-labelledby` pairing are
otherwise untouched.

Bilingual rendering follows the two patterns already in the file:
`<Lang>` for single strings (eyebrow, headings, `contactIntro`, contact
labels), and paired block containers for the lists:

```astro
<section id="about">
  <h2><Lang en={ui.aboutHeading.en} ru={ui.aboutHeading.ru} /></h2>
  <div class="l en">{ui.aboutParagraphs.en.map((text) => <p>{text}</p>)}</div>
  <div class="l ru" lang="ru">{ui.aboutParagraphs.ru.map((text) => <p>{text}</p>)}</div>
</section>
```

`#capabilities` uses the same two-container shape, each container holding three
`<h3>` + `<p>` pairs. `#contact` renders one `<ul class="contact-list">` whose
four `<li>` each hold a `<Lang>` label pair and exactly one `<a href>` with the
item's `text` — the href and the visible text are identifiers (an address, a
hostname, a handle) and stay untranslated, per `AGENTS.md`.

Nothing in the new template contains a digit, so `test/home.test.ts`'s
"no digit in the rendered markup" proxy still holds: every number-bearing
string lives in `src/i18n/ui.ts`, which that test does not scan and
`scripts/check-no-metrics.mjs` does not walk. `OAuth 2.1` therefore never
enters a scanned directory.

### 3. Structured data (`src/layouts/Base.astro` + `src/lib/seo.ts`)

Add `homeJsonLd(site: string): object` to `src/lib/seo.ts` (zero-import, so
`test/seo.test.ts` exercises it directly) returning a single graph:

```ts
{
  '@context': 'https://schema.org',
  '@graph': [
    { '@type': 'Person', name: 'Dmitrii Mashkov', url: <site>/, jobTitle: 'Senior platform engineer',
      email: 'mailto:hello@dmitriimashkov.com',
      sameAs: ['https://www.linkedin.com/in/dmitriimashkov', 'https://github.com/mctlhq', 'https://t.me/dmitriimashkov'] },
    { '@type': 'WebSite', name: 'Dmitrii Mashkov', url: <site>/, inLanguage: 'en' },
  ],
}
```

`<site>/` is `new URL('/', site).href`, i.e. `https://dmitriimashkov.com/`
derived from `astro.config.mjs`'s `site: 'https://dmitriimashkov.com'`, never
typed as a literal. No `worksFor`, `address`, `alumniOf`, `telephone` or
`SearchAction`.

`Base.astro` chooses what to emit:

```ts
const isHome = Astro.url.pathname === '/';
const structuredData = isHome ? homeJsonLd(Astro.site!.href) : jsonLd;
```

and the existing `{structuredData && <script type="application/ld+json" ...>}`
block emits it. Consequences: the home route gains exactly one block; journal
and ADR routes keep passing `breadcrumbJsonLd()` through the `jsonLd` prop
untouched; every other route still emits nothing; no page can ever emit two
blocks, because one expression feeds one element. The CSP is unaffected —
`INLINE_SCRIPT_RE` already excludes `ld+json`, and no executable inline script
changes, so `scripts/csp-hash.mjs`, `scripts/check-headers.mjs` and
`test/csp.test.ts` are untouched.

### 4. Styles (`src/styles/site.css`)

- `.eyebrow`: `--font-display`, `--mctl-typography-font-size-sm`,
  `--surface-fg-muted`, uppercase-free (the copy already carries its own
  casing), small bottom margin, so the hero block reads as eyebrow → name →
  thesis. Muted-on-surface is an already-validated contrast pair.
- `.cta-primary`: mirrors the one existing filled affordance —
  `background: var(--accent); color: var(--accent-fg); border-color: var(--accent);`.
  Two pins are mandatory, because the existing `.cta:hover` sets
  `color: var(--accent)` (accent text on an accent fill = invisible) and
  `.cta:visited:not(:hover)` sets `color: var(--surface-fg)` (a pair
  `check-contrast` does not validate):
  `.cta-primary:hover`, `.cta-primary:visited:not(:hover)` keep
  `color: var(--accent-fg)` with the accent background, distinguishing hover by
  `border-color: var(--accent-highlight)` only. No `transition`, no
  `animation` — `test/a11y.test.ts` forbids both.
- `.identity`/`#about p`, `.capability-list h3`/`p`: measure, spacing and a
  `--surface-line` separator consistent with `.block`; body copy inherits the
  page font.
- `.contact-list`: `list-style: none`, flex/grid rows, and
  `.contact-list a { display: inline-flex; min-block-size: 24px; align-items: center; }`
  matching the hit-area floor issue #88 (Q13) applied to `.project-links a`,
  `.breadcrumb a`, `.journal-meta a` and `.table-scroll a`. The selector is
  added to `TARGET_SELECTORS` in `test/a11y.test.ts` so the floor is enforced,
  not merely present.
- No new colour literal: every declaration uses an `--mctl-*` or semantic
  token, so `scripts/check-contrast.mjs` keeps passing without a new pair.

### 5. Dist-level checks (`scripts/check-dist.mjs`)

`checkHomePage()` is updated with the structure this cycle produces:
`<details open>` count `0` (the contact disclosure is gone; the two remaining
blocks are closed), `<summary><h2` count `2`, and a home-page JSON-LD check
that reuses the existing "exactly one `application/ld+json` block, must parse"
shape and asserts the `Person`/`WebSite` fields. The generic per-page
`checkJsonLd()` stays scoped to journal/ADR pages so their `BreadcrumbList`
contract is unchanged. Without this edit the Docker image build fails, since
`check-dist.mjs` runs inside the `Dockerfile`.

### 6. Project link correction

`src/content/projects/mctl-loyalty.en.md` and `.ru.md`: the single
`    url: https://labs-mctl-loyalty.mctl.ai` line becomes
`    url: https://rewards.mctl.ai`. `checkProjectParity()` in
`src/content.config.ts` compares `links[].url` across the two language files,
so both must change together or the content build throws. The
`EXPECTED_LINKS` row in `test/projects.test.ts` is updated to the same URL; the
`Service` / `Сервис` labels stay.

### 7. Journal entry

One new file, `src/content/journal/2026-09-13-q15-conversion-first-home.md`
(date per the merge day), with `status: in_progress`, `service: portfolio`,
`issue: https://github.com/mctlhq/portfolio/issues/98`,
`proposal_slug: issue-98-q15-conversion-first-home-role-history-c`,
`visibility: public`, bilingual `title` and `decided`, `issue_opened_at`, and
`interventions: []`; no `pr`, `merged_at`, `release`, `released_at` or
`deployed_at`. `docs/journal.md` and the loader's collection-wide check allow
this because no other entry is currently `in_progress`. Consider `seoTitle` and
`indexing` in line with the last few entries so `test/title.test.ts` stays
inside its 65/75-character budget.

## Alternatives

1. **Pass the home JSON-LD from `src/pages/index.astro` through the existing
   `jsonLd` prop** (no `Base.astro` change at all). Rejected: the issue places
   the graph in `Base.astro` and scopes it to "the home route only", and
   keeping the route test (`pathname === '/'`) in the layout means a future
   second home-like route cannot silently inherit or lose the graph. The
   helper still lives in `src/lib/seo.ts`, so the data remains unit-testable
   either way.
2. **Keep the identity, capability and contact copy inside `<details>`
   blocks** (smallest diff, reuses `Details.astro`, keeps `check-dist.mjs`'s
   current counts). Rejected: it is precisely the defect — a screener will not
   click three disclosures, and acceptance criterion 3 forbids it explicitly.
3. **Flatten `capabilityItems` / `contactItems` into parallel string arrays**
   (`capabilityTerms`, `capabilityBodies`, `contactLabels`, `contactHrefs`,
   `contactTexts`) so `test/ui.test.ts` needs no change. Rejected: the issue
   fixes the object shapes, and parallel arrays let a term and a body drift
   out of alignment — exactly the failure mode `test/support/expected-projects.ts`
   was created to end last cycle.
4. **Make `scripts/check-links.mjs` fetch the external contact destinations**
   to satisfy acceptance criterion 9 literally. Rejected: it would re-introduce
   the CI flake that issue #55 removed, break `test/links.test.ts`'s
   no-network proof, and contradict `docs/link-check.md`. Reporting the skipped
   off-origin hrefs by name (existing behaviour) plus reviewer step 3 covers
   the intent.

## Platform impact

- **Migrations:** none. No schema change, no data migration, no deployment
  topology change. `rewards.mctl.ai` already exists and serves the same
  application (declared in `mctlhq/mctl-gitops` at
  `platform-gitops/services/labs/mctl-loyalty/values.yaml`); this cycle only
  changes which host the portfolio links to.
- **Backward compatibility:** `/#contact` is a new in-page anchor; no route is
  added or removed, so no redirect and no sitemap change. `ctaColophon` stays
  in `ui.ts` and in the nav/footer, so the colophon remains reachable.
  `detailsContactSummary` is removed with its only consumer.
- **Resource impact:** static output only; no new runtime request, no new
  asset, no client script. The page grows by roughly 6-7 KB of bilingual copy
  plus a small JSON-LD block, against a 40960-byte
  `MAX_INDEX_BYTES` cap on `dist/index.html`.
- **Risks and mitigations:**
  - *`dist/index.html` exceeds the byte cap.* Mitigation: measure right after
    the first `npm run build` (`node scripts/check-dist.mjs` prints the byte
    count on a passing run); if it is close, report it in the journal entry
    rather than trimming the contracted copy or raising the cap.
  - *The Docker build fails on the stale `<details open>` / `<summary><h2`
    counts.* Mitigation: section 5 changes them in the same commit; verify by
    running `node scripts/check-dist.mjs` locally after `npm run build`, not
    only `npm test`.
  - *The primary CTA becomes unreadable on hover or after a visit* because of
    the existing `.cta` pins. Mitigation: the two explicit `.cta-primary` pins
    in section 4, plus `node scripts/check-contrast.mjs`.
  - *`test/ui.test.ts` rejects the new object arrays.* Mitigation: the widened
    kind check in section 1, landing in the same commit as the new keys.
  - *Russian copy breaks with JavaScript disabled.* Mitigation: every new
    bilingual pair uses the established `.l.en` / `.l.ru` containers with
    `lang="ru"` on the Russian half — CSS-only, no script involved; reviewer
    step 2 confirms.
  - *A claim on the page cannot be verified.* Mitigation: the copy names no
    employer, no number about an employer's systems, no availability
    statement and no location; the only numbers on the page remain the four
    `metrics.json`-derived counters.
