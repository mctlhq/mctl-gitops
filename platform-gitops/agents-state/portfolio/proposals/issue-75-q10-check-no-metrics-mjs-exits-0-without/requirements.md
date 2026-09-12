# Q10: symlink-safe entry guard for check-no-metrics.mjs, and a derived entry-point test that cannot forget a script

## Context

`scripts/check-no-metrics.mjs` is the first command `npm test` runs. Its
top-level entry block at line 293 is a bare string comparison,
`if (process.argv[1] === fileURLToPath(import.meta.url))`. Node realpaths an
ESM module's `import.meta.url` but does not realpath `process.argv[1]` when
the script is invoked by an absolute path, so on any checkout reached through
a symlink the two strings differ, `main()` never runs, and the script exits 0
having checked nothing. Reproduced in this investigation on Node v22.23.2: a
copy of the committed script planted with a violating fixture and spawned by
an absolute path through a symlinked directory printed nothing and exited 0,
while the same fixture reached through its real path printed
`check-no-metrics: src/content/projects/fixture.en.md:5: matched
version-shaped literal "9.9.9" -- not permitted in project content` and
exited 1. A probe through the same symlink confirms the mechanism directly:
`argv1=/tmp/symtest/link/scripts/probe.mjs`,
`meta=/tmp/symtest/real/scripts/probe.mjs`, `equal=false`. This is why
`T11b` and `T11c` in `test/metrics-build.test.ts` — which spawn the script
from a `mkdtemp(tmpdir())` fixture, and macOS `tmpdir()` is
`/var/folders/...`, a symlink to `/private/var/folders/...` — fail locally
while CI stays green. CI's green was not evidence of correctness.

The three sibling scripts (`scripts/check-contrast.mjs:415`,
`scripts/check-links.mjs:287`, `scripts/check-headers.mjs:295`) already carry
a hybrid `isEntryPoint()` that is immune to this. A test exists specifically
to pin that shape — `test/entry-point.test.ts` — but its coverage is a
hand-typed array on line 24 naming only those three files. The forgotten
script was therefore invisible to the test written to forbid exactly its
defect. This is the second failure of the same list: on #69 the omission was
`scripts/check-headers.mjs`, fixed by appending one array element, which
treated the symptom. This proposal fixes the guard and replaces the list with
a derivation whose emptiness is itself asserted, so that a scan matching
nothing fails loudly instead of passing vacuously.

Deriving the set over `scripts/*.mjs` in this investigation surfaced a second
offender the hand list also forgot: `scripts/snapshot-metrics.mjs:480` carries
the identical bare compare and has no `isEntryPoint()` function at all. It is
inside `scripts/*.mjs`, so it is inside the derivation's scope, and the
derived test cannot go green while it stands. Fixing it is therefore part of
this cycle — and is the first concrete demonstration that the derived rule
finds what the typed list could not.

## User stories

- AS the maintainer of `portfolio` I WANT `scripts/check-no-metrics.mjs` to
  run its checks regardless of whether the checkout is reached through a
  symlink SO THAT a silent exit 0 can never be mistaken for a passing gate.
- AS a contributor running `npm test` on macOS I WANT `T11b` and `T11c` in
  `test/metrics-build.test.ts` to pass without relocating their fixture SO
  THAT local and CI results agree and a local red is a real defect.
- AS a future author of a new `scripts/*.mjs` check I WANT
  `test/entry-point.test.ts` to cover my script automatically SO THAT I cannot
  ship an unguarded entry block by forgetting to edit a list.
- AS a reviewer I WANT the derivation that produces that coverage to fail
  loudly when it matches nothing SO THAT a broken enumeration is reported
  rather than silently reducing coverage to zero.

## Acceptance criteria (EARS)

### A. Fix the guard

