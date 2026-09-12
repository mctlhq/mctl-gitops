# Q8: backfill the five missing journal entries from the polish wave

> **Operator amendment, applied before approval (2026-09-12).** The
> deliverable is **six** content files, not five: the five backfilled entries
> described throughout, plus **this cycle's own journal entry**, specified as
> Copy (normative) -> 6 in `requirements.md` and as task 6b in `tasks.md`.
> Every cycle writes its own entry; a backfill that repeats the omission it
> corrects has corrected nothing. Consequently the derived cycle counter is
> **20**, not 19, and `git status --porcelain` must list six added files.
> Propagated in full on 2026-09-12 after review: every derived-effect count in
> this file now reads six, and the remaining "five" mentions are the ones that
> genuinely mean the five backfilled entries (the backfill itself, the rejected
> alternatives, and the copy blocks). The scope remains content files only.

## Context

`AGENTS.md` requires one journal entry per DevLoop cycle under
`src/content/journal/YYYY-MM-DD-<slug>.md`. Five consecutive cycles of the
polish wave (issues #45, #55, #47, #48, #49) shipped without one, on the
mistaken belief that the `journal` schema in `src/content.config.ts` needs
timestamps the implementer cannot know. It does not: `merged_at`,
`released_at` and `deployed_at` are `.optional()`, and the shipped entry
`src/content/journal/2026-09-11-p8-production-hardening-accessibility-wc.md`
already carries only `issue_opened_at` and `proposal_approved_at`. The
omission cost five entries; this cycle backfills them.

The site exists to be a verifiable artifact of the DevLoop, and the colophon
is where that claim is made. `src/pages/colophon/index.astro` computes
`const cycleCount = journal.length` from the collection, and
`scripts/check-dist.mjs` re-derives the same number by scanning
`src/content/journal/*.md` independently, so five missing files mean the
public cycle count under-reports the loop by five. Adding the files raises
the counter by exactly six — the five backfilled entries plus this cycle's own
— adds six rows to `CycleTable.astro` and six
pages at `/colophon/journal/<slug>/`, with no literal to edit anywhere. This
cycle adds content files only: no code, no style, no template change.

The issue states the counter moves "from 13 to 18". The checkout as it
stands today holds **fourteen** public entries under `src/content/journal/`
(every one carries `visibility: public`), the fourteenth being
`2026-09-12-q7-polish-wave-findings.md`, whose own cycle was approved at
`2026-09-12T12:36:04Z` — later than all five backfilled cycles. The issue's
arithmetic was written before that entry landed. What is normative here is
the invariant, not the number: the counter is `journal.length` and nothing
else, so after this change it reads **20** — nineteen from the backfill plus this
cycle's own entry (see "This cycle's own entry" below) — and `scripts/check-dist.mjs`
will enforce that against its own scan of the content directory. An
implementer who hard-codes 18 anywhere both violates criterion 5's own
"no literal count" clause and fails the build.

## User stories

- AS a reader of the colophon I WANT every DevLoop cycle to appear in the
  cycle table SO THAT the count and the table are a complete record rather
  than a filtered one.
- AS a reader following a cycle I WANT a `/colophon/journal/<slug>/` page for
  each of the five polish-wave cycles SO THAT I can read what was decided,
  in either language, and follow the link to the originating issue.
- AS the repository's maintainer I WANT the backfilled entries to validate
  against the same `z.strictObject` schema as every prior entry SO THAT the
  record stays machine-checkable and no per-entry exception is introduced.
- AS a Russian-reading visitor I WANT `title` and `decided` in Russian on all
  six entries SO THAT the `.l.en` / `.l.ru` toggle has a counterpart for
  every string on the new pages.

## Acceptance criteria (EARS)

- WHEN the build loads the `journal` collection THE SYSTEM SHALL find exactly
  six new files under `src/content/journal/` (the five below plus Copy 6),
  named
  `2026-09-11-csp-hash-quoting-and-browser-verified-headers.md`,
  `2026-09-12-content-link-contrast-and-an-offline-link-check.md`,
  `2026-09-12-repository-links-out-of-the-disclosure.md`,
  `2026-09-12-colophon-tables-and-computed-lead-time.md` and
  `2026-09-12-navigation-state-and-accessibility-affordances.md`.
- WHEN each new file is parsed against the `journal` schema in
  `src/content.config.ts` THE SYSTEM SHALL accept it: the seven required keys
  `service`, `issue`, `proposal_slug`, `visibility`, `title`, `decided`,
  `issue_opened_at` are present, `proposal_approved_at` is present, no key
  outside the schema appears (`z.strictObject`), and `merged_at`,
  `released_at` and `deployed_at` are omitted entirely.
- WHILE the six files exist THE SYSTEM SHALL leave `interventions` absent
  from each of them, so the schema's `.default([])` supplies the value and
  `totalInterventions()` over the collection is unchanged.
- WHEN `test/colophon.test.ts` scans `src/content/journal/*.md` THE SYSTEM
  SHALL find every timestamp value single-quoted and matching
  `ISO_WITH_OFFSET` from `src/lib/journal.ts`, so YAML never coerces one into
  a `Date` before Zod sees it.
- WHEN each file's frontmatter is written THE SYSTEM SHALL reproduce every
  timestamp, URL and `proposal_slug` character for character as given in the
  Copy section below, with no value reconstructed or reformatted.
- WHEN each file's body is written THE SYSTEM SHALL write no body at all:
  frontmatter delimited by `---` and nothing after the closing delimiter,
  matching every existing journal entry.
- WHEN the loader's `generateId` derives an id from each filename THE SYSTEM
  SHALL produce a slug that `src/pages/colophon/journal/[...slug].astro`
  turns into a page, so `dist/colophon/journal/<slug>/index.html` exists for
  all six after `npm run build`.
- WHEN a new journal page is rendered THE SYSTEM SHALL emit `title` and
  `decided` through `<Lang>` in both languages, so the built page has an
  equal count of `class="l en"` and `class="l ru"`, as
  `scripts/check-dist.mjs` check (b) requires.
- WHEN `dist/colophon/index.html` is produced THE SYSTEM SHALL carry a
  `data-cycle-count` and a `data-cycle-row` occurrence count both equal to
  the number of `visibility: public` files under `src/content/journal/`,
  derived from `journal.length` and the collection, with no literal count
  introduced in any file. WITH the fourteen entries present today plus the
  five backfilled here plus this cycle's own entry, that value is 20.
- WHILE the change is authored THE SYSTEM SHALL introduce no numeric literal
  for the cycle count anywhere — neither 18 nor 19 nor 20 — in `src/`, `scripts/`
  or `test/`.
- WHILE `data-intervention-count` is rendered THE SYSTEM SHALL report the
  same total as before this change, since none of the six entries records an
  intervention.
- IF a `decided` value contains a double quote character THEN THE SYSTEM
  SHALL keep the YAML scalar parseable while preserving the character exactly
  (escaped as `\"` inside the double-quoted scalar the other entries use).
- WHEN `node scripts/check-no-metrics.mjs` runs THE SYSTEM SHALL pass: that
  script scans `src/pages`, `src/components` and `src/layouts` only, and the
  figures quoted in `decided` are descriptive prose in a content file,
  exactly as in every prior entry.
- WHEN `npm test`, `npm run build` and `node scripts/check-dist.mjs` run THE
  SYSTEM SHALL exit zero, and `dist/` SHALL contain no file ending in `.js`.
- WHEN `node scripts/check-links.mjs` runs over the rebuilt tree THE SYSTEM
  SHALL resolve the new pages' internal links against `dist/` and report the
  six GitHub issue URLs as skipped off-origin, issuing no network request.

## Out of scope

- Editing any existing journal entry, including adding `merged_at`,
  `released_at` or `deployed_at` to entries that omit them.
- Any code, style, template, script or test change. This cycle adds six
  content files and nothing else.
- Any change to `src/content.config.ts`, including relaxing or extending the
  `journal` schema.
- Adding a `pr` or `release` field to the new entries; both are optional and
  both render as an em dash, which is the honest value for a record being
  backfilled from issue and proposal data alone.
- The fourteen findings tracked in #52 (shipped as
  `2026-09-12-q7-polish-wave-findings.md`).
