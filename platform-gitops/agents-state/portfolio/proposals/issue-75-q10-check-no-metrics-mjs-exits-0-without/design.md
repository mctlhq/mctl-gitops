# Design: issue-75-q10-check-no-metrics-mjs-exits-0-without

## Current state

### The scripts and how they decide to run

`scripts/` holds nine `.mjs` programs. They fall into three groups by how the
top-level code decides to invoke `main()`:

1. **Hybrid `isEntryPoint()` — correct.** `scripts/check-contrast.mjs:415`,
   `scripts/check-links.mjs:287`, `scripts/check-headers.mjs:295`. Each has
   the identical body:

   ```js
   function isEntryPoint() {
     if (typeof import.meta.main !== 'undefined') {
       return import.meta.main;
     }
     if (!process.argv[1]) {
       return false;
     }
     try {
       return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
     } catch {
       return false;
     }
   }

   if (isEntryPoint()) {
     await main();
   }
   ```

   `realpathSync` is imported from `node:fs` — `scripts/check-headers.mjs:15`,
   `scripts/check-contrast.mjs:24`, and `scripts/check-links.mjs:18` (as
   `import { existsSync, realpathSync } from 'node:fs'`).

2. **Bare string compare — defective.** `scripts/check-no-metrics.mjs:293`
   and `scripts/snapshot-metrics.mjs:480`, both exactly:

   ```js
   if (process.argv[1] === fileURLToPath(import.meta.url)) {
     await main();
   }
   ```

   Neither file declares an `isEntryPoint()` and neither imports
   `realpathSync`. `scripts/check-no-metrics.mjs` currently imports only
   `readdir, readFile, stat` from `node:fs/promises`, plus `node:path` and
   `fileURLToPath` from `node:url`.

3. **Unconditional `await main();`.** `scripts/check-dist.mjs:941`,
   `scripts/csp-hash.mjs:81`, `scripts/render-og.mjs:169`,
   `scripts/vendor-assets.mjs:733`. No condition at all, so nothing can make
   them skip; they are a different shape and are not part of this problem.

### The defect, measured

Node resolves `process.argv[1]` against `process.cwd()` but does not realpath
it; an ESM module's `import.meta.url` is realpathed. When the script is
spawned by an **absolute** path whose directories include a symlink, the two
diverge. Reproduced during this investigation on Node v22.23.2, spawning a
probe through a symlinked directory:

```
argv1= /tmp/symtest/link/scripts/probe.mjs
meta = /tmp/symtest/real/scripts/probe.mjs
equal= false
import.meta.main= true
```

The committed `scripts/check-no-metrics.mjs`, copied into that same symlinked
tree alongside a `src/content/projects/fixture.en.md` body containing
`9.9.9`, spawned by absolute path:

```
absolute-symlinked-path status= 0
stdout: ""
stderr: ""
```

Reached through the real path, the same fixture yields the problem line and
exit 1. `import.meta.main` being `true` in that probe confirms the hybrid's
first branch is sufficient on any Node that defines it (22.18+/24.2+), and
the `realpathSync` fallback covers the rest.

### Why the tests see it and CI does not

`test/metrics-build.test.ts:98` sets `const FIXTURE_ROOT_BASE = tmpdir();`.
`makeCheckNoMetricsScriptCopy()` at line 172 does
`mkdtemp(path.join(FIXTURE_ROOT_BASE, 'check-no-metrics-content-'))`, copies
the real script plus `src/components/CycleDiagram.astro` and
`src/layouts/Base.astro` (so the script's own `ALLOW` entries are not reported
stale), and `runCheckNoMetrics()` at line 192 spawns
`node <root>/scripts/check-no-metrics.mjs` — an absolute path. On Linux CI
`tmpdir()` is `/tmp`, a real directory, so `argv[1]` and the realpathed
`import.meta.url` agree and the script runs. On macOS `tmpdir()` is
`/var/folders/...`, a symlink to `/private/var/folders/...`, so they do not,
and `T11b` (line 200) and `T11c` (lines 248 and 258) fail: `T11b` asserts a
non-zero status and a stderr match, `T11c` mutant asserts the same on a
mutated `mctl-design.en.md`. The fixture is doing exactly what it should; the
script is the bug.

### The guard that should have caught it

`test/entry-point.test.ts` exists for precisely this shape. Its header
comment (lines 1-15) explains the hazard in the right terms — "not
symlink-safe: a symlinked checkout would silently skip the check with exit
0" — and it has two genuinely good pieces:

