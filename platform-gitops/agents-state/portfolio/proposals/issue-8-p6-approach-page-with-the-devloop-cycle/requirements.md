# P6: Approach page with the DevLoop cycle as an inline SVG

## Context

The site has a home page (`src/pages/index.astro`) and a work page
(`src/pages/work.astro`). The primary navigation (`src/components/Nav.astro`)
still points its third link at `/#approach`, an anchor that no longer exists:
`test/home.test.ts` asserts that `id="approach"` was removed from the home page
when P4 landed. This cycle builds the page that link was always meant to reach.

`/approach/` answers the question the home page only claims: what "the agentic
way" actually is. It carries one theme-aware inline SVG of the ten-step DevLoop
cycle, a `Gates` block naming the four rules that make the loop governed, a
`Numbers` block reading three values from the metrics snapshot, and a
`Proven open source` block listing the stack the loop runs on. The diagram is
the argument of the page, so it has to be legible at 360 px, legible in both
themes, announced to assistive technology, and bilingual like every other
string on the site — with no raster asset, no client JavaScript and no
third-party request, per ADR-0002 and the site constraints in `AGENTS.md`.

## User stories

- AS a hiring manager reading on a phone I WANT the whole development cycle as
  one readable picture SO THAT I understand the process without reading prose.
- AS a Russian-speaking reader I WANT every label on the page, including the
  labels inside the diagram, in Russian SO THAT the page reads as written
  rather than translated.
- AS a screen-reader user I WANT the diagram to announce a name and a
  description SO THAT I get the same content as a sighted reader.
- AS a skeptical engineer I WANT the numbers on this page to come from a dated
  snapshot SO THAT I can tell a measurement from a claim.
- AS the maintainer I WANT the page's promises (SVG weight, bilingual parity,
  no typed metric digits) enforced by a script in the build SO THAT a later
  change cannot quietly break them.

## Copy (the contract)

Every user-facing string below is the exact text to ship. Strings marked
`[issue]` are reproduced character for character from the issue; strings marked
`[authored]` are new text this proposal introduces because the artefact
requires it (an accessible name, a page `<title>`, a journal entry) and the
issue supplies none.

### Page shell

- Page `<title>` `[authored]`, one Latin string in both languages, following
  `ui.workPageTitle`: `Approach — Dmitrii Mashkov`
- `<h1>`: reuses the existing `ui.navApproach` pair — EN `Approach`,
  RU `Подход`

### Intro paragraph `[issue]`

- EN: `Inside the platform this cycle is called the DevLoop. A change starts as a written issue and ends as a deployment that the platform observed — every step leaves a record a person can audit.`
- RU: `Внутри платформы этот цикл называется DevLoop. Изменение начинается как написанный issue и заканчивается деплоем, который платформа наблюдала — каждый шаг оставляет след, который человек может проверить.`

### Diagram node labels `[issue]`, in loop order

| # | EN | RU | gate |
|---|----|----|------|
| 1 | `Issue` | `Issue` | no |
| 2 | `Investigate` | `Исследование` | no |
| 3 | `Proposal` | `Предложение` | no |
| 4 | `Approve` | `Одобрение` | yes (human) |
| 5 | `Implement` | `Реализация` | no |
| 6 | `Review gate` | `Ревью-гейт` | yes (automated) |
| 7 | `Shepherd merge` | `Мерж шефердом` | no |
| 8 | `Release` | `Релиз` | no |
| 9 | `Deploy` | `Деплой` | no |
| 10 | `Monitor` | `Наблюдение` | no |

After `Monitor` the loop returns to `Issue`.

### SVG accessible name and description `[authored]`

Both hold one string carrying both languages, separated by ` / `, exactly as
`src/components/Nav.astro` already does for `aria-label`
(`${ui.navLabel.en} / ${ui.navLabel.ru}`). An SVG `<title>` contributes its
whole text content to the accessible name and is never rendered, so a
CSS-hidden `.l.ru` child inside it would still be announced; the slash form is
deterministic.