- Writing an ADR. ADR-0006 already exists and is referenced in copy only.

## Copy (normative)

The five files below, together with Copy 6 further down, are the deliverable,
byte for byte. Key order matches
`2026-09-11-p8-production-hardening-accessibility-wc.md`. Timestamps are
single-quoted; `title` and `decided` values are double-quoted scalars, with
any internal double quote escaped as `\"`.

### 1. `src/content/journal/2026-09-11-csp-hash-quoting-and-browser-verified-headers.md`

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/45
proposal_slug: issue-45-q1-csp-hash-is-unquoted-so-the-site-s-on
visibility: public
title:
  en: "CSP hash quoting, and headers verified in a browser"
  ru: "Кавычки в CSP-хэше и заголовки, проверенные браузером"
decided:
  en: "Production served the inline script's SHA-256 as a bare token, so Chrome discarded it as an invalid source and refused to run the site's only script: the language and theme toggles were inert on every page and a stored preference was never applied. Four separate guards stayed green throughout — the generator emitted the unquoted form, the Dockerfile grepped for a substring, the runtime check tested the header for a substring, and the source-level test could only see the template placeholder. The fix quotes the token at the one place that writes a quote, and replaces every substring assertion with a parse of the script-src directive plus an end-to-end comparison against the bytes actually served. ADR-0006 records the rule the incident bought: a header counts as verified only when a browser engine has loaded the page and reported no violation."
  ru: "Прод отдавал SHA-256 инлайн-скрипта голым токеном, поэтому Chrome отбрасывал его как невалидный источник и отказывался выполнять единственный скрипт сайта: переключатели языка и темы не работали ни на одной странице, а сохранённый выбор не применялся. Четыре проверки при этом оставались зелёными — генератор печатал форму без кавычек, Dockerfile искал подстроку, рантайм-проверка искала подстроку в заголовке, а тест на уровне исходников видел только плейсхолдер в шаблоне. Починка ставит кавычки в единственном месте, которое их пишет, и заменяет все подстрочные утверждения разбором директивы script-src и сквозной сверкой с реально отданными байтами. ADR-0006 фиксирует правило, купленное этим инцидентом: заголовок считается проверенным только тогда, когда браузерный движок загрузил страницу и не сообщил о нарушении."
