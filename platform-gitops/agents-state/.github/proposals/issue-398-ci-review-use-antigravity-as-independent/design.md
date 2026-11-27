# Design: issue-398-ci-review-use-antigravity-as-independent

## Current state

Source pins: `mctlhq/.github` main `233dc60548ae628b3a9a6804d15fd85dd90adf48`
(2026-11-26, merge of mctlhq/.github#415). `mctlhq/mctl-gitops` main `5c61adc1642a134bce26b1afd80f7c10e7711d4f`.
`mctlhq/mctl-telegram` main `c74249b9cbd01c88a54e7f86e1431e0f4db116f2`. All read on
2026-11-27.

### What already exists in `mctlhq/.github` (read in the clone)

- `.github/workflows/claude-review.yml` (1676 lines). The primary reviewer. Steps
  `Classify outcome: PASS | BLOCKING_FINDINGS | NO_VERDICT_TRANSIENT |
  NO_VERDICT_OTHER | STALE | SELF_EDIT` (lines 1648-1673) and the job output
  `review_outcome` (lines 45-49, 329) implement the mctlhq/.github#287 fix. A usage-limit hit
  now exits 1 and is marked `NO_VERDICT_TRANSIENT`.
- `.github/workflows/agy-review.yml` (975 lines). The reusable Agy reviewer:
  formal mode, full-diff validation, structured `review_result`.
- `.github/workflows/agy-formal-review.yml`. The formal wrapper.
  `.github/scripts/agy_review_publish.py` is the trusted publisher.
  `ALLOWED_CHECKS = {'agy-formal-review', 'independent-review'}` and
  `SHADOW_CHECK = 'independent-review-shadow'`. `carry_proof` handles merge-queue
  commits from a trusted Agy head verdict or a trusted unedited `claude[bot]` PASS.
  Shadow behaviour, read at `233dc60`: with `gate_mode=shadow` the publisher sets
  its check name to `independent-review-shadow`, so `prepare`, `fail` and the
  carry path all write only that check. `publish()` finishes the shadow check and
  returns before the `POST .../reviews` call and before any dismissal.
  `publish_queue()` never posts a review in either mode. `policy()` refuses shadow
  without stale dismissal and (strict or queue), so a missing-baseline repository
  gets no formal run at all.
- `.github/workflows/agy-formal-dispatch.yml`. The `workflow_dispatch` entrypoint
  with inputs `repository, pr_number, head_sha, check_name, gate_mode,
  queue_head_ref/sha, queue_base_sha`. Its `run-name` encodes repo, PR, head and
  check, and the controller parses it with `RUN_TITLE_RE`.
- `.github/workflows/review-gate-controller.yml`. Runs `*/5` plus
  `workflow_dispatch` (`dry_run` default true, `force_rerun`). The job runs only on
  `mctlhq/.github` `refs/heads/main`, in environment `agy-review-publisher`. It runs
  live only when `vars.AGY_REVIEW_GATE_ENABLED == 'true'`, with
  `AGY_REVIEW_GATE_REPOS` defaulting to `mctlhq/mctl-gitops:shadow`. A
  write-scoped App token is minted only when live. Otherwise it mints a read-only one.
- `.github/scripts/review_gate_controller.py` (968 lines). Relevant pieces:
  - `parse_policy`: reads rulesets plus classic protection; derives `strict`,
    `stale_dismissal`, `queued`, and `required_bound` (context
    `independent-review` with `integration_id` equal to the App ID).
  - `evaluate_repo`: raises `Unknown` (no decision at all) unless the policy has
    stale dismissal and (strict or queue), in shadow and enforce alike. It also
    raises in enforce mode unless `required_bound` holds. It cancels superseded
    dispatch runs whose `publish` has not started. It writes `independent-review`
    or `independent-review-shadow` via `upsert_check_run` with external id
    `gate/v1:<repo>:<pr>:<head>:<mode>:<digest>`.
  - `decide_pr`: checks blocking precedence first
    (`review_trust.has_blocking_changes_requested`). It then checks trusted Claude
    PASS (`review_trust.verify_claude_pass`). It then classifies the latest
    completed Claude run (`classify_claude_run`), which keys off the `Classify outcome:`
    step names. After that come reuse (`find_qualifying_agy_reuse`), the terminal
    failure guard (`has_terminal_fallback_failure`), dedupe of active dispatches, and
    `MAX_ACTIVE_FORMAL_RUNS = 2`.
  - `Metrics`: `queue_wait_seconds` and `time_to_valid_verdict_seconds` are
    declared and serialized but never appended to anywhere in `.github/scripts`.
- `.github/scripts/review_trust.py`: `caller_allowlist_for(repo)` expects the
  consumer caller at `.github/workflows/claude-review.yml`.
  `is_trusted_reusable_ref` accepts `...claude-review.yml@main`, or `@<sha>` when
  the ref equals the resolved SHA. It does not check that the SHA is reachable from
  `.github` main, and there is no review-policy version boundary, so any
  historical on-main revision of the reviewer would be trusted.
- `.github/tests/test_review_gate_controller.py` (17 tests) and
  `test_agy_formal_reviews.py` (60 tests) run under `workflow-tests.yml`.
- `docs/plans/agy-formal-reviews.md` documents the App trust boundary, the
  activation steps, `carry_proof`, and the controller section for mctlhq/.github#398. It is
  marked "NOT LIVE".

### Deployed state checked

- `gh api repos/mctlhq/.github/actions/workflows/review-gate-controller.yml/runs`:
  scheduled runs 45941981695, 45907862998 and 45834994317 (2026-11-26/27) were all
  `skipped`. Manual run 45821382776 (2026-11-26 12:37, dry run) succeeded. It
  evaluated `mctlhq/mctl-gitops#3032` in `shadow` as `SELF_EDIT -> dispatch` (dry,
  nothing dispatched), with `fallback_rate 0.5`. Scheduled run 45754471179
  (2026-11-26 04:19, commit 768949d) failed; the cause was not determined.
- `gh api repos/mctlhq/.github/actions/variables`: HTTP 403. The values of
  `AGY_REVIEW_GATE_ENABLED` and `AGY_REVIEW_GATE_REPOS` are unknown (only inferred
  from the skipped runs).
- `gh api repos/mctlhq/mctl-gitops/rules/branches/main`: active ruleset 18465404
  `main-protection`, updated 2026-11-26T14:30:10Z. It requires 1 approving review,
  with `dismiss_stale_reviews_on_push: true`, `require_last_push_approval: false`
  and `require_extra_approval_for_unattributed_changes: true`. Required checks are
  `cloudflare-plan`, `reserved-hosts`, `validate` (integration 15368, GitHub
  Actions) and `agy-formal-review` (integration 5732062, the reviewer App).
  `strict_required_status_checks_policy: false`. The merge queue uses `MERGE`,
  groups of one, `ALLGREEN`, and a 120 min check timeout. Ruleset 14564982 `main` is
  disabled. `bypass_actors` read back as `null` (may be permission-limited).
  Classic protection: HTTP 403, unknown. `independent-review` is not required.
- mctl-gitops callers (contents API at main):
  - `claude-review.yml` uses `claude-review.yml@84f51e2d...`, which is 59 commits
    behind `.github` main and contains zero `Classify outcome` steps.
  - `agy-review.yml` uses `agy-review.yml@main` with `blocking: false`
    (informational).
  - `agy-formal-queue.yml` runs on `merge_group`. It mints a `DISPATCH_APP` token
    (environment `app-dispatch-queue`) and dispatches `agy-formal-dispatch.yml` with
    queue inputs and the default `check_name=agy-formal-review`.
- `gh api .../agy-formal-dispatch.yml/runs` (latest 30): PR-head runs titled `@ any`
  were triggered manually by `mashkovd`. Head-pinned runs were triggered by
  `mctl-gitops-dispatch[bot]` (the queue path). So the required `agy-formal-review`
  on PR heads is currently produced by owner-dispatched formal Agy reviews. It is
  always-on, not a fallback.
- mctlhq/mctl-gitops#3023: open, head `3e60a75cbad7d8cf70934288012c0aa2144c9180`,
  base `e305a4c83374d17cd18630e1f5f4e8c6a0f228b3`, auto-merge on, author
  `mashkovd`, zero reviews, no `agy-formal-review` check run on the head. Claude
  run 45643936821 concluded `success` via `@84f51e2`, so the controller would
  classify it `NO_VERDICT_OTHER` and would not fall back.
- `gh api repos/mctlhq/mctl-telegram/rules/branches/main`: no rules; rulesets list
  empty. `branches/main` summary shows classic protection with required checks
  `test`, `docker` and `product-updates` (app 15368) and `enforcement_level:
  non_admins`. Full classic protection (required reviews, strict, stale dismissal)
  returned HTTP 403, so it is unknown.
- mctl-telegram callers: `claude-review.yml@1a23d779...` (163 commits behind,
  zero `Classify outcome` steps, `sensitive-paths` set). `agy-review.yml@main` is
  informational. There is no formal or queue caller.
- mctlhq/mctl-telegram#1485 (head `176cb7012e73...`) and mctlhq/mctl-telegram#1481 (release PR by
  `mctl-agents[bot]`) both merged on 2026-11-26, merged by `mashkovd`, with zero
  reviews recorded. Whether that reflects no review requirement or an admin
  override is unknown.