- `<title>`: `The DevLoop cycle / Цикл DevLoop`
- `<desc>`: `A closed loop of ten steps: Issue, Investigate, Proposal, Approve, Implement, Review gate, Shepherd merge, Release, Deploy, Monitor, and back to Issue. Approve and Review gate are drawn with a dashed outline because they are the two gates: Approve is a human decision, Review gate is automated. / Замкнутый цикл из десяти шагов: Issue, Исследование, Предложение, Одобрение, Реализация, Ревью-гейт, Мерж шефердом, Релиз, Деплой, Наблюдение и снова Issue. Одобрение и Ревью-гейт нарисованы пунктиром, потому что это две контрольные точки: Одобрение — решение человека, Ревью-гейт — автоматический.`

### Details block 1 — summary `[issue]`

- EN `Gates` / RU `Контрольные точки`

Bullets, in order `[issue]`:

- EN 1: `The implementer never reads the issue; it reads only the approved proposal, so a proposal must contain every acceptance criterion before approval.`
- EN 2: `Approval is a durable signal into the workflow, not an edit of a file.`
- EN 3: `Every pull request passes an automated reviewer; unresolved high-severity findings block the merge.`
- EN 4: `The main branch accepts merge commits only, requires a review, and has no administrator bypass.`
- RU 1: `Имплементер никогда не читает issue; он читает только одобренное предложение, поэтому предложение должно содержать каждый критерий приёмки до одобрения.`
- RU 2: `Одобрение — это устойчивый сигнал в воркфлоу, а не правка файла.`
- RU 3: `Каждый pull request проходит автоматического ревьюера; незакрытые находки высокой серьёзности блокируют мерж.`
- RU 4: `Ветка main принимает только merge-коммиты, требует ревью и не имеет обхода для администратора.`

### Details block 2 — summary `[issue]`

- EN `Numbers` / RU `Числа`

Three stat labels, in order `[issue]`, each rendered by the existing
`src/components/Stat.astro`:

1. EN `DevLoop proposals` / RU `Предложений DevLoop` — value
   `metrics.sources.mctl.devloop_proposals`
2. EN `Services in production` / RU `Сервисов в проде` — value
   `metrics.sources.mctl.services`
3. EN `Releases` / RU `Релизов` — value `metrics.sources.github.releases`

Label 2 is character-identical to the existing `ui.statServices` pair and
reuses it. Label 3 differs from the existing `ui.statReleases` pair, whose
Russian side is `Релизы`; the issue asks for `Релизов` here, so this page gets
its own key and the home page keeps its wording.

Snapshot caption: the existing `ui.statCaptionPrefix` pair (EN `Snapshot`,
RU `Снимок`) followed by a space and `snapshotDate(metrics.generated_at)` from
`src/lib/metrics.ts`, exactly as `src/pages/index.astro` renders it today. With
the current placeholder `src/data/metrics.json` every value is `null`, so all
three stats and the date render as the em dash `—` returned by `formatStat`
and `snapshotDate`.

### Details block 3 — summary `[issue]`

- EN `Proven open source` / RU `Проверенный open source`

List items: the nine items of the home page's `What I run` block
(`ui.detailsRunItems`, rendered by `src/pages/index.astro`) in their existing
order, followed by four more. In full:

- EN: `k3s on Hetzner, provisioned with OpenTofu`, `ArgoCD, Argo Workflows and Argo Rollouts`, `HashiCorp Vault with External Secrets`, `CloudNativePG`, `VictoriaMetrics, Grafana and Loki`, `Traefik and cert-manager`, `Temporal`, `Backstage`, `Cloudflare`, `Claude Agent SDK`, `release-please`, `Astro`, `nginx`
- RU: `k3s на Hetzner, разворачивается OpenTofu`, `ArgoCD, Argo Workflows и Argo Rollouts`, `HashiCorp Vault с External Secrets`, `CloudNativePG`, `VictoriaMetrics, Grafana и Loki`, `Traefik и cert-manager`, `Temporal`, `Backstage`, `Cloudflare`, `Claude Agent SDK`, `release-please`, `Astro`, `nginx`

