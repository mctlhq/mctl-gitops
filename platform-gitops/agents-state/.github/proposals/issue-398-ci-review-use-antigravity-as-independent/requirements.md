# Antigravity as independent fallback reviewer (mctlhq/.github#398)

## Context

On 2026-11-25, `mctlhq/mctl-gitops#3023` (a preview-only environment flag change at head `3e60a75cbad7d8cf70934288012c0aa2144c9180`) demonstrated a recurring review-gate failure class:

1. `.github/workflows/claude-review.yml` (workflow run `45643936821`) exhausted both `CLAUDE_CODE_OAUTH_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN_2` on the shared usage limit, posted a soft transient comment (`issuecomment-7166702352`), and exited `0` (`claude-review / review` concluded `SUCCESS` with `reviews: []`). This is the fail-open defect tracked in `mctlhq/.github#287`.
2. `.github/workflows/agy-review.yml` (workflow run `45643936946`, job `139309714628`) produced `<!-- VERDICT: PASS -->` (`issuecomment-7166721240`), but ran with `formal_review: false`, so it was informational only and skipped `formal_record`. The PR rightly remained blocked without a GitHub approving review.
3. Meanwhile, `mctlhq/.github` (`origin/main` at `60e9db522f18299e73dac23fffedfe5b4ce81930`) already ships `.github/workflows/agy-review.yml` (`formal_review: true`), `.github/workflows/agy-formal-review.yml`, `.github/workflows/agy-formal-dispatch.yml`, and `.github/scripts/agy_review_publish.py` with `mctl-agy-reviewer` (`app_id: 5732062`). However, in `mctlhq/mctl-gitops`, `agy-formal-review` was removed from ruleset `18465404` on 2026-11-16 while `.github/workflows/agy-formal-queue.yml` remained active on `merge_group`, causing every merge-queue formal dispatch (for example run `45647591593` on PR `#3024`) to fail in `formal / prepare`.

This proposal defines a provider-neutral independent review gate (`independent-review`) with Claude as primary reviewer and Antigravity (`agy`) as fallback reviewer only when Claude hits an explicitly allowlisted transient unavailability, quota exhaustion across all configured Claude tokens, or timeout without a valid verdict. It coordinates `mctlhq/.github#287`, `#347`, `#351`, and `#299` without duplicating reviewers or weakening any branch protection, review assurance, or merge-queue guarantee.

Phase 0 produces specification, design, task breakdown, evidence matrix, and migration/rollback plan only. No production workflows, permissions, rulesets, or `mctlhq/mctl-gitops#3023` are modified before independent review and explicit owner `GO_IMPLEMENT`.

## User stories

- AS a repository maintainer I WANT PRs blocked by Claude quota exhaustion or transient unavailability to fall back automatically to an independent formal Antigravity review SO THAT safe changes are not stranded while false-green CI is eliminated.
- AS the org owner I WANT Antigravity to run only on genuine transient no-verdict failures and never override Claude P1/P2 findings or refusals SO THAT provider shopping is impossible and self-hosted runner capacity is preserved.
- AS a security reviewer I WANT formal approvals and required check updates to run only from trusted default-branch code with isolated credentials, exact subject/diff-digest binding, and fail-closed API reads SO THAT untrusted PR content, forged comments, or stale heads cannot mint approval.
- AS a GitOps operator using the merge queue I WANT the provider-neutral gate to support `merge_group` with verified diff-preserving carry-forward SO THAT valid PRs land without the `BEHIND` loop or extra LLM calls when the diff is unchanged.
- AS an auditor I WANT metrics and immutable provenance on every gate evaluation SO THAT fallback rate, no-verdict rate, queue wait, and time to valid verdict are measurable.

## Acceptance criteria (EARS)

Outcome contract and fail-closed primary (`#287`)

- THE SYSTEM SHALL classify every review-gate evaluation into exactly one structured outcome from `{PASS, BLOCKING_FINDINGS, NO_VERDICT_TRANSIENT, NO_VERDICT_OTHER, STALE, UNKNOWN}`.
- WHEN `.github/workflows/claude-review.yml` exhausts all configured Claude tokens on a usage limit (`shape == "limit"`) or fails with no readable terminal verdict on the pinned `(head_sha, base_sha)` THEN `claude-review / review` SHALL exit non-zero (eliminating the `exit 0` false green of `#287`) and emit machine-verifiable transient/non-transient diagnostics.
- IF `claude-review.yml` produces a missing, corrupt, or non-array execution output, fails to post a commit-bound `APPROVED` or `CHANGES_REQUESTED` review naming `HEAD_SHA`, or skips execution due to an error in `gate` THEN THE SYSTEM SHALL NOT report `PASS` and SHALL classify the outcome as `NO_VERDICT_OTHER` or `UNKNOWN` (or `NO_VERDICT_TRANSIENT` only on allowlisted pre-verdict timeout/runner/quota failure).
- WHEN `claude-review.yml` detects a workflow self-edit (`self_edit == true`) THEN THE SYSTEM SHALL preserve non-failing `self_edit=true` semantics on `claude-review / review` as a non-review signal AND the provider-neutral gate SHALL classify it as `NO_VERDICT_OTHER` (non-passing, no automatic fallback approval).