- Reviewer App installation on mctl-telegram: not observable with this run's
  token. Unknown.
- `$MCTL_GITOPS_ROOT` services/tenants and the mctl MCP tools were not used. This
  change concerns GitHub Actions and branch protection, not a deployed tenant
  service, so no tenant, hostname or service config is asserted.

### Issue coordination

mctlhq/.github#287 is closed (classifier merged). mctlhq/.github#347 is closed and
needs no coordination. mctlhq/.github#351 (merge-queue BEHIND loop on head-bound
`agy-formal-review`) is open and is the only issue this proposal coordinates with.
mctlhq/.github#348 (always-on per-PR draft) is open but superseded by the
controller per the plan doc. mctlhq/.github#400 and mctlhq/.github#415 delivered
the controller.

### Gap summary

| # | Gap | Effect today |
|---|-----|--------------|
| G1 | Both consumers pin a Claude reusable without the classifier | Quota runs look like `NO_VERDICT_OTHER`; the fallback can never fire, which fails closed but is useless |
| G2 | Controller not live; `independent-review` not required anywhere | The gate exists only as shadow dry runs |
| G3 | mctl-gitops requires always-on `agy-formal-review`, dispatched by hand | Agy runs on every PR; contradicts "fallback only"; stalls when the owner does not dispatch (mctlhq/mctl-gitops#3023) |
| G4 | Queue caller always dispatches `check_name=agy-formal-review` | `independent-review` would never appear on queue commits; interacts with mctlhq/.github#351 |
| G5 | `is_trusted_reusable_ref` accepts any SHA, not only SHAs reachable from main | A caller could pin an unmerged `.github` branch commit and still be "trusted" |
| G6 | `queue_wait_seconds` and `time_to_valid_verdict_seconds` never populated | Required metrics are missing |
| G7 | `evaluate_repo` refuses even shadow evaluation without baseline protection | mctl-telegram cannot even be observed without first changing protection |
| G8 | Telegram review policy and App installation unknown | Enforcement there cannot be designed on evidence yet |
| G9 | No review-policy version boundary for trusted reviewer SHAs | An obsolete reviewer revision that is still on main history stays trusted |
| G10 | Gate completion, race and stale handling not specified or tested end to end | A verdict could complete the gate after head, base, digest or blocking reviews changed |

## Proposed solution

### Scope split

- **In scope now (this implementation):** the evidence matrix (section 1), the
  shared-code hardening (section 2: G1, G4-G7, G9, G10) with its synthetic tests,
  and the consumer caller bumps (section 3). The shadow and dry-run paths are
  built and tested here.
- **Owner-gated, not part of this implementation:** turning shadow on live
  (section 4), because it needs a repository-variable change that is not
  authorized by this proposal.
- **Deferred (activation):** the isolated fixture (section 5), the mctl-gitops
  preview pilot (section 6), mctl-telegram enforcement (section 7) and any
  enforce mode. Activation needs Agy review capacity, which is currently
  exhausted, and a separate owner decision. Nothing in this implementation
  assumes the fallback can be piloted now.

Close the in-scope gaps in the smallest order that keeps everything fail-closed.
Reuse the merged controller, dispatcher, wrapper and publisher unchanged except
for the targeted hardening below. Every step that changes a permission, an
installation, a variable, a required check or a ruleset is an owner-only step
with its own explicit authorization. It is never bundled into a code PR.

### 1. Evidence matrix (docs only)

Add a section `Evidence matrix (2026-11-27)` to `docs/plans/agy-formal-reviews.md`
with the per-repository table from "Deployed state checked". It covers the
publisher identity, required checks with integration IDs, the review requirement,
the merge queue, caller pins, observed and unknown items, and source SHAs. Each row
is marked `observed` / `unknown (reason)`. This is the first deliverable the owner
asked for, and later tasks update it rather than restate it.

### 2. Shared-code hardening in `mctlhq/.github` (one PR, independent review)

- **G5 ancestry:** in `review_trust.is_trusted_reusable_ref`, keep the current
  shape check and add an injected `is_on_main(sha)` predicate. The controller and
  publisher implement it via `GET repos/mctlhq/.github/compare/<sha>...main` with
  `status in {'ahead','identical'}`. Any error is untrusted (raise
  `TrustError`/`Unknown`). `@main` keeps its meaning (resolved SHA must be on
  main). Cache per tick.
- **G9 policy-version boundary:** add a second injected predicate
  `meets_policy_boundary(sha)`: the SHA must be the owner-approved boundary
  commit or a descendant of it, checked with the same compare call
  (`compare/<boundary>...<sha>` in `ahead`/`identical`). The boundary is a
  constant on `mctlhq/.github` main, changed only by a reviewed PR. An unset or
  unreadable boundary is untrusted. The trust check is "on main AND meets the
  boundary", so an obsolete revision still on main history is denied.
- **G1 diagnosability:** in `classify_claude_run`, when the review job has none of
  the `Classify outcome:` steps, return `NO_VERDICT_OTHER` with reason
  `caller pinned before outcome classifier (<referenced sha>)`. The behaviour is
  unchanged (fail, no dispatch), but the summary tells the operator to bump the
  caller instead of suggesting a model problem.
- **G7 shadow observation:** reuse the current publisher shadow branch; it
  already returns before `POST .../reviews` (see Current state). In
  `evaluate_repo`, if `gate_mode == 'shadow'` and the baseline is missing, record
  `baseline missing, not enforceable` in metrics, continue evaluating, and add
  that text to the `independent-review-shadow` check summary. For such a
  repository the Agy leg is dry run only: the controller records the decision it
  would take and dispatches nothing, because the publisher's `policy()` refuses
  shadow without a baseline and that refusal is kept. Enforce mode is unchanged
  and still raises. Shadow may write only `independent-review-shadow`: no
  `APPROVED` or `CHANGES_REQUESTED` review and no dismissal, in the PR-head,
  merge-queue, missing-baseline and error paths. A static test pins that the
  shadow branch has no review or dismissal call, and fixture tests cover each
  path. Any path that cannot be shown to meet this runs as dry run only.
- **G10 gate completion, races and staleness:** before the controller writes a
  successful `independent-review`/`independent-review-shadow` check, and before
  the publisher finishes its check, re-read the live head, base,
  `pr_diff_digest_v1`, blocking reviews and the owned check (its id and external
  id). Any change, any blocking review, or any failed read gives no success. The
  publisher's existing post-publish re-read and self-dismissal stay as they are;
  where the controller already does a step, the task adds tests rather than code.
  Events, dispatches and verdicts that refer to a non-live head, base or digest,
  or replay a consumed run attempt, are ignored for completion. Concurrent Claude
  and Agy verdicts resolve by blocking precedence and then by the single external
  id per (repository, PR, head, mode, digest). On merge-queue commits only a fresh
  review or `carry_proof` completes the check, as today.
- **G6 metrics:** `time_to_valid_verdict_seconds` is the time from the head commit's
  first matching Claude run `created_at` to the qualifying PASS review's
  `submitted_at`, or to the reused Agy check's `completed_at`.
  `queue_wait_seconds` is the time from the dispatch run `created_at` to `run_started_at`
  for active and completed dispatches seen this tick. No new API calls beyond
  those already paged.
- **G4 queue check name:** document in `agy-formal-dispatch.yml` and the plan
  that a queue caller for an `independent-review` repository passes
  `check_name=independent-review`. `agy_review_publish.py` already accepts it
  (`ALLOWED_CHECKS`), and `carry_proof` already carries a trusted Claude PASS, so no
  publisher change is needed. Add a test for exactly that path. Coordinate with
  mctlhq/.github#351: this change must not alter the head-bound
  `agy-formal-review` behaviour that issue is fixing, and it adds a cross-link
  only.

No change to the outcome vocabulary, the reuse rules, the terminal-failure guard,
the cancellation of stale runs, `MAX_ACTIVE_FORMAL_RUNS`, App permissions or the
controller's trigger allowlist (`NO_VERDICT_TRANSIENT`, allowlisted `timed_out` /
`startup_failure`, trusted `SELF_EDIT`).

