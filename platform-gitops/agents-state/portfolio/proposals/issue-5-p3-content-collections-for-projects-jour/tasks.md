# Tasks: issue-5-p3-content-collections-for-projects-jour

- [ ] 1. Add `src/lib/journal.ts` with no imports at all: `ISO_WITH_OFFSET`,
      `yyyyMmDd`, `isoWithOffset(value)`, the `Intervention` and `JournalTimes`
      interfaces, `leadTimeHours(entry)` and `interventionCount(entry)` exactly
      as specified in `design.md` section 2 — DoD: the file imports nothing;
      `leadTimeHours` returns unrounded hours, `null` for absent/`null`/empty
      `deployed_at`, and throws `RangeError` on an unparseable value or on
      `deployed_at` earlier than `issue_opened_at`; `interventionCount` returns
      `0` when `interventions` is absent.
- [ ] 2. Add `src/lib/adr.ts` with no imports at all: `ADR_SECTIONS` (the five
      headings in order), `adrBodyProblems(id, body)` and
      `checkAdrBodies(entries)` — DoD: `adrBodyProblems` reports a missing
      section, the five sections out of order, a section lacking a
      `class="l en"` block, a section lacking a `class="l ru"` block, and an
      `id` that disagrees with the four-digit filename prefix;
      `checkAdrBodies` aggregates every problem from every entry into one
      thrown `Error` whose message lists file and section for each.
- [ ] 3. Create `src/content.config.ts` (depends on 1, 2) with the three
      collections from `design.md` section 1: `glob` loaders from
      `astro/loaders`, the explicit `generateId` that keeps `<slug>.<lang>`
      ids, the shared `githubUrl` / `httpsUrl` / `semver` / `bilingual` /
      `stamp` primitives, and `z.strictObject` everywhere including nested
      objects — DoD: `export const collections = { projects, journal, adr }`;
      every field, enum and optionality matches the issue; `stamp` rejects a
      `Date` (an unquoted YAML timestamp) with a message that names quoting as
      the fix.
- [ ] 4. Wrap the `adr` collection's loader (depends on 2, 3) so that after
      `base.load(ctx)` it calls `checkAdrBodies` over the **whole**
      `ctx.store`, not only the entries re-read this run — DoD: the wrapper
      keeps the base loader's `schema`/`name` contract, and removing a heading
      from a seeded ADR makes `astro sync`, `astro check`, `astro dev` and
      `astro build` all fail.
- [ ] 5. Write the three seed ADRs (depends on 3, 4):
      `src/content/adr/0001-bootstrap-boundary.md`,
      `0002-static-astro-no-client-bundles.md`,
      `0005-self-contained-runtime-assets.md`, each `status: accepted`,
      `date: '2026-09-11'`, `visibility: public`, `id` matching the filename,
      bodies using the heading-with-two-spans and blank-line-delimited
      `<div class="l en">` / `<div class="l ru" lang="ru">` pattern from
      `design.md` section 4, and the EN/RU copy from section 9 verbatim — DoD:
      all three load; 0003 and 0004 do not exist; every one of the fifteen
      sections has both languages; no heading text is invented or translated
      differently from section 9's table.
- [ ] 6. Write the four seed journal entries (depends on 3) at the filenames in
      `design.md` section 7, copying every field, timestamp, PR, release and
      intervention from sections 7, 8 and 9 verbatim, with every timestamp
      quoted — DoD: all four load; `visibility: public` on all four;
      `deployed_at` set on the two platform entries and absent on the two
      portfolio entries; `interventions` lengths are 2, 2, 3, 4; no entry
      carries a `lead_time`, `lead_time_hours` or `manual_interventions` field;
      no value was re-derived rather than copied.
- [ ] 7. Write the project pair (depends on 3)
      `src/content/projects/mctl-api.en.md` and `mctl-api.ru.md` from
      `design.md` section 9 — DoD: both load; they share `slug`, `group`,
      `order`, `repo` and `stack` and differ only in `lang`, `name` language,
      `summary`, the `links[].label` and the body; no numeric metric appears in
      either frontmatter.
- [ ] 8. Add `src/pages/dev/[check].astro` (depends on 3) as the dynamic route
      whose `getStaticPaths` returns the single `collections` path only under
      `import.meta.env.DEV`, rendering the three `getCollection` counts — DoD:
      `/dev/collections/` lists three counts under `astro dev`; `astro build`
      emits no file for the route; the page ships no client-side script.
- [ ] 9. Update `package.json` scripts (depends on 1, 2): `"check": "astro sync
      && astro check"` and `"test": "node --test test/journal.test.ts
      test/adr.test.ts"` — DoD: `npm run check` and `npm test` both exit 0 on
      the clean tree and non-zero when a validation or test fails; no new
      dependency or devDependency is added.
- [ ] 10. Run `npm run check`, `npm test`, `npm run build` and `node
      scripts/csp-hash.mjs` (depends on 1-9) — DoD: all four succeed;
      `find dist -name '*.js' | wc -l` prints `0`; `csp-hash.mjs` still reports
      exactly one inline script within the 400-byte cap.
- [ ] 11. Regenerate `package-lock.json` **only** if a dependency actually
      changed, and then only with `npm install --package-lock-only` as
      `AGENTS.md` requires — DoD: ideally the lockfile is untouched by this
      cycle; if it changed, every `<pkg>-binding-<platform>` the dependencies
      declare is present, not only the linux/x64 one.
