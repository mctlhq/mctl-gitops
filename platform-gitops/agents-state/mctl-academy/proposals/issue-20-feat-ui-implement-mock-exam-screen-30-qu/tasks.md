# Tasks: issue-20-feat-ui-implement-mock-exam-screen-30-qu

- [ ] 1. Scaffold `client/` (Vite + React + TypeScript): `client/package.json`,
      `client/vite.config.ts`, `client/tsconfig.json`, `client/src/main.tsx`,
      base `index.html`. — DoD: `cd client && npm ci && npm run dev` serves an
      empty app locally; `npm run build` produces `client/dist/`; root
      `npm run lint:content` / `npm run test:content` still pass unchanged.

- [ ] 2. Build-time content bundle generator: a script (e.g.
      `client/scripts/build-content-bundle.mjs`) that reads
      `content/branding.yaml` and `content/questions/*.yaml` with the `yaml`
      package (same read pattern as `scripts/build-preview.mjs`), filters to
      `status === "published"`, and emits
      `client/src/data/mock-bundle.generated.json` containing the branding
      mock config (domains, weights, `mock_questions`, `question_count`,
      `time_limit_minutes`, `disclose_bank_size`) plus the filtered question
      list. Wire it as a `prebuild`/`predev` step in `client/package.json`. —
      DoD: running the script against the current `content/` produces valid
      JSON; a unit test asserts non-`published` questions are excluded and
      that `.generated.json` is gitignored (added to root `.gitignore`).

- [ ] 3. `ExamDataSource` interface + `StaticBundleDataSource` implementation
      (depends on 2) — DoD: typed interface with methods to fetch the mock
      config and question set; the static implementation reads the generated
      bundle; unit-testable without a DOM or network.

- [ ] 4. `selectMockQuestions(questions, brandingMockConfig)` (depends on 3) —
      DoD: unit tests cover (a) happy path returns exactly `mock_questions`
      count per domain, 30 total; (b) a domain short on published questions
      returns a typed shortfall result rather than throwing or silently
      under-filling; (c) selection is randomized across repeated calls (not
      deterministically the same 30 every time).

- [ ] 5. `shuffleOptions(question)` (depends on 3) — DoD: unit test asserts all
      4 options are present exactly once post-shuffle and that `correct`/
      `explanation` travel with their original option text.

- [ ] 6. `ExamSession` state machine + `sessionStorage` persistence (depends
      on 4, 5) — DoD: unit tests cover start → in-progress → submit
      transitions; answer recording and overwrite; auto-submit when
      `remainingMs <= 0`; reload mid-session restores answers and recomputes
      `remainingMs` from stored `expiresAt` rather than resetting the clock.

- [ ] 7. `MockStartScreen` component (depends on 3, 4) — DoD: renders question
      count, time limit, and current bank size from the data source; renders
      the "not enough content" state when `selectMockQuestions` reports a
      shortfall; a start action transitions into the exam.

- [ ] 8. `MockExamScreen` component (depends on 6) — DoD: renders the current
      question's stem and four shuffled options as single-select; renders a
      30-item navigator showing per-question answered/unanswered state and
      allows jumping to any question; renders a live countdown from
      `remainingMs`; a submit action prompts for confirmation if any question
      is unanswered, then transitions to submitted; auto-submits with no
      further input when the timer reaches zero.

- [ ] 9. `MockResultsScreen` component (depends on 6, 8) — DoD: renders overall
      score; renders, per question, the learner's selection, the correct
      option, and every option's explanation, using a restricted-Markdown
      renderer ported from `build-preview.mjs`'s `md()`/`esc()` approach
      (escape first, then allow only backtick code spans — no raw HTML).

- [ ] 10. Wire the three screens behind the state machine into a single mock
      flow entry point (depends on 7, 8, 9) — DoD: `npm run dev` in `client/`
      lets a person locally click through start → answer some/all of 30
      questions → submit (manually and via a shortened timer for manual
      testing) → see results, with no console errors.

- [ ] 11. CI: add a client build job to `.github/workflows/ci.yml` (depends on
      1) — DoD: new job runs `cd client && npm ci && npm run build`
      (including the bundle generator from task 2) on PR and push to `main`,
      independent of and non-blocking to the existing `content` job; a
      broken client build fails CI.

- [ ] 12. Root `README.md` update: add a short "Local development — client"
      section under the existing `## Contributing` area noting
      `cd client && npm ci && npm run dev`, replacing `CONTRIBUTING.md`'s "The
      application does not exist yet" placeholder note for this narrow slice
      (depends on 1) — DoD: instructions are accurate against what task 1
      actually produces.

## Tests

- [ ] T1. `selectMockQuestions` returns exactly 6/10/6/8 per domain (30 total)
      when each domain has sufficient published questions.
- [ ] T2. `selectMockQuestions` returns a shortfall result (not a throw, not a
      silently short mock) when a domain lacks enough published questions —
      exercised directly against the real current bank (20 questions) to
      prove the degraded state actually triggers today.
- [ ] T3. `shuffleOptions` preserves all 4 options with their original
      `correct`/`explanation` values, only reordering.
- [ ] T4. `ExamSession` auto-submits when `remainingMs` reaches 0 without
      requiring learner action.
- [ ] T5. `ExamSession` reload mid-exam restores prior answers and computes
      `remainingMs` from the persisted `expiresAt`, not from a reset clock.
- [ ] T6. `MockExamScreen` never renders `correct` or `explanation` for any
      question while the session is `in_progress`.
- [ ] T7. `MockResultsScreen` renders `correct` and `explanation` for every
      question once the session is `submitted`.
- [ ] T8. `MockStartScreen` displays the live bank size and does not render
      any claim that a repeat mock is guaranteed fresh questions.
- [ ] T9. Restricted-Markdown renderer escapes raw HTML in a question stem/
      option/explanation and only expands backtick code spans (regression
      guard mirroring `build-preview.mjs`'s `md()` behavior).
- [ ] T10. CI: the new client-build job fails when `client/` fails to build
      (verified by temporarily breaking the build in a throwaway commit during
      implementation, not part of the merged PR).

## Rollback

All changes are additive and isolated to a new `client/` directory, a new CI
job, and a short README addition — no existing file under `content/`,
`scripts/`, `tests/`, or the root `Dockerfile`/`package.json` is modified, and
nothing is deployed (the Dockerfile and `mctl_deploy_service` are untouched).
Rollback is reverting the merge commit (per `CLAUDE.md`, merges are never
squashed, so this is a clean single-commit revert): `git revert -m 1 <merge
commit>` on a new branch, PR, merge — same conventions as the original change.
No data migration, no deployed service, no Vault secret, and no running
workload is affected either way, so rollback carries no operational risk.
