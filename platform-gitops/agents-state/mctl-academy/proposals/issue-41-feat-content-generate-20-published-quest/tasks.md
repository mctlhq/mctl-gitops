# Tasks: issue-41-feat-content-generate-20-published-quest

- [ ] 1. Confirm source coverage for `domain-3` objectives lacking a
      `content/sources/` record (`files-api`, `datasets`,
      `fine-tuning-jobs`, `lora-adapters`, `data-lab`): for each, find a
      canonical page under `docs.tokenfactory.nebius.com` via its `llms.txt`
      index (`SOURCES.md`). — DoD: a candidate URL is chosen per objective
      and recorded (e.g. in the PR description), and each URL's host is on
      the `SOURCES.md` allowlist.

- [ ] 2. Capture snapshots for the URLs from task 1, one per objective, via
      `npm run snapshot:capture -- <url> --id src-<slug> --objective domain-3/<objective>`
      (depends on 1; requires `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` /
      `R2_SECRET_ACCESS_KEY` — see requirements.md Open questions). — DoD:
      a new `content/sources/src-<slug>.yaml` exists per successfully
      captured objective, each with `status: current` and a `snapshot`
      block whose `key` equals its `sha256`. Objectives where capture could
      not run (no credentials available) are recorded as blocked, not
      silently skipped.

- [ ] 3. Author needs_review-eligible questions for `domain-3/dataset-formats`
      and `domain-3/supervised-fine-tuning` (already-snapshotted sources; no
      dependency on tasks 1-2) — DoD: at least 5 new
      `content/questions/q-*.yaml` files total across these two objectives
      (e.g. 3 + 2), each with `status: needs_review`, `domain: domain-3`,
      correct `objective`, 4 options with 4 distinct explanations, exactly
      one `correct: true`, `authored.by` matching `^agent:[a-z0-9][a-z0-9-]*$`,
      no `reviewed` block, and an `evidence` excerpt (<=25 words) that is
      verbatim in the source's live `.md` text.

- [ ] 4. Author questions for the 5 objectives from task 1 (depends on 2) —
      DoD: 15 new `content/questions/q-*.yaml` files (e.g. 3 per objective)
      covering `files-api`, `datasets`, `fine-tuning-jobs`, `lora-adapters`,
      `data-lab`. Each item's `status` is `needs_review` if task 2 captured
      that objective's source, `draft` otherwise. Same per-item shape rules
      as task 3.

- [ ] 5. Verify no duplicate `id` collides with any existing
      `content/questions/*.yaml` id, and no two options within any one
      question share `text` (case/whitespace-insensitive) — DoD: manual or
      scripted uniqueness check across the union of existing + new files
      passes clean.

- [ ] 6. Check whole-bank answer-position balance across the union of
      existing + new `domain-3` (and, if `npm run lint:content` is run
      repo-wide, all) questions before opening PRs (depends on 3, 4) — DoD:
      no single option position (`a`/`b`/`c`/`d`) holds the correct answer
      in more than 50% of all questions bank-wide, matching the check in
      `scripts/validate-content.mjs`.

- [ ] 7. Run `npm ci && npm run lint:content && npm run test:content` against
      the working tree with all new files added (depends on 3, 4, 5, 6) —
      DoD: both commands exit 0 with no errors reported for any new file.

- [ ] 8. Split the 20 new question files into >=2 PRs of <=10 questions each,
      each on its own `feat/`-prefixed branch (not starting with `_`),
      never committed to `main`, merged with a merge commit — never squash
      (depends on 7) — DoD: every PR is open, contains <=10
      `content/questions/*.yaml` files (plus any `content/sources/*.yaml`
      files it depends on), and no PR touches `content/schemas/`,
      `scripts/`, or `.github/workflows/`.

- [ ] 9. Fill in `.github/pull_request_template.md` on each PR, with the
      content-attestation checklist fully and truthfully checked (depends
      on 8) — DoD: every checkbox in the "Content attestation" and "Checks"
      sections is checked, and the PR body states which `domain-3`
      objectives it covers.

- [ ] 10. Request review from the `content/**` `CODEOWNERS` owner on each PR
       and confirm `content-evidence.yml` runs (same-repo branch, so it is
       not skipped) — DoD: each PR shows a completed (pass or documented
       expected-fail-on-draft) `content-evidence` check run and an assigned
       reviewer.

## Tests

- [ ] T1. `npm run lint:content` passes with all 20 new question files (and
      any new source files) present, with zero errors.
- [ ] T2. `npm run test:content` (the 15 rule-violation fixtures in
      `tests/content-lint.test.mjs`) still passes unmodified — this proposal
      adds content, not lint rules, so the existing suite must be
      unaffected.
- [ ] T3. For every new question at `status: needs_review`, its cited
      source's `content/sources/*.yaml` record has a non-null `snapshot`
      block — a static check standing in for `npm run verify:evidence`,
      which needs live R2 credentials this proposal's own verification does
      not assume are available.
- [ ] T4. For every new question at `status: draft`, confirm it stays out of
      `content/branding.yaml`'s existing objective set boundary violations —
      i.e. `objective` starts with `domain-3/` and is one of the 7 objective
      ids already defined there (no accidental new objective introduced).
- [ ] T5. Grep the 20 new files (stem, option text, explanations) for the
      literal strings "Nebius Agentic AI Builder" and "Tool Use, Memory &
      Context Management" — DoD: zero matches, per `LEGAL.md` naming rules
      and requirements.md's acceptance criterion against importing the
      issue's mismatched domain label into content.

## Rollback

Every change in this proposal is additive (new `content/questions/*.yaml`
and, if task 2 ran, new `content/sources/*.yaml`) — nothing existing is
edited, so there is no migration to reverse. If a PR merges content that
later turns out wrong (excerpt doesn't hold up, objective mapping is
disputed, or the domain-label open question resolves differently than
assumed):

- Before human review: close the PR, or push a follow-up commit removing the
  affected `content/questions/*.yaml` files from the branch.
- After merge but before `published`: an item sitting at `draft` or
  `needs_review` is not selectable by learners (only `published` items are
  drawn into Practice/Mock, per `content/schemas/question.schema.json`'s
  `status` description) — deleting the file in a follow-up PR is sufficient,
  no data to unwind.
- After a human has flipped an item to `published`: per PLAN.md's
  attempt-immutability model, any attempt already taken references a
  snapshotted `content_version`, not the live file, so retiring the question
  (`status: retired`) is the correct rollback, not deletion — deletion would
  break the reference. This case only arises after Stage D (human review),
  which is out of scope of this proposal's automated part.
- If a captured `content/sources/*.yaml` snapshot turns out to be wrong
  (bad URL, wrong objective mapping): delete the source file and every
  question that cites it in the same follow-up PR, since a question with a
  dangling `source_id` fails `checkEvidence` immediately.
