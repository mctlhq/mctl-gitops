# Design: issue-46-q2-content-links-fail-contrast-footer-an

## Current state

**No anchor colour exists for page content.** `src/layouts/Base.astro` links
five stylesheets: `public/assets/mctl/mctl.css` (tokens),
`public/assets/mctl/global.css`, `public/assets/mctl/prose.css`,
`public/assets/fonts/fonts.css` and `/styles/site.css` (the build-time copy of
`src/styles/site.css` made by `scripts/vendor-assets.mjs`). `global.css` is 28
lines and sets only `box-sizing`, `body` and `::selection` — it has no `a` rule
and no `text-decoration` declaration anywhere, so anchors keep the user-agent
colour *and* the user-agent underline. `prose.css` does carry
`.mctl-prose a { color: var(--accent); text-decoration: none; border-bottom: 1px
solid var(--surface-line-strong) }`, but nothing on the site sets
`class="mctl-prose"`, so the rule never matches. `src/styles/site.css` colours
anchors in exactly four places: `.site-nav a` (and `:hover`), `.site-footer a`
(`color: inherit`), `.cta` (and `:hover`) and `.project-links a`.

**Token values, read from `public/assets/mctl/mctl.css` and measured with the
same WCAG relative-luminance formula `scripts/check-contrast.mjs` already
implements:**

| token | dark | light |
| --- | --- | --- |
| `--surface-bg` | `#0a0b0d` | `#f1ede4` |
| `--surface-elevated` | `#0f1114` | `#f7f4ec` |
| `--accent` | `#e25a3c` | `#b83d28` |
| `--accent-highlight` | `#ff8a6a` | `#9a3220` |

| pair | dark | light |
| --- | --- | --- |
| `--accent` over `--surface-bg` | 5.40:1 | 4.81:1 |
| `--accent` over `--surface-elevated` | 5.19:1 | 5.11:1 |
| `--accent-highlight` over `--surface-bg` | 8.53:1 | 6.30:1 |
| `--accent-highlight` over `--surface-elevated` | 8.19:1 | 6.70:1 |
| `#0000EE` over `--surface-bg` | 2.10:1 | 8.04:1 |
| `#551A8B` over `--surface-bg` | 1.79:1 | 9.43:1 |

The 2.10 figure reproduces the axe `color-contrast` 2.09 in the issue, and
`--accent` clears 4.5:1 in both themes with margin — so the design system's own
accent is a legitimate link colour and no new token is needed.

**Affected markup.** `Base.astro` has no `<main>`; each of the seven page
files authors its own (`src/pages/index.astro:18`, `work.astro:26`,
`approach.astro:19`, `colophon/index.astro:28`, `colophon/journal/[...slug].astro:36`,
`colophon/adr/[...slug].astro:46`, `404.astro:12`). The unclassed content links
are: `index.astro:57-58` (the Contact `<Details>`), `CycleTable.astro:37,41,42`
and `colophon/index.astro:72` (both tables), the journal meta block
(`[...slug].astro:43,45`) and the two "Back to the colophon" links, and
`404.astro:15`.

**Contrast script.** `scripts/check-contrast.mjs` parses raw `--mctl-*` hex
tokens out of `mctl.css`, maps semantic names to raw tokens per theme in
`SEMANTIC_TOKENS`, and walks a hard-coded `PAIRS` list (7 pairs × 2 themes = 14)
with a 4.5:1 threshold for `kind: 'text'` and 3:1 for `kind: 'focus-ring'`. It
never reads `src/styles/site.css`, so it cannot see what colour a rule actually
declares — it asserts about tokens, not about the stylesheet. It runs
`await main()` at module top level, so it cannot currently be imported by a
test. `docs/accessibility-checklist.md` records the resulting pair count and
the tightest ratio in prose.

**Footer.** `src/components/Footer.astro` imports `pkg` from `package.json`
(version `0.1.11` today) and renders
`<Lang .../>:` then `<span data-release>{pkg.version}</span>`. `astro.config.mjs`
leaves `compressHTML` at its default `true`, which is why the newline between
the colon and the `<span>` is dropped and the page reads `Release:0.1.11`. The
codebase already knows this: `colophon/index.astro:46,49` writes explicit
`{' '}` expressions between a `<span>` and the following text for the same
reason. The source link is `href="https://github.com/mctlhq"`.
`test/colophon.test.ts:106-109` asserts the footer imports `package.json`,
renders `{pkg.version}` and contains no `\d+\.\d+\.\d+` literal.
`scripts/check-dist.mjs` asserts `data-release` equals `package.json`'s version
on every built page.