- `isolateIsEntryPoint(source)` (line 28) brace-counts the real
  `function isEntryPoint() { ... }` block out of a committed file's source, so
  the assertion is on real code rather than a regex over the whole file. It
  `assert.ok(start !== -1, ...)` when the declaration is absent.
- `entryPointProblems(source, label)` (line 55) requires **both** halves:
  `/import\.meta\.main/` and (`/realpathSync\(/` **and**
  `/fileURLToPath\(import\.meta\.url\)/`). Three synthetic-source tests at
  lines 78, 89 and 100 prove it discriminates rather than matching everything.

The weak point is line 24:

```js
const FILES = ['scripts/check-contrast.mjs', 'scripts/check-links.mjs', 'scripts/check-headers.mjs'];
```

A hand-typed array. `scripts/check-no-metrics.mjs` is absent, so the loop at
line 68 never reads it. The same array was already wrong once: #69 added
`check-headers.mjs` to it. Running the derived rule over `scripts/*.mjs`
during this investigation shows it is currently wrong twice over:

```
all .mjs: 9  check-contrast check-dist check-headers check-links check-no-metrics csp-hash render-og snapshot-metrics vendor-assets
kept   : 5  check-contrast check-headers check-links check-no-metrics snapshot-metrics
with isEntryPoint():     check-contrast check-headers check-links
MISSING isEntryPoint():  check-no-metrics snapshot-metrics
```

### Conventions this repo already follows

- `AGENTS.md`: evidence goes into a committed file or a script that runs in
  `npm test`, never into a pull request body; one journal entry per cycle.
- `test/source-hygiene.test.ts` is the house pattern for a derived scan that
  refuses to be vacuous: it walks directories, filters by extension so that
  binaries are excluded "by construction, never by an ad hoc skip list", and
  asserts `textFiles.length > 0` before the real loop. The new derivation in
  `test/entry-point.test.ts` should read as a sibling of that file.
- `npm test` runs `node scripts/check-no-metrics.mjs` first, then
  `check-contrast.mjs`, then `node --test` over 29 `.ts` test files including
  `test/metrics-build.test.ts` and `test/entry-point.test.ts`.

## Proposed solution

Three edits to source plus one test rewrite. Nothing about what the checks
*check* changes.

### 1. `scripts/check-no-metrics.mjs` — hybrid guard

Add `import { realpathSync } from 'node:fs';` alongside the existing
`node:fs/promises` import. Insert a `function isEntryPoint()` immediately
above the entry block, byte-for-byte the body already in
`scripts/check-headers.mjs:295` (including the doc comment's pointer at its
siblings, adjusted to name the right ones), and replace line 293 with
`if (isEntryPoint()) {`.

This is deliberately a copy rather than a new shared module — see
Alternatives. `entryPointProblems()` asserts on each file's own isolated
block, so the shape must be present in each file for the guard to have
anything to read.

### 2. `scripts/snapshot-metrics.mjs` — same hybrid guard

Identical change at line 480. This file has the same bare compare and no
`isEntryPoint()`, and it is inside `scripts/*.mjs`, so the derived test in
step 3 selects it. Two consequences make this the only honest option: the
derived test cannot pass while it stands (`isolateIsEntryPoint()` would
assert-fail with "expected a `function isEntryPoint()` declaration"), and
excluding it would mean reintroducing a hand-typed list, which is the defect
this issue exists to delete. Its practical failure mode is that
`npm run metrics` silently does not rewrite `src/data/metrics.json` on a
symlinked checkout.

Note the difference in how `snapshot-metrics.mjs` is reached: it currently
imports nothing from `node:fs` (only `node:fs/promises`), so it too gains
`import { realpathSync } from 'node:fs';`. The implementer should check the
real import block rather than assume.

### 3. `test/entry-point.test.ts` — derive `FILES`, assert the derivation

Replace the hand-typed array with:

```js
const SCRIPTS_DIR = path.join(ROOT, 'scripts');
const ENTRY_BLOCK_RE = /^if \(.*\) \{\r?\n\s*await main\(\);\r?\n\}/m;
const REQUIRED = [
  'scripts/check-contrast.mjs',
  'scripts/check-links.mjs',
  'scripts/check-headers.mjs',
  'scripts/check-no-metrics.mjs',
  'scripts/snapshot-metrics.mjs',
];
const MIN_DERIVED = 4;

function deriveEntryPointScripts(scriptsDir: string): string[] { ... }
```

