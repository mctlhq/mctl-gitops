# Design: issue-191-ci-fail-the-build-when-the-committed-con

## Current state

`scripts/build-content-bundle.mjs` (read in full) generates two files from
`content/`:

- `client/src/content-bundle.json` — every published, eligible question,
  built via `partitionQuestions()` from `scripts/lib/content-model.mjs`
  (the single shared eligibility rule the file's own header describes as
  "safe by construction").
- `client/src/course-catalog.json` — the vendor-neutral course catalog
  derived from `content/courses/*.yaml`, including per-course published
  question counts.

Both output paths default to `join(ROOT, "client", "src", ...)` but are
overridable via `ACADEMY_BUNDLE_OUT` / `ACADEMY_CATALOG_OUT` env vars — this
matters for design because it means the generator can be pointed at a scratch
location without touching the working tree, though for this proposal we want
it to write to the real paths so `git diff` sees them.

Both generated files are tracked in git (confirmed: `git ls-files | grep -E
"content-bundle.json|course-catalog.json"` returns both paths). Today the
only thing that keeps a stale or hand-edited copy from being served is
regeneration on the read paths, per `client/package.json`:

```
"predev": "node ../scripts/build-content-bundle.mjs",
"prebuild": "node ../scripts/build-content-bundle.mjs",
"pretest": "node ../scripts/build-content-bundle.mjs",
```

`scripts/lib/validate-generated-artifacts.mjs` is invoked by the builder
itself (confirmed by reading the top of `build-content-bundle.mjs`, which
imports `validateGeneratedArtifacts`) and checks the *shape* of what was just
built — four options, exactly one correct, non-empty strings, valid option
ids, etc. It has no way to know whether the file already sitting in the
working tree (or already staged in a PR) matches what it just produced,
because it validates the in-memory structures the builder holds, not a
diff against the committed copy.

`.github/workflows/ci.yml`'s `content` job (read in full) currently runs, in
order: checkout, `oven-sh/setup-bun`, `bun install --frozen-lockfile`,
`bun run lint:content` (step name `Content lint`), `bun run test:content`
(step name `Content lint tests`), `bun run build:preview` (step name
`Build course preview`), then uploads the preview as an artifact. The job's
own inline comment states its defining property: "Structural validation
only: no secrets, no network. This is the job that runs identically on a
fork PR." `bun run lint:content` runs `node scripts/validate-content.mjs`;
`bun run test:content` runs the `node --test` suite listed in
`package.json`, which includes `tests/build-content-bundle.test.mjs` and
`tests/validate-generated-artifacts.test.mjs` — both of which test the
builder's *logic* against fixture content directories (via
`ACADEMY_CONTENT_DIR` / `ACADEMY_BUNDLE_OUT` env var overrides, per the
builder's own support for those), not the real `content/` tree against the
real committed `client/src/*.json`.

So: nothing in the existing pipeline runs the real builder against the real
`content/` tree and compares the result to what is actually committed. That
is precisely the gap #191 describes.

Precedent for a "regenerate and diff" CI pattern already exists in this repo
in a different workflow: `.github/workflows/capture-sources.yml` and
`.github/workflows/source-drift.yml` both use `git diff --staged --quiet`
to detect whether a generated step produced changes. This proposal follows
the same idiom, using the unstaged form (`git diff --exit-code <paths>`)
since nothing needs to be staged first — the files are already present in
the checkout and the builder overwrites them in place.

## Proposed solution

Add one new step to the `content` job in `.github/workflows/ci.yml`,
immediately after the existing `Content lint` step and before
`Content lint tests` (rationale for placement below):

```yaml
      - name: Content lint
        run: bun run lint:content

      - name: Verify committed content bundle matches generated output
        run: |
          node scripts/build-content-bundle.mjs
          git diff --exit-code client/src/content-bundle.json client/src/course-catalog.json
```

This is exactly the two commands the issue proposes, added as a distinct
named CI step (matching the job's existing convention of one step per
concern, e.g. `Content lint`, `Content lint tests`, `Build course preview`
are already separate rather than combined into one script).

Placement: directly after `Content lint`, before `Content lint tests` and
`Build course preview`. Reasoning:

- `lint:content` (`scripts/validate-content.mjs`) must run first: it is the
  cheapest, most fundamental structural check (schema shape, cross-file
  references, the objective map, the agent-authorship rule, publication
  preconditions). If `content/` itself is structurally invalid, failing
  there gives a clearer error than a generator that may behave oddly on
  invalid input.
- The new step must run before `Build course preview`
  (`scripts/build-preview.mjs`) only in the sense that it doesn't need to —
  they operate on independent outputs (bundle/catalog vs. the preview
  site) — but running the bundle diff check earlier gives faster, more
  specific failure signal for the most common drift case (someone edited
  `content/` and forgot to regenerate) before the more expensive preview
  build runs.