**Colophon chain list.** `ui.colophonChainItems` is a seven-item string array
per language, rendered as `<li>{item}</li>` in two sibling `<ul class="l en">` /
`<ul class="l ru">` blocks (`colophon/index.astro:34-39`). `test/ui.test.ts`
requires every value in `ui` to be an `{ en, ru }` pair of strings or of
equal-length string arrays, so the items cannot be restructured into objects
without breaking that invariant; `stackChipRu` and `stackChipUntranslated` are
the existing precedent for auxiliary data living outside `ui`.

**Gates.** `npm test` = `check-no-metrics.mjs`, `check-contrast.mjs`, then 15
`node --test` files. `prebuild` = `npm run vendor && npm test`, so `npm test`
runs *before* `astro build` and can never see `dist/`; `check-dist.mjs` exists
for that and runs only inside the Dockerfile today.
`.github/workflows/build.yml` has a `test` job (`npm test`) and a `build` job
that builds the image and runs `check-headers.mjs` against a live container.
AGENTS.md explicitly permits the implementer to edit `build.yml`, and equally
explicitly forbids acceptance criteria that require text in the pull request
body.

## Proposed solution

### 1. `main a` in `src/styles/site.css`, not `.mctl-prose`

Add one block to `src/styles/site.css`, after the existing "Navigation" and
"CTAs" sections:

```css
/* Content links: every <a> inside <main> that carries no styling of its own.
   Chosen over putting class="mctl-prose" on <main> -- see design.md. */
main a,
main a:visited {
  color: var(--accent);
}
main a:hover {
  color: var(--accent-highlight);
}
/* :visited raises specificity to (0,1,2), which would otherwise beat .cta
   (0,1,0) and .project-links a (0,1,1). Pin both so a visited CTA or work
   link keeps its current colour. */
.cta:visited {
  color: var(--surface-fg);
}
.project-links a:visited {
  color: var(--surface-fg);
}
```

The underline is left to the user agent (nothing resets it), so colour is not
the only signal and WCAG 1.4.1 is untouched. `.site-nav a` and `.site-footer a`
live outside `<main>` in `Base.astro` and cannot be reached by these selectors
at all.

Also extend the existing `@media print` block, which forces a light palette but
leaves `--accent` at the dark primary (3.64:1 on white):

```css
  --accent: var(--mctl-accent-terracotta-light-primary); /* 5.62:1 on #fff */
```

### 2. `scripts/check-contrast.mjs` reads the stylesheet

Three changes, keeping the file's existing shape (problems accumulated into an
array, `process.exitCode = 1`, named exemptions rather than lowered
thresholds):

1. Add `'accent-highlight'` to `SEMANTIC_TOKENS` for both themes
   (`mctl-accent-terracotta-{dark,light}-highlight`).
2. Add a `LINK_STATES` list — `{ selector: 'main a', state: 'link' }`,
   `{ selector: 'main a:visited', state: 'visited' }`,
   `{ selector: 'main a:hover', state: 'hover' }` — and a
   `linkColourProblems(siteCss, tokens)` function that, for each state, finds
   the rule block whose comma-separated selector list contains that selector,
   reads its `color:` declaration, and resolves it per theme: `var(--accent)`
   and `var(--accent-highlight)` and `var(--surface-fg)` through
   `SEMANTIC_TOKENS`, a literal `#rrggbb` as itself, anything else as an
   unresolvable failure. Each resolved colour is checked at `kind: 'text'`
   (4.5:1) against `surface-bg` and `surface-elevated` in both themes. A state
   with no matching rule, or a rule with no `color`, is itself a problem, with
   the message naming the browser default that would apply (`#0000EE`, or
   `#551A8B` for the visited state) and its measured ratio on dark.
3. Export the pure helpers (`parseTokens`, `contrastRatio`, `resolveColour`,
   `linkColourProblems`) and guard the top-level `await main()` with a
   direct-invocation check
   (`import.meta.url === pathToFileURL(process.argv[1]).href`) so
   `node scripts/check-contrast.mjs` still behaves exactly as today while a
   test can import the module without running it.

The red/green proof lives in a new `test/contrast-link.test.ts` added to the
`node --test` list in `package.json`: it imports `linkColourProblems`, feeds it
the committed `src/styles/site.css` (expects zero problems), then feeds it three
mutated copies of that same text — `main a` colour replaced with `#0000EE`,
`main a:visited` colour replaced with `#551A8B`, and the whole `main a` block
deleted — and asserts each mutation produces a problem naming the dark theme.
That satisfies "prove the new assertion by mutation" inside `npm test`, where
the implementer can actually deliver it.

