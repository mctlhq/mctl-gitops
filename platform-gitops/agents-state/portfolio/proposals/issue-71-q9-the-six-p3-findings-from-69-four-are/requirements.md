# Q9: the six P3 findings from #69 -- four are guards that can pass without checking

## Context

The review of #69 approved that merge with "No P1/P2 findings (6 P3). Good to
merge." All six survived the merge, and none of them can be picked up by the
shepherd: its follow-up prompt is scoped to P1/P2 by construction, so a P3 never
reaches the implementer no matter what the pull request thread says. They need
their own cycle.

Four of the six are the defect class this wave has been closing for seven
cycles: a check that reports success because its subject was absent. Two of
those four are in code the previous cycle itself wrote. `test/check-dist.test.ts`
has a control test whose body is two `doesNotMatch` assertions and no positive
proof that the spawned script ever reached the stage under test, against a
fixture tree that is deliberately incomplete -- verified in the clone: the
script dies today only if something throws, and `scripts/check-dist.mjs` has no
top-level `try/catch` to stop that (`await main()` at line 925, unguarded).
`scripts/check-dist.mjs:769` pushes `err.message` unprefixed, and the
`readFile(ASTRO_CONFIG_PATH)` above `siteOrigin()`'s own throw produces a bare
`ENOENT: no such file or directory, open ".../astro.config.mjs"` -- reproduced
in the clone -- the only line in the report without the `check-dist: ` prefix
the rest of the script and any log grep rely on.
`scripts/vendor-assets.mjs:564`'s `nonEmptyHashedFile()` is weaker than its own
docblock, because `hashMismatch()` returns `null` both for "name matches its
bytes" and for "name carries no hash at all"
(`src/lib/content-hash.ts:38-44`, verified directly: `hashInName('site.css')`
is `null`). The fifth finding is a guard that can fail on the wrong thing --
`test/work.test.ts:55` matches the chip literal `Go` as a bare substring over
the whole raw file text since D2 removed `stripComments()`. The sixth is a
tooling blind spot: `test/fonts.test.ts` carries six raw 0x00 bytes (offsets
12997, 13346, 14220, 14636, 15193, 15606 -- lines 297, 305, 321, 329, 339, 347),
so `grep` reports `Binary file test/fonts.test.ts matches` and any grep-based
sweep over `test/*.ts` silently skips the file while GitHub still renders it as
text. A seventh item, `test/entry-point.test.ts`'s header, documents a narrower
scope than its own `FILES` list enforces.

Closing them matters because each one is a place where the repository's own
evidence is weaker than it reads. A vacuous control test, an unprefixed problem
line, a manifest check that accepts an unhashed name, and a guard invisible to
grep are all the same failure: the artifact says "checked" where nothing was
checked.

## User stories

- AS a reviewer of this repository I WANT every guard test to prove it reached
  the stage it claims to test SO THAT a green control test is evidence rather
  than a coincidence of an early crash.
- AS an operator reading CI output I WANT every problem line `scripts/check-dist.mjs`
  emits to carry the `check-dist: ` prefix SO THAT a log grep on that prefix
  cannot miss a failure.
- AS an operator running `npm run vendor` with no network I WANT the offline
  verification to reject a manifest entry whose filename carries no content hash
  SO THAT an `immutable`-cached URL is never served over content that is not
  pinned to it.
- AS a future implementer touching `src/pages/work.astro` I WANT the chip-literal
  guard to match on word boundaries SO THAT a comment containing `Golang` does
  not fail naming a literal that is not hard-coded.
- AS an agent or human sweeping the test suite with grep I WANT no source file to
  contain a raw NUL byte SO THAT no file is silently skipped by a text search.
- AS a later cycle deciding what `test/entry-point.test.ts` covers I WANT its
  header to name the same three scripts its `FILES` list enforces SO THAT
  `scripts/check-headers.mjs` cannot be dropped from the list as "out of scope".

## Acceptance criteria (EARS)

### A1 -- the check-dist control test must prove it reached the stage under test

- WHEN the A3b control test in `test/check-dist.test.ts` runs against its
  self-consistent fixture THE SYSTEM SHALL assert that the spawned script's
  stderr **contains** `check-dist: dist/sitemap-index.xml does not exist` -- a
  problem produced by a stage that runs strictly after `checkHashedSubresources()`,
  confirmed in the clone as the last line the current script emits for that
  fixture -- in addition to the two existing `doesNotMatch` assertions.