- Running it before `test:content` is deliberate: `test:content` includes
  `tests/build-content-bundle.test.mjs`, which exercises the builder against
  fixture directories, not the real tree. There's no dependency either way,
  but keeping "does content/ + the builder match the committed real
  artefacts" as the first content-shape gate mirrors the issue's own
  suggested ordering ("Add a step to the `content` job in `ci.yml`, after
  `lint:content`").

No secrets, no network: `scripts/build-content-bundle.mjs` reads only local
files under `content/` (or `ACADEMY_CONTENT_DIR` if set, which CI will not
set, so it defaults to the real `content/` tree) and writes to
`client/src/*.json` (or `ACADEMY_BUNDLE_OUT`/`ACADEMY_CATALOG_OUT`, again
unset in CI). `git diff --exit-code` is a local git operation. This
preserves the `content` job's documented fork-PR-safe property.

Failure signal: `git diff --exit-code` prints a normal unified diff of
exactly which lines changed in which of the two files, then exits 1,
failing the step and the job. This directly satisfies the issue's "A
non-zero exit means the committed artefacts are not what the verified
sources generate, and names the drift precisely."

No change is needed to `scripts/build-content-bundle.mjs`,
`scripts/lib/validate-generated-artifacts.mjs`, `scripts/lib/content-model.mjs`,
`client/package.json`, or any test file — this is additive, CI-only.

## Alternatives

1. **Fold the check into `scripts/validate-content.mjs` (`lint:content`)
   itself**, so `bun run lint:content` both lints and asserts freshness in
   one script/step. Rejected: `validate-content.mjs` validates *source*
   content (`content/`) against schema and cross-file rules and is
   documented in `CLAUDE.md` as one of three explicit gate layers ("JSON
   Schema", "The lint", "The bundle builder"), each with a distinct
   responsibility. Mixing "is content/ well-formed" with "does the
   committed generated artefact match content/" blurs that intentional
   separation and would make a content-authoring failure and a stale-build
   failure look like the same kind of error in the log. A separate named CI
   step keeps the failure mode legible, matches the issue's proposed diff
   exactly, and needs no script changes at all.

2. **Add an npm/bun script (e.g. `verify:bundle-fresh`) in `package.json`
   that wraps both commands**, then call that one script from `ci.yml`.
   Considered because it's slightly more reusable (a contributor could run
   it locally). Rejected in favor of inlining the two commands directly in
   the workflow step, matching the issue's exact proposed snippet and
   avoiding adding a new persistent script/npm-script surface for a
   two-line check; the equivalent local reproduction is already just
   copy-pasting the two commands from the CI log, which is standard for
   this kind of drift check (compare `capture-sources.yml`'s and
   `source-drift.yml`'s inline `git diff --staged --quiet` usage, neither
   of which is wrapped in an npm script).

3. **Run the check as a pre-commit / pre-push git hook instead of (or in
   addition to) CI.** Rejected as the primary mechanism: hooks are
   opt-in per contributor machine and easily bypassed or never installed,
   whereas CI is the actually-enforced gate this issue asks for
   ("fail the build"). Nothing in the repo currently installs git hooks
   (no `.husky/`, no `prepare` script found), so adding one would be a new
   pattern for the repo, out of proportion to a two-line CI addition that
   already fully satisfies the issue.

## Platform impact

- **Migrations**: none. No database, schema, or content-model change.
- **Backward compatibility**: none broken. Any PR whose committed
  `content-bundle.json`/`course-catalog.json` already matches generated
  output (the expected state, since `predev`/`prebuild`/`pretest` already
  force regeneration during normal local development) sees no behavior
  change — the new step passes silently. Only PRs that already have drift
  (a real bug this issue targets) start failing, which is the intended
  effect.
- **Resource impact**: negligible. One extra `node` invocation of a script
  that already runs multiple times per `client` build/test/dev cycle, plus
  a `git diff` over two JSON files, added to a job that already runs on
  every PR. No new job, no new service dependency, no new secret.
  `bun install --frozen-lockfile` (already a job step) provides the `node`
  toolchain the script needs — root `package.json` lists `yaml` and no
  other builder dependency beyond Node's built-ins (`node:fs`, `node:path`,
  `node:url`), all already resolved by the existing install step.
- **Risks + mitigations**:
  - *Risk*: a contributor's local working tree has a regenerated bundle
    with different key ordering or whitespace than what CI's checkout +
    regenerate produces. Mitigation: confirmed by reading
    `build-content-bundle.mjs` lines 124/126, both files are written with
    `writeFileSync(OUT, JSON.stringify(bundle, null, 2) + "\n")` (and the
    same pattern for the catalog) — a fixed, deterministic serialization
    with no key-ordering dependency on iteration order beyond what the
    script itself constructs. The existing `predev`/`prebuild`/`pretest`
    scripts already prove this is stable in practice today (they overwrite
    the file on every local dev/build/test run without contributors
    reporting spurious diffs). No code change needed.
  - *Risk*: a contributor forgets to regenerate before pushing and gets a
    CI failure late (after other jobs may have already run). Mitigation:
    placement right after `lint:content`, the first step in the fastest job,
    surfaces this as early as CI feedback gets; no earlier local-only gate
    is introduced by this proposal (see Alternative 3), but the fix is a
    one-line local command (`node scripts/build-content-bundle.mjs`) that
    contributors already run implicitly via `predev`/`prebuild`/`pretest`.
  - *Risk*: false-positive drift caused by environment differences (e.g. a
    stale `content/` fixture accidentally picked up via a leftover
    `ACADEMY_CONTENT_DIR` env var in the CI runner). Mitigation: CI does not
    set `ACADEMY_CONTENT_DIR`/`ACADEMY_BUNDLE_OUT`/`ACADEMY_CATALOG_OUT`
    anywhere in `ci.yml` today (confirmed by reading the file in full), so
    the script's defaults (`content/`, `client/src/content-bundle.json`,
    `client/src/course-catalog.json`) apply, matching what a contributor's
    plain local run produces.
