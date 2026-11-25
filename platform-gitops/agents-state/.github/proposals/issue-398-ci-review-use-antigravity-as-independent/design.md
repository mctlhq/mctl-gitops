# Design: issue-398-ci-review-use-antigravity-as-independent

## Current state (source-pinned inventory, 2026-11-25)

Every repository, workflow, ruleset, and app identity below was read directly from `origin/main` or live GitHub REST/GraphQL endpoints on 2026-11-25. Items that could not be read with the available token are explicitly marked `UNKNOWN`.

### 1. Shared review workflows (`mctlhq/.github` at `60e9db522f18299e73dac23fffedfe5b4ce81930`)

| File | Trigger / Role | Current Behaviour & Findings |
| --- | --- | --- |
| `.github/workflows/claude-review.yml` | `workflow_call`; outputs `self_edit` (`#384`) | Runs primary (`CLAUDE_CODE_OAUTH_TOKEN`) then fallback (`CLAUDE_CODE_OAUTH_TOKEN_2`). `Classify reviewer outcome` (lines 1453-1468) matches quota on `shape == "limit"` (final attempt unbilled) and executes `exit 0` -> false green (`#287`). Also fails open if execution output is missing/unreadable in `review-check`/`review-final`, if no review is posted (`#204`/`#1555`), or if `gate` skips `review` (`#287` sweep). |
| `.github/workflows/agy-review.yml` | `workflow_call`; outputs `review_record` | Runs on `[self-hosted, agy-reviewer]` (two Mac minis) with NO App write key. Supports `formal_review: true` (`EXTRA_CONVENTIONS=""`, rejects binary `-	-	`, empty, or `> 150000` byte diffs, requires exact last-line `<!-- VERDICT: ... -->`, rejects `PASS` containing `\bP[12]\b`). `review_record` (`agy-review/v1`) lacks `provider` and full `diff_digest`. `formal_review: false` is informational comment only. |
| `.github/workflows/agy-formal-review.yml` | `workflow_call` (`prepare` -> `review` -> `publish`) | Runs `prepare`/`publish` on `ubuntu-latest` in `environment: agy-review-publisher` (`main` branch policy). Resolves script commit from `referenced_workflows`, sparse-checks out `.github/scripts` from that SHA, mints short-lived `mctl-agy-reviewer` token (`contents: read`, `pull-requests: write`, `checks: write`, `administration: read`). |
| `.github/workflows/agy-formal-dispatch.yml` | `workflow_dispatch` on `main` | Calls `./.github/workflows/agy-formal-review.yml` with `repository`, `pr_number`, `queue_head_ref`, `queue_head_sha`, `queue_base_sha`. |
| `.github/scripts/agy_review_publish.py` | Trusted publisher (`prepare` / `publish` / `fail`) | Hardcodes `CHECK = 'agy-formal-review'`. `policy()` refuses unless target default branch has `dismiss_stale_reviews_on_push`, (`strict` OR `merge_queue` with `MERGE`), AND `agy-formal-review` bound to `integration_id == AGY_REVIEW_APP_ID`. Supports `merge_group` `carry_proof` (`#363`) for identical diffs only when PR head already has an App-owned non-carried `agy-formal-review` `success`. Does not yet carry `claude[bot]` `APPROVED` reviews or check `diff_digest` / author-reviewer separation. |
| `.github/workflows/pr-review.yml` & `agy-pr-review.yml` | `.github` callers on `pull_request` | `pr-review.yml` calls local `./.github/workflows/claude-review.yml`; `agy-pr-review.yml` calls `agy-review.yml@main` with `blocking: false`. |
| `.github/workflows/agy-canary.yml` | Daily cron probing `agy` defaults | Checks `agy models` and one-line prompt on `AGY_HOME_PRIMARY` / `AGY_HOME_FALLBACK`; distinguishes `absent`, `run-failed`, `unknown`. |
| `.github/tests/test_*.py` | `workflow-tests.yml` unit + mutation suite | Covers `agy_review_publish.py` (including 20 mutations in `test_agy_formal_reviews.py`), `claude-review` dedup/classify/denials/selfedit/settle/usage, `agent-trailer`, `steward-usage`. |
| Open PR `mctlhq/.github#348` | `ci/agy-formal-auto-dispatch` (`#347`) | Adds `agy-formal-auto-dispatch.yml` (`*/5` cron) + `agy_formal_auto_dispatch.py` (25 mutation-tested guards) + `head_sha` pinning in `agy-formal-dispatch.yml`. Currently waits on `claude[bot]` verdict rather than acting as Claude fallback. |

### 2. GitOps callers, rulesets, and live failures (`mctlhq/mctl-gitops` at `9bb8076f9a69d72bfe9cd5c60e76747e973ab3a6`)

