# Tasks: issue-398-ci-review-use-antigravity-as-independent

Precondition: independent review of this proposal AND explicit owner `GO_IMPLEMENT` decision. Do NOT modify shared workflows, rulesets, GitHub App permissions/installations, or `mctlhq/mctl-gitops#3023` before approval.

## Phase 1 — Shared implementation in `mctlhq/.github` (shadow/off by default)

- [ ] 1. Fix `#287` and add explicit outcome classification to `.github/workflows/claude-review.yml`:
  - In `Classify reviewer outcome`, exit `1` (`::error::`) on `shape == "limit"` after posting the transient comment.
  - In `Check primary review actually succeeded` and `Check final review outcome`, fail closed when execution output JSON is absent, malformed, or lacks a `result` entry.
  - Add `Verify terminal verdict posted` step confirming an unedited `claude[bot]` `APPROVED`/`CHANGES_REQUESTED` review on `(HEAD_SHA, BASE_SHA)` carrying `Reviewed head=$HEAD_SHA base=$BASE_SHA` via REST + GraphQL.
  - Emit deterministic outcome steps (`Classify outcome: PASS | BLOCKING_FINDINGS | NO_VERDICT_TRANSIENT | NO_VERDICT_OTHER | STALE | SELF_EDIT`) and `workflow_call` outputs `review_outcome`, `reviewed_head`, `reviewed_base` while keeping `#384` `self_edit=true` non-failing on `claude-review / review`.
  — DoD: `.github/tests/test_claude_review_classify.py` and new `#287`/verdict-verify tests pass with mutation checks proving every fail-closed guard red when reverted.

- [ ] 2. Extend `.github/workflows/agy-review.yml` formal record with `provider` and canonical `pr_diff_digest_v1` (depends on 1):
  - In `Prepare review prompt` (`formal_review == true`), compute `mb=$(git merge-base "$BASE_SHA" "$HEAD_SHA")` and `diff_digest` in `#299` `pr_diff_digest_v1` canonical format over `git diff-tree -r --no-renames --full-index -z "$mb" "$HEAD_SHA"` (handling empty/binary/truncated checks as before).
  - Include `provider: "agy"` and `diff_digest` in `formal_record` (`schema_version: "agy-review/v2"`).
  — DoD: `PromptGateTests` and `ExportTests` in `.github/tests/test_agy_formal_reviews.py` pass locally and verify missing/mismatched `diff_digest` or `provider` fails export.

- [ ] 3. Extend `.github/scripts/agy_review_publish.py`, `.github/workflows/agy-formal-review.yml`, and `.github/workflows/agy-formal-dispatch.yml` (depends on 2):
  - Parameterize allowlisted `CHECK_NAME` (`independent-review` | `agy-formal-review`) and `GATE_MODE` (`enforce` | `shadow`, defaulting `agy-formal-dispatch.yml` compatibility cleanly).
  - Verify `provider == 'agy'`, `diff_digest` match via live compare `merge_base` + isolated blobless tree-only `git diff-tree` `pr_diff_digest_v1` check, `pr['user']['login'] != self.login` (author != reviewer), and **zero unedited `claude[bot]` `CHANGES_REQUESTED` reviews on `head_sha`** (before and after posting `APPROVE`). Under `strict: false`, accept live `base_sha` advances when `head_sha`, `base_ref`, and `pr_diff_digest_v1` remain identical.
  - In `shadow` mode, require `dismiss_stale_reviews_on_push` + (`strict` or `merge_queue`) without requiring `CHECK_NAME` in `required_status_checks`, and post only non-blocking `independent-review-shadow` check status (never `APPROVE`/`REQUEST_CHANGES` reviews).
  - In `carry_proof`, allow carrying `independent-review = success` on `merge_group` only when zero unedited `claude[bot]` (or `mctl-agy-reviewer[bot]`) `CHANGES_REQUESTED` reviews exist on `live_pr_head`, `compare_files(queue_base, live_pr_head) == compare_files(queue_base, queue_head)`, and `live_pr_head` holds a qualifying trusted unedited `claude[bot]` `APPROVED` verdict OR a non-carried App-owned `independent-review` / `agy-formal-review` `success`.
  — DoD: `.github/tests/test_agy_formal_reviews.py` covers `independent-review`, `pr_diff_digest_v1`, `provider`, `shadow` (`independent-review-shadow` + zero approvals), author-reviewer check, `claude[bot]` `CHANGES_REQUESTED` precedence, `strict: false` base-advance tolerance, `claude[bot]` queue carry-forward, and kills mutations for every new guard.