issue_opened_at: '2026-09-11T21:15:10Z'
proposal_approved_at: '2026-09-11T21:23:37Z'
---
```

### 2. `src/content/journal/2026-09-12-content-link-contrast-and-an-offline-link-check.md`

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/55
proposal_slug: issue-55-q2-content-link-contrast-footer-and-colo
visibility: public
title:
  en: "Content link contrast, and a link check that needs no network"
  ru: "Контраст ссылок в тексте и проверка ссылок без сети"
decided:
  en: "Links inside page content carried no colour rule at all, so they rendered in the user-agent default — 2.10:1 against the dark surface, 1.79:1 once visited, where WCAG 2.2 AA asks for 4.5:1. They now use the design system's accent, measured at 5.40:1 and 4.81:1, with the print palette overridden separately because the dark-theme accent falls to 3.64:1 on white. The cascade is pinned by a test that resolves the winning declaration for three selectors across four states rather than asserting that rules exist — an earlier attempt passed that weaker check while a visited call-to-action silently lost its hover colour. This cycle also replaced an earlier attempt whose acceptance criterion demanded that every link return HTTP 200: an external check makes the build depend on other people's uptime, and forgiving a network failure lets the gate pass without checking while not forgiving it makes CI flake on a rate limit. The link check now resolves internal references against the built tree and issues no request at all."
  ru: "Ссылки внутри текста не имели правила цвета вообще и рендерились браузерным умолчанием — 2.10:1 на тёмной поверхности и 1.79:1 после посещения, при требовании WCAG 2.2 AA в 4.5:1. Теперь они используют акцент дизайн-системы, измерено 5.40:1 и 4.81:1, а печатная палитра переопределена отдельно, потому что тёмный акцент даёт на белом 3.64:1. Каскад закреплён тестом, который вычисляет победившее объявление для трёх селекторов в четырёх состояниях, а не утверждает наличие правил: предыдущая попытка проходила эту более слабую проверку, пока посещённая кнопка призыва молча теряла цвет при наведении. Этот же цикл заменил более раннюю попытку, критерий приёмки которой требовал, чтобы каждая ссылка отвечала HTTP 200: внешняя проверка ставит сборку в зависимость от чужого аптайма, и прощение сетевого сбоя пропускает гейт без проверки, а непрощение даёт ложные падения на рейт-лимите. Проверка ссылок теперь резолвит внутренние ссылки против собранного дерева и не делает ни одного запроса."
issue_opened_at: '2026-09-11T23:42:58Z'
proposal_approved_at: '2026-09-12T00:19:43Z'
---
```

