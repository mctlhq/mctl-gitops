# Tasks: issue-19-feat-ui-implement-practice-mode-screen-w

- [ ] 1. Scaffold `client/` workspace: `package.json` (react, react-dom,
      vite, @vitejs/plugin-react, typescript, vitest, @testing-library/react,
      @testing-library/jest-dom, jsdom), `vite.config.ts`, `tsconfig.json`,
      `client/index.html`, `client/src/main.tsx`, empty `client/src/App.tsx`
      — DoD: `npm ci && npm run build` inside `client/` produces
      `client/dist/index.html` with no errors; `npm run dev` serves a blank
      page locally.
- [ ] 2. Write `scripts/build-content-bundle.mjs` (depends on 1 only for
      output location, not logic — can be built first): load
      `content/branding.yaml` and `content/questions/*.yaml` the same way
      `scripts/build-preview.mjs` does, filter to `status: published`,
      write `client/src/content-bundle.json` with `{ id, domain, objective,
      stem, options: [{ id, text, correct, explanation }] }[]` — DoD:
      running the script against the repo's current `content/` produces a
      JSON file containing only `published` questions (cross-check count
      against `grep -l 'status: published' content/questions/*.yaml | wc -l`).
- [ ] 3. Wire `scripts/build-content-bundle.mjs` as a `prebuild`/`pretest`
      step in `client/package.json` (depends on 1, 2) — DoD: deleting
      `client/src/content-bundle.json` and running `npm run build` or
      `npm test` in `client/` regenerates it automatically.
- [ ] 4. Implement `client/src/practice/usePracticeSession.ts`: load the
      bundle, Fisher-Yates shuffle question order and each question's
      option order once per session, expose current question, index/total,
      per-question `revealed` set, running score, and `selectOption`/`next`
      (depends on 3) — DoD: unit tests in task T-hook pass.
- [ ] 5. Implement `client/src/practice/renderInlineMarkdown.ts`: port
      `build-preview.mjs`'s `esc()`/`md()` pair (escape all HTML-significant
      characters, then convert backtick spans to `<code>`, nothing else)
      (depends on 1) — DoD: unit test asserts parity with `build-preview.mjs`
      on a shared set of sample strings (script paraphrases the existing
      `esc`/`md` regexes; test fixtures live in both test suites).
- [ ] 6. Implement `client/src/practice/PracticeScreen.tsx`: renders the
      current question's stem via `renderInlineMarkdown`, four option
      buttons in shuffled order, reveals correctness + explanation for a
      clicked option only, shows a summary screen at `index === total`, and
      an empty state when the bundle has zero published questions (depends
      on 4, 5) — DoD: component tests below pass; manual `npm run dev`
      smoke shows a question, click reveals feedback, other options remain
      clickable and independently revealable.
- [ ] 7. Wire `PracticeScreen` into `client/src/App.tsx` /
      `client/src/main.tsx` as the app's root view (depends on 6) — DoD:
      `npm run build` output, served locally (e.g. `npx serve client/dist`),
      shows the Practice screen at `/`.
- [ ] 8. Add a `client` job to `.github/workflows/ci.yml`: checkout,
      `actions/setup-node` (Node 22, cache npm, working-directory `client`),
      `npm ci`, `npm run build`, `npm test` — parallel to, not blocking,
      the existing `content` job (depends on 1-7 existing so the job has
      something to run) — DoD: CI run on the PR shows both `content` and
      `client` jobs passing independently.
- [ ] 9. Update `README.md` (or add `client/README.md` if the root README
      is reserved for project-level content) with a short "Practice mode
      (client)" section: what it is, how to run it locally, and an explicit
      note that it has no backend/auth/persistence yet, linking to
      `PLAN.md` section 7 for the eventual full application (depends on 7)
      — DoD: doc reviewed alongside the PR, states the scope boundary from
      requirements.md's "Out of scope" section.

## Tests

- [ ] T1. `build-content-bundle.mjs` unit test: given a fixture directory
      with one `published`, one `draft`, one `needs_review`, and one
      `retired` question, the emitted bundle contains only the `published`
      one.
- [ ] T2. `usePracticeSession` unit test: with a fixed/mocked random source,
      shuffling produces a permutation of the same option set (all four
      original `id`s present, order changed for a bank large enough to make
      an unchanged order improbable) and does not mutate the loaded bundle.
- [ ] T3. `usePracticeSession` unit test: `selectOption` on a given option
      id adds only that id to `revealed` for the current question; other
      option ids remain unrevealed until independently selected.
- [ ] T4. `renderInlineMarkdown` unit test: parity with `build-preview.mjs`'s
      `esc`/`md` on shared fixtures, including an HTML-injection attempt
      (`<script>`, `"`, `&`) rendered inert, and a backtick span rendered as
      `<code>`.
- [ ] T5. `PracticeScreen` component test (React Testing Library): clicking
      an incorrect option shows that option's explanation and an
      "incorrect" indicator, does not reveal the correct option's state,
      and clicking the correct option afterward reveals it independently.
- [ ] T6. `PracticeScreen` component test: reaching the last question and
      clicking through to the summary shows a score reflecting the number
      of questions whose first-clicked option was correct.
- [ ] T7. `PracticeScreen` component test: an empty bundle (`[]`) renders
      the empty state, not a crash or a blank screen.
- [ ] T8. Build smoke test (can be the CI `client` job itself, not
      necessarily a unit test): `npm run build` in `client/` exits 0 and
      produces `client/dist/index.html`.

## Rollback

Everything in this proposal is additive and isolated to a new `client/`
directory, a new `scripts/build-content-bundle.mjs`, and a new job block in
`.github/workflows/ci.yml`; nothing existing is modified in place except that
one CI file. No database, no deployed service, and no `content/` data is
touched or migrated.

If this needs to be undone: revert the merge commit for this PR
(`git revert -m 1 <merge-sha>`, non-squash merge per `CLAUDE.md`
conventions). That removes `client/`, `scripts/build-content-bundle.mjs`,
and the `client` CI job in one step, leaving the `content` job and
`build:preview` untouched exactly as they are today. There is no live
deployment to roll back (`mctl-academy` is not yet onboarded per `PLAN.md`
section 8), so rollback is a pure Git operation with no MCP/gitops or
runtime side effects to reverse.