- WHEN `scripts/check-no-metrics.mjs` is invoked as a program THE SYSTEM SHALL
  decide whether to call `main()` through a `function isEntryPoint()` that
  returns `import.meta.main` when `typeof import.meta.main !== 'undefined'`,
  and otherwise compares `realpathSync(process.argv[1])` against
  `realpathSync(fileURLToPath(import.meta.url))`, returning `false` if
  `process.argv[1]` is absent or if either call throws.
- WHEN `scripts/check-no-metrics.mjs` needs `realpathSync` THE SYSTEM SHALL
  import it from `node:fs`, matching `scripts/check-headers.mjs:15`.
- WHILE the bare `process.argv[1] === fileURLToPath(import.meta.url)`
  comparison remains anywhere in `scripts/check-no-metrics.mjs`'s top-level
  entry block THE SYSTEM SHALL be considered not to satisfy this proposal;
  the block SHALL read `if (isEntryPoint()) { await main(); }`.
- WHEN `scripts/check-no-metrics.mjs` is spawned by an absolute path whose
  directories include a symlink, over a tree containing a version-shaped
  literal in `src/content/projects` THE SYSTEM SHALL print the
  `check-no-metrics: <file>:<line>: matched version-shaped literal` problem
  line and exit non-zero.
- WHEN `node --test test/metrics-build.test.ts` runs on a platform whose
  `os.tmpdir()` is a symlink THE SYSTEM SHALL report 9 pass / 0 fail, with
  `FIXTURE_ROOT_BASE` in `test/metrics-build.test.ts:98` left as `tmpdir()`
  and the fixture directories unmoved.
- IF the hybrid guard in `scripts/check-no-metrics.mjs` is replaced by the
  bare string comparison THEN THE SYSTEM SHALL fail `T11b` and `T11c` in
  `test/metrics-build.test.ts` on their behaviour — a missing problem line on
  stderr, not merely a differing exit code — and both that red output and the
  restored 9 pass / 0 fail output SHALL be stated in the commit body.

### B. Stop the list from being the weak point

- WHEN `test/entry-point.test.ts` determines which files to assert on THE
  SYSTEM SHALL derive them by enumerating `scripts/*.mjs` and keeping those
  whose source contains a top-level entry block of the shape
  `if (...) { await main(); }`, rather than reading a hand-typed array.
- WHILE the derivation runs THE SYSTEM SHALL assert every derived file carries
  an `isEntryPoint()` in the hybrid form, using the existing
  `isolateIsEntryPoint()` and `entryPointProblems()` helpers unchanged in
  intent.
- WHEN the derivation completes THE SYSTEM SHALL assert it returned at least
  four files, and SHALL assert that `scripts/check-contrast.mjs`,
  `scripts/check-links.mjs`, `scripts/check-headers.mjs` and
  `scripts/check-no-metrics.mjs` are each among them.
- IF the enumeration matches fewer than four files THEN THE SYSTEM SHALL fail
  with a message naming the shortfall — the count found and the count
  required — rather than passing with nothing asserted.
- IF a required known script is absent from the derived set THEN THE SYSTEM
  SHALL fail naming that script.
- WHEN a script under `scripts/` that is not one of the four named scripts
  carries the `if (...) { await main(); }` shape THE SYSTEM SHALL assert the
  hybrid form on it too; concretely, `scripts/snapshot-metrics.mjs` is in the
  derived set today and SHALL therefore be given the same hybrid
  `isEntryPoint()` in this cycle so the derived test is green.
- WHILE `scripts/check-dist.mjs`, `scripts/csp-hash.mjs`,
  `scripts/render-og.mjs` and `scripts/vendor-assets.mjs` call top-level
  `await main();` with no `if (...)` wrapper THE SYSTEM SHALL leave them
  outside the derived set, by construction of the shape matcher and not by an
  ad hoc skip list.
- WHEN a reader opens `test/entry-point.test.ts` THE SYSTEM SHALL present a
  header comment that describes the derived rule — which files are enumerated,
  what shape selects them, and what the emptiness assertion protects —
  rather than naming a fixed set of three scripts.