The four added items are product names, identical in both languages.

### Journal entry `[authored]`

`src/content/journal/2026-09-11-approach-page.md`, frontmatter only, matching
`src/content/journal/2026-09-11-work-page.md`:

- `service: portfolio`
- `issue: https://github.com/mctlhq/portfolio/issues/8`
- `proposal_slug: issue-8-p6-approach-page-with-the-devloop-cycle`
- `visibility: public`
- `title.en`: `Approach page`
- `title.ru`: `Страница подхода`
- `decided.en`: `The site now has /approach/: the ten-step DevLoop cycle as one theme-aware inline SVG with bilingual labels and an accessible name, a Gates block naming the four rules that make the loop governed, three numbers read from the dated metrics snapshot, and the open-source stack the loop runs on — still zero JavaScript and no raster asset.`
- `decided.ru`: `На сайте появилась страница /approach/: десятишаговый цикл DevLoop одной инлайн-SVG, которая следует теме, с двуязычными подписями и доступным именем, блок контрольных точек с четырьмя правилами, три числа из датированного снимка метрик и open-source-стек, на котором работает цикл — по-прежнему без JavaScript и без растровых изображений.`
- `issue_opened_at: '2026-09-10T22:48:15Z'` (the issue's GitHub `created_at`)
- `proposal_approved_at`: the timestamp of the approval commit, in the same
  quoted ISO 8601 form

## Acceptance criteria (EARS)

### Page and routing

1. WHEN a reader requests `/approach/` THE SYSTEM SHALL serve a static page
   built from `src/pages/approach.astro` that uses `src/layouts/Base.astro`,
   with the page `<title>` `Approach — Dmitrii Mashkov`.
2. WHEN the primary navigation renders THE SYSTEM SHALL link its Approach entry
   to `/approach/`, not to `/#approach`.
3. WHILE the page is served THE SYSTEM SHALL ship no client-side JavaScript
   from it: `scripts/check-dist.mjs` already fails the build on any `.js` file
   under `dist/`, and that check SHALL continue to pass.

### Content and bilingual parity

4. WHEN the page renders THE SYSTEM SHALL show the intro paragraph, the three
   details blocks and every diagram node label as `.l en` / `.l ru` pairs whose
   text is character-identical to the Copy section above.
5. WHILE `dist/approach/index.html` exists THE SYSTEM SHALL contain an equal
   number of `class="l en"` and `class="l ru"` occurrences in that file,
   counting the occurrences inside the inline SVG; the build SHALL fail
   otherwise.
6. WHILE the inline SVG exists in `dist/approach/index.html` THE SYSTEM SHALL
   contain an equal number of `class="l en"` and `class="l ru"` occurrences
   *within each `<svg>` element itself*, so the parity of criterion 5 cannot be
   satisfied by text outside the diagram.
7. WHEN the third details block renders THE SYSTEM SHALL list the nine items of
   `ui.detailsRunItems` first, in their existing order and unmodified, followed
   by `Claude Agent SDK`, `release-please`, `Astro`, `nginx`, in both
   languages; the shared prefix SHALL be derived from one source array in
   `src/i18n/ui.ts`, not re-typed.

### Metrics provenance

8. WHEN the `Numbers` block renders THE SYSTEM SHALL read all three values from
   `src/data/metrics.json` through expressions rooted at `metrics.sources.`,
   and SHALL render the snapshot date through
   `snapshotDate(metrics.generated_at)`.
9. WHILE `src/pages/approach.astro` exists THE SYSTEM SHALL contain no digit in
   its template region (everything after the frontmatter fence) other than
   digits that are part of an HTML heading element name (`<h1>`…`<h6>`), the
   same mechanical proxy `test/home.test.ts` applies to the home page.
10. IF a metric value in `src/data/metrics.json` is `null` THEN THE SYSTEM SHALL
    render the em dash `—` for that stat, via the existing `formatStat`.
11. WHILE `src/components/CycleDiagram.astro` exists THE SYSTEM SHALL neither
    import `src/data/metrics.json` nor render any stat, so the diagram's
    geometry digits can never be mistaken for a typed metric.

### The diagram

12. WHEN the diagram renders THE SYSTEM SHALL draw the ten nodes in the order
    `Issue`, `Investigate`, `Proposal`, `Approve`, `Implement`, `Review gate`,
    `Shepherd merge`, `Release`, `Deploy`, `Monitor`, connected as a closed
    loop whose last connector returns to `Issue`.
13. WHEN the diagram renders THE SYSTEM SHALL mark `Approve` and `Review gate`
    with a stroke visibly distinct from the other eight nodes, using a dashed
    outline in the accent colour so the distinction survives a monochrome
    rendering and is not carried by colour alone.
14. WHILE the inline SVG markup exists THE SYSTEM SHALL keep the total byte
    length of all `<svg>…</svg>` elements in `dist/approach/index.html` under
    12288 bytes (12 KB); the build SHALL fail otherwise.
15. WHILE the inline SVG markup exists THE SYSTEM SHALL contain no raster data:
    no `<image` element, no `data:` URI, no `xlink:href`, and no reference to a
    `.png`, `.jpg`, `.jpeg`, `.gif` or `.webp` file; the build SHALL fail
    otherwise.
16. WHILE the inline SVG markup exists THE SYSTEM SHALL express every colour as
    `currentColor` or a `var(--…)` design token, and SHALL contain no literal
    colour (`#rrggbb`, `rgb(`, `hsl(`, or a named CSS colour); the build SHALL
    fail otherwise. This is the mechanical half of the contrast criterion: the
    diagram's text then inherits exactly the `--surface-fg` on `--surface-bg`
    pair the page body already uses, which measures 15.9:1 in the dark theme
    (`#e6e7e9` on `#0a0b0d`) and 15.2:1 in the light theme (`#15181d` on
    `#f1ede4`), and the gate stroke uses `--accent`, which measures 5.4:1 dark
    (`#e25a3c`) and 4.8:1 light (`#b83d28`) — all above 4.5:1.
17. WHEN each `<svg>` element in `dist/approach/index.html` is inspected THE
    SYSTEM SHALL carry on it `role="img"` and an `aria-labelledby` whose every
    id token resolves to the `id` of a `<title>` or `<desc>` element inside
    that same `<svg>`; each `<svg>` SHALL contain exactly one `<title>` and one
    `<desc>`, each carrying both the English and the Russian text of the Copy
    section; the build SHALL fail otherwise.
18. WHILE two layout variants of the diagram exist THE SYSTEM SHALL give every
    `id` in each variant a variant-specific suffix, so no `id` is duplicated in
    the document.
19. WHILE the viewport is narrower than 600 px THE SYSTEM SHALL show the
    vertical variant of the diagram and hide the wide variant, and vice versa
    at 600 px and above, through a media query in `src/styles/site.css`.
20. WHILE the diagram is rendered THE SYSTEM SHALL size it fluidly: every
    `<svg>` SHALL carry a `viewBox`, SHALL carry no `width`/`height` presentation
    attribute, and SHALL be sized by CSS `width: 100%; height: auto;`, so it
    cannot overflow its container at any viewport width. The narrow variant's
    `viewBox` width SHALL be at most 360. The build SHALL fail if any `<svg>`
    on the page lacks a `viewBox` or carries a `width` or `height` attribute.
21. WHILE the diagram is rendered THE SYSTEM SHALL use no font smaller than
    13 CSS px at the 360 px breakpoint for node labels, and SHALL NOT use
    `--font-editorial` anywhere on the page or in the diagram (Instrument Serif
    ships no Cyrillic subset, so any translated string set in it drops its
    Russian half onto a fallback family).

### Styling and delivery

22. WHILE the page is served THE SYSTEM SHALL satisfy the existing
    `style-src 'self'` Content-Security-Policy in `nginx.conf`: all new CSS
    SHALL go into `src/styles/site.css` (vendored to `public/styles/site.css`
    by `npm run vendor`), and no `style` attribute or inline `<style>` element
    SHALL be introduced.
23. WHEN `npm test` runs THE SYSTEM SHALL execute a new
    `test/approach.test.ts`, wired into the `test` script in `package.json`.
24. WHEN `node scripts/check-dist.mjs` runs after `npm run build` THE SYSTEM
    SHALL evaluate criteria 5, 6, 14, 15, 16, 17 and 20 against
    `dist/approach/index.html` and exit non-zero, naming the failing check, if
    any of them does not hold.
25. WHEN the cycle is committed THE SYSTEM SHALL add the journal entry
    `src/content/journal/2026-09-11-approach-page.md` with the frontmatter of
    the Copy section, valid against the `journal` collection schema in
    `src/content.config.ts`.

### Reviewer steps (not implementer criteria)

Per `AGENTS.md`, work that genuinely needs a human is named as a reviewer step
rather than an acceptance criterion, because the implementer cannot satisfy it
with a commit:

- R1. Open `/approach/` at a 360 px viewport in a browser, in both themes, and
  confirm the diagram is readable with no horizontal scroll.
- R2. Measure the rendered text and gate-stroke contrast with a contrast tool
  in both themes and confirm the figures in criterion 16.
- R3. Confirm with an actual screen reader that the diagram announces its name
  and description; this is recorded in `docs/accessibility-checklist.md` during
  P8, not in this cycle (per the issue).

## Out of scope

- Animation of the diagram, in any form.
- Real metric values: `src/data/metrics.json` stays as it is, every value
  `null`, rendering as an em dash. The collector lands in P8b.
- `docs/accessibility-checklist.md` and the screen-reader confirmation it
  records (P8).
- The `/colophon/` page the home page already links to.
- Any change to `.github/workflows/claude-review.yml`,
  `.github/workflows/release-please.yml` or `.github/dependabot.yml`
  (reserved by the bootstrap boundary in `AGENTS.md`).
- Any new npm dependency, browser-driven test runner, or client-side script.
- Changing the home page's own `What I run` block or `ui.statReleases`.

## Open questions

- The issue caps "the SVG" at 12 KB but sanctions two CSS-toggled variants.
  This proposal reads the cap as applying to the *sum* of all `<svg>` elements
  on the page, which is the stricter reading; criterion 14 enforces that.
- The issue asks for a `<title>` and `<desc>` "in both languages". A `<title>`
  contributes its entire text content to the accessible name even when a child
  is `display:none`, so this proposal uses one `EN / RU` string per element
  (the existing `Nav.astro` `aria-label` convention) rather than an
  `.l.en`/`.l.ru` pair. A reviewer who prefers the pair form should say so
  before approval.
- The gate distinction is explained only in the SVG `<desc>` and in the
  adjacent `Gates` block; no visible legend is added, because the issue
  supplies no copy for one and this proposal prefers not to invent visible
  prose. If a visible legend is wanted, it needs EN and RU copy in a follow-up.
- The breakpoint between the two layouts is set at 600 px, the value implied by
  the issue's "under 600 px width". No other breakpoint in the repo to match.
- `Releases` on this page is `Релизов`, while the home page's identical English
  label is `Релизы`. Assumed deliberate (genitive after a count); both are
  kept.