Fallback trigger policy and precedence

- WHEN Claude produces a valid, unedited `PASS` (`APPROVED` by `claude[bot]` `type=Bot` with `commit_id == head_sha` and exact `Reviewed head=<head_sha> base=<base_sha>` verified unchanged via GraphQL) THEN THE SYSTEM SHALL conclude `PASS` for `independent-review` without triggering Antigravity.
- WHEN Claude produces `BLOCKING_FINDINGS` (`CHANGES_REQUESTED` by `claude[bot]` on the exact subject) THEN THE SYSTEM SHALL conclude `BLOCKING_FINDINGS` (`failure`) and SHALL NOT trigger Antigravity fallback; even if an Antigravity review reports `PASS` on the same subject, Claude `BLOCKING_FINDINGS` SHALL keep the gate blocked.
- WHEN Claude ends with `NO_VERDICT_TRANSIENT` after primary and fallback Claude tokens are exhausted (verified from trusted workflow run state, entry-workflow blob equality with default branch, and absence of any `claude[bot]` verdict) THEN THE SYSTEM SHALL reuse an existing Antigravity result ONLY IF it was produced by a formal, trusted `agy-formal-review.yml` run for the exact `(repository, pr_number, head_sha, base_sha)` with matching full diff digest, valid non-contradictory verdict, and unedited `mctl-agy-reviewer[bot]` provenance; otherwise THE SYSTEM SHALL dispatch `.github/workflows/agy-formal-review.yml` (`formal_review: true`).
- IF Claude ends with `NO_VERDICT_OTHER`, `STALE`, or `UNKNOWN` THEN THE SYSTEM SHALL NOT trigger Antigravity fallback and SHALL NOT mark `independent-review` as `success`.
- IF an informational `.github/workflows/agy-review.yml` (`formal_review: false`) comment, forged PR comment, or PR-uploaded artifact claims `PASS` THEN THE SYSTEM SHALL ignore it completely and SHALL NOT treat it as formal evidence or approval.
- IF Antigravity fallback ends with `FAIL:P1`, `FAIL:P2`, `FAIL:P1,P2`, no verdict, quota exhaustion, timeout, truncated/empty/oversized/binary diff, contradictory `PASS` containing `P1`/`P2`, stale `head_sha`/`base_sha`, runner unavailability, auth failure, or unreadable/partially-paginated GitHub API response THEN THE SYSTEM SHALL NOT post an approval and SHALL leave `independent-review` non-successful (`failure` or `in_progress` only while an active current-head run is legitimately executing).

Trusted publisher, diff verification, and security boundaries

- THE SYSTEM SHALL reuse `.github/workflows/agy-review.yml` (`formal_review: true`), `.github/workflows/agy-formal-review.yml`, and `.github/scripts/agy_review_publish.py` rather than creating a parallel reviewer or publisher.
- WHILE executing formal review, `.github/workflows/agy-review.yml` SHALL run with no `AGY_REVIEW_APP_PRIVATE_KEY` or write App credentials, SHALL ignore caller-supplied `conventions`, SHALL fail closed on empty, truncated (`> 150000` bytes), or binary diffs, and SHALL include `provider` (`"agy"`) and a canonical full-diff `diff_digest` (`sha256` over the exact reviewed diff) in `review_record`.
- BEFORE publishing any formal `APPROVE` or `REQUEST_CHANGES` review or check conclusion, `.github/scripts/agy_review_publish.py` SHALL resolve its own trusted source SHA from `referenced_workflows`, verify `repository`, `pr_number`, `base_ref` == `default_branch`, non-fork same-repo PR, `head_sha`, `base_sha`, full `diff_digest` against live GitHub tree/compare state, `provider`, structured `verdict`, branch protection policy (`dismiss_stale_reviews_on_push` AND (`strict` OR `merge_queue` with `MERGE`) AND App-bound required check in `enforce` mode), and author separation (`pr.user.login != agy_login`).
- IMMEDIATELY BEFORE and AFTER posting `APPROVE`, the trusted publisher SHALL re-read live PR `head_sha`/`base_sha` (or `queue_state` in `merge_group` mode); IF head/base or queue ref moved during publication, THEN THE SYSTEM SHALL dismiss the just-posted approval and fail closed.
- WHEN `gate_mode == "shadow"` THEN THE SYSTEM SHALL NOT post `APPROVE` or `REQUEST_CHANGES` PR reviews and SHALL publish only diagnostic/shadow status without altering required branch checks.
- THE SYSTEM SHALL NOT grant bypass actors, weaken existing required checks during migration, impersonate human reviewers, or satisfy `require_code_owner_review` / human-only approval policies with a bot review.

Stable required check, `merge_group`, and concurrency