### 3. Consumer caller bumps (one PR per consumer repo, reviewed there)

- mctl-gitops `.github/workflows/claude-review.yml`: bump the pin from `84f51e2`
  to the merged `.github` SHA from step 2, which must meet the G9 boundary.
  Inputs and secrets are unchanged.
- mctl-telegram `.github/workflows/claude-review.yml`: bump from `1a23d779` to
  the same SHA. Keep `sensitive-paths`. Review the 163-commit delta for input
  changes before merging.
- These are ordinary workflow edits. The Claude self-edit path (`SELF_EDIT`)
  applies to these PRs by design, and they are reviewed by the existing process.

### 4. Shadow activation (owner-only, not part of this implementation)

This needs repository-variable changes, which this proposal does not authorize.
A live shadow run that dispatches formal Agy also needs Agy capacity; until then
shadow can only be exercised as a manual dry run. When separately authorized, the
owner sets `AGY_REVIEW_GATE_REPOS=mctlhq/mctl-gitops:shadow mctlhq/mctl-telegram:shadow`
and `AGY_REVIEW_GATE_ENABLED=true` on `.github`. For mctl-telegram, the owner
decides whether to install `mctl-agy-reviewer` on that repository (needed even for
a read-only token). Until then, mctl-telegram is reported `UNKNOWN` by the
controller, which is the correct fail-closed result. Shadow writes only
`independent-review-shadow`. It changes no required check and is observed for an
agreed window (proposal: 7 days or 30 evaluated PRs) with the metrics from G6.

