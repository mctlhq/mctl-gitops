# Tasks: issue-21-feat-content-generate-20-published-quest

- [ ] 1. Research canonical `docs.tokenfactory.nebius.com` pages for the 5
      source-less `domain-2` objectives (`chat-completions`,
      `embeddings-and-rerank`, `retrieval-pipelines`, `framework-integrations`,
      `agent-sandboxes`) — DoD: one candidate `.md` URL per objective,
      confirmed on the `SOURCES.md` allowlist host list, noted alongside the
      objective it will back.

- [ ] 2. Capture the 5 new sources with `node scripts/capture-source.mjs
      <url> --id src-<slug> --objective domain-2/<objective>` (depends on 1)
      — DoD: 5 new `content/sources/src-*.yaml` files exist, each validates
      against `content/schemas/source.schema.json`, each `objectives` entry
      resolves in `content/branding.yaml`, and (when R2 credentials are
      available in the executing environment) each carries a `snapshot`
      block with `key === sha256`. If credentials are unavailable, write the
      record without `snapshot` and note the gap in the PR description —
      dependent questions then stay `draft`/`needs_review` per
      `checkEvidence()`, not `published`.

- [ ] 3. Draft 15 new questions across the 5 newly-sourced objectives, 3
      each (depends on 2) — DoD: files under `content/questions/q-*.yaml`,
      ids matching `^q-[a-z0-9]{12}$` with an unused mnemonic prefix per
      objective (`cc`, `er`, `rp`, `fi`, `as`), `domain: domain-2`,
      `objective` matching the source's objective, `authored.by:
      agent:<name>`, `status: draft`, 4 unique-text options with exactly one
      `correct: true` and every option carrying a ≥12-character
      `explanation`, and one `evidence` entry per question with a
      ≤25-word excerpt copied verbatim from the fetched source text.

- [ ] 4. Draft 5 more questions on the already-sourced objectives — 3 on
      `function-calling` (citing `src-function-calling`), 2 on
      `structured-output` (citing `src-structured-output`) — DoD: same shape
      requirements as Task 3, ids continuing the existing `fc0*`/`so0*`
      sequences (`q-fc05...`, `q-fc06...`, `q-fc07...`, `q-so04...`,
      `q-so05...`).

- [ ] 5. Vary correct-answer placement across all 20 new items so the
      bank-wide check in `scripts/validate-content.mjs` (fires at ≥12
      questions, threshold 50% share for any one position) stays clear once
      merged into the existing 20-question bank — DoD: manual tally of `a`/
      `b`/`c`/`d` correct-option counts across old + new questions shows no
      position above 50%.

- [ ] 6. Run `npm run lint:content` and `npm run test:content` locally over
      the full working tree (depends on 3, 4, 5) — DoD: lint exits 0 with
      "Content lint passed: N sources, 40 questions, 0 lessons"-style output
      and no errors; the 15 existing rule-violation tests in
      `tests/content-lint.test.mjs` still pass unmodified.

- [ ] 7. Split the 20 questions into 2 PRs of 10 each on non-`main`,
      non-underscore-prefixed branches (depends on 6) — DoD: each PR body
      uses `.github/pull_request_template.md`'s content-attestation section
      with all checkboxes genuinely satisfied (including "at most 10
      questions"), targets `mctlhq/mctl-academy` directly (not a fork), and
      is conventional-commit-titled under 72 characters (e.g. `feat(content):
      add domain-2 questions for chat-completions and embeddings-and-rerank`).

- [ ] 8. Confirm `content-evidence.yml` runs green on both PRs (depends on 7)
      — DoD: `Verify citations` job passes for same-repo PRs, confirming
      every new excerpt occurs verbatim in its source's R2 snapshot; a red
      run means fixing the excerpt or the snapshot, not lowering `status`
      past what `checkEvidence()` already allows.

- [ ] 9. Human `CODEOWNERS` review and merge (depends on 8) — DoD: the
      `@mashkovd` reviewer applies the two-criterion checklist (evidence
      supports the statement; exactly one option is best) per
      `CONTENT-POLICY.md`, adds a `reviewed: {by, at}` block to each approved
      question, flips `status: draft` -> `published` for approved items, and
      merges each PR with a merge commit (never squash).

- [ ] 10. Post-merge verification (depends on 9) — DoD: `npm run
      lint:content` on `main` reports 27 `domain-2` questions total, all 7
      `domain-2` objectives represented by at least one `published` question,
      and zero errors.

## Tests

- [ ] T1. `npm run lint:content` passes with zero errors on the full content
      tree after all 20 files are added (schema + cross-file + lifecycle +
      answer-position checks all green).
- [ ] T2. `npm run test:content` — all 15 existing rule-violation tests in
      `tests/content-lint.test.mjs` still fail closed exactly as before; no
      test is modified to accommodate the new content.
- [ ] T3. `npm run verify:evidence` (or the `content-evidence.yml` CI run)
      confirms every new question's excerpt occurs verbatim in its cited
      source's snapshot, for every question whose source has a `snapshot`
      block.
- [ ] T4. Manual cross-check: every objective id under `domains[1].objectives`
      in `content/branding.yaml` (the `domain-2` entry) has at least one
      `content/questions/*.yaml` file with matching `objective` and
      `status: published` after merge.
- [ ] T5. Manual cross-check: no two options within any single new question
      have equal (trimmed, case-insensitive) text — the lint catches this,
      but confirm on the drafts before opening the PR to avoid a review
      round-trip.

## Rollback

Content-only, additive, no schema or application changes — rollback is a
plain git revert:

- If a lint or evidence-CI failure surfaces after merge (should not happen,
  since both gates are enforced pre-merge), revert the offending PR's merge
  commit on `main`. Since PRs are merged with a merge commit (never squashed),
  each batch reverts cleanly as a unit without touching the other batch.
- If a published question is later found to have a citation that does not
  hold up (e.g. the maintainer's own audit, or a learner report per
  `CONTRIBUTING.md`'s "question reports" path), the existing lifecycle
  already covers it: flip `status` to `needs_review` or `retired` in a normal
  follow-up PR. Per `content/schemas/question.schema.json` and `PLAN.md`
  section 4, retiring or editing a question never mutates an attempt already
  taken — moot today since the application does not exist yet, but the
  content model already assumes it.
- If Track A's new source snapshots turn out to be wrong (wrong page, or a
  page that drifts immediately), delete the source record and any question
  that cites it in one PR — the lint's `checkEvidence()` will fail loudly if
  a question is left citing a now-missing `source_id`, so an incomplete
  rollback cannot pass CI silently.
