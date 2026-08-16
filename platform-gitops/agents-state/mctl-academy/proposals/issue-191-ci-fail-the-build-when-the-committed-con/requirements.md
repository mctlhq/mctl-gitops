# CI: fail the build when the committed content bundle diverges from generated output

## Context

`client/src/content-bundle.json` and `client/src/course-catalog.json` are
generated artefacts produced by `scripts/build-content-bundle.mjs` from
`content/`, but both files are also tracked in git (confirmed via `git
ls-files`). Today, safety against a stale or hand-edited bundle being served
to a learner is held entirely by regeneration: `client/package.json`'s
`predev`, `prebuild`, and `pretest` scripts all invoke
`node ../scripts/build-content-bundle.mjs` before the client runs, dev-serves,
or tests, so any committed drift is silently overwritten at those points and
never actually reaches a learner. That is a real defense, which is why this
is a hardening task and not a vulnerability fix.

What is missing is the *signal* for reviewers. Nothing in CI today proves
that the bytes committed in `client/src/content-bundle.json` and
`client/src/course-catalog.json` are what `content/` actually generates. A
bad merge, a stale regeneration before commit, or a hand edit can land a
divergent artefact, and CI stays green while the diff a human reviews in the
PR silently misrepresents the shipped content. The `content` job in
`.github/workflows/ci.yml` already runs `bun run lint:content` and
`bun run test:content` with no secrets and no network (this is deliberate:
see the job's own comment about running identically on fork PRs), so it is
the natural place to add a regenerate-and-diff check with the same
no-secrets, no-network property.

This closes the same gap the P1 raised against #190 pointed at, even though
that specific finding was refuted (the PR in question changed 80 raw files
under `content/`, `Verify citations` passed, and regenerating produced no
diff — see
https://github.com/mctlhq/mctl-academy/pull/190#issuecomment-5309540706). The
underlying hardening idea — CI should assert committed-equals-generated, not
just leave it to regeneration on the read paths — stands on its own.

## User stories

- AS a CODEOWNER reviewing a content or code PR, I WANT CI to fail if the
  committed `content-bundle.json` or `course-catalog.json` disagrees with
  what `content/` generates, SO THAT I can trust the diff I am reviewing
  actually represents what will ship.
- AS a contributor who forgot to regenerate the bundle after editing
  `content/`, I WANT CI to tell me precisely, SO THAT I can fix it before
  merge instead of relying on someone noticing in review.
- AS a maintainer, I WANT this check to run with no secrets and no network,
  SO THAT it also runs correctly on fork PRs, consistent with the rest of the
  `content` job.

## Acceptance criteria (EARS)

- WHEN the `content` job in `.github/workflows/ci.yml` runs, THE SYSTEM SHALL
  execute `node scripts/build-content-bundle.mjs` followed by
  `git diff --exit-code client/src/content-bundle.json
  client/src/course-catalog.json` as a step after the existing
  `Content lint` step (`bun run lint:content`).
- IF the regenerated `client/src/content-bundle.json` or
  `client/src/course-catalog.json` differs from the committed copy, THEN THE
  SYSTEM SHALL fail the `content` job with a non-zero exit code and a diff
  in the job log naming exactly which file(s) and lines drifted.
- WHILE the committed artefacts match what `content/` generates, THE SYSTEM
  SHALL keep the `content` job green with no behavior change to any other
  step.
- WHEN this new step runs, THE SYSTEM SHALL require no secrets and no network
  access, so it produces the same result on a fork-originated pull request as
  on a branch PR within the org.
- WHEN this check fails, THE SYSTEM SHALL NOT require any change to
  `scripts/build-content-bundle.mjs`, `scripts/lib/validate-generated-artifacts.mjs`,
  or any schema — the fix is always to regenerate and commit the artefacts,
  or to fix the `content/` source that produced the wrong output.

## Out of scope

- Removing `client/src/content-bundle.json` / `client/src/course-catalog.json`
  from version control. The issue explicitly rejects this: the client imports
  the bundle directly, and committing it is what makes shipped content
  reviewable in a PR diff, which is the property this issue protects.
- Any runtime (server or client) re-validation of bundle content. CLAUDE.md
  is explicit: "No runtime check exists, or should be added." This proposal
  is CI-only.
- Changing what `scripts/build-content-bundle.mjs` emits, or the shape
  contract enforced by `scripts/lib/validate-generated-artifacts.mjs`. Those
  already run inside the builder and are exercised by
  `tests/build-content-bundle.test.mjs` and
  `tests/validate-generated-artifacts.test.mjs`; this proposal only adds a
  CI-level "are the committed bytes current" check on top.
- Citation/evidence verification against the private R2 snapshot
  (`scripts/verify-evidence.mjs`). That is a separate, secret-requiring step
  that cannot run on fork PRs, as the issue itself notes, and is unaffected
  by this change.
- Auto-fixing or auto-committing regenerated artefacts in CI. On drift, CI
  fails and a human/agent regenerates and commits locally; this proposal does
  not add a bot-commit step.

## Open questions

None. The issue specifies the exact two commands to add
(`node scripts/build-content-bundle.mjs` then
`git diff --exit-code client/src/content-bundle.json
client/src/course-catalog.json`) and the exact placement (the `content` job,
after `lint:content`). The one implementation detail the issue leaves open —
whether to add this as a new named CI step or fold it into an existing
script/npm-run-script — is resolved in design.md in favor of a new named
step directly in `ci.yml`, matching the issue's proposed snippet and the
job's existing style of one named step per concern (`Content lint`,
`Content lint tests`, `Build course preview` are already separate steps
rather than one combined script).