### Activation gate (sections 5-7)

Sections 5-7 are deferred and are not part of this implementation. They start
only when Agy review capacity is restored AND the owner records a separate
activation decision. The order is fixed: shared hardening, shadow, isolated
fixture, preview pilot, then a separate owner decision on enforcement.

### 5. Fixture pilot in enforce mode (deferred, owner-only)

This uses an authorized isolated fixture repository designated by the owner,
with a ruleset requiring `independent-review` bound to integration 5732062, stale
dismissal, strict checks and a merge queue. It verifies the effective repository
and organization rulesets, integration IDs, stale dismissal and merge-queue
behaviour, runs the acceptance fixtures (see tasks.md Tests) live, records run
URLs and exact SHAs in the evidence matrix, and observes whether the App or
`claude[bot]` `APPROVED` review counts toward the review requirement there. No
enforcement anywhere precedes this evidence.

### 6. mctl-gitops opt-in pilot (deferred, owner-only, separate GO_IMPLEMENT)

The change is additive. The owner adds `independent-review` (integration
5732062) to ruleset 18465404 alongside the existing `agy-formal-review`. Nothing
is removed. The owner switches mctl-gitops to `:enforce` in
`AGY_REVIEW_GATE_REPOS`. A mctl-gitops queue caller variant (or input) dispatches
`check_name=independent-review` for queue commits. The pilot runs on one
preview-only PR, opened for the pilot, with an exact head SHA, not an existing
live PR. It
proves queue behaviour and rollback. Whether `agy-formal-review` is later removed
(making Agy truly fallback-only) is a separate owner decision recorded in the plan.
Until then Agy still runs on every mctl-gitops PR, and the controller adds the
Claude path in parallel without weakening anything.