- WHEN a new mutation test in `test/check-dist.test.ts` copies
  `scripts/check-dist.mjs` into the fixture and replaces the single occurrence of
  the literal line `problems.push(...checkNavigationState(html, rel));` with a
  `throw new Error('injected upstream failure');` THE SYSTEM SHALL assert that the
  patched copy's stderr does **not** contain
  `check-dist: dist/sitemap-index.xml does not exist`, proving the control's new
  reach assertion is load-bearing.
- WHILE performing that replacement THE SYSTEM SHALL assert the anchor line
  occurred exactly once in the copied source before substitution, so the
  injection itself cannot become vacuous.
- WHEN the mutation test runs after the A2 wrapper is in place THE SYSTEM SHALL
  additionally assert the patched copy exits non-zero and its stderr contains
  `check-dist: unhandled error: injected upstream failure`.

### A2 -- prefix every problem line, and add the missing top-level wrapper

- IF `siteOrigin()` or the `readFile(ASTRO_CONFIG_PATH)` inside it throws THEN
  `scripts/check-dist.mjs` SHALL push the message as
  `err.message.startsWith('check-dist:') ? err.message : \`check-dist: ${err.message}\``,
  so a read failure is prefixed and the script's own already-prefixed throw is not
  prefixed twice.
- WHEN `scripts/check-dist.mjs` is run THE SYSTEM SHALL route its whole run
  through a top-level `try/catch` of the same shape
  `scripts/check-headers.mjs:270-286` already carries: the existing `main()`
  renamed to `run()`, a new `async function main()` that awaits `run()` inside a
  `try`, and a `catch` that prints
  `check-dist: unhandled error: ${err.message}` and sets `process.exitCode = 1`.
- WHEN a new test in `test/check-dist.test.ts` runs the script against a fixture
  with **no** `astro.config.mjs` THE SYSTEM SHALL assert that every non-empty
  stderr line starts with `check-dist: `, and the failure message SHALL name the
  offending line.
- WHEN a new control test runs the script against a fixture whose
  `astro.config.mjs` exists but declares no `site` key THE SYSTEM SHALL assert
  stderr contains `check-dist: could not find \`site\` in astro.config.mjs` and
  does not contain `check-dist: check-dist:`.
- WHILE the top-level wrapper exists THE SYSTEM SHALL keep the unconditional
  `await main();` call at module scope -- no `isEntryPoint()` guard is added to
  `scripts/check-dist.mjs` in this cycle.

### A3 -- nonEmptyHashedFile() must reject an unhashed name

- IF the basename of a path passed to `nonEmptyHashedFile()` in
  `scripts/vendor-assets.mjs` yields `hashInName(...) === null` THEN the function
  SHALL return `false`, rejecting the file before the `hashMismatch()` comparison.
- WHILE implementing that change THE SYSTEM SHALL leave `hashMismatch()` in
  `src/lib/content-hash.ts` unchanged -- its lenient contract is correct for the
  two checkers that legitimately meet unhashed names -- and SHALL extend the
  existing import at `scripts/vendor-assets.mjs:41` to bring in `hashInName`.
- WHEN a new mutant test in `test/vendor-assets.test.ts` sets the copied tree's
  `src/data/assets.json` `styles[4]` to `/styles/site.css`, writes a non-empty
  `public/styles/site.css` in the copy, and runs the script with
  `VENDOR_FORCE_OFFLINE=1` THE SYSTEM SHALL assert the run exits 1 and stderr
  matches `/vendor: no valid existing tree/`.
- WHILE that mutant test exists THE SYSTEM SHALL keep the existing
  `control: vendor-assets.mjs against an unmutated copy exits 0 under
  VENDOR_FORCE_OFFLINE=1` test passing, proving every legitimate manifest entry,
  preload href and `fonts.css` `url()` still carries a hash.

### B1 -- word boundary on the chip-literal matcher

- WHEN `chipLiteralProblems()` in `test/work.test.ts` tests a chip literal against
  a source THE SYSTEM SHALL use ``new RegExp(`\\b${escapeRegExp(literal)}\\b`)``.
- WHEN a new test passes the source `'<!-- Golang and Google are mentioned -->'`
  THE SYSTEM SHALL assert `chipLiteralProblems()` returns `[]`.
- WHEN a new test passes the source `'<p>Go is a language</p>'` THE SYSTEM SHALL
  assert the returned problems include `must not hard-code the chip literal "Go"`.
- WHILE the boundary is in place THE SYSTEM SHALL keep every existing D2a and D2b
  test in `test/work.test.ts` passing unchanged -- the two comment-only cases, the
  regex-terminator case, the frontmatter list item (`  - Go\n`), the element-text
  case and the template-interpolation case.

