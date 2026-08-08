# Tasks: issue-83-fix-content-re-audit-pr-64-evidence-and

- [ ] 1. Investigate the PR #64 merge-gate history — DoD: using `gh pr view 64`,
  `gh api repos/mctlhq/mctl-academy/commits/1ba8078596c2cbd90895a54160bf4d69a29fe75a/check-runs`,
  and `gh api repos/mctlhq/mctl-academy/branches/main/protection` (or the
  rulesets API) with a token that has repo-admin read access, determine
  whether "Content evidence / Verify citations" was configured as a required
  status check at merge time, and whether the merge used an admin/bypass
  path. Record the finding in the PR description under a short "Root cause"
  note, per the issue's "confirm from history rather than assuming intent."
  This sandbox's token returned `403 Resource not accessible by integration`
  on the protection endpoint, so this task needs different credentials than
  this investigation had.

- [ ] 2. Re-review all 18 PR #64 questions against the two CONTENT-POLICY
  criteria — DoD: a written pass/fail per file (does the cited evidence
  support the statement; is exactly one option best) for all 18 ids listed in
  the issue, independent of the existing `authored`/`reviewed` stamps. Confirm
  or supersede the issue's initial read (`q-op04a1b2c3d4`, `q-pf03d1e2f3a4`,
  `q-pf04e2f3a4b5` defensible as written; the other 15 not).

- [ ] 3. Repair or quarantine each of the 15 flagged items (depends on 2) —
  DoD: for each of `q-de04e5f6a7b8`, `q-de05f6a7b8c9`, `q-de06a7b8c9d0`,
  `q-de07b8c9d0e1`, `q-de08c9d0e1f2`, `q-de09d0e1f2a3`, `q-op03f4a5b6c7`,
  `q-pf05f3a4b5c6`, `q-pf06a4b5c6d7`, `q-pf07b5c6d7e8`, `q-pf08c6d7e8f9`,
  `q-pf09d8e9f0a1`, `q-pf10e9f0a1b2`, `q-pf11f0a1b2c3`, `q-pf12a1b2c3d4`:
  either (a) rewrite `stem`/`options`/`explanation`/`evidence` in place, same
  file and `id`, citing a genuine <=25-word verbatim excerpt from an already
  `SOURCES.md`-approved source (reuse one of `src-rate-limits`,
  `src-endpoint-lifecycle`, `src-org-projects`, `src-inference-overview`, or
  another existing `content/sources/*.yaml` entry) that actually supports the
  rewritten claim, with `authored.at`/`reviewed.at` updated to real
  timestamps; or (b) set `status: needs_review` with a short explanatory
  commit message when no approved source defensibly supports a claim worth
  keeping. No file is deleted either way.

- [ ] 4. Eliminate the three live verifier failures as part of task 3 — DoD:
  `q-de04e5f6a7b8`, `q-de06a7b8c9d0`, and `q-de09d0e1f2a3` no longer cite the
  `src-rate-limits` excerpt "Lifecycle is deployment state. Readiness is
  traffic-serving capability." for an unrelated claim; each is either
  repaired with a genuinely matching excerpt or quarantined.

- [ ] 5. Update `reviewed.at` for the 3 items confirmed defensible as written
  (depends on 2) — DoD: `q-op04a1b2c3d4`, `q-pf03d1e2f3a4`, `q-pf04e2f3a4b5`
  carry a `reviewed.at` timestamp reflecting the actual re-review pass rather
  than the original 2026-08-07T19:31:00Z bulk stamp; content otherwise
  unchanged since it already passes both criteria.

- [ ] 6. Run the full local gate (depends on 3, 4, 5) — DoD:
  `bun run lint:content`, `bun run verify:evidence` (against the real R2
  bucket, real credentials), and `bun run test:content` all exit 0 on the
  repaired tree.