`docs/accessibility-checklist.md` gains a "Content link contrast" row and has
its pair count updated to the number the script prints.

### 3. Footer

`src/components/Footer.astro`:

```astro
<a href={REPO_URL}>
  <Lang en={ui.footerGithubLabel.en} ru={ui.footerGithubLabel.ru} />
</a>
...
<span>
  <Lang en={ui.footerReleaseLabel.en} ru={ui.footerReleaseLabel.ru} />{' '}
  <a href={releaseTagUrl(pkg.version)}><span data-release>{pkg.version}</span></a>
</span>
```

The explicit `{' '}` survives `compressHTML`, as it already does on the
colophon page. `REPO_URL` and `releaseTagUrl()` come from a new
`src/lib/links.ts`:

```ts
export const REPO_URL = 'https://github.com/mctlhq/portfolio';
export const PACKAGES_URL = `${REPO_URL}/packages`;
export function releaseTagUrl(version: string): string {
  return `${REPO_URL}/releases/tag/${version}`;
}
```

Tags in this repository are semver without a `v` prefix (AGENTS.md,
"Releases"), so `${REPO_URL}/releases/tag/0.1.10` is the correct shape —
verified 200 on 2026-09-11. No digits enter `Footer.astro`, so
`check-no-metrics.mjs` and the existing no-semver-literal assertion in
`test/colophon.test.ts` both stay green, and `data-release` still wraps the
version so `check-dist.mjs`'s parity check is unaffected.

### 4. Colophon chain links

Keep `ui.colophonChainItems` byte-identical and linkify by substring. Add to
`src/lib/links.ts`:

```ts
export const CHAIN_LINKS = [
  { text: 'github.com/mctlhq/portfolio', href: REPO_URL },
  { text: 'ghcr.io/mctlhq/portfolio', href: PACKAGES_URL },
] as const;

export function splitByLinks(item: string): Array<{ text: string; href?: string }>;
```

`splitByLinks` scans the item for the longest matching entry at each position
and returns an ordered list of plain and linked segments; a segment order that
matters here because `github.com/mctlhq/portfolio` is a prefix-free set with
`ghcr.io/mctlhq/portfolio`, but the longest-match rule keeps it correct if a
shorter entry (e.g. `github.com/mctlhq`) is ever added.
`colophon/index.astro` then renders
`<li>{splitByLinks(item).map((s) => (s.href ? <a href={s.href}>{s.text}</a> : s.text))}</li>`
for both language lists. Because the split is applied identically to the `en`
and `ru` arrays, the `class="l en"` / `class="l ru"` counts that
`check-dist.mjs` compares are unchanged, and the Russian prefixes
(`Исходники: `, `Образ: `) stay verbatim. A unit test in a new
`test/links.test.ts` covers `splitByLinks` (segment order, no text lost, both
languages) and `releaseTagUrl`.

### 5. `scripts/check-links.mjs` and the CI step

New script, modelled on `check-dist.mjs` (walks `dist/`, accumulates problems,
`process.exitCode = 1`) and on `vendor-assets.mjs`'s network policy:

- Walk `dist/**/*.html`, extract every `href`, dedupe.
- Internal `href` (`/…`): resolve against the tree — `/colophon/` must be
  `dist/colophon/index.html`; a miss is a hard failure. This also covers the
  `trailingSlash: 'always'` convention.
- `mailto:` — recorded and skipped, with a printed line saying so.
- External `http(s)`: one sequential `GET` with redirects followed, a 30s
  timeout and one retry; any final status other than 200 fails.
- The release-tag URL is classified `soft`: 200 passes, 404 prints a warning
  and passes, anything else fails. release-please bumps `package.json` inside
  the release pull request, so on that one pull request the tag genuinely does
  not exist yet and a hard check would block the release the repository depends
  on.
- If the request layer itself throws (DNS, timeout, refused connection), the
  run prints `check-links: network unreachable, skipping external checks` and
  exits 0 — the same fallback shape `vendor-assets.mjs` uses, so an offline
  build is not turned into a failure.

`.github/workflows/build.yml`'s `test` job replaces `- run: npm test` with
`- run: npm run build` (whose `prebuild` is `npm run vendor && npm test`, so
the same tests still run, once) and adds `- run: node scripts/check-links.mjs dist`.
The output lands in the CI log where a reviewer can read it.
`docs/link-check.md` records the command, the date and the status table from a
real run, since the implementer cannot paste it into the pull request body.

## Alternatives