### C1 -- entry-point test header matches its FILES list

- WHEN `test/entry-point.test.ts`'s header comment is read THE SYSTEM SHALL name
  all three scripts its `FILES` constant at line 19 enforces --
  `scripts/check-contrast.mjs`, `scripts/check-links.mjs` and
  `scripts/check-headers.mjs`.
- WHILE naming them THE SYSTEM SHALL state that `scripts/check-headers.mjs` is the
  one whose silent pass would make the `build` job's only assertion vacuous --
  `.github/workflows/build.yml`'s final step,
  `node scripts/check-headers.mjs http://127.0.0.1:8080`, is that job's sole check.

### C2 -- the chip guard's comment describes behaviour it no longer has

Absorbed from portfolio#31 item 8, which the operator verified still open
against `main` at `4098039` while closing that issue. Same class as C1:
documentation that contradicts the code it documents.

- WHEN `src/i18n/ui.ts` line 300 is read THE SYSTEM SHALL describe the chip
  guard as throwing, not warning. Commit `be62cce` changed it from a warning to
  a `throw`, and that comment is the one place a reader looks to find out what
  the guard does on a missing translation.
- WHILE correcting it THE SYSTEM SHALL change nothing about the guard itself.

### C3 -- a version number typed into content, and the guard that cannot see it

Absorbed from portfolio#31 item 7. AGENTS.md forbids numbers typed into
content; `src/content/projects/mctl-design.en.md:14` and `mctl-design.ru.md:14`
both name version `0.5.0`.

**The interesting half is why it survived.** `scripts/check-no-metrics.mjs:29`
declares `SCAN_DIRS = ['src/pages', 'src/components', 'src/layouts']`. The
directory the violation lives in is not in that list, so the gate did not miss
it -- the gate could not see it. That is this cycle's own subject, in the gate
that exists to enforce the rule.

- WHEN `src/content/projects/mctl-design.en.md` and `mctl-design.ru.md` are read
  THE SYSTEM SHALL state that the site vendors the design system without naming
  a version, in both languages. The source of truth is `MCTL_VERSION` at
  `scripts/vendor-assets.mjs:92`; `@mctlhq/css` is not an npm dependency, so no
  bot will ever bump the content copy and the two drift on the next re-pin.
**Corrected after review (operator, 2026-09-12).** My first version of this
requirement said to add `src/content/projects` to `SCAN_DIRS`. That was wrong in
both directions, and I had asserted a mutation proof for it without running one.
Measured against the tree:

- `MATCH_RE` is `/\b[0-9]{2,}\b/g` — two or more digits. Every component of
  `0.5.0` is a single digit, so the matcher returns `null` on
  `- this site vendors version 0.5.0`. The widened gate would not have caught the
  one violation it was added for, and the mutation test would have exited zero
  and been recorded as proof.
- Twelve of the fourteen project files already carry two-or-more-digit literals:
  `order: 10` through `order: 14` in every file's frontmatter, plus
  `60 seconds` and `15-minute` in prose. The widened gate would have flooded on
  legitimate copy, so the clean-tree exit was unreachable too.

A directory is the wrong axis. The rule being enforced is "no version number
typed into content", and that needs a matcher for what a version looks like:

- WHEN `scripts/check-no-metrics.mjs` runs THE SYSTEM SHALL apply a
  semver-shaped matcher — `/\b\d+\.\d+(?:\.\d+)?\b/` — to the **body** of
  every file under `src/content/projects`, and fail naming the file and line when
  one matches.
- **AND** THE SYSTEM SHALL exclude each file's YAML frontmatter from that scan.
  `order:` is structural, not prose, and is the reason a whole-file scan cannot
  work.
- **AND** THE SYSTEM SHALL leave `MATCH_RE` and the existing `SCAN_DIRS`
  untouched. The two checks answer different questions and must not be merged:
  the existing one catches metrics typed into templates, this one catches
  versions typed into project copy.
- **AND** THE SYSTEM SHALL NOT scan `src/content/journal` or `src/content/adr`
  under either matcher. Those record timestamps, counts and release numbers as
  their subject matter; extending to them is a separate decision, not this
  cycle's.
- WHEN the new matcher runs against the tree after the content fix THE SYSTEM
  SHALL exit zero. Verified before writing this: the matcher hits exactly two
  lines today, `mctl-design.en.md:14` and `mctl-design.ru.md:14`, and nothing
  else across the other twelve projects.