`deriveEntryPointScripts` reads `scriptsDir` with `readdirSync(..., {
withFileTypes: true })`, keeps `.mjs` files, reads each source, keeps those
matching `ENTRY_BLOCK_RE`, and returns repo-relative POSIX paths
(`scripts/<name>.mjs`) sorted. It takes the directory as a **parameter**, not
from module scope — that is what makes the emptiness mutation proof in the
acceptance criteria possible without editing the function.

Then three assertions, in a dedicated test that runs before the per-file loop
is even built:

- `assert.ok(derived.length >= MIN_DERIVED, ...)` with a message naming both
  numbers, e.g. `` `derivation over scripts/*.mjs matched ${derived.length}
  file(s), expected at least ${MIN_DERIVED} -- short by ${MIN_DERIVED -
  derived.length}; the enumeration is broken, not the scripts` ``.
- For each entry in `REQUIRED`, `assert.ok(derived.includes(entry), ...)`
  naming the missing script and printing the derived set.
- A test that passes an empty temporary directory to
  `deriveEntryPointScripts` and asserts it returns `[]`, so the reader can see
  that the count assertion has something real to fire on.

The per-file loop keeps its current body — `readFileSync`,
`isolateIsEntryPoint`, `assert.deepEqual(entryPointProblems(block, file),
[])` — and simply iterates `deriveEntryPointScripts(SCRIPTS_DIR)` instead of
`FILES`. The three synthetic-source discrimination tests at lines 78-115 are
untouched.

Because `node:test` collects `test()` registrations at module evaluation
time, the derivation runs at import. If it throws (missing `scripts/`), the
file fails to load and the suite goes red — an acceptable and loud failure.

### 4. `test/entry-point.test.ts` header comment

Rewrite lines 1-15 to state the derived rule: every `scripts/*.mjs` whose
source carries a top-level `if (...) { await main(); }` block must declare an
`isEntryPoint()` in the hybrid form (`import.meta.main` where defined, a
`realpathSync()` comparison below it), because a bare `process.argv[1]`
compare makes the script exit 0 without running on a symlinked checkout; that
the set is enumerated rather than typed, so a new script is covered without
anyone remembering to add it; that the enumeration is floored at four files
(below the true count of five, deliberately)
and pinned to five known names so a broken scan fails instead of passing
vacuously; and that the unconditional `await main();` scripts are excluded by
the shape, not by a skip list. It should retain the note that
`scripts/check-headers.mjs` is the one whose silent pass would make
`.github/workflows/build.yml`'s final step vacuous, and should name
`scripts/check-no-metrics.mjs` as the first command `npm test` runs. It must
not name a fixed set as the definition of coverage.

### 5. Mutation proofs and the journal

Both mutation proofs required by the acceptance criteria are transient: apply
the mutation, capture the output, revert, capture the green output, and state
both in the commit body. They are not committed as tests — the repository
already carries committed mutation tests where the mutation is a fixture
write (`T11c` mutant in `test/metrics-build.test.ts:258`), but mutating the
committed script's own guard or the test's own enumeration cannot be done from
inside the suite without shipping the defect.

The behavioural requirement matters: the red must be `T11b`/`T11c` failing on
their stderr assertion (a missing
`check-no-metrics: ...: matched version-shaped literal` line), not merely on a
status mismatch. Both are already written that way — `T11b` asserts
`notEqual(status, 0)` **and** `assert.match(result.stderr, /.../)` — so the
red output naturally names the behaviour.

The whole-cycle green must be `npm run vendor && npm test` from a checkout
reached through a symlink (e.g. `ln -s $PWD /tmp/portfolio-link && cd
/tmp/portfolio-link && npm run vendor && npm test`), not from CI.

Finally, `src/content/journal/YYYY-MM-DD-<slug>.md` per the `journal`
collection schema at `src/content.config.ts:112`: `service: portfolio`, the
issue URL, `proposal_slug`, `visibility`, bilingual `title` and `decided`,
`issue_opened_at` as a quoted ISO 8601 stamp, `interventions: []`.

## Alternatives

**Extract `isEntryPoint()` into a shared `scripts/lib/entry-point.mjs` and
import it in all five scripts.** Attractive on DRY grounds and it would make
the guard impossible to get wrong per-file. Dropped for two reasons. First, it
breaks the existing test's mechanism: `isolateIsEntryPoint()` isolates a
`function isEntryPoint()` declaration out of each committed file, and a
one-line import declares no such function, so the whole shape-pinning
apparatus — including the three discrimination tests — would have to be
rebuilt around a different subject. Second, the correctness of an entry guard
depends on `import.meta.url` of *the file being guarded*; a shared helper
would have to take the caller's URL as an argument, so every call site keeps a
per-file expression anyway and the duplication is only half removed. The issue
asks for "the same hybrid `isEntryPoint()` as its three siblings", which is
the copy.