- WHEN the matcher's discrimination is checked THE SYSTEM SHALL keep the three
  existing synthetic-source tests at `test/entry-point.test.ts:78`, `:89` and
  `:100` passing unchanged.

### Whole-cycle criteria

- WHEN `npm run vendor && npm test` is run from a checkout reached through a
  symlinked path THE SYSTEM SHALL complete green, and that run SHALL be the
  evidence cited rather than a CI run alone.
- WHEN the enumeration in `test/entry-point.test.ts` is temporarily pointed at
  an empty directory THE SYSTEM SHALL fail the count assertion naming the
  shortfall; that mutation output SHALL be stated in the commit body.
- WHEN the cycle lands THE SYSTEM SHALL carry a journal entry at
  `src/content/journal/YYYY-MM-DD-<slug>.md` conforming to the `journal`
  collection schema in `src/content.config.ts:112` — `service`, `issue`,
  `proposal_slug`, `visibility`, bilingual `title` and `decided`,
  `issue_opened_at`, and `interventions` — with both EN and RU text present.

## Out of scope

- The five P3 findings from #74's review. They are wording and hardening notes
  on code that works.
- Changing what `scripts/check-no-metrics.mjs` checks — its `RULES`, `ALLOW`,
  `SCAN_DIRS`, `MATCH_RE` and the `src/content/projects` version matcher are
  correct and stay untouched. Only the entry guard changes.
- Auditing entry guards outside `scripts/*.mjs` — no `src/`, `test/` or
  `.github/` entry shapes are reviewed.
- Moving or restructuring the `T11b`/`T11c` fixture away from
  `mkdtemp(tmpdir())`. Explicitly forbidden: it would hide the defect.
- Converting `scripts/check-dist.mjs`, `scripts/csp-hash.mjs`,
  `scripts/render-og.mjs` or `scripts/vendor-assets.mjs` to an
  `isEntryPoint()` form. Their unconditional `await main();` is a different
  shape and the derivation excludes it deliberately.
- Adding `scripts/snapshot-metrics.mjs` to the four names the count/membership
  assertion requires. It is covered by the derivation, which is the point; the
  required-name floor stays at the four the issue lists.
- Changing `.github/workflows/build.yml`, the `npm test` script list, or
  anything about how CI invokes the suite.

## Open questions

- The issue's scope items 3 and 4 describe the derivation but do not mention
  `scripts/snapshot-metrics.mjs`, which this investigation found carries the
  identical bare compare at line 480 and no `isEntryPoint()` at all. The
  derived test cannot be green while it stands, and it is inside
  `scripts/*.mjs` so it is not covered by the "outside `scripts/*.mjs`"
  exclusion. Proceeding on the reading that fixing it is required by scope
  item 3 rather than being new scope: the issue's own thesis is that any
  script the list forgets is unguarded. A reviewer who disagrees should say so
  before approval, because the only alternative that keeps the derived test
  green is an exclusion list — which is the defect this issue exists to
  remove.
- `scripts/snapshot-metrics.mjs` is invoked by `npm run metrics`, not by
  `npm test`, so its silent exit 0 means `src/data/metrics.json` is silently
  not regenerated rather than a gate passing vacuously. Same defect, different
  blast radius; treated identically here.
- The exact regular expression used to recognize the
  `if (...) { await main(); }` shape is left to the implementer. A candidate
  validated during this investigation —
  `/^if \(.*\) \{\r?\n\s*await main\(\);\r?\n\}/m` — selects exactly
  `check-contrast`, `check-headers`, `check-links`, `check-no-metrics` and
  `snapshot-metrics` out of the nine `scripts/*.mjs` files, and excludes the
  four that call top-level `await main();` unwrapped.
- The issue says "at least four files". After this cycle the true count is
  five. The floor stays four as specified, so adding a sixth script does not
  require editing the assertion; the named-membership check is what pins the
  known scripts.