### 3. `src/content/journal/2026-09-12-repository-links-out-of-the-disclosure.md`

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/47
proposal_slug: issue-47-q3-work-hides-repository-links-inside-co
visibility: public
title:
  en: "Repository links out from behind the disclosure"
  ru: "Ссылки на репозитории — из-под свёрнутого блока"
decided:
  en: "Every project card hid its repository link and metrics inside a collapsed disclosure, so a reader scanning the work page saw fourteen identical rows reading \"Details\" and not one link to code — the main thing a portfolio exists to offer. Links and metrics now sit at card level. The one project without a public repository states that with a chip driven by an explicit field in its content file, rather than inferred from a missing key: an absence has other causes, and a claim about a fact should rest on data somebody wrote. Each disclosure also gained a distinct accessible name, so a screen reader no longer announces \"Details\" fourteen times."
  ru: "Каждая карточка проекта прятала ссылку на репозиторий и метрики внутри свёрнутого блока, поэтому читатель, просматривающий страницу работ, видел четырнадцать одинаковых строк «Подробнее» и ни одной ссылки на код — то есть главное, ради чего портфолио существует. Ссылки и метрики теперь на уровне карточки. Единственный проект без публичного репозитория сообщает об этом чипом, который управляется явным полем в контент-файле, а не выводится из отсутствия ключа: у отсутствия бывают другие причины, а утверждение о факте должно опираться на данные, которые кто-то написал. Каждый свёрнутый блок получил различимое имя, поэтому скринридер больше не произносит «Подробнее» четырнадцать раз."
issue_opened_at: '2026-09-11T21:28:47Z'
proposal_approved_at: '2026-09-12T04:24:45Z'
---
```

### 4. `src/content/journal/2026-09-12-colophon-tables-and-computed-lead-time.md`

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/48
proposal_slug: issue-48-q4-colophon-tables-clip-and-lead-time-is
visibility: public
title:
  en: "Colophon tables that fit, and lead time that is computed"
  ru: "Таблицы колофона, которые помещаются, и вычисленное время цикла"
decided:
  en: "The cycle table was eight columns of nowrap inside a 768-pixel measure, so its rightmost columns sat past the edge at every viewport with nothing indicating that the content continued. Wrapping is now allowed in the two title columns and forbidden everywhere a break would be wrong, and a narrow screen gets a visible scroll affordance and hides two secondary columns. Lead time was showing an em dash for ten of twelve cycles, not because the derivation was missing but because it read only the deploy timestamp, which two entries carry; reading the release timestamp as a fallback computes eight. A missing value now renders visibly and audibly distinct from a measured zero, so an em dash means \"not recorded\" rather than \"not implemented\". Timeline stamps became localised time elements with the elapsed interval between steps shown."
  ru: "Таблица циклов — восемь колонок без переносов внутри измерения в 768 пикселей, поэтому её правые колонки оказывались за краем при любой ширине окна, и ничто не сообщало, что содержимое продолжается. Перенос теперь разрешён в двух колонках заголовков и запрещён везде, где разрыв был бы неверен, а на узком экране появился видимый признак прокрутки и скрыты две второстепенные колонки. Время цикла показывало прочерк у десяти циклов из двенадцати не потому, что вычисление отсутствовало, а потому, что оно читало только отметку деплоя, которая есть у двух записей; чтение отметки релиза как запасной даёт восемь. Отсутствующее значение теперь визуально и на слух отличается от измеренного нуля, поэтому прочерк означает «не записано», а не «не реализовано». Отметки таймлайна стали локализованными элементами времени с показом интервала между шагами."
issue_opened_at: '2026-09-11T21:28:59Z'
proposal_approved_at: '2026-09-12T06:32:13Z'
---
```