### 7. mctl-telegram enforcement (deferred)

It is designed only after step 4 evidence shows the real review requirement. Any
protection change (stale dismissal, strict, required `independent-review`) is a
separate owner authorization. Release-please PRs get the same gate.

### Trust and failure behaviour (unchanged, restated)

- The provider-neutral check is written only by the App (integration 5732062)
  and is required by `integration_id`, so an Actions job cannot spoof it.
- A Claude PASS counts only if it is unedited (GraphQL `lastEditedAt`), bound to
  the head and to the base or digest, and produced by a trusted caller. An Agy PASS
  counts only if it comes from formal `agy-formal-review.yml` on main, matches the
  exact head and digest, is not carried, and has an unedited App review with the
  marker.
- Any `CHANGES_REQUESTED` from either bot wins. There is no "try the other
  provider" on blocking, `NO_VERDICT_OTHER`, refusal or malformed output. The
  fallback stays transient-only and is not widened by this proposal.
- An API failure, an unreadable page or an unknown active dispatch gives `UNKNOWN`:
  no write, no approval.
- A reviewer SHA counts only if it is on main and meets the review-policy
  version boundary (G9).
- No human approval is replaced. Where a ruleset demands a human reviewer, the App
  or bot review does not satisfy it, and this design does not try to.