- [ ] 4. Implement central trusted orchestrator `.github/scripts/review_gate_controller.py` and `.github/workflows/review-gate-controller.yml` (depends on 1, 3):
  - Supersede PR `#348` (`agy_formal_auto_dispatch.py` patterns reused and generalized).
  - Trigger ONLY on `schedule: '*/5 * * * *'` and `workflow_dispatch` (`repository`, `pr_number`, `dry_run`, `gate_mode`) on `mctlhq/.github` `main` in `environment: agy-review-publisher` (omitting `workflow_call` because `environment: agy-review-publisher` restricts to `main` and would reject `pull_request` callers).
  - Read live PR, rules/protection (`strict` flag), reviews + GraphQL edit state, check-runs, workflow runs + `referenced_workflows` + entry-workflow blob vs `default_branch`, live `pr_diff_digest_v1`, and active dispatch runs; fail closed as `UNKNOWN` on any partial/malformed read.
  - Enforce caller trust in BOTH `claude[bot]` verdict evaluation (Step 2) and fallback classification (Step 3), allow `strict: false` `base_sha` advances when `(merge_base, head_sha)` `pr_diff_digest_v1` matches live PR diff, and enforce strict precedence: `claude[bot]` `BLOCKING_FINDINGS` > `claude[bot]` `PASS` > (`NO_VERDICT_TRANSIENT` OR trusted `SELF_EDIT` on `.github/workflows/` PRs) -> reuse qualifying formal Agy result for `(repo, pr, base_ref, head_sha, diff_digest)`, else dispatch `agy-formal-dispatch.yml` with `head_sha` and `check_name=independent-review`. Reject `NO_VERDICT_OTHER`, informational Agy comments, forged comments, and PR artifacts.
  - Cancel superseded queued formal runs for stale heads unless `publish` started; respect `MAX_ACTIVE_FORMAL_RUNS = 2`.
  - Emit structured metrics (`fallback_rate`, `no_verdict_rate`, `queue_wait_seconds`, `time_to_valid_verdict_seconds`) to job summary and non-secret artifact.
  — DoD: `.github/tests/test_review_gate_controller.py` passes all unit, negative, and mutation tests (`MutationTests`), and `.github/workflows/workflow-tests.yml` runs the full suite + `actionlint`.

- [ ] 5. Reconcile documentation and open PRs in `mctlhq/.github` (depends on 4):
  - Update `docs/plans/agy-formal-reviews.md` and `AGENTS.md` to document `independent-review` fallback architecture and supersede `#348`.
  - Close/update `mctlhq/.github#348` and `mctlhq/mctl-gitops#2605` cleanly after owner review.
  — DoD: PR in `mctlhq/.github` passes all CI checks and independent review with `AGY_REVIEW_GATE_ENABLED=false` (no runtime changes yet).

## Phase 2 — Isolated fixture & opt-in `mctl-gitops` preview-only pilot (`shadow`)

- [ ] 6. Bump `mctl-gitops/.github/workflows/claude-review.yml` pin to the merged `mctlhq/.github` SHA (depends on 5):
  - Verify on a routine PR that `claude-review / review` emits `Verify terminal verdict posted` on `PASS` and exits `1` (`NO_VERDICT_TRANSIENT`) when quota fails (`#287` fixed live).
  — DoD: Caller pin PR merged in `mctl-gitops`; live check behavior verified.

- [ ] 7. Run isolated fixture and opt-in `mctl-gitops` preview-only PR pilot in `shadow` mode (depends on 6):
  - Exercise `review-gate-controller.yml` (`gate_mode=shadow`, `dry_run=false`) against: (a) a PR with Claude `PASS`, (b) a synthetic/live Claude `NO_VERDICT_TRANSIENT` preview-only PR, and (c) negative cases (Claude `BLOCKING_FINDINGS`, informational Agy `PASS`, stale push).
  - Verify zero `mctl-agy-reviewer[bot]` `APPROVE` reviews are posted in `shadow`, and verify `fallback_rate`, `no_verdict_rate`, `queue_wait_seconds`, `time_to_valid_verdict_seconds` metrics report cleanly.
  — DoD: Pilot shadow report attached to `#398` with exact run URLs, head SHAs, and zero false greens.

## Phase 3 — `mctl-gitops` `enforce` cutover & `merge_group` validation (owner-gated)

- [ ] 8. Stage `mctl-gitops/.github/workflows/agy-formal-queue.yml` with `check_name=independent-review` in `gate_mode=shadow` (depends on 7):
  - Pass `check_name=independent-review` and `gate_mode=shadow` when dispatching `agy-formal-dispatch.yml@main` on `merge_group` so `merge_group` succeeds without requiring `independent-review` in ruleset `18465404` beforehand.
  — DoD: PR passes `validate-manifests`, `actionlint`, and merges through `merge_group` with zero `45647591593`-style `prepare` errors.