### D1 -- no raw NUL bytes in source

- WHEN `test/fonts.test.ts` builds or queries a composite family/weight key THE
  SYSTEM SHALL use the printable separator `|` in place of the raw 0x00 byte, at
  all six occurrences (lines 297, 305, 321, 329, 339, 347).
- WHILE replacing them THE SYSTEM SHALL introduce a single local helper
  `faceKey(family, weight)` in `test/fonts.test.ts` that all six call sites use,
  so the separator is written once.
- WHEN the new guard test runs THE SYSTEM SHALL assert that no file under
  `test/`, `scripts/` or `src/` contains a 0x00 byte, and the failure message
  SHALL name the file and the byte offset of the first occurrence.
- WHEN `grep -n "facePairKeys" test/fonts.test.ts` is run after the change THE
  SYSTEM SHALL print line numbers rather than `Binary file ... matches`.

### Suite-level

- WHEN the cycle is complete THE SYSTEM SHALL keep `npm run vendor && npm test`
  green, with the new test file wired into `package.json`'s `test` script.
- WHILE each of A1, A2, A3 and B1 is fixed THE SYSTEM SHALL ship the proof as a
  committed test that would fail against the pre-fix code and passes after, with
  the assertion on the message rather than on a bare boolean. The before-fix and
  after-fix assertion output SHALL be recorded in the implementer's commit body,
  not in the pull request description -- `AGENTS.md` states the implementer opens
  its pull request from a fixed template and cannot edit the body, so a criterion
  requiring evidence there can never be met.
- WHEN the cycle is complete THE SYSTEM SHALL add one journal entry at
  `src/content/journal/2026-09-12-q9-six-review-findings.md` with
  `service: portfolio`, `issue: https://github.com/mctlhq/portfolio/issues/71`,
  `proposal_slug: issue-71-q9-the-six-p3-findings-from-69-four-are`,
  `visibility: public`, `interventions: []`, and exactly this copy:

  `title.en`:
  ```
  Q9: eight review findings, four of them guards that could pass unchecked
  ```
  `title.ru`:
  ```
  Q9: восемь замечаний ревью, четыре из них — проверки, способные пройти вхолостую
  ```
  `decided.en`:
  ```
  Eight findings are closed in their own cycle: six the previous review raised but could not route to the implementer, plus two absorbed from an older follow-up issue whose other seven items earlier cycles had already closed. Four are the defect class this wave has been closing: a check that reports success because its subject was absent. The check-dist control test now asserts a positive marker that the spawned script actually reached the stage under test, and a committed mutation test that injects an upstream throw proves the control goes red instead of passing vacuously; scripts/check-dist.mjs gains the top-level try/catch wrapper its own comment already claimed, so an accumulated report prints instead of being lost to a stack trace, and every problem line now carries the check-dist prefix, including the ones that come from a failed read rather than from the script's own throw; scripts/vendor-assets.mjs now rejects a manifest entry whose filename carries no content hash at all, instead of accepting it because there was nothing to compare against; and the chip-literal guard in test/work.test.ts matches on a word boundary, so a future comment containing a longer word can no longer fail while naming a literal that is not hard-coded. The remaining two are corrections by inspection: the entry-point test's header now names all three scripts its own list enforces, and the composite keys in the font test use a printable separator instead of a raw NUL byte that made the whole file invisible to grep. The two absorbed findings are of the same kind. A comment describing the chip guard still said it warns on a missing translation, which it stopped doing when the guard was changed to throw, and that comment is the one place a reader looks to find out. And a version number was typed into two project descriptions, which the project's own rules forbid: the gate meant to prevent that scans templates only, and its matcher requires two consecutive digits, so a three-part version of single digits was both outside the directories it looks at and invisible to the pattern it looks for. A version-shaped matcher over project copy now covers it, deliberately not extended to the journal or the decision records, where numbers are the subject matter rather than a leak.
  ```
  `decided.ru`:
  ```
  Восемь замечаний закрыты отдельным циклом: шесть подняло предыдущее ревью, но они не доходили до исполнителя, и ещё два перенесены из более старого follow-up issue, остальные семь пунктов которого закрыли предыдущие циклы. Четыре из них относятся к тому же классу дефектов, который эта волна закрывает: проверка сообщает об успехе, потому что её предмет отсутствовал. Контрольный тест check-dist теперь проверяет положительный маркер того, что запущенный скрипт действительно дошёл до проверяемого этапа, а зафиксированный мутационный тест, подставляющий исключение выше по потоку, доказывает, что контроль краснеет, а не проходит вхолостую; scripts/check-dist.mjs получает обёртку try/catch верхнего уровня, о которой его собственный комментарий уже говорил, так что накопленный отчёт печатается, а не теряется в трассировке стека, и каждая строка проблемы теперь несёт префикс check-dist, включая те, что приходят из неудавшегося чтения, а не из собственного исключения скрипта; scripts/vendor-assets.mjs теперь отвергает запись манифеста, в имени файла которой вовсе нет хеша содержимого, вместо того чтобы принимать её из-за отсутствия предмета сравнения; а проверка литералов чипов в test/work.test.ts сопоставляет по границе слова, так что будущий комментарий с более длинным словом больше не сможет упасть, назвав литерал, который нигде не захардкожен. Остальные два — исправления по результату чтения: заголовок теста точки входа теперь называет все три скрипта, которые его собственный список проверяет, а составные ключи в тесте шрифтов используют печатаемый разделитель вместо сырого нулевого байта, из-за которого весь файл был невидим для grep. Два перенесённых замечания — того же рода. Комментарий к проверке чипов по-прежнему утверждал, что она предупреждает о пропущенном переводе, хотя проверку давно изменили на выброс исключения, — а именно в этот комментарий читатель и смотрит, чтобы узнать поведение. И в двух описаниях проектов был вписан номер версии, что правила проекта запрещают: гейт, который должен это предотвращать, просматривает только шаблоны, а его шаблон поиска требует двух цифр подряд, поэтому трёхчастная версия из однозначных чисел оказалась и вне просматриваемых каталогов, и невидимой для самого выражения. Теперь её ловит выражение, распознающее форму версии в текстах проектов, — сознательно не распространённое на журнал и записи о решениях, где числа составляют содержание, а не утечку.
  ```