- [ ] 12. Write the pull request description (depends on 10) containing: the
      demonstration output for the three failure modes of acceptance criterion
      1 (see T5-T7), a statement that `z.strictObject` is zod 4.6.2's
      non-deprecated spelling of the issue's `.strict()` and enforces the same
      rejection, a statement that the five ADR headings carry both language
      spans so `claude-review.yml`'s EN/RU convention holds while the checker
      keys on the English token, the note that `deployed_at` is unset on the two
      portfolio entries because the site has never been deployed, and the note
      that `npm test` / `npm run check` are not yet a CI job because
      `.github/**` is human-owned under the bootstrap boundary — DoD: a reviewer
      can verify every acceptance criterion from the description plus the diff,
      without re-running anything.
- [ ] 13. Delete every temporary fixture added for T5-T7 (depends on 12) — DoD:
      `git status` is clean of fixtures; `npm run check && npm test && npm run
      build` pass on the final tree; `src/content/` holds exactly nine markdown
      files.

## Tests

- [ ] T1. `test/journal.test.ts` (`node --test`, no framework):
      `leadTimeHours` returns a `number` for a fully timestamped fixture and
      the expected value to within floating-point tolerance; returns `null`
      when `deployed_at` is absent, `null` or `''`; accepts `Date` and `string`
      inputs interchangeably; throws `RangeError` when `deployed_at` precedes
      `issue_opened_at` and on an unparseable timestamp.
- [ ] T2. `test/journal.test.ts`: `interventionCount` returns `0` for an absent
      `interventions`, `0` for `[]`, and `4` for a four-element array;
      `isoWithOffset` accepts `'2026-09-10T22:44:09Z'` and
      `'2026-09-10T22:44:09+02:00'` and rejects `'2026-09-10T22:44:09'`,
      `'2026-09-10'` and a `Date` instance.
- [ ] T3. `test/adr.test.ts`: `adrBodyProblems` returns `[]` for a well-formed
      bilingual body; reports the missing section when one of the five headings
      is dropped; reports the ordering problem when `Drivers` precedes
      `Consequences`; reports the missing language when a section has only an
      `.l.en` block; reports the mismatch when `id` disagrees with the filename
      prefix. `checkAdrBodies` throws once with every problem from two bad
      entries named in the message, and does not throw for good entries.
- [ ] T4. Manual: `npm run dev`, open `/dev/collections/`, confirm the three
      counts read `projects: 2`, `journal: 4`, `adr: 3` (acceptance criterion
      2); then `npm run build` and confirm no `dist/dev/` directory exists.
- [ ] T5. Fixture demonstration (acceptance criterion 1a): copy a seeded
      journal entry, delete its `issue_opened_at`, run `rm -rf .astro && npm
      run build`, capture the failure, delete the fixture.
- [ ] T6. Fixture demonstration (criterion 1b): copy a seeded journal entry,
      add `lead_time_hours: 12`, run `rm -rf .astro && npm run build`, capture
      the unknown-key failure, delete the fixture. Repeat once with the
      `.astro` cache warm to prove the check is not cache-skippable.
- [ ] T7. Fixture demonstration (criterion 1c): copy a seeded ADR as `0099-`,
      delete its `Revisit criteria` section, run `npm run build`, capture the
      failure naming file and section, delete the fixture. Repeat with the
      Russian block of one section removed to show the EN/RU half of the check.
- [ ] T8. Acceptance criterion 5: `npm run check && npm test && npm run build
      && [ "$(find dist -name '*.js' | wc -l)" -eq 0 ]` succeeds as one
      command on the final tree.
- [ ] T9. Cross-check the seeded data against the sources named in `design.md`
      section 7 — each `proposal_slug` exists under
      `platform-gitops/agents-state/<service>/proposals/`, each `pr` URL is the
      merged PR, each `release` is a published tag — and confirm
      `leadTimeHours` over the real seeds yields a number for the two platform
      entries and `null` for the two portfolio entries.

## Rollback

Nothing in this cycle is consumed by a rendered page, nothing touches the
Dockerfile, nginx config, CSP or vendored assets, and no dependency changes, so
rollback is purely source-level:

1. If the problem is found before merge: close the `feat/agents-*` PR. The
   repository is unaffected because every file in this cycle is new; there is no
   modified-file revert to untangle except the two `package.json` script lines.
2. If the problem is found after merge but before a release:
   `git revert -m 1 <merge commit>` on a branch, PR, merge. The revert removes
   `src/content/`, `src/content.config.ts`, `src/lib/`, `test/`,
   `src/pages/dev/` and restores `"check": "astro check"` with no `test`
   script. `npm run build` and the image build return to P2 behaviour exactly,
   because `dist/` never contained anything from this cycle.
3. If the problem is a single bad validation rather than the model (for example
   the ADR ordering check proving too strict), the narrow fix is to relax that
   one predicate in `src/lib/adr.ts` — the content and the schemas can stay.
4. If the problem is one wrong seeded timestamp, fix that one frontmatter value
   in a follow-up cycle and record the correction as an intervention only if a
   human made the edit outside the DevLoop; the ledger semantics are the point,
   so a silent in-place fix is the wrong rollback.
5. There is nothing to roll back on the platform: no deployment, no GitOps
   change, no Vault secret, no domain. `mctl_rollback_service` is not involved.