- [ ] 9. (Owner action) Update `mctl-gitops` ruleset `18465404`, enable `enforce` on `review-gate-controller` and `agy-formal-queue.yml` (depends on 8):
  - Add `independent-review` (`integration_id: 5732062`) to `required_status_checks`, keeping `cloudflare-plan`, `reserved-hosts`, `validate`, `required_approving_review_count: 1`, `dismiss_stale_reviews_on_push: true`, `merge_queue`, and `DeployKey` bypass unchanged, and enable `enforce` on `review-gate-controller`.
  - Merge the 1-line PR flipping `mctl-gitops/.github/workflows/agy-formal-queue.yml` from `gate_mode=shadow` to `gate_mode=enforce` (GitHub runs the queue commit's updated `agy-formal-queue.yml` against the already-updated ruleset with zero deadlock window).
  - Record before/after `gh api repos/mctlhq/mctl-gitops/rules/branches/main` JSON on `#398`.
  - Verify live on opt-in preview-only PRs: (1) Claude `PASS` -> `independent-review=success` without Agy -> `merge_group` carry-forward merges cleanly; (2) Claude quota exhaustion -> Agy formal `PASS` -> `mctl-agy-reviewer[bot]` `APPROVE` + `independent-review=success` -> `merge_group` carry-forward merges cleanly; (3) forced `merge_group` diff mismatch -> Agy formal runs on queue commit.
  — DoD: Live acceptance checklist signed off on `#398`; `agy-formal-dispatch.yml` `45647591593`-style `merge_group` errors resolved to 0.

- [ ] 10. Optional low-latency `workflow_run` wakeup relay on `mctl-gitops` `main` (depends on 9):
  - If `*/5` poll wait materially adds to `time_to_valid_verdict_seconds`, add `.github/workflows/review-gate-dispatch.yml` (`workflow_run: ["Claude PR review"]`, `main`-only `app-dispatch-review` env, `actions: write`-only dispatch to `mctlhq/.github`).
  — DoD: Measured median wakeup-to-`independent-review` update drops below 30s with zero privilege expansion.

## Phase 4 — Cross-repo follow-ups & org-wide rollout (owner-gated)

- [ ] 11. File and track cross-repo follow-up issues (depends on 7):
  - `mctl-agents`: update `run_shepherd.py` (`GATING_BOTS` / `has_responded`) to recognize `mctl-agy-reviewer[bot]` / `independent-review` (keeping `NEVER_MERGE_SERVICES` human-merged).
  - `mctl-claude-remote`: update `pr-steward` `review_bots[]` / check evaluation for fallback-approved PRs.
  — DoD: Follow-up issues opened and linked to `#398`.

- [ ] 12. (Owner action, per repo) Audit and onboard remaining caller repositories:
  - Install `mctl-agy-reviewer` on selected target repos (`mctl-api`, `mctl-agents`, `mctl-portal`, `mctl-web`, `mctl-telegram`, etc.); verify classic-protected repos count `mctl-agy-reviewer[bot]` `APPROVE`; resolve private-repo ruleset visibility (`pfeifenpatenschaft-backend`, `mctl-support`, `projects-mcp`); on `mctl-agents` ruleset `18455891`, add `independent-review` before removing `claude-review / review` in the same window while retaining `require_code_owner_review: true`.
  — DoD: Per-repo ruleset before/after diff recorded on `#398` with zero unguarded windows.

## Tests

All workflow and controller tests are offline, data-driven, and read the real shipped workflow/script files rather than copies.

- [ ] T1. Claude valid `PASS` (`APPROVED`, unedited GraphQL, `Reviewed head= base=`) -> `independent-review` = `success`, zero Agy dispatch calls.
- [ ] T2. Claude `BLOCKING_FINDINGS` (`CHANGES_REQUESTED`) -> `independent-review` = `failure`, zero Agy dispatch; even when a formal or informational Agy `PASS` is present on the same subject, gate remains `failure`.
- [ ] T3. Claude both tokens exhausted (`NO_VERDICT_TRANSIENT`: `shape == "limit"` -> `claude-review / review` exits `1`) + valid formal Agy `PASS` on exact `(repo, pr, head_sha, base_sha, diff_digest)` -> `mctl-agy-reviewer[bot]` `APPROVE` + `independent-review` = `success`.
- [ ] T4. Claude job `timed_out` or `startup_failure` with no verdict and matching entry blob -> classified `NO_VERDICT_TRANSIENT` -> triggers Agy formal fallback.
- [ ] T5. Claude billed failure (`NO_VERDICT_OTHER`), missing execution file, or unposted verdict despite SDK exit 0 -> `claude-review` fails closed, zero Agy fallback triggered, `independent-review` stays `failure`; whereas trusted `SELF_EDIT` (`self_edit=true`) routes cleanly to `mctlhq/.github` `main`-only `agy-formal-review.yml` (`formal_review: true`) without deadlock.
- [ ] T6. Agy `FAIL:P1` / `FAIL:P2` / `FAIL:P1,P2` -> `mctl-agy-reviewer[bot]` `REQUEST_CHANGES` + `independent-review` = `failure`.
- [ ] T7. Agy no-verdict, quota exhaustion, timeout, empty/truncated (`>150000` bytes)/binary diff, missing/malformed verdict tag, contradictory `PASS` containing `P1`/`P2`, missing/mismatched `diff_digest`, or wrong `provider` -> zero PR approval, `independent-review` = `failure`.
- [ ] T8. Security boundaries: informational Agy `PASS` comment, forged `github-actions[bot]` limit comment, PR-edited `.github/workflows/claude-review.yml` (skip-paths/conventions/untrusted `referenced_workflows` on Step 2 or Step 3), PR-uploaded artifact, fork PR, non-default base, or `pr.user.login == agy_login` -> never triggers fallback or grants approval from PR workflow inputs.
- [ ] T9. Race & staleness: head, `base_ref`, or `pr_diff_digest_v1` move before/during `publish` (or concurrent `claude[bot]` `CHANGES_REQUESTED`) -> refuses or dismisses `APPROVE` and marks check `failure`; whereas non-conflicting `base_sha` advance under `strict: false` with identical `(merge_base, head_sha)` `pr_diff_digest_v1` stays valid; duplicate events, replay, and superseded `queued` runs cancel older-head runs while preserving in-flight `publish`.
- [ ] T10. Concurrent formal reuse: existing trusted, unedited formal `mctl-agy-reviewer[bot]` `PASS` for exact `(repo, pr, base_ref, head_sha, diff_digest)` is reused on Claude `NO_VERDICT_TRANSIENT`/`SELF_EDIT` only when Claude has no `BLOCKING_FINDINGS`; carried or informational records never qualify.
- [ ] T11. `merge_group` (`#351`): identical PR diff carries `independent-review = success` from either unedited trusted `claude[bot]` `PASS` or non-carried formal `mctl-agy-reviewer[bot]` `PASS` only with zero `claude[bot]` `CHANGES_REQUESTED` on `live_pr_head`; any `CHANGES_REQUESTED`, diff mismatch, `>300` files, pure-rename/mode-only entry, moved ref, or parent mismatch refuses carry-forward or forces full formal review.
- [ ] T12. Unreadable/partial API (`403`/`500`, malformed JSON, duplicate JSON keys, later pagination page failure, `total_count` mismatch) -> `UNKNOWN` (`Refused`), zero dispatch, zero approval, never `success`.
- [ ] T13. `shadow` mode -> never calls `POST .../reviews` (`APPROVE`/`REQUEST_CHANGES`), works without `independent-review` in `required_status_checks`, records telemetry only.
- [ ] T14. Mutation suite (`MutationTests`): reverting each critical guard in `claude-review.yml`, `agy-review.yml`, `agy_review_publish.py`, and `review_gate_controller.py` causes its designated test `T1`-`T13` to fail, and restoring it turns green.

## Metrics and pilot exit criteria

- Emit per-window metrics: `fallback_rate`, `no_verdict_rate` (by provider), `queue_wait_seconds`, `time_to_valid_verdict_seconds`, and `false_green_incidents`.
- Pilot exit criteria before Phase 3/4 expansion: `0` false-green checks, `0` unapproved/stale merges, `100%` mutation-test kill rate, and measured queue-wait / time-to-verdict within `mctl-gitops` 120-min `merge_queue` timeout.

## Rollback

1. Before ruleset `enforce` cutover: disable `review-gate-controller.yml` (`AGY_REVIEW_GATE_ENABLED=false`) or revert the `.github` PR; pinned callers and `mctl-gitops` merges are unaffected.
2. After `mctl-gitops` ruleset cutover: (a) owner removes `independent-review` from `required_status_checks` in ruleset `18465404` first (restoring pre-cutover snapshot), (b) disables `review-gate-controller` for `mctl-gitops` (and disables `agy-formal-queue.yml` if not using `agy-formal-review`), and (c) keeps `#287` fail-closed fix in place while falling back to manual `@claude review` / human review until recovery.
