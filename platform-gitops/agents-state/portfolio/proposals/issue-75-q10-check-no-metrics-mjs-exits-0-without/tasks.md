# Tasks: issue-75-q10-check-no-metrics-mjs-exits-0-without

- [ ] 1. Reproduce the defect before changing anything: symlink the checkout
      (`ln -s "$PWD" /tmp/portfolio-link`), run
      `node --test test/metrics-build.test.ts` from `/tmp/portfolio-link`, and
      capture the output. — DoD: the pre-fix output is captured for the commit
      body. On Linux, where `os.tmpdir()` is a real `/tmp`, `T11b`/`T11c` may
      already pass; in that case additionally capture the direct proof —
      spawn a copy of `scripts/check-no-metrics.mjs` by absolute path through
      a symlinked directory over a tree containing a `9.9.9` body in
      `src/content/projects` and record `exit=0` with empty stdout/stderr.
      That direct proof, not the platform-dependent test result, is the
      baseline the mutation proof in task 8 must reverse.

- [ ] 2. Give `scripts/check-no-metrics.mjs` the hybrid guard: add
      `import { realpathSync } from 'node:fs';` next to the existing
      `node:fs/promises` import, declare `function isEntryPoint()` with the
      same body as `scripts/check-headers.mjs:295` (`import.meta.main` when
      `typeof import.meta.main !== 'undefined'`; `false` when
      `!process.argv[1]`; a `realpathSync(process.argv[1]) ===
      realpathSync(fileURLToPath(import.meta.url))` comparison inside a
      `try`; `false` on `catch`), and replace the bare compare at line 293
      with `if (isEntryPoint()) {`. — DoD: no
      `process.argv[1] === fileURLToPath(import.meta.url)` remains in the
      file; the entry block reads `if (isEntryPoint()) { await main(); }`;
      the doc comment above `isEntryPoint()` names its sibling scripts
      correctly. `node scripts/check-no-metrics.mjs` from the repo root still
      prints its `check-no-metrics: OK -- ...` line and exits 0.

- [ ] 3. Give `scripts/snapshot-metrics.mjs` the identical hybrid guard at
      line 480 (depends on 2, for the exact text to copy). Check its real
      import block first — it currently imports from `node:fs/promises` only
      and needs `realpathSync` added from `node:fs`. — DoD: same conditions as
      task 2, applied to `scripts/snapshot-metrics.mjs`. Rationale, which the
      implementer should not skip: this file carries the same defect, it is
      inside `scripts/*.mjs`, and the derived test from task 5 selects it, so
      the alternative to fixing it is an exclusion list — the artifact this
      cycle exists to delete.

- [ ] 4. Replace the hand-typed `FILES` array at
      `test/entry-point.test.ts:24` with a derivation: a
      `deriveEntryPointScripts(scriptsDir)` function that takes the directory
      as a parameter, reads it with `readdirSync(..., { withFileTypes: true
      })`, keeps `.mjs` files, reads each source with `readFileSync`, keeps
      those whose source matches a top-level
      `if (...) { await main(); }` block, and returns sorted repo-relative
      POSIX paths of the form `scripts/<name>.mjs`. A validated candidate
      matcher is `/^if \(.*\) \{\r?\n\s*await main\(\);\r?\n\}/m`. — DoD: the
      function takes the directory as an argument (not module scope, so task 6
      can point it at an empty directory); it returns exactly
      `scripts/check-contrast.mjs`, `scripts/check-headers.mjs`,
      `scripts/check-links.mjs`, `scripts/check-no-metrics.mjs`,
      `scripts/snapshot-metrics.mjs` against the post-task-3 tree, and
      excludes `check-dist`, `csp-hash`, `render-og` and `vendor-assets`.

- [ ] 5. Iterate the per-file hybrid-form loop over the derived set (depends
      on 4). The loop body keeps `readFileSync`, `isolateIsEntryPoint()` and
      `assert.deepEqual(entryPointProblems(block, file), [])` unchanged. — DoD:
      every derived file gets its own `test()`; all five pass against the
      post-task-3 tree; the three synthetic-source discrimination tests at the
      current lines 78, 89 and 100 are unmodified and still pass.