**Append `'scripts/check-no-metrics.mjs'` to the existing `FILES` array.** One
line, and it would make `T11b`/`T11c` green after step 1. Dropped because it
is the fix #69 already applied to the same array and the issue names it
explicitly as treating the symptom. It would also have left
`scripts/snapshot-metrics.mjs` undiscovered — a concrete, measurable cost, not
a stylistic objection.

**Derive over `scripts/*.mjs` with an exclusion list for scripts that use
unconditional `await main();` and for `snapshot-metrics.mjs`.** Simpler to
land because no script outside `check-no-metrics.mjs` needs changing. Dropped:
an exclusion list is the same hand-typed artifact with the polarity flipped,
and every script anyone adds to it is silently unguarded again. The shape
matcher already excludes the four unconditional scripts by construction, which
is the `source-hygiene.test.ts` posture ("excluded by construction, never by
an ad hoc skip list").

**Move `T11b`/`T11c`'s fixture off `tmpdir()` to a directory inside the repo,
or `realpathSync()` the `mkdtemp` result in the test.** Would make the two
tests green immediately with no change to any script. Explicitly forbidden by
the issue, and correctly so: the fixture's symlinked path is the only thing in
the suite that exercises the defect. Making the test avoid the symlink would
delete the evidence and leave the production script broken.

**Assert the derived set equals exactly five files.** Tighter than a floor of
four. Dropped because it makes every new guarded script a failing test until
someone edits the number — reintroducing the maintenance burden by a different
route. A floor plus named membership fails loudly on a broken scan and stays
silent on a legitimate addition, which is the asymmetry wanted.

## Platform impact

**Migrations.** None. No content, schema, build output, CSP hash, vendored
asset or Docker layer changes. `src/data/metrics.json` is not rewritten by
this cycle.

**Backward compatibility.** The hybrid guard is strictly more permissive about
*when* `main()` runs: every invocation that ran before still runs, plus the
symlinked ones that silently did not. `npm test`'s first two commands invoke
`scripts/check-no-metrics.mjs` and `scripts/check-contrast.mjs` by relative
path from the repo root, which resolves against the realpathed `process.cwd()`
and therefore already matched; those invocations are unaffected.
`test/check-headers.test.ts` imports `scripts/check-headers.mjs` and relies on
its guard keeping `main()` from reading argv — unchanged behaviour, since
`import.meta.main` is false for an imported module.

**Risk: `scripts/snapshot-metrics.mjs` starts running where it previously
exited 0.** Mitigated by the fact that it is only invoked by `npm run
metrics`, never by `npm test`, `npm run build` or any workflow step in
`.github/workflows/build.yml`. The behaviour change is that a symlinked-path
`npm run metrics` now does its job.

**Risk: the derivation picks up a future `scripts/*.mjs` and turns its missing
guard into a test failure.** That is the intended behaviour and the entire
point of part B. The failure message from `isolateIsEntryPoint()` ("expected a
`function isEntryPoint()` declaration") and from `entryPointProblems()` names
the file and the missing half, so the fix is obvious to whoever hits it.

**Risk: `ENTRY_BLOCK_RE` is too literal and stops matching after an innocuous
reformat** (extra blank line, a comment between `if` and `await main();`, or a
guard written as `if (isEntryPoint()) await main();` with no braces). A script
silently dropping out of the derived set is exactly the vacuity this cycle is
closing. Mitigated by the floor-of-four assertion plus the five named
memberships: the five scripts that matter today cannot drop out unnoticed, and
a general regression in the matcher takes the count below four and fails. The
residual risk is a *sixth* script using an unmatched variant; the header
comment should state the shape the matcher recognizes so an author knows what
to write.

**Risk: Node version spread.** `import.meta.main` landed in Node 22.18 and
24.2. CI pins `node-version: 24` (`.github/workflows/build.yml`), and this
investigation ran v22.23.2 where it is defined. The `realpathSync` fallback
covers anything older, and returning `false` on a throw means a missing or
unreadable `argv[1]` degrades to "not the entry point" rather than crashing.

**Resource impact.** `test/entry-point.test.ts` gains nine synchronous
`readFileSync` calls over `scripts/*.mjs` (about 150 KB total) at module load.
Negligible.