## Out of scope

- Changing `hashMismatch()` or any other export in `src/lib/content-hash.ts`. The
  fix for A3 is at the caller.
- Adding an `isEntryPoint()` guard to `scripts/check-dist.mjs`. Its absence is
  context for A1, not work; `test/check-dist.test.ts` and the new tests spawn the
  script as a CLI, which works either way, and adding one would change what
  `test/entry-point.test.ts`'s `FILES` list is expected to contain while C1 is
  fixing that same header to name exactly three scripts.
- Deleting or softening the comment at `scripts/check-dist.mjs:762-767` that
  claims parity with `scripts/check-headers.mjs`. The claim is made true by adding
  the wrapper, not by removing the sentence.
- `resolveFamilyName()` in `test/fonts.test.ts`. Recorded in Open questions as a
  known shape that would break the parser; no declaration of that shape exists in
  `src/styles/site.css` or the three vendored `public/assets/mctl/*.css`, and
  `parseTopLevelRules()` skips `@media` and finds no `@layer`/`@supports` in them.
  No change.
- Any change to `src/pages/`, `src/components/`, `src/layouts/`, `astro.config.mjs`,
  `nginx.conf`, `Dockerfile` or the CSP. This cycle touches three scripts, `src/i18n/ui.ts`, two project content files, four
  test files, `package.json`'s `test` script, and one new journal entry.
- The P2 finding from round 1 of the #69 review, which was already fixed in
  `1cf7bbc`.

## Open questions

- The issue's acceptance section asks for before-fix and after-fix outputs to be
  "stated in the PR". `AGENTS.md` forbids that shape of criterion: the implementer
  cannot edit its pull request body. Resolved here by requiring the evidence as
  committed mutation tests plus a statement in the commit body. A reviewer who
  wants the outputs in the thread can paste them as a review comment.
- The issue also asks for the new suite total to be stated. The same constraint
  applies. The total is required in the commit body, not the pull request body,
  and not in the journal copy -- `AGENTS.md` keeps typed numbers out of rendered
  content. Arithmetic from the tasks below predicts seven new tests over the
  295 at `efdb072`, so 302 is expected; the criterion is `npm test` green with the
  actual total stated, not the specific figure.
- The NUL-byte guard needs a home. This proposal creates
  `test/source-hygiene.test.ts` and wires it into `package.json`'s `test` script,
  since no existing test file owns repository-wide source hygiene. A reviewer who
  prefers it folded into an existing file can say so; the assertion is three lines
  either way.
- The A1 mutation test anchors on the literal line
  `problems.push(...checkNavigationState(html, rel));` in
  `scripts/check-dist.mjs`. If a later cycle renames that call, the injection
  assertion fails loudly rather than silently, which is the intended failure mode,
  but it is a coupling worth knowing about.