### 5. `src/content/journal/2026-09-12-navigation-state-and-accessibility-affordances.md`

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/49
proposal_slug: issue-49-q5-navigation-state-disclosure-defaults
visibility: public
title:
  en: "Navigation state, and affordances that were missing or inert"
  ru: "Состояние навигации и подсказки, которых не было или которые не работали"
decided:
  en: "The language and theme toggles were adjacent inline elements whose spacing depended on a whitespace node in the markup — present in English, absent in Russian, where the two active buttons merged into one slab. That defect had been invisible until the CSP fix made the toggles work at all. A container now owns the gap. The navigation marks the current page, and journal and ADR pages mark their section and show a breadcrumb. One disclosure opens by default on each of two pages — contact, and the section that explains the diagram above it — and the rest stay closed, because restraint is the point. Toggle groups became named groups, a skip link precedes eight header controls, section titles entered the heading outline, and accessible names are given in one language: the build now fails if any aria-label contains both a Latin and a Cyrillic letter."
  ru: "Переключатели языка и темы были соседними строчными элементами, расстояние между которыми зависело от пробельного узла в разметке — в английской версии он был, в русской нет, и две активные кнопки сливались в одну плашку. Этот дефект нельзя было увидеть, пока починка CSP не заставила переключатели работать вообще. Теперь отступом владеет контейнер. Навигация отмечает текущую страницу, а страницы журнала и ADR отмечают свой раздел и показывают хлебные крошки. На двух страницах один блок раскрыт по умолчанию — контакты и раздел, объясняющий диаграмму над ним, — остальные закрыты, потому что сдержанность и есть замысел. Группы переключателей стали именованными группами, ссылка перехода к содержимому идёт перед восемью элементами шапки, заголовки разделов попали в структуру заголовков, а доступные имена даются на одном языке: сборка теперь падает, если в каком-либо aria-label встречаются одновременно латиница и кириллица."
