# Tasks: issue-42-feat-content-generate-20-published-quest

- [ ] 1. Identify one allowlisted documentation URL per uncovered domain-4
      objective (`dedicated-endpoints`, `capacity-and-scaling`,
      `observability`, `billing-and-consumption`, `team-access`) under
      `docs.tokenfactory.nebius.com` (preferred) or `docs.nebius.com`
      (infrastructure-only fallback) — DoD: a list of 5 URLs, one per
      objective, each host-checked against `ALLOWED_HOSTS` in
      `scripts/validate-content.mjs`.
- [ ] 2. Capture a source record + R2 snapshot for each URL from task 1 via
      `npm run snapshot:capture -- <url> --id src-<slug> --objective
      domain-4/<objective>` (depends on 1) — DoD: 5 new
      `content/sources/src-*.yaml` files exist, each with `snapshot.key`
      equal to its own `sha256` and `status: current`, matching the shape of
      `src-endpoint-lifecycle.yaml`. Fallback if `R2_*` credentials are
      unavailable to the executing agent: skip this task, note it as blocked
      in the PR description, and proceed with tasks 3-5 scoped to only the
      two already-sourced objectives (`endpoint-lifecycle`, `rate-limits`);
      file a follow-up for a maintainer to run capture with Vault-provisioned
      credentials.
- [ ] 3. Draft 20 question YAML files under `content/questions/`, `status:
      draft`, `authored.by: agent:academy-content`, distributed across all
      seven domain-4 objectives (~3 per objective; adjust once task 2's
      actual objective count is known), each citing a source from task 2 or
      the two pre-existing domain-4 sources (depends on 2) — DoD: 20 new
      files, each with a unique `q-<prefix><nn><12-hex>` id not colliding
      with any existing file, 4 options with exactly one `correct: true`, an
      `explanation` on every option, at least one `evidence` entry with a
      ≤25-word verbatim excerpt from its cited source, and no two options on
      the same item sharing text.
- [ ] 4. Run `npm run lint:content` and `npm run test:content` locally and
      fix every reported error, including the bank-wide answer-position
      check once total questions reach 12+ (depends on 3) — DoD: both
      commands exit 0 with the new files included.
- [ ] 5. Run `npm run verify:evidence` locally if `R2_*` credentials are
      available (same check CI runs in `content-evidence.yml`), otherwise
      rely on CI to run it on the opened PR (depends on 3, 2) — DoD: every
      new item's excerpt verified verbatim against its source's snapshot, or
      confirmed green on the PR's CI run.
- [ ] 6. Split the 20 drafted items into at least two PRs of ≤10 questions
      each, branch names `feat/domain-4-questions-1`,
      `feat/domain-4-questions-2` (no leading underscore), each PR
      completing the content attestation checklist in
      `.github/pull_request_template.md` and noting in the description which
      objectives it covers and (if task 2 was skipped) which objectives are
      still unsourced (depends on 4, 5) — DoD: PRs opened against `main`,
      each ≤10 questions, each CI green (`ci.yml` content job +
      `content-evidence.yml`), each requesting `@mashkovd` review per
      `CODEOWNERS`.
- [ ] 7. Wait for human review — CODEOWNER approves against the two-criterion
      checklist in `CONTENT-POLICY.md`, adds `reviewed: {by, at}` to each
      approved item, flips `status` to `published`, merges with a merge
      commit (depends on 6) — DoD: out of automated scope; recorded here so
      the proposal's boundary is explicit. This task is not something the
      implementer can close itself.

## Tests

- [ ] T1. `npm run lint:content` passes with all 20 new items plus any new
      source records included in the working tree.
- [ ] T2. `npm run test:content` (the 15 existing lint-rule tests) still
      passes unmodified — this batch must not need lint changes.
- [ ] T3. For each new item, manually confirm its evidence excerpt appears
      verbatim (exact substring, case-sensitive) in the fetched source text
      before capture, as a pre-check ahead of `verify-evidence.mjs` /
      `content-evidence.yml`.
- [ ] T4. Confirm no `q-*` or `src-*` id collides with any file already in
      `content/questions/` or `content/sources/` on `main` at PR-open time.
- [ ] T5. Confirm each new item's `objective` starts with `domain-4/` and
      exists in `content/branding.yaml`'s objective map (what
      `checkObjective` in `scripts/validate-content.mjs` enforces).
- [ ] T6. Confirm bank-wide correct-answer position share stays at or below
      50% for every position after the new items are added (what the
      answer-position-bias block in `scripts/validate-content.mjs` enforces
      once the bank has 12+ questions).
- [ ] T7. Confirm every new item has `authored.by` matching `^agent:[a-z0-9]
      [a-z0-9-]*$` and no `reviewed` block (drafts must not pre-empt human
      review).

## Rollback

All changes are additive YAML files under `content/questions/` and
`content/sources/`; nothing existing is modified.

- Before merge: closing the PR(s) discards the branch; nothing lands on
  `main`. No cleanup needed.
- After merge but before any item is flipped to `published`: revert the
  merge commit(s) (`git revert -m 1 <merge-sha>`) on a new branch, PR, and
  merge per the normal branch/PR/merge-commit workflow — `draft` items carry
  no learner-facing effect (`selectMockQuestions.ts` / practice selection
  only draws from `published`), so this is low-risk and reversible at any
  time.
- After an item is reviewed and published: per `SOURCES.md`'s drift model,
  do not delete or rewrite it — set `status: retired` instead ("Retiring
  never alters an attempt already taken"). A hard revert of a published,
  already-served item is explicitly against the project's own lifecycle
  design.
- If a captured source (task 2) turns out to be wrong or low-quality after
  review: retire the questions citing it (`status: retired`) rather than
  deleting the source record, since other future items may still cite it
  correctly; open a follow-up to fix or replace the source.