## Alternatives

1. **New provider-neutral reviewer workflow per consumer repo** (a caller that
   runs Claude then Agy in one job). Dropped. It duplicates the reviewer and the
   publisher, puts the fallback decision in PR-triggered context, and the issue
   forbids duplication. The central controller already reads only trusted main
   code.
2. **Keep always-on required `agy-formal-review` and simply automate its
   dispatch on every PR** (mctlhq/.github#348 draft). Dropped as the target. It spends Agy on
   every PR, makes Agy the primary rather than the fallback, and keeps the
   mctlhq/.github#351 BEHIND-loop exposure. It remains the status quo during migration.
3. **Promote the informational Agy PASS comment when Claude has no verdict.**
   Rejected. It is not formal, not subject-bound, and is forgeable. The issue
   explicitly excludes it.
4. **Relax the controller to dispatch Agy on any Claude non-PASS.** Rejected. That
   is provider shopping, and it lets Agy override refusals and ambiguous output.

## Platform impact

- **Backward compatibility:** the step 2 code changes are no-ops while
  `AGY_REVIEW_GATE_ENABLED` is unset. G5 and G9 can only make a previously
  trusted ref untrusted, which is fail-closed. Consumer pins pointing at merged SHAs stay
  valid.
- **Migration:** additive only. `agy-formal-review` stays required in mctl-gitops
  until a separate owner decision. mctl-telegram gets no required check from this
  proposal.
- **Resources:** the controller runs a GitHub-hosted job every 5 min (about 1 min
  each), within the existing concurrency group with no cancel. The ancestry check
  adds at most one compare call per distinct SHA per tick. Agy runner load drops
  once mctl-gitops stops requiring always-on Agy, if the owner decides so.
- **Risks and mitigations:**
  - *Required check never appears, so PRs hang:* the pilot uses one PR and a
    fixture. Rollback removes only the added context. The controller writes
    `failure`, not silence, on terminal outcomes.
  - *Stale approval after a push:* stale dismissal is required by the baseline
    check, the publisher rechecks head and base, and external ids include the head
    and digest.
  - *Queue commit lacks the check (G4 / mctlhq/.github#351):* there is an
    explicit queue test, and the deferred mctl-gitops pilot waits on that
    issue's status.
  - *App review counting is unknown:* it is observed in the deferred fixture
    before any pilot, and nothing assumes it.
  - *Agy capacity is exhausted:* activation is deferred; the in-scope work is
    code and synthetic tests and does not depend on Agy runs.
  - *Secret exposure:* the App key stays only in environment `agy-review-publisher`
    on main. No PR code is checked out in privileged jobs. The model runner never
    receives the key.
  - *Shadow posting real reviews:* the publisher shadow branch already returns
    before `POST .../reviews`; the step 2 static and fixture tests pin that for
    every path. A path that cannot be shown safe runs as dry run only.