- [ ] 6. Add the derivation guards (depends on 4): a `MIN_DERIVED = 4` floor
      asserted with a message naming the count found, the count required and
      the shortfall; a per-name membership assertion over
      `['scripts/check-contrast.mjs', 'scripts/check-links.mjs',
      'scripts/check-headers.mjs', 'scripts/check-no-metrics.mjs',
      'scripts/snapshot-metrics.mjs']` that names the missing script and prints
      the derived set on failure — **all five**, including the one task 3 gives
      the guard to; with only four pinned, a `snapshot-metrics.mjs` that lost
      its guard would drop the set to four and pass both the floor and the
      membership check; and a test
      that calls `deriveEntryPointScripts` on a freshly created empty
      temporary directory and asserts it returns `[]`. — DoD: three new
      assertions present; the floor stays at four (not five), so a future
      sixth script needs no edit; `scripts/snapshot-metrics.mjs` is covered by
      the derivation and is deliberately **not** added to the required-name
      list.

- [ ] 7. Rewrite the header comment of `test/entry-point.test.ts` (lines
      1-15) to describe the derived rule (depends on 4, 5, 6): what is
      enumerated (`scripts/*.mjs`), which shape selects a file
      (`if (...) { await main(); }`), what the required form is
      (`import.meta.main` where defined, `realpathSync()` comparison below
      it), why the bare compare is the hazard (exit 0 without running on a
      symlinked checkout), why the set is derived rather than typed (the list
      was wrong on #69 and wrong again here), and what the floor-of-four plus
      named-membership assertions protect against (a scan matching nothing
      passing vacuously). Retain the existing note that
      `scripts/check-headers.mjs`'s silent pass would make
      `.github/workflows/build.yml`'s final step vacuous, and add that
      `scripts/check-no-metrics.mjs` is the first command `npm test` runs. —
      DoD: the comment describes a rule, not a fixed set of three scripts; no
      sentence in it names a closed list as the definition of coverage.

- [ ] 8. Mutation proof for the guard (depends on 2, 5): temporarily restore
      the bare `process.argv[1] === fileURLToPath(import.meta.url)` compare in
      `scripts/check-no-metrics.mjs`, run
      `node --test test/metrics-build.test.ts` from a path where the fixture's
      `mkdtemp(tmpdir())` result is reached through a symlink, capture the red
      output, restore the hybrid guard, and capture the green. — DoD: the
      captured red names `T11b` and `T11c` failing on their **behaviour** —
      the absent `check-no-metrics: <file>:<line>: matched version-shaped
      literal` line on stderr — and not on exit code alone; the captured green
      reads 9 pass / 0 fail; both outputs appear verbatim in the commit body;
      `test/metrics-build.test.ts:98`'s `FIXTURE_ROOT_BASE = tmpdir()` and
      every fixture directory are unchanged in the diff.

- [ ] 9. Mutation proof for the derivation guard (depends on 6): temporarily
      point `deriveEntryPointScripts` at an empty directory, run
      `node --test test/entry-point.test.ts`, capture the failure, and revert.
      — DoD: the captured output shows the count assertion failing and naming
      the shortfall (0 found, at least 4 required); it appears in the commit
      body; the reverted file is byte-identical to the task-7 state.

- [ ] 10. Full green on a symlinked path (depends on 2-7):
      `ln -s "$PWD" /tmp/portfolio-link && cd /tmp/portfolio-link && npm run
      vendor && npm test`. — DoD: the run completes green from the symlinked
      path; `git diff --exit-code -- public/assets src/data/assets.json` is
      clean after `npm run vendor`, matching the check
      `.github/workflows/build.yml` performs; the symlinked-path result is the
      evidence stated in the commit body, not a CI result alone.

- [ ] 11. Write the journal entry at
      `src/content/journal/YYYY-MM-DD-<slug>.md` (depends on 10). — DoD:
      validates against the `journal` collection schema at
      `src/content.config.ts:112` — `service: portfolio`, `issue:
      https://github.com/mctlhq/portfolio/issues/75`, `proposal_slug:
      issue-75-q10-check-no-metrics-mjs-exits-0-without`, `visibility:
      public`, bilingual `title` and `decided` with both `en` and `ru`
      non-empty, `issue_opened_at` as a quoted ISO 8601 stamp with a timezone,
      `interventions: []`. The `decided` text states that the fix found a
      second offender (`scripts/snapshot-metrics.mjs`) the hand-typed list had
      also forgotten. No emoji; `npm test` passes with the entry in place.

## Tests

- [ ] T1. Every file returned by `deriveEntryPointScripts` carries an
      `isEntryPoint()` in the hybrid form — one `test()` per derived file,
      asserting `entryPointProblems(isolateIsEntryPoint(source), file)` is
      empty. Five tests today.
- [ ] T2. The derived set contains `scripts/check-no-metrics.mjs` — the test
      that proves part B actually closes the hole part A patched. Failure
      message names the file and prints the derived set.
- [ ] T3. The derived set contains `scripts/check-contrast.mjs`,
      `scripts/check-links.mjs`, `scripts/check-headers.mjs` and
      `scripts/snapshot-metrics.mjs` — the last being the script task 3 gives
      the hybrid guard to, and the one whose omission from the pinned list
      would have reopened this cycle's own hole.
- [ ] T4. The derivation returns at least four files; the failure message
      names the count found, the count required and the shortfall.
- [ ] T5. `deriveEntryPointScripts` over an empty temporary directory returns
      `[]` — so the reader can see T4 has a real condition to fire on.
- [ ] T6. The derivation excludes `scripts/check-dist.mjs`,
      `scripts/csp-hash.mjs`, `scripts/render-og.mjs` and
      `scripts/vendor-assets.mjs`, which call top-level `await main();` with no
      `if (...)` wrapper — excluded by the shape matcher, not by a skip list.
- [ ] T7. The three existing discrimination tests still pass unchanged:
      `entryPointProblems` reports a bare
      `process.argv[1] === fileURLToPath(import.meta.url)` form as missing
      `import.meta.main`; reports a bare `import.meta.main` form as missing the
      `realpathSync()` fallback; and reports nothing for the correct hybrid.
- [ ] T8. `test/metrics-build.test.ts` reports 9 pass / 0 fail, including
      `T11b` and `T11c`, when run from a path whose `os.tmpdir()` is reached
      through a symlink, with the fixture unmoved.
- [ ] T9. `test/check-headers.test.ts` still passes — it imports
      `scripts/check-headers.mjs` and depends on the guard keeping `main()`
      from reading argv; confirms the shared shape is unbroken.
- [ ] T10. `npm test` is green end to end from a symlinked checkout,
      including the first two commands
      (`node scripts/check-no-metrics.mjs && node scripts/check-contrast.mjs`)
      and all 29 `node --test` files.

## Rollback

Every change is source-local and additive; no schema, content, build output,
CSP hash, vendored asset or deployed artifact is touched, so rollback is a
revert with no cleanup.

- Scoped revert, most likely case: the derivation's regex turns out to be too
  literal against a script this investigation did not read. Revert
  `test/entry-point.test.ts` to the hand-typed
  `FILES = ['scripts/check-contrast.mjs', 'scripts/check-links.mjs',
  'scripts/check-headers.mjs', 'scripts/check-no-metrics.mjs']` (the #69-style
  fix, now including the fourth script) and keep tasks 2 and 3. The symlink
  defect stays fixed and coverage stays no worse than before this cycle, at
  the cost of part B.
- Scoped revert of task 3 alone: if running `scripts/snapshot-metrics.mjs` on
  a symlinked path proves to have an unwanted side effect, restore its bare
  compare. This forces a compensating change in
  `test/entry-point.test.ts`, because the derived set would then contain a
  file with no `isEntryPoint()` and the suite would be red — so this revert is
  only viable together with the scoped revert above. Note the coupling before
  attempting it.
- Full revert: `git revert <merge commit>` on the cycle's merge commit
  restores all five files (`scripts/check-no-metrics.mjs`,
  `scripts/snapshot-metrics.mjs`, `test/entry-point.test.ts`, the journal
  entry, and any lockfile touch — there should be none, since no dependency
  changes). `npm test` returns to the pre-cycle state, which is green in CI
  and red on a symlinked macOS checkout.
- Nothing needs redeploying: `mctl_rollback_service` is not involved, because
  no image or gitops value changes as a result of this cycle.
