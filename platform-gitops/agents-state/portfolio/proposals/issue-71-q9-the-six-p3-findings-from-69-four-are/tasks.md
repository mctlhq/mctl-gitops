# Tasks: issue-71-q9-the-six-p3-findings-from-69-four-are

- [ ] 1. **A2, half 1 -- prefix the problem line.** In `scripts/check-dist.mjs`,
      replace the unprefixed `problems.push(err.message);` at line 769 (inside
      `checkSitemap()`'s `catch`) with
      `problems.push(err.message.startsWith('check-dist:') ? err.message : \`check-dist: ${err.message}\`);`
      — DoD: running the script against a fixture with no `astro.config.mjs`
      emits `check-dist: ENOENT: no such file or directory, open '.../astro.config.mjs'`,
      and against a config with no `site` key it still emits exactly one
      `check-dist: ` prefix, not two.

- [ ] 2. **A2, half 2 -- add the top-level wrapper** (depends on 1). In
      `scripts/check-dist.mjs`, rename `async function main()` (line 830) to
      `async function run()`, add a new `async function main()` that awaits
      `run()` inside a `try` and whose `catch` prints
      `check-dist: unhandled error: ${err.message}` and sets
      `process.exitCode = 1`, mirroring `scripts/check-headers.mjs:270-286`.
      Keep the module-scope call `await main();` unconditional — do not add an
      `isEntryPoint()` guard. Leave the comment at lines 762-767 in place; the
      wrapper is what makes its claim true — DoD: `node scripts/check-dist.mjs`
      against a script patched to throw mid-run exits non-zero and prints the
      `unhandled error` line instead of a stack trace; `npm run build` still
      passes end to end.

- [ ] 3. **A1 -- give the A3b control a positive reach marker** (depends on 2).
      In `test/check-dist.test.ts`, add
      `assert.match(result.stderr, /check-dist: dist\/sitemap-index\.xml does not exist/);`
      to the `A3b control` test at line 76, before the two existing
      `doesNotMatch` assertions — DoD: the control now fails if the spawned
      script dies before `checkSitemap()` runs; the two `doesNotMatch`
      assertions are unchanged.

- [ ] 4. **A1 -- commit the non-vacuity mutant** (depends on 3). In
      `test/check-dist.test.ts`, add `makeFixtureWithUpstreamThrow()`: build the
      normal fixture, read the copied `scripts/check-dist.mjs`, assert the
      literal `problems.push(...checkNavigationState(html, rel));` occurs exactly
      once, replace it with `throw new Error('injected upstream failure');`, and
      write the patched source back. Add a test using it that asserts a non-zero
      exit, `assert.match(result.stderr, /check-dist: unhandled error: injected upstream failure/)`,
      and `assert.doesNotMatch(result.stderr, /sitemap-index\.xml does not exist/)`
      — DoD: the mutant proves the reach marker added in task 3 disappears when
      an upstream stage throws; the anchor-count assertion fails loudly if a
      later cycle renames that call.

- [ ] 5. **A2 proof -- prefix invariant test** (depends on 2). Extend
      `makeFixture()` in `test/check-dist.test.ts` with an options argument
      `{ astroConfig?: 'site' | 'no-site' | 'missing' }` defaulting to `'site'`,
      then add a test using `'missing'` that splits stderr on `\n`, drops empty
      lines, and asserts every remaining line starts with `check-dist: `, naming
      the first offending line in the failure message — DoD: the test fails
      against the pre-task-1 code with the literal `ENOENT: ...` line in its
      message, and passes after.

- [ ] 6. **A2 proof -- no double prefix** (depends on 5). Add a test using
      `astroConfig: 'no-site'` (a config file exporting an object with no `site`
      key) asserting stderr matches
      ``/check-dist: could not find `site` in astro\.config\.mjs/`` and
      `assert.doesNotMatch(result.stderr, /check-dist: check-dist:/)` — DoD:
      `siteOrigin()`'s own already-prefixed throw is proven not to be
      double-prefixed by task 1's ternary.

- [ ] 7. **A3 -- reject unhashed names in `nonEmptyHashedFile()`.** In
      `scripts/vendor-assets.mjs`, extend the import at line 41 to
      `import { contentHash8, hashInName, hashMismatch } from '../src/lib/content-hash.ts';`
      and add `if (hashInName(path.basename(p)) === null) return false;` to
      `nonEmptyHashedFile()` (line 564), before the `readFile`. Do not modify
      `src/lib/content-hash.ts` — DoD: `hashMismatch()` keeps its lenient
      contract for `scripts/check-dist.mjs`, `scripts/check-headers.mjs` and
      `test/cache.test.ts`; the docblock above `nonEmptyHashedFile()` is now
      true as written.

- [ ] 8. **A3 proof -- the named mutant** (depends on 7). In
      `test/vendor-assets.test.ts`, add `unhashSiteCssEntry(tmp)`: set the
      copied `src/data/assets.json`'s `styles[4]` to `/styles/site.css` and write
      a non-empty `public/styles/site.css` in the copy. Add a `mutant:` test
      that runs `runVendorOffline(tmp)` and asserts `status === 1` and
      `assert.match(result.stderr, /vendor: no valid existing tree/)` — DoD: the
      test exits 0 (green run, failed assertion) against the pre-task-7 code and
      exits 1 as asserted after; the existing `control: ... exits 0 under
      VENDOR_FORCE_OFFLINE=1` test still passes, proving no legitimate href was
      caught by the new rejection.

- [ ] 9. **B1 -- word boundary on the chip-literal matcher.** In
      `test/work.test.ts:55`, change the predicate to
      ``new RegExp(`\\b${escapeRegExp(literal)}\\b`).test(source)`` and update
      `chipLiteralProblems()`'s docblock to say the match is word-bounded and
      why — DoD: the seven `CHIP_LITERALS` still match as whole words, including
      the two containing a space.

- [ ] 10. **B1 proof -- two boundary tests** (depends on 9). Add to
      `test/work.test.ts`: a test asserting
      `chipLiteralProblems('<!-- Golang and Google are mentioned -->', 'synthetic')`
      deep-equals `[]`, and a test asserting
      `chipLiteralProblems('<p>Go is a language</p>', 'synthetic')` contains a
      problem matching `/must not hard-code the chip literal "Go"/` — DoD: the
      first fails against the pre-task-9 code with the message naming `"Go"`,
      and both pass after.

- [ ] 11. **C1 -- correct the entry-point test header.** Rewrite
      `test/entry-point.test.ts` lines 1-2 to name all three scripts in `FILES`
      (`scripts/check-contrast.mjs`, `scripts/check-links.mjs`,
      `scripts/check-headers.mjs`) and to state that `scripts/check-headers.mjs`
      is the one whose silent pass would make the `build` job's only assertion
      (`node scripts/check-headers.mjs http://127.0.0.1:8080` in
      `.github/workflows/build.yml`) vacuous. Leave `FILES` and every test
      unchanged — DoD: header and `FILES` agree; no behavioural change.

- [ ] 11b. **C2 -- correct the chip guard's comment.** In `src/i18n/ui.ts`
      line 300, change "warns at build time" to say the guard throws, matching
      what `be62cce` made it do. Absorbed from portfolio#31 item 8 — DoD: the
      comment describes a throw; the guard itself is untouched; no test changes.

- [ ] 11c. **C3, half 1 -- drop the typed version from content.** In
      `src/content/projects/mctl-design.en.md:14` and `mctl-design.ru.md:14`,
      remove `0.5.0` and say the site vendors the design system, in both
      languages. Absorbed from portfolio#31 item 7 — DoD: neither file names a
      version; the EN and RU lines still say the same thing as each other;
      `MCTL_VERSION` in `scripts/vendor-assets.mjs:92` remains the only place
      the number lives.

- [ ] 11d. **C3, half 2 — a matcher that can see a version** (depends on 11c).
      In `scripts/check-no-metrics.mjs`, add a second, independent check: for
      every `.md` under `src/content/projects`, split off the YAML frontmatter
      and apply `/\b\d+\.\d+(?:\.\d+)?\b/` to the body only, failing with a
      `check-no-metrics:`-prefixed line naming the file and line number.
      Frontmatter is excluded because `order: 10` through `order: 14` live there
      in every file. Leave `MATCH_RE` and `SCAN_DIRS` untouched — the two checks
      answer different questions. Do NOT include `src/content/journal` or
      `src/content/adr`.

      **My first version of this task said to add `src/content/projects` to
      `SCAN_DIRS`, and that was wrong in both directions** — `MATCH_RE` is
      `/\b[0-9]{2,}\b/g` and returns `null` on `0.5.0`, so the gate would not
      have caught the violation it was added for; and twelve of the fourteen
      files already carry `order:` values plus `60 seconds` and `15-minute`, so
      it would have flooded on legitimate copy. Measured, not assumed: the
      semver matcher above hits exactly two lines in the tree today,
      `mctl-design.en.md:14` and `mctl-design.ru.md:14`, and nothing else.

      DoD: `node scripts/check-no-metrics.mjs` exits zero on the fixed tree, and
      exits non-zero naming the file and line when `0.5.0` is put back — show
      both outputs, and show the message, not only the exit code.

- [ ] 12. **D1 -- replace the raw NUL separators.** In `test/fonts.test.ts`, add
      a local `faceKey(family, weight)` helper returning `` `${family}|${weight}` ``
      with a docblock naming why (`|` cannot occur in a CSS font-family name;
      the raw byte made the file read as binary to grep), and route all six
      current NUL sites through it — the three `new Set(faceRules.map(...))`
      constructions at lines 297, 321, 339 and the three `facePairKeys.has(...)`
      lookups at lines 305, 329, 347 — DoD: `grep -c $'\x00' test/fonts.test.ts`
      reports no matches, `grep -n "facePairKeys = new Set" test/fonts.test.ts`
      prints line numbers instead of `Binary file ... matches`, and every font
      test still passes, including the negative assertion at line 329.

- [ ] 13. **D1 guard -- `test/source-hygiene.test.ts`** (depends on 12). New
      file: walk `test/`, `scripts/` and `src/` recursively, filter to the
      extensions `.ts`, `.mjs`, `.astro`, `.css`, `.md`, `.json` (so
      `scripts/fonts/*.ttf` and any vendored binary are excluded by
      construction), read each as a `Buffer`, and assert `buf.indexOf(0) === -1`
      with a failure message naming the relative path and the offset. Add
      `test/source-hygiene.test.ts` to the end of `package.json`'s `test` script
      file list — DoD: the guard fails against the pre-task-12 tree naming
      `test/fonts.test.ts` at offset 12997, and passes after; the file list in
      `package.json` runs it.

- [ ] 14. **Journal entry** (depends on 1-13). Add
      `src/content/journal/2026-09-12-q9-six-review-findings.md` with
      `service: portfolio`,
      `issue: https://github.com/mctlhq/portfolio/issues/71`,
      `proposal_slug: issue-71-q9-the-six-p3-findings-from-69-four-are`,
      `visibility: public`, `interventions: []`, the `issue_opened_at` and
      `proposal_approved_at` timestamps for this cycle, and the `title.en`,
      `title.ru`, `decided.en` and `decided.ru` copy exactly as given in
      `requirements.md` — DoD: `npm test` passes `test/journal.test.ts`, the
      copy is character-for-character what the proposal carries, and no typed
      numeral appears in the rendered copy.

- [ ] 15. **Record the evidence in the commit body** (depends on 1-14). The
      commit body states, for each of A1, A2, A3, B1 **and C3**, the assertion
      message the new test emits against the pre-fix code and the fact that it
      passes after, plus the `npm test` total before (295) and after. C3's pair
      is `node scripts/check-no-metrics.mjs`'s output with `0.5.0` restored and
      with it removed; it has the identical before/after shape as the other four
      and is the fix this absorption is centred on, so it is not optional. This
      replaces the issue's "state both outputs in the PR" criterion, which
      `AGENTS.md` makes unsatisfiable — DoD: the **five** before/after message
      pairs and the new total are in the commit body.

## Tests

- [ ] T1. `A3b control` in `test/check-dist.test.ts` asserts stderr contains
      `check-dist: dist/sitemap-index.xml does not exist` in addition to its two
      `doesNotMatch` assertions. (task 3)
- [ ] T2. New `test/check-dist.test.ts` mutant: an injected upstream throw makes
      the reach marker disappear, exits non-zero, and prints
      `check-dist: unhandled error: injected upstream failure`; the anchor is
      asserted to occur exactly once before substitution. (task 4)
- [ ] T3. New `test/check-dist.test.ts` test: with no `astro.config.mjs`, every
      non-empty stderr line starts with `check-dist: `. Fails pre-fix naming the
      `ENOENT: ...` line. (task 5)
- [ ] T4. New `test/check-dist.test.ts` control: with a config lacking `site`,
      stderr carries the prefixed `could not find \`site\`` line and no
      `check-dist: check-dist:`. (task 6)
- [ ] T5. New `test/vendor-assets.test.ts` mutant: `styles[4]` set to
      `/styles/site.css` with a non-empty file of that name on disk is rejected
      by `verifyExistingTree()` — exit 1, stderr matching
      `/vendor: no valid existing tree/`. (task 8)
- [ ] T6. Existing `test/vendor-assets.test.ts` control (unmutated copy exits 0
      offline) still passes, proving A3's rejection catches nothing legitimate.
      (task 8)
- [ ] T7. New `test/work.test.ts` test: `'<!-- Golang and Google are mentioned -->'`
      reports no problem. Fails pre-fix naming `"Go"`. (task 10)
- [ ] T8. New `test/work.test.ts` test: `'<p>Go is a language</p>'` still
      reports `"Go"`. (task 10)
- [ ] T9. Every existing D2a and D2b test in `test/work.test.ts` is re-run
      unchanged and passes — the two comment-only cases, the regex-terminator
      case, the frontmatter list item (`  - Go\n`), the element-text case and the
      template-interpolation case. (task 10)
- [ ] T10. New `test/source-hygiene.test.ts`: no `.ts`/`.mjs`/`.astro`/`.css`/
      `.md`/`.json` file under `test/`, `scripts/` or `src/` contains a 0x00
      byte. (task 13)
- [ ] T11. Every font test in `test/fonts.test.ts` passes with the `|`
      separator, including the negative `!facePairKeys.has(...)` assertion.
      (task 12)
- [ ] T11b. New test, over a temporary fixture tree rather than over the
      constant: a semver-shaped literal placed in the body of a file under
      `src/content/projects` is reported, and the same literal placed in a file
      under `src/content/journal` or `src/content/adr` is NOT, and an `order:`
      value in a project file's frontmatter is NOT. This pins the behaviour the
      boundary exists for — which directories are read and which part of a file
      is read — instead of pinning the names in a constant, so a refactor that
      keeps the behaviour passes and a widening that changes it fails.
      (task 11d)

- [ ] T11c. C3 mutation over a temporary copy of the project tree: writing
      `version 0.5.0` back into `mctl-design.en.md`'s body makes the check fail
      naming that file and line; removing it makes it pass. Assert on the
      message, not just the exit code. Include a control showing the existing
      `60 seconds` and `15-minute` prose and every `order:` value stay
      unreported, since the first version of this requirement would have failed
      on all of them. (task 11d)

- [ ] T12. `npm run vendor && npm test` is green end to end; the new total is
      stated in the commit body. Expected: **nine** new tests over the 295 at
      `efdb072` — the original seven plus T11b and T11c from this absorption.
      (task 15)

## Rollback

Every change in this cycle is confined to three scripts
(`check-dist.mjs`, `vendor-assets.mjs`, `check-no-metrics.mjs`),
`src/i18n/ui.ts`, two project content files, four existing test files, one new
test file, `package.json`'s `test` script and one new journal entry. No content
schema, no data file, no CI workflow and no deployment artifact changes, so a
rollback is a `git revert` of the merge commit followed by
`npm run vendor && npm test` to confirm 295 pass / 0 fail again.

**Rendered output does change**, in one place: `/work/`'s `mctl-design` card
drops the words naming version `0.5.0` in both languages. That is the C3 content
fix, it is deliberate, and it is the only visible difference on the site.

Per-finding, if only one of the eight turns out to be wrong:

- A2's wrapper: revert the `main`/`run` split and restore the single
  `async function main()` plus `await main();`. Tasks 3, 4, 5 and 6 depend on it,
  so revert those tests in the same commit.
- A3: revert the `hashInName(...) === null` line and the import change in
  `scripts/vendor-assets.mjs`, plus T5. Nothing else reads that predicate.
- B1: revert the one-line regex change and T7/T8; the D2a/D2b tests are
  unaffected either way.
- C1, D1: pure text and separator changes with no behavioural coupling outside
  `test/fonts.test.ts` and `test/source-hygiene.test.ts`; reverting D1 requires
  reverting T10 with it, or the guard will fail on the restored NUL bytes.
- C2: a one-line comment change in `src/i18n/ui.ts` with no code or test
  coupling. Revert the line; nothing else moves.
- C3: two independent halves, revertible separately. Half 1 is the two content
  lines in `mctl-design.en.md` / `.ru.md` — restoring them changes `/work/` back
  and, on its own, makes the half-2 check fail, so revert half 2 with it or
  accept a red gate. Half 2 is the new semver check in
  `scripts/check-no-metrics.mjs` plus T11b and T11c — reverting it leaves the
  content fix in place and simply stops enforcing it.