- THE SYSTEM SHALL expose a single App-bound required status check context `independent-review` (published by `mctl-agy-reviewer`, `integration_id: 5732062`) compatible with both `pull_request` / `workflow_dispatch` heads and `merge_group` commits.
- WHEN a `merge_group` entry (`refs/heads/gh-readonly-queue/<branch>/pr-<N>-<base>`) is evaluated THEN the trusted publisher SHALL verify live `queue_state` (`parents == [base, live_pr_head]`) and SHALL carry `independent-review = success` without an LLM call ONLY IF `compare_files(base, pr_head) == compare_files(base, queue_head)` (non-empty, `< 300` files, no mode-only/pure-rename, unmoved queue ref after comparison) AND the live PR head carries a qualifying unedited `claude[bot]` `PASS` or non-carried `mctl-agy-reviewer[bot]` formal `PASS` (with zero `BLOCKING_FINDINGS`); otherwise it SHALL run `agy-review.yml` (`formal_review: true`) on the queued commit and fail the queue entry on any non-`PASS` or unreadable state.
- WHEN duplicate events or head updates arrive THEN concurrency groups and the controller SHALL dedupe per `(repository, pr_number, head_sha)` and cancel stale queued runs for superseded heads (never cancelling a `publish` job already in progress).
- THE SYSTEM SHALL compute and emit per-run metrics (`fallback_rate`, `no_verdict_rate`, `queue_wait_seconds`, `time_to_valid_verdict_seconds`) in workflow job summaries/artifacts without exposing PR prose or secrets.

## Out of scope

- Modifying any GitHub workflow, GitHub App permission/installation, repository environment, or branch ruleset in Phase 0.
- Approving, unblocking, force-merging, or auto-approving `mctlhq/mctl-gitops#3023`.
- Promoting informational `agy-review` comments, green CI runs, owner MFA alone, or manual advisory receipts into GitHub PR approvals.
- Replacing `mctl-api` `internal/reviewstore` / `mctl/review-evidence` (`mctlhq/.github#299`); this gate runs in GitHub Actions reusing `agy-review.yml` and `agy_review_publish.py` and remains orthogonal to `#299`.
- Making Antigravity formal review mandatory on every PR when Claude already produced a valid `PASS`.
- Migrating `mctl-agents` `run_shepherd.py` (`GATING_BOTS`) or `mctl-claude-remote` `pr-steward` in the first `.github` PR (tracked as explicit follow-up tasks in `tasks.md`).

## Open questions

- **App installation scope beyond `mctl-gitops` (`UNKNOWN`):** `orgs/mctlhq/installations/181323208/repositories` returned 404 under a user OAuth token (requires App JWT). Live runs `43966181276` and `45647591593` prove `mctl-agy-reviewer` is installed on `mctl-gitops`; installation on the other 24 active org repos is `UNKNOWN`. Default: pilot on `mctl-gitops` only; owner explicitly adds non-pilot repos to `mctl-agy-reviewer` before Phase 4 cutover.
- **Private repository branch rules (`UNKNOWN`):** `pfeifenpatenschaft-backend`, `mctl-rules`, `projects-mcp`, and `mctl-support` returned HTTP 403 on `rules/branches/main` (private-repo rulesets require GitHub Pro/Team) and had no visible classic protection. Default: `policy()` fails closed on any repo lacking observable `dismiss_stale_reviews` + (`strict` or `merge_queue`) + App-bound required check; owner verifies/upgrades or excludes those repos before onboarding.
- **Classic branch protection review counting (`UNVERIFIED` outside Rulesets):** `mctl-agy-reviewer[bot]` `APPROVED` reviews were observed live on Ruleset-protected `mctl-gitops#2716` and `#2720`, but not yet verified live on classic-protected `mctl-telegram`, `mctl-loyalty`, or `mctl-academy`. Default: verify live on one classic-protected repo before Phase 4 migration.
- **Disposition of open `mctlhq/.github#348` and `mctlhq/mctl-gitops#2605`:** Both PRs predate this design. Default: supersede `#348` (reusing its fail-closed `agy_formal_auto_dispatch.py` patterns inside the new `review_gate_controller.py`) and close/replace `#2605` after Phase 0 owner approval.
- **Controller trigger cadence vs immediate dispatch:** Central `*/5` scheduled controller in `mctlhq/.github` needs zero secrets in caller repos; an optional `workflow_run` relay on target repo `main` (minting an `actions: write`-only dispatch token like `agy-formal-queue.yml`) cuts latency from 0-5 min to ~15s. Default: Phase 1-2 pilot uses central `*/5` + `workflow_dispatch` controller (no new caller secrets), with `workflow_run` wakeup relay added in Phase 3 if queue wait / time-to-verdict telemetry warrants it.
- **Downstream automation (`run_shepherd.py` and `pr-steward`):** Today `run_shepherd.py:1660` sets `has_responded` from `claude[bot]` only and `pr-steward` configs default `review_bots: ["claude[bot]"]`. Default: file cross-repo follow-up issues in `mctl-agents` and `mctl-claude-remote` as part of tasks 9-10 so implementer PRs can accept `mctl-agy-reviewer[bot]` + `independent-review` once `mctl-gitops` pilot passes (`NEVER_MERGE_SERVICES` stays human-merged).