issue_opened_at: '2026-09-11T21:29:09Z'
proposal_approved_at: '2026-09-12T07:14:28Z'
---
```

### 6. `src/content/journal/2026-09-12-backfilling-five-omitted-journal-entries.md`

**Amendment (operator, before approval).** This cycle writes its own entry, as
every cycle does. Without it this cycle repeats the exact omission it exists to
correct, and a later cycle would have to backfill it — which is how the five
above came to be missing. It is additional to the five; the five are a backfill
of other cycles, this one is the ordinary per-cycle record.

`proposal_approved_at` is not guessed: read it from
`$PROPOSAL_DIR/.status.yaml`'s `approval.approved_at` at implementation time,
the same source `2026-09-12-q7-polish-wave-findings.md` used. `issue_opened_at`
is issue #68's `created_at`, given below.

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/68
proposal_slug: issue-68-q8-backfill-the-five-missing-journal-ent
visibility: public
title:
  en: "Backfilling five journal entries that five cycles were told to skip"
  ru: "Восполнение пяти записей журнала, которые пяти циклам велели пропустить"
decided:
  en: "Five consecutive cycles of the polish wave shipped without a journal entry, on my instruction and on a belief that turned out to be false: that the entry schema needs merge, release and deploy timestamps an implementer cannot know at implementation time. It does not. An existing entry carries only issue_opened_at and proposal_approved_at, and the three later stamps are optional; the belief was never checked against the schema it claimed to describe. The cost was five missing records out of a loop whose whole claim is that it records itself, and a public cycle counter that under-reported by five — silently, because the counter is derived from the files present and a file that was never written cannot be missed. The five are restored here from issue and proposal data, with the later stamps honestly absent rather than reconstructed. This cycle also writes its own entry, which is the point: a backfill that repeats the omission it corrects has corrected nothing."
  ru: "Пять подряд идущих циклов волны полировки вышли без записи в журнале — по моему указанию и на основании убеждения, оказавшегося ложным: будто схема записи требует отметок о мерже, релизе и деплое, которых имплементер в момент реализации знать не может. Не требует. Существующая запись несёт только issue_opened_at и proposal_approved_at, а три поздние отметки необязательны; убеждение ни разу не сверили со схемой, которую оно описывало. Ценой стали пять недостающих записей у цикла, вся суть которого — записывать самого себя, и публичный счётчик циклов, занижавший число на пять — молча, потому что счётчик выводится из имеющихся файлов, а ненаписанный файл пропажей не выглядит. Пять записей восстановлены из данных issue и пропозалов, поздние отметки честно отсутствуют, а не реконструированы. Этот цикл пишет и собственную запись — в чём и смысл: восполнение, повторяющее исправляемый им пропуск, ничего не исправило."
issue_opened_at: '2026-09-12T12:27:57Z'
proposal_approved_at: '<read from $PROPOSAL_DIR/.status.yaml approval.approved_at, single-quoted, verbatim>'
---
```

## Open questions

- **The cycle counter is 20, not 18.** (Amended: was 19 before this cycle's
  own entry was added to the deliverable.) The issue's criterion 5 says the
  counter "reads 18, derived from `journal.length`". The clone holds fourteen
  public entries, so the derived value after this change is 20. The two
  halves of that criterion disagree, and only one of them can be satisfied:
  the derivation is enforced by `scripts/check-dist.mjs`, which recomputes
  the expected count from `src/content/journal/*.md`, so pinning 18 is not
  reachable without deleting an entry — which is out of scope and would
  reintroduce the very defect being fixed. Resolved in favour of the
  derivation, exactly as criterion 5's own "no literal count is introduced
  anywhere" clause requires. **A human reviewer should confirm this reading
  before approval**, and confirm that the extra entry is
  `2026-09-12-q7-polish-wave-findings.md` (issue #52), which the issue text
  itself lists as out of scope and which was presumably not yet merged when
  the issue was written.
- The issue shows the full frontmatter block only for file 1; files 2-5 show
  an abbreviated block that omits `service` and `visibility`. Acceptance
  criterion 1 nonetheless requires "seven required keys each", and `service`
  and `visibility` are two of the seven. Resolved by writing
  `service: portfolio` and `visibility: public` on all six, which is the
  only reading under which the schema validates and the pages render at all
  (`publicEntries()` in `src/lib/content.ts` drops anything not `public`).
  Recorded here rather than blocking.
- The issue gives `decided` and `title` as bullet points rather than inside
  the YAML block, so key order within the frontmatter is not stated. Resolved
  by following the order of the existing entries: `service`, `issue`,
  `proposal_slug`, `visibility`, `title`, `decided`, `issue_opened_at`,
  `proposal_approved_at`. Order is cosmetic to the parser; consistency with
  thirteen existing files is the reason.
- Two `decided.en` values contain a straight double quote (`"Details"` in
  file 3, `"not recorded"` / `"not implemented"` in file 4). No existing
  journal entry contains one, so the repository has no precedent for the
  escaping. Resolved by keeping the double-quoted scalar style of every other
  entry and escaping the inner quotes as `\"`, which preserves the characters
  exactly. A single-quoted scalar would also work but would require doubling
  each of the many apostrophes in the same text, which is more error-prone.
- The issue does not state `pr` or `release` for any of the five cycles. Both
  are `.optional()` and render as an em dash. Resolved by omitting them
  rather than guessing; noted as out of scope above.