- `.github/workflows/claude-review.yml`: pins `mctlhq/.github/.github/workflows/claude-review.yml@84f51e2d83868aa1205e41c5ad6684d8666b5797` (pre-#381/#382/#384, already emits `Reviewed head= base=`).
- `.github/workflows/agy-review.yml`: calls `@main` with `blocking: false` (informational).
- `.github/workflows/agy-formal-queue.yml`: triggers on `merge_group: [checks_requested]`, mints `mctl-gitops-dispatch` (`app-dispatch-queue` environment restricted to `gh-readonly-queue/main/*`), dispatches `agy-formal-dispatch.yml@main` in `mctlhq/.github`.
- Ruleset `18465404` (`main-protection`, updated `2026-11-16T23:09:46+01:00`):
  - `required_approving_review_count: 1`, `dismiss_stale_reviews_on_push: true`, `require_extra_approval_for_unattributed_changes: true`, `require_code_owner_review: false`.
  - `required_status_checks` (`strict: false`): `cloudflare-plan`, `reserved-hosts`, `validate` (all `integration_id: 15368`). `agy-formal-review` is absent.
  - `merge_queue`: `MERGE`, `ALLGREEN`, group size 1, `check_response_timeout_minutes: 120`.
  - `bypass_actors`: `DeployKey` (`always`) only (`gitops-bump.yaml` / `release-deploy.yaml`).
- **Live `merge_group` failure observed today:** Run `45647591593` (2026-11-25T15:39:15Z, PR `#3024`, queue head `9bb8076f9a69d72bfe9cd5c60e76747e973ab3a6`) failed in `formal / prepare` at `agy_review_publish.py:192` (`Refused: formal approval needs stale-review dismissal, strict checks or a merge queue, and the App-bound agy-formal-review check`) because `agy-formal-review` is no longer required in ruleset `18465404`.
- **Live reproducer `mctlhq/mctl-gitops#3023`:** Head `3e60a75cbad7d8cf70934288012c0aa2144c9180`; Claude run `45643936821` concluded `SUCCESS` after usage-limit comment `7166702352` (`reviews: []`); informational Agy run `45643936946` commented `PASS` (`7166721240`); PR stays blocked.
- **Historical live proof of formal `mctl-agy-reviewer`:** On 2026-11-16, `agy-formal-dispatch.yml` succeeded on `mctl-gitops#2720` (PR head `43966181276` -> `mctl-agy-reviewer[bot]` `APPROVED` at `22:04:16Z`; queue `43966531006` `success`) and `#2716` (`43952192441` `APPROVED`; queue `43959611609` / `43961068128` `success`).
- Open draft PR `mctlhq/mctl-gitops#2605` (`ci/agy-formal-review-pilot`) stages an always-on `pull_request_target` caller; inactive.

### 3. Org-wide repository inventory (25 active repositories)

| Group | Repositories | Protection / Rules Observed | Claude / Agy Callers Observed |
| --- | --- | --- | --- |
| Ruleset `1` approval + `dismiss_stale` + `merge_queue` | `mctl-gitops` | Ruleset `18465404`; required checks `cloudflare-plan`, `reserved-hosts`, `validate` (`15368`) | `claude-review.yml` (`@84f51e2d`), `agy-review.yml`, `agy-formal-queue.yml` |
| Ruleset `1` approval + `dismiss_stale` + `require_code_owner_review` | `mctl-agents` | Ruleset `18455891`; required checks include `claude-review / review` (unpinned app) | `claude-review.yml` (`@2ae26326`), `agy-review.yml` |
| Ruleset `1` approval + `dismiss_stale` (public) | `mctl-portal`, `mctl-web`, `mctl-api`, `mctl-agent`, `mctl-docs`, `mctl-design`, `mctl-claude-remote`, `mctl-pairdesk`, `seerrsense`, `portfolio`, `mctl-alice`, `newton-mcp-gateway`, `mctl-glovo`, `bridge-step0-sandbox` (14 repos) | Rulesets active (`strict: false`, `require_extra_approval_for_unattributed_changes: true`); build/lint/validate checks required | 13 have `claude-review.yml` (SHAs range `25478e95`..`648bf5eb`); 9 also have `agy-review.yml`; `bridge-step0-sandbox` has neither |
| Ruleset without PR approval rule | `mctl-coolify-mcp` | Deletion, non-FF, build/snapshot checks only | Neither workflow |
| Classic branch protection only (`rules: []`) | `mctl-telegram` (`approvals=1, dismiss=true, strict=true`), `mctl-academy` (`approvals=1, dismiss=true`), `mctl-loyalty` (`approvals=1, dismiss=true`), `.github` (`approvals=0, strict=false`, `Analyze (actions)`) | Classic protection active | All 4 wire Claude (`pr-review.yml` in `.github`); 3 wire Agy (`agy-pr-review.yml` in `.github`, `mctl-loyalty` does not) |
| Private repos (`rules` HTTP 403) | `pfeifenpatenschaft-backend`, `mctl-rules`, `projects-mcp`, `mctl-support` | `rules/branches/main` HTTP 403 (`Upgrade to GitHub Pro...`); classic protection `NONE` -> effective rules `UNKNOWN` | 3 wire `claude-review.yml` (`pfeifenpatenschaft-backend` also `agy-review.yml`); `mctl-rules` has neither |

### 4. GitHub App identities and environments

| Identity / Environment | ID / Scope | Permissions / Secrets Observed | Unknown / Gaps |
| --- | --- | --- | --- |
| `claude[bot]` (`claude`) | User ID `209825114`, App inst `109526686` (`all`) | `checks: write`, `pull_requests: write`, `issues: write`, `contents: write`, `workflows: write` | Subscription OAuth tokens (`CLAUDE_CODE_OAUTH_TOKEN`, `_2`) live in repo/org Actions secrets |
| `mctl-agy-reviewer[bot]` (`mctl-agy-reviewer`) | App ID `5732062`, Bot ID `355912856`, Inst `181323208` (`selected`) | `administration: read`, `checks: write`, `contents: read`, `metadata: read`, `pull_requests: write`; no bypass role | `mctl-gitops` verified installed; installation on other 24 repos is `UNKNOWN` (404 on app-only endpoint) |
| `mctl-gitops-dispatch` | Inst `179684760` (`selected`) | `actions: write`, `metadata: read` | Key in `mctl-gitops` env `app-dispatch-queue` (`gh-readonly-queue/main/*`) |
| `mctl-org-read` | Inst `179684981` (`all`) | `actions: read`, `contents: read`, `issues: read`, `metadata: read` | Available if central controller needs read access to private repos |
| `mctlhq/.github` env `agy-review-publisher` | Protected `branch_policy: main` | Holds `AGY_REVIEW_APP_ID=5732062` and `AGY_REVIEW_APP_PRIVATE_KEY` | Ready for central controller reuse |
| `mctl-gitops` env `agy-review-publisher` | Protected `branch_policy: main` | Empty (no vars, no secrets) | Intentionally left unpopulated under central controller design |

### 5. Downstream consumers of review state

- `mctl-agents` `orchestrator/run_shepherd.py`: `REVIEW_BOT = "claude[bot]"`, `GATING_BOTS = ("claude[bot]", "chatgpt-codex-connector[bot]")`; `has_responded` (line 1660) tracks `claude[bot]` only; `NEVER_MERGE_SERVICES = frozenset({"mctl-academy", "mctl-gitops", ".github"})`.
- `mctl-claude-remote` `skills/pr-steward/SKILL.md`: `review_bots[]` defaults to `["claude[bot]"]`, gates merges on `approved_at_head` + `checks_green` excluding the review workflow's own check.

## Proposed solution

### 1. Structured outcome contract (`review_outcome/v1`)

Every gate evaluation for subject `S = (repository, pr_number, base_ref, head_sha, diff_digest)` (plus `reviewed_base_sha`, or `merge_group` `(repository, pr_number, queue_head_ref, queue_head_sha, queue_base_sha)`) produces one deterministic state:

| State | Meaning | Triggers Agy Fallback? | Gate Check (`independent-review`) | GitHub Review Action |
| --- | --- | --- | --- | --- |
| `PASS` | Primary (`claude[bot]`) or verified fallback (`mctl-agy-reviewer[bot]`) completed full review of exact `S` with zero P1/P2 findings | No (if Claude); already satisfied (if formal Agy) | `success` | `claude[bot]` or `mctl-agy-reviewer[bot]` `APPROVE` at `head_sha` (PR mode); none in `merge_group` |
| `BLOCKING_FINDINGS` | Trusted reviewer reported P1/P2 findings on exact `S` (`CHANGES_REQUESTED` / `FAIL:P1`/`P2`) | **Never** (even if concurrent/informational Agy passes) | `failure` | `CHANGES_REQUESTED` at `head_sha` |
| `NO_VERDICT_TRANSIENT` | Claude primary and fallback tokens exhausted allowlisted transient limit/unavailable/timeout with no valid verdict on `S` | **Yes** (reuse valid formal Agy on exact `S` if present; else dispatch `agy-formal-review.yml`) | `in_progress` while Agy formal runs; `failure` if fallback cannot start or fails | None until Agy formal publishes valid `PASS` or `FAIL` |
| `SELF_EDIT` | Trusted `claude-review` deferred review (`self_edit=true`) because PR touched `.github/workflows/` | **Yes (main-only trusted review)** via `agy-formal-review.yml` on `mctlhq/.github` `main` (ignoring PR workflow edits) | `in_progress` while formal Agy runs; never bypasses review | Formal `mctl-agy-reviewer[bot]` `APPROVE` or `REQUEST_CHANGES` on reviewed diff |
| `NO_VERDICT_OTHER` | Billed Claude failure, refusal, `skip-paths` without policy, or Agy non-transient failure / malformed / binary / oversized / contradictory / missing verdict | **Never** | `failure` | None (or `REQUEST_CHANGES` if Agy returned explicit `FAIL:P1`/`P2`) |
| `STALE` | Live `head_sha`, `base_ref`, `(merge_base, head_sha)` `diff_digest` (or `base_sha` under `strict: true`), or `merge_group` ref changed before/during evaluation or publication | Cancel superseded queued run; evaluate new head | Existing head check stays non-success; dismiss race approval | Dismiss if posted during race; non-conflicting `base_sha` advances under `strict: false` with unchanged `diff_digest` remain valid |
| `UNKNOWN` | Any failed/partial/malformed API read, missing/corrupt execution file, ambiguous run source, or unreadable branch policy | **Never** (retry read in controller without approving) | Leave non-success (`failure` on publisher failure; do not mark `success`) | None |

### 2. Coordinated `#287` fix and explicit outcome signals in `.github/workflows/claude-review.yml`

Fix all five false-green paths identified in `#287` in one cohesive update (no separate duplicate `#287` patch):

1. **Non-zero exit on transient quota exhaustion:** In `Classify reviewer outcome`, keep posting the explanatory transient PR comment for `shape = "limit"`, emit explicit classification outputs/markers (`outcome=NO_VERDICT_TRANSIENT`), and end with `exit 1` (`::error::`) instead of `exit 0`.
2. **Fail closed on missing/unreadable execution output (`review-check` and `review-final`):** Treat absent or non-JSON `$OUT` or missing `result` entry as `failed=true` (`UNKNOWN` / `NO_VERDICT_OTHER`) rather than defaulting `is_error="false"`.
3. **Verify a terminal review was posted:** Add step `Verify terminal verdict posted` after `review-final` (when `failed != 'true'` and not `dedup`/`selfedit`/`stale`/`skip`). It queries `pulls/$PR_NUMBER/reviews` (`--paginate`) and GraphQL edit status for an unedited `claude[bot]` `APPROVED` or `CHANGES_REQUESTED` review on `HEAD_SHA` carrying `Reviewed head=$HEAD_SHA base=$BASE_SHA`. If absent or unreadable, fail the job (`NO_VERDICT_OTHER` / `UNKNOWN`) so permission denials (`#204`/`#1555`) never go green.
4. **Machine-readable step markers + `workflow_call` outputs:** Expose `review_outcome`, `reviewed_head`, `reviewed_base` on `jobs.review` and `on.workflow_call.outputs`, backed by dedicated deterministic outcome-gate steps (`Classify outcome: PASS`, `Classify outcome: BLOCKING_FINDINGS`, `Classify outcome: NO_VERDICT_TRANSIENT`, `Classify outcome: NO_VERDICT_OTHER`, `Classify outcome: STALE`, `Classify outcome: SELF_EDIT`) so a default-branch controller can inspect exact `steps[]` state via the GitHub Jobs API without trusting PR comments or PR artifacts.
5. **Preserve `#384` self-edit handling without workflow-PR deadlock:** On `self_edit=true`, `claude-review / review` remains non-failing with `self_edit=true` and `Classify outcome: SELF_EDIT` (never running `claude` with PR-modified workflow context). Because ruleset `18465404` has `bypass_actors: DeployKey` only, classifying `SELF_EDIT` as dead-end `failure` would permanently block `.github/workflows/` PRs (including pin bumps). Instead, the central controller treats a trusted `SELF_EDIT` as an explicit trigger for `agy-formal-review.yml` executing purely from `mctlhq/.github` `main` (never reading PR-head workflows or caller `conventions`, sandboxed with zero repo execution), ensuring every workflow diff receives an independent formal review.

### 3. Trusted fallback orchestrator (`review-gate-controller.yml` + `.github/scripts/review_gate_controller.py`)

Keep all credentials (`AGY_REVIEW_APP_PRIVATE_KEY` in `agy-review-publisher`) centralized in `mctlhq/.github` `main`:

- **Entry workflow (`.github/workflows/review-gate-controller.yml`):**
  - Triggers ONLY on `schedule: '*/5 * * * *'` (safety sweep across configured target repos, superseding PR `#348`'s `agy-formal-auto-dispatch.yml`) AND `workflow_dispatch` (accepting untrusted hint `repository` + optional `pr_number`), both executing strictly on `refs/heads/main`. (`workflow_call` is intentionally omitted because `environment: agy-review-publisher` enforces `branch_policy: main` and would reject `pull_request`-ref callers such as `pr-review.yml`; `.github`'s own PRs are evaluated from `main` via the `schedule` / `workflow_run` path in shadow/reporting mode.)
  - Runs on `ubuntu-latest` inside `environment: agy-review-publisher` (`main` only), checks out `.github/scripts` from verified `referenced_workflows` SHA, mints short-lived `mctl-agy-reviewer` token (`contents: read`, `pull-requests: write`, `checks: write`, `administration: read`) for the target repository (and uses `mctl-org-read` / `GITHUB_TOKEN` only for read-only discovery).
  - Never checks out PR code and never reads PR titles, PR bodies, PR branch names, PR artifacts, or `github-actions[bot]` issue comments as verdict or trigger evidence.
- **Controller decision algorithm per open non-draft same-repo PR targeting `default_branch`:**
  1. Read live PR (`head_sha`, `base_sha`, `base_ref`, `author`), branch rules/classic protection (`strict` vs non-strict), paginated `pulls/{n}/reviews` + GraphQL edit metadata, paginated `commits/{head_sha}/check-runs`, and active `review-gate` / `agy-formal-dispatch` workflow runs. Compute current `live_diff_digest` (`pr_diff_digest_v1` over live `(merge_base(live_base_sha, head_sha), head_sha)`). Any failed, partial, or `total_count`-mismatched read returns `UNKNOWN` and changes nothing.
  2. **Check `claude[bot]` authoritative verdict on `(head_sha, base_ref)` (uniform trust + `strict: false` base-advance resilience):**
     - Verify caller trust for any candidate `claude[bot]` review just as in Step 3: locate the matching `claude-review` workflow run for `head_sha` and require `referenced_workflows` to name a trusted `mctlhq/.github/.github/workflows/claude-review.yml@<trusted_sha>` plus entry-workflow blob equality at `head_sha` vs `default_branch` (preventing a PR from altering `conventions` or `skip-paths` before `claude[bot]` approves).
     - Match a parsed `Reviewed head=<head_sha> base=<reviewed_base_sha>` unedited `claude[bot]` review as current-subject when `head == head_sha` AND (`reviewed_base_sha == live_base_sha` OR (`strict == false` AND live `compare(reviewed_base_sha...head_sha)` `pr_diff_digest_v1 == live_diff_digest`, proving `main` advances did not alter the PR's three-dot reviewed diff; otherwise mark `STALE`)).
     - **Precedence:** Any qualifying unedited `claude[bot]` `CHANGES_REQUESTED` on `head_sha` -> `BLOCKING_FINDINGS`: publish/ensure `independent-review` = `failure` (never dispatch Agy; ignore any Agy `PASS`).
     - Otherwise, a qualifying unedited `claude[bot]` `APPROVED` (with zero `CHANGES_REQUESTED` on `head_sha`) -> `PASS`: publish/ensure `independent-review` = `success` (`Satisfied by primary reviewer claude[bot] for <head_sha>`). Note: for older pinned callers still emitting pre-`Reviewed head=` verdicts, require pin bump to the updated `claude-review.yml` before `enforce` cutover.
  3. **Check whether Claude run requires trusted Antigravity review (`NO_VERDICT_TRANSIENT` or `SELF_EDIT`):**
     - Locate completed `claude-review` workflow runs for `head_sha` (or `issue_comment` on same `head_sha`) on the target repo.
     - For `NO_VERDICT_TRANSIENT`: verify `referenced_workflows` names `mctlhq/.github/.github/workflows/claude-review.yml@<trusted_sha>` AND entry-workflow blob at `head_sha` matches `default_branch`, with steps showing `Classify outcome: NO_VERDICT_TRANSIENT` (`conclusion == "success"`) OR `review` job concluded `timed_out` / `startup_failure` with no `self_edit` and no `claude[bot]` verdict.
     - For `SELF_EDIT`: verify `referenced_workflows` names `mctlhq/.github/.github/workflows/claude-review.yml@<trusted_sha>` and `review` job steps show `Classify outcome: SELF_EDIT` (`conclusion == "success"`) with no `claude[bot]` `CHANGES_REQUESTED`. (Even if the PR modified `.github/workflows/*`, entry-workflow modification is expected on `SELF_EDIT` and execution is strictly handed off to `mctlhq/.github` `main`'s `agy-formal-review.yml`, which executes zero PR workflow code.)
     - Otherwise (still queued/in_progress -> `independent-review = in_progress` / wait; `NO_VERDICT_OTHER` -> `independent-review = failure` without fallback; missing Claude run -> wait/pending).
  4. **Reuse or dispatch Antigravity formal review (only on `NO_VERDICT_TRANSIENT` or `SELF_EDIT`, with zero `claude[bot]` `CHANGES_REQUESTED`):**
     - **Concurrent formal reuse check:** Inspect `mctl-agy-reviewer[bot]` reviews on `head_sha` and `independent-review` / `agy-formal-review` non-carried check-runs by `app_id == 5732062`. Reuse ONLY IF an unedited formal `mctl-agy-reviewer[bot]` verdict (`<!-- agy-formal:<run>:<attempt>:<head_sha>:<VERDICT> -->`) exists from a verified `agy-formal-review.yml` run for `(repo, pr, base_ref, head_sha)` with matching `live_diff_digest`; never reuse informational `agy-review` comments (`formal_review: false`).
     - **Dedupe / stale cancellation:** If an `agy-formal-dispatch.yml` run is already active for `(repo, pr, head_sha)`, wait (`independent-review = in_progress`). Cancel active dispatch runs for older heads of the same PR unless their `publish` job has already started. Respect `MAX_ACTIVE_FORMAL_RUNS = 2` (two self-hosted Mac mini runners).
     - **Dispatch:** Ensure `independent-review` check run exists as `in_progress` on `head_sha`, then dispatch `agy-formal-dispatch.yml` (`ref=main`, `repository`, `pr_number`, `head_sha`, `check_name=independent-review`, `gate_mode=<mode>`).
- **Optional low-latency wakeup relay (`.github/workflows/review-gate-dispatch.yml`, Phase 3 opt-in on target repos):**
  - Triggers on `workflow_run: workflows: ["Claude PR review"], types: [completed]` (always runs from target repo `main`!).
  - Uses a minimal `actions: write`-only dispatch App token (`app-dispatch-review` env restricted to `main`) to call `workflow_dispatch` on `review-gate-controller.yml` with `(repository, pr_number)` only. Even if dropped or unavailable, the `*/5` schedule guarantees completion.

### 4. Trusted publisher & canonical `pr_diff_digest_v1` hardening (`.github/workflows/agy-review.yml`, `agy-formal-review.yml`, `.github/scripts/agy_review_publish.py`)

Extend the existing formal pipeline without creating a second reviewer:

1. **Single canonical `pr_diff_digest_v1` and `provider` in `agy-review.yml` (`formal_review: true`):**
   - In `Prepare review prompt`, resolve three-dot merge-base `mb=$(git merge-base "$BASE_SHA" "$HEAD_SHA")` and compute `diff_digest` using the exact `pr_diff_digest_v1` canonical byte serialization from `#299` over `git diff-tree -r --no-renames --full-index -z "$mb" "$HEAD_SHA"`: `"pr_diff_digest_v1\n"` + sorted entries `"<old_mode> <new_mode> <old_blob> <new_blob> <status>\t<len(path)>\n<path>\n"` + `"<count>\n"` (in addition to existing empty/binary/`150000`-byte cap gates).
   - Include `'provider': 'agy'` and `'diff_digest': diff_digest` in `formal_record` (`schema_version: 'agy-review/v2'`, defaulting `agy_review_publish.py` to require `v2` once workflow and script ship together).
2. **Pre-publish verification in `agy_review_publish.py`:**
   - Parameterize `CHECK` via allowlisted `CHECK_NAME in {'independent-review', 'agy-formal-review'}` (default `'agy-formal-review'` for backward compatibility until callers opt into `'independent-review'`) and `GATE_MODE in {'enforce', 'shadow'}`.
   - Compute live `pr_diff_digest_v1` on the publisher without trusting PR working trees or downloading file blobs: query GitHub compare API `/compare/{live_base}...{head_sha}` to obtain the authoritative `merge_base_commit.sha`, then in an isolated empty temp git repo (`GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null`, `-c core.fsmonitor=false`, zero checkout) run `git fetch --no-tags --filter=blob:none --depth=1 origin <merge_base> <head_sha>` and `git diff-tree -r --no-renames --full-index -z <merge_base> <head_sha>` to compute the exact same `pr_diff_digest_v1`.
   - In `prepare` and `publish`, cross-check `result['provider'] == 'agy'`, verify `pr['user']['login'] != self.login` (author/reviewer separation), verify `result['diff_digest'] == live_diff_digest`, and verify **zero unedited `claude[bot]` `CHANGES_REQUESTED` reviews** exist on `head_sha` (both before and after posting `APPROVE`; if `claude[bot]` posted `CHANGES_REQUESTED` or `head_sha`/`base_ref`/`live_diff_digest` moved, dismiss any just-posted `APPROVE` and fail closed). Under `strict: false`, a live `base_sha` advance that preserves `head_sha`, `base_ref`, and `live_diff_digest` is accepted rather than rejected as `STALE`.
   - In `enforce` mode, `policy(branch)` requires `dismiss_stale_reviews_on_push == True`, (`strict == True` OR `merge_queue` with `MERGE`), AND `CHECK_NAME` bound to `integration_id == self.app`.
   - In `shadow` mode, `policy(branch)` checks `dismiss_stale_reviews_on_push` + (`strict` OR `merge_queue`) **without** requiring `CHECK_NAME` in `required_status_checks`, posts **only** non-blocking diagnostic check-run context `independent-review-shadow` (never satisfying an enforced `independent-review` check and never calling `POST .../reviews` for `APPROVE` / `REQUEST_CHANGES`).

### 5. `merge_group` support (`#351`) and `carry_proof` extension

1. Unify `mctl-gitops/.github/workflows/agy-formal-queue.yml` with `independent-review` using a two-step shadow-first cutover (preventing `prepare` deadlocks between queue workflow updates and ruleset updates):
   - First update `agy-formal-queue.yml` to pass `check_name=independent-review` with `gate_mode=shadow` (passes while `independent-review` is not yet in ruleset `18465404`).
   - Next, owner adds `independent-review` (`integration_id: 5732062`) to `required_status_checks` in ruleset `18465404`, and flips `agy-formal-queue.yml` (`gate_mode=shadow` -> `gate_mode=enforce`) + enables controller `enforce`. Because `merge_group` executes `.github/workflows/agy-formal-queue.yml` from the queue commit itself, the cutover PR runs with `gate_mode=enforce` against the already-updated ruleset with zero unmergeable window.
2. Extend `Publisher.carry_proof(pr, branch)` in `agy_review_publish.py` so a `merge_group` commit can carry `independent-review = success` without invoking Antigravity when:
   - Live `queue_state` holds (`ref` live, `parents == [queue_base, live_pr_head]`, PR open & non-draft);
   - `compare_files(queue_base, live_pr_head) == compare_files(queue_base, queue_head)` (non-empty, `< 300` files, no mode-only/pure-rename, queue ref unmoved afterward);
   - **Zero unedited `claude[bot]` `CHANGES_REQUESTED` reviews exist on `live_pr_head`** (and no unedited `mctl-agy-reviewer[bot]` `CHANGES_REQUESTED` on `live_pr_head`); AND
   - Live PR head holds EITHER:
     - a qualifying unedited `claude[bot]` `APPROVED` review with `Reviewed head=<live_pr_head> base=<reviewed_base>` matching `(live_pr_head, pr_base)` (exact `base` under `strict: true`, or matching `pr_diff_digest_v1` under `strict: false`), verified trusted (`referenced_workflows` + entry-workflow blob equality), OR
     - a qualifying non-carried App-owned `independent-review` / `agy-formal-review` `completed`/`success` check-run (`external_id` matching this repo and PR) paired with no `claude[bot]` `CHANGES_REQUESTED` on `live_pr_head`.
3. If carry-forward proof fails for any reason (changed diff, >300 files, missing/stale/failed PR-head verdict, `claude[bot]` `CHANGES_REQUESTED`, unreadable API), `prepare()` either fails closed on `BLOCKING_FINDINGS` or falls through cleanly to running `agy-review.yml` (`formal_review: true`) on `queue_head_sha`! If that model review fails or returns findings/no-verdict, `independent-review` concludes `failure` and GitHub's merge queue evicts the entry.

### 6. Observability & metrics

Emit one structured JSON metric record (artifact + `$GITHUB_STEP_SUMMARY` table, no secrets/diff text) from `review_gate_controller.py` and `agy_review_publish.py`:
- `fallback_rate`: `agy_fallback_dispatched / (claude_evaluated + agy_fallback_dispatched)` per window.
- `no_verdict_rate`: counts of `NO_VERDICT_TRANSIENT`, `NO_VERDICT_OTHER`, `UNKNOWN` by provider (`claude`, `agy`).
- `queue_wait_seconds`: `job.started_at - run.created_at` for formal fallback runs.
- `time_to_valid_verdict_seconds`: `check_run.completed_at - head_commit.committer.date` (or `pr_sync_event_ts`) for terminal `PASS`/`BLOCKING_FINDINGS`.

## Evidence matrix

| Requirement / Acceptance Test | Component / Symbol | Verification Method | Observed Status (2026-11-25) | Required Proof Before Cutover |
| --- | --- | --- | --- | --- |
| Claude PASS -> no fallback; P1/P2 blocks even if Agy passes | `review_gate_controller.decide_pr` | Unit + negative fixtures + mutation tests | Not yet implemented (`#348` exists for always-on agy) | Mutation tests fail when `BLOCKING_FINDINGS` guard is removed; live pilot PR PASS without Agy |
| `#287` Claude quota `exit 1` + fail-closed missing/unposted verdict | `claude-review.yml` (`Classify`, `review-check`, `review-final`, `Verify terminal verdict`) | `test_claude_review_classify.py` + mutation tests | Reproduced live fail-open on `mctl-gitops#3023` (`45643936821`) | All `#287` negative fixtures exit `1`; reverted guard turns test red |
| Claude both tokens exhausted -> Agy formal PASS -> `APPROVE` + `independent-review=success` | `review-gate-controller.yml`, `agy-formal-review.yml`, `agy_review_publish.py` | Unit + live shadow + opt-in preview PR pilot | `mctl-agy-reviewer` `APPROVE` proved on `#2716`/`#2720`; fallback orchestration not yet built | Live preview-only pilot PR obtains `mctl-agy-reviewer[bot]` `APPROVE` + `independent-review=success` |
| Agy P1/P2, no-verdict, malformed/truncated/binary, contradictory `PASS`, stale, API error -> no approval | `agy-review.yml` (`formal_record`, `Prepare`), `agy_review_publish.py` | `test_agy_formal_reviews.py` + `MutationTests` | Existing 20 mutations verified in repo; `diff_digest`/author checks pending | Added mutations for `diff_digest`, `provider`, author!=reviewer, `gate_mode=shadow` |
| Informational Agy PASS / forged comment / PR workflow edit / PR artifact -> rejected | `review_gate_controller.py` (`referenced_workflows`, entry blob check), `agy_review_publish.py` | Unit + negative security fixtures + mutation tests | Reproduced informational Agy `PASS` on `mctl-gitops#3023` (`45643936946`); stays unapproved | Negative fixtures proving forged comment, PR-edited `skip-paths`, and PR artifact cannot trigger fallback or approval |
| `merge_group` compatibility & diff-preserving carry-forward (`#351`) | `agy_review_publish.py` (`carry_proof`, `queue_state`), `agy-formal-queue.yml` | `CarryTests`, `QueueTests`, live `mctl-gitops` queue pilot | `agy-formal-queue.yml` currently failing (`45647591593`) due to ruleset mismatch | Live pilot PR (Claude PASS) & fallback pilot PR (Agy formal PASS) both merge through `mctl-gitops` merge queue |
| Stale cancellation, duplicate events, concurrent formal reuse | `review_gate_controller.py`, `agy-review.yml` concurrency | `test_review_gate_controller.py` + `MutationTests` | `#348` stale-cancel pattern reviewed | Replay, duplicate dispatch, and superseded-head tests pass and kill mutations |

## Migration and rollback plan

### Migration phases

1. **Phase 0 (This proposal — no runtime changes):** Merge proposal at `status: proposed` in `mctl-gitops`; independent review + explicit owner **`GO_IMPLEMENT`** decision on `mctlhq/.github#398` / DevLoop decide page. Leave `mctl-gitops#3023` blocked until valid review/approval.
2. **Phase 1 (Shared `.github` implementation in shadow, zero runtime disruption):**
   - Implement `#287` + outcome markers in `claude-review.yml` (pinned callers are unaffected until their pin SHA is updated).
   - Extend `agy-review.yml`, `agy-formal-review.yml`, `agy-formal-dispatch.yml`, `agy_review_publish.py`, and add `review_gate_controller.py` / `review-gate-controller.yml` (default `AGY_REVIEW_GATE_ENABLED=false` / `shadow` dry-run).
   - Supersede `mctlhq/.github#348` and close/update `mctl-gitops#2605`.
   - Pass full `.github/tests` unit + mutation suite + `actionlint`.
3. **Phase 2 (Isolated fixture + opt-in `mctl-gitops` preview-only pilot):**
   - Bump `mctl-gitops/.github/workflows/claude-review.yml` pin to the new `.github` SHA. (Verify `#287` fails honestly when Claude hits quota.)
   - Run `review-gate-controller.yml` in `gate_mode=shadow` against an isolated fixture / opt-in preview-only PR on `mctl-gitops` (`dry_run=false`, `gate_mode=shadow`, zero `APPROVE` writes, zero ruleset changes).
   - Measure `fallback_rate`, `no_verdict_rate`, `queue_wait_seconds`, `time_to_valid_verdict_seconds` and verify `false_green_incidents == 0`.
4. **Phase 3 (`mctl-gitops` `enforce` cutover — owner-gated):**
   - Step 3a: Update `mctl-gitops/.github/workflows/agy-formal-queue.yml` to pass `check_name=independent-review` and `gate_mode=shadow` (zero ruleset errors before `independent-review` is added to ruleset `18465404`).
   - Step 3b (Owner action): Update ruleset `18465404` on `mctl-gitops` to add `independent-review` (`integration_id: 5732062`) to `required_status_checks` (preserving `cloudflare-plan`, `reserved-hosts`, `validate`, `required_approving_review_count: 1`, `dismiss_stale_reviews_on_push: true`, `merge_queue`, and `DeployKey` bypass) and flip `review-gate-controller` config for `mctl-gitops` to `enforce`. Record before/after JSON on `#398`.
   - Step 3c: Merge the follow-up PR flipping `mctl-gitops/.github/workflows/agy-formal-queue.yml` from `gate_mode=shadow` to `gate_mode=enforce` (`merge_group` executes the queue commit's updated `agy-formal-queue.yml` with `enforce` against the already-updated ruleset). Prove one normal Claude `PASS` PR and one simulated/real Claude-quota fallback preview PR through the merge queue.
   - Step 3d: Optionally add `workflow_run` wakeup relay (`review-gate-dispatch.yml`) on `mctl-gitops` `main` to cut wakeup latency from 0-5 min to ~15s.
5. **Phase 4 (Org-wide rollout — per-repo owner gate):**
   - Pre-check per repo: verify `mctl-agy-reviewer` installation, confirm `dismiss_stale_reviews_on_push` + (`strict` or `merge_queue`), resolve private-repo rulesets (4 private repos) and `mctl-agents` `claude-review / review` required check swap (`claude-review / review` -> `independent-review` in the same window so merges never stall).
   - Land follow-up PRs in `mctl-agents` (`run_shepherd.py`) and `mctl-claude-remote` (`pr-steward`) if automated remediation/merge should accept `mctl-agy-reviewer[bot]` fallback approvals.

### Rollback plan

Because removing a check from `required_status_checks` must happen **before** stopping the publisher that reports it (otherwise every PR hangs awaiting a missing required check), rollback follows strict reverse order:
1. **Before Phase 3 (Shadow / `.github` code only):** Set `AGY_REVIEW_GATE_ENABLED=false` (or revert `review-gate-controller.yml` / `.github` PR). Zero ruleset or caller impact; pinned callers keep working.
2. **After Phase 3 (`mctl-gitops` `enforce` active):**
   - Step 1 (Owner): Remove `independent-review` from `required_status_checks` in ruleset `18465404` (restore pre-cutover snapshot JSON), leaving `cloudflare-plan`, `reserved-hosts`, `validate`, `required_approving_review_count: 1`, `dismiss_stale_reviews_on_push: true`, and `merge_queue` intact.
   - Step 2: Set `mctl-gitops` back to `shadow` or disable `review-gate-controller` for `mctl-gitops` (and disable `agy-formal-queue.yml` if not using `agy-formal-review`, eliminating the current `45647591593` error noise).
   - Step 3: If needed, revert caller pin in `mctl-gitops/.github/workflows/claude-review.yml` (while noting reverting `#287` would re-expose false-green on quota, so prefer keeping `#287` fix and relying on manual `@claude review` / human review during outage).
3. Existing approvals already published by `mctl-agy-reviewer[bot]` remain auditable in GitHub review history; no audit data is deleted on rollback.

## Alternatives

1. **Per-repository `pull_request_target` formal workflow with replicated `AGY_REVIEW_APP_PRIVATE_KEY` (`mctl-gitops#2605` style):**
   - Dropped: requires provisioning and rotating `AGY_REVIEW_APP_PRIVATE_KEY` across 20+ repository environments, runs unconditionally on pushes unless gated by extra API polling, and exposes a larger App-key blast radius. Centralizing `AGY_REVIEW_APP_PRIVATE_KEY` in `mctlhq/.github` `agy-review-publisher` keeps a single secret boundary.
2. **Wait for `mctl-api` OIDC `mctl/review-evidence` (`mctlhq/.github#299`):**
   - Complementary, not a blocker/substitute here: `#299` requires implementing three new `mctl-api` slices (D/E/F) and migrating all rulesets away from GitHub `APPROVE` reviews, and is currently blocked on `issue-299` approval/slices. Reusing `agy-review.yml` (`formal_review: true`) + `agy_review_publish.py` solves the P1 `#3023` outage using infrastructure already deployed on `mctlhq/.github`, while remaining cleanly replaceable by `#299` later.
3. **Cron-only `#348` (`agy-formal-auto-dispatch`) without fixing `#287` or supporting Claude fallback:**
   - Dropped: `#348` assumes `agy-formal-review` is always required on every PR (which saturated the two Mac mini runners and was removed on 2026-11-16) and leaves `#287` false-green on `claude-review / review`.

## Platform impact

- **Runner capacity:** Normal PRs with Claude `PASS` invoke zero Antigravity formal runs (saving both Mac mini runner slots and Antigravity quota compared to always-on `#347`/`#2605`). Only Claude `NO_VERDICT_TRANSIENT` (plus `merge_group` entries whose diff changed against the base) consume `[self-hosted, agy-reviewer]` capacity (`MAX_ACTIVE_FORMAL_RUNS = 2`).
- **Security:** `AGY_REVIEW_APP_PRIVATE_KEY` stays confined to `mctlhq/.github` `agy-review-publisher` (`main`-only). Reviewer runners hold no App keys. PR-controlled files, workflow inputs (`conventions`), comments, and artifacts cannot steer fallback or mint approval.
- **Backward compatibility:** Pinned callers on older `claude-review.yml` SHAs continue operating unchanged until bumped. Existing informational `agy-review.yml` callers remain non-blocking and non-authoritative.
