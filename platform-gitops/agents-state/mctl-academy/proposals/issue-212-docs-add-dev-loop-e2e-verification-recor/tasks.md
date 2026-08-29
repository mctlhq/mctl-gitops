# Tasks: issue-212-docs-add-dev-loop-e2e-verification-recor

- [ ] 1. Create `docs/` directory and write `docs/dev-loop-e2e.md` with:
      (a) a one-paragraph description of the dev-loop
      (issue -> spec proposal -> human approval -> PR) linking to
      `mctlhq/mctl-agents` ADR-006, and
      (b) a `## Verified runs` section with a Markdown table
      (`Date | Issue | Pipeline version`) containing exactly one row:
      `2026-08-29 | mctlhq/mctl-academy#212 (https://github.com/mctlhq/mctl-academy/issues/212) | mctl-agents 1.30.0`.
      — DoD: `docs/dev-loop-e2e.md` exists, renders as valid Markdown, and
      contains both the intro paragraph and the one-row table described
      above; no other file in the repository is modified, added, or deleted.

- [ ] 2. Confirm the ADR-006 link target (depends on 1) — DoD: either the
      exact `mctlhq/mctl-agents` ADR-006 path is confirmed and the link in
      `docs/dev-loop-e2e.md` is updated to point at it precisely, or (if it
      cannot be confirmed in this change) the PR description explicitly
      flags the link as best-effort/unconfirmed for human-reviewer
      follow-up, consistent with the open question recorded in
      requirements.md.

- [ ] 3. Open PR from a correctly-named branch (depends on 1, 2) — DoD:
      branch name starts with `docs/` (not `_`), commit subject uses the
      `docs:` conventional-commit prefix and is under 72 characters, PR
      body explains why (E2E-verifying the dev-loop's atomic-approve stage),
      and the "Content attestation" section of
      `.github/pull_request_template.md` is deleted per its own instruction
      (this PR does not touch `content/`).

## Tests

- [ ] T1. Manual/visual check: render `docs/dev-loop-e2e.md` (e.g. via
      GitHub's Markdown preview or a local Markdown viewer) and confirm the
      table has exactly one row with the three specified columns and the
      intro paragraph's ADR-006 link is a valid, clickable URL.
- [ ] T2. Diff check: `git diff --stat` against the base branch shows
      exactly one file added (`docs/dev-loop-e2e.md`) and zero files
      modified or deleted — enforcing the "no other files should change"
      requirement.
- [ ] T3. Confirm existing gates are unaffected: `npm run lint:content` and
      `npm run test:content` (per `CLAUDE.md`) still pass unchanged, since
      no `content/` file is touched. No new automated test is needed for a
      plain Markdown record with no build-time consumer.

## Rollback

Revert the single commit that adds `docs/dev-loop-e2e.md` (`git revert
<sha>`) or delete the file and merge that removal through the normal PR
flow. Because the file is inert documentation — not referenced by any
build, lint, schema, or runtime code path — removal has no downstream
effect on `client/`, `server/`, `content/`, or any deployed service, and
no data migration or redeploy is required.