- [ ] 7. Restore the merge-time hard gate (depends on 1) — DoD: `main`'s
  branch protection / repository ruleset lists "Content evidence / Verify
  citations" as a required status check, and the set of actors/roles who can
  merge a `content/**`-touching PR cannot bypass it (no admin override left
  enabled for that check on `main`). If the implementer's own token lacks
  admin scope to apply this, the DoD becomes: the exact desired ruleset state
  (check name, branch, no-bypass) is written out precisely enough in the PR
  description for a human admin to apply via Settings, and that is flagged
  explicitly as a follow-up action item, not silently left undone.

- [ ] 8. Content-PR CI ergonomics (depends on 6, 7 — do not start before main
  is green and the gate from 7 is in place) — DoD:
  `.github/workflows/content-evidence.yml`'s `evidence` job still triggers on
  every same-repo pull request (no workflow-level `on.pull_request.paths:`
  filter) and always posts a completed status; internally, the job skips only
  the R2 verification step (with a fast, explicit "no content-affecting
  changes in this PR" success) when the PR diff touches none of `content/**`,
  `content/schemas/**`, `scripts/verify-evidence.mjs`,
  `scripts/lib/snapshot-store.mjs`; the `push: branches: [main]` trigger is
  left untouched (always full verification, unconditionally).

- [ ] 9. Write the PR description — DoD: includes the root-cause note from
  task 1, the clean-room attestation checklist from
  `.github/pull_request_template.md` checked truthfully, an explicit note of
  the resulting `published` question count and, if it dropped below the
  Phase 1 target of 80, an explicit acknowledgment that correctness took
  priority per the issue, and a link/reference to any follow-up item still
  outstanding from task 7 if the ruleset change could not be applied directly.

## Tests

- [ ] T1. `bun run lint:content` passes on the full repaired content tree.
- [ ] T2. `bun run verify:evidence` passes against the real R2 bucket (the
  `content-evidence.yml` `evidence` job is green on the PR, same-repo run).
- [ ] T3. `bun run test:content` passes (all rule tests in
  `tests/content-lint.test.mjs` plus `tests/verify-evidence.test.mjs`,
  `tests/build-content-bundle.test.mjs`, `tests/build-preview.test.mjs`).
- [ ] T4. None of `content/questions/q-de04e5f6a7b8.yaml`,
  `q-de06a7b8c9d0.yaml`, `q-de09d0e1f2a3.yaml` cite the lifecycle/readiness
  excerpt against `src-rate-limits` anymore; each is either repaired to a
  genuinely matching excerpt or has `status != published`.
- [ ] T5. `node scripts/build-content-bundle.mjs` and
  `node scripts/build-mock-bundle.mjs`, run against the repaired tree,
  produce output containing no id from task 3's list whose `status` was set
  to `needs_review` (spot-check the generated bundle JSON).
- [ ] T6. After task 8 lands: a PR that changes only files outside
  `content/**`/`scripts/verify-evidence.mjs`/`scripts/lib/snapshot-store.mjs`
  shows "Content evidence / Verify citations" completing quickly with a
  passing status, not stuck "Expected"/pending.
- [ ] T7. After task 7 lands: confirmed by a human with repo-admin access
  (this sandbox's token cannot read/write branch protection — verified
  403 on `GET .../branches/main/protection`) that a draft PR introducing a
  `published`/`needs_review` item with a deliberately broken excerpt cannot be
  merged through the normal merge button/queue.

## Rollback

- Content repairs are plain YAML changes in git; `git revert` the content
  commit(s) restores the prior file bodies. Quarantining is a single-field
  `status` edit, trivially reversible the same way, and no file is deleted at
  any point in this proposal, so no content is ever unrecoverable.
- The CI ergonomics change (task 8) touches one file,
  `.github/workflows/content-evidence.yml`. If the internal path-conditional
  logic misbehaves (e.g. false-skips a content-affecting PR), revert to the
  unconditional-every-PR version — that direction fails safe (more
  verification runs, never fewer) and was the prior actual behavior.
- The branch-protection/ruleset change (task 7) can be reverted via the same
  GitHub Settings UI/API used to apply it. Because it is not expressible as a
  file in this repo, the PR description (task 9) records the exact before/
  after state so the change is reproducible and reversible even without
  gitops history for it.