1. **`class="mctl-prose"` on `<main>` (the issue's option b).** Dropped, and it
   is the more interesting rejection. There is no `<main>` in `Base.astro`, so
   this is a seven-file change, not the one-file change the issue's own "files
   expected to change" list implies. Worse, `.mctl-prose a` (specificity 0,1,1)
   beats `.cta` (0,1,0), so both home-page call-to-action links would turn
   accent-coloured and lose their underline suppression in favour of a
   `border-bottom` — a direct violation of acceptance criterion 3. The class
   also brings a container font-family/size/line-height, `h2 { border-bottom }`,
   new margins on `p`/`ul`/`ol`, `code` recoloured to `--syntax-key` on a
   `--surface-card` background, and `blockquote`/`hr` rules, all of which would
   collide with `.hero-name`, `.subline`, `.stat-*` and the colophon tables in
   `site.css`. That is a redesign, not a contrast fix.
2. **Adding a new `--link` token or a literal hex.** Dropped: `--accent`
   already clears 4.5:1 in both themes (5.40 / 4.81), `--focus-ring` is
   `var(--accent)` so links and their focus ring stay one colour, and a literal
   hex would be the one thing the new script is designed to reject.
3. **Checking only token pairs in `check-contrast.mjs`, as today.** Dropped:
   adding `{ fg: 'accent', bg: 'surface-bg', kind: 'text' }` to `PAIRS` would
   prove the accent is contrast-safe but says nothing about whether any rule
   uses it, so deleting the `main a` rule would leave the build green. The
   issue asks specifically for a check that fails on a revert, which forces the
   script to read `src/styles/site.css`.
4. **Restructuring `ui.colophonChainItems` into objects with `href` fields.**
   Dropped: `test/ui.test.ts` requires every `ui` value to be an `{ en, ru }`
   pair of strings or equal-length string arrays, and the copy is the contract
   — splitting sentences into fragments invites drift between the languages.
   Substring linkification keeps both language strings byte-identical.
5. **Running the external link check inside `npm test`.** Dropped: `npm test`
   runs from `prebuild`, before `dist/` exists, and the site's build is
   expected to survive an offline network (see the fallback in
   `vendor-assets.mjs`). A network check belongs after the build, in CI, with a
   skip-on-unreachable policy.

## Platform impact

- **Migrations:** none. No content schema, no data file, no deployment
  configuration changes. `src/styles/site.css` is copied to
  `public/styles/site.css` by `npm run vendor`, which `prebuild` already runs,
  so the new rules ship without any manual step — but the copy under
  `public/styles/` is committed, so the implementer must run `npm run vendor`
  and commit the regenerated file or the deployed CSS will lag the source.
- **Backward compatibility:** the visible change is limited to link colour
  inside `<main>`, one footer separator, one footer `href`, and two new links
  on `/colophon/`. No URL, route or public asset path changes. `data-release`
  keeps its exact current shape, so `check-dist.mjs`'s parity check and any
  external consumer of that hook are unaffected.
- **Resource impact:** none at runtime. Roughly ten CSS declarations; no new
  network request from the browser (links are navigations, not subresources),
  so the "zero third-party browser requests" constraint and the CSP are
  untouched — `check-dist.mjs`'s absolute-subresource scan only looks at
  `link`/`script`/`img`/`source`. CI gains one build and one link-check step in
  the `test` job (the tests themselves run the same number of times as before,
  since `npm run build` invokes them through `prebuild`).
- **Risks and mitigations:**
  - *`:visited` specificity leaking into classed links* — the exact defect
    acceptance criterion 3 guards. Mitigated by the explicit `.cta:visited` and
    `.project-links a:visited` pins, and by a source-level assertion in
    `test/a11y.test.ts` that both pins exist.
  - *Browser `:visited` privacy restrictions* — `color` is one of the few
    properties a browser will apply to `:visited`, so this works; but it also
    means the computed style cannot be read back by script. This is why the
    proof is a static analysis of the stylesheet rather than a rendered
    measurement.
  - *Release-tag link 404 on the release pull request* — mitigated by the soft
    classification in `check-links.mjs`, documented in the script's header.
  - *GitHub rate-limiting the anonymous link check* — mitigated by
    deduplication, sequential requests and a single retry; a transport-level
    failure degrades to a skip rather than a red build.
  - *`ghcr.io` link target* — `https://ghcr.io/mctlhq/portfolio` and
    `https://github.com/mctlhq/portfolio/pkgs/container/portfolio` both return
    404 anonymously today, so the link points at
    `https://github.com/mctlhq/portfolio/packages` (200). Recorded as an open
    question; revisit if the container package is published publicly.
  - *Print contrast* — the `@media print` block forces a white background but
    not a new accent, so without the one-line override printed links would sit
    at 3.64:1. Included here because the block already exists and the fix is a
    single declaration.
