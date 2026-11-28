# Provider-neutral independent review gate: harden the Claude-primary / Agy-fallback controller and its shadow mode for mctl-gitops and mctl-telegram (activation deferred)

## Revision 2026-11-27

Revised per the [amendment register](https://github.com/mctlhq/.github/issues/398#issuecomment-7229397620) and its [correction](https://github.com/mctlhq/.github/issues/398#issuecomment-7229485206). The earlier decision does not carry over to this content; it needs independent re-review and a fresh approval bound to the new digest.

- Scope is split. In scope now: architectural hardening (trusted reviewer SHA with a review-policy version boundary, fail-closed rules, head/base/digest recheck at gate completion, race and stale invalidation, merge-queue behaviour) and the shadow/dry-run mode with its tests.
- Deferred: activation, meaning the isolated fixture with real rulesets and App review counting, the preview pilot, and any enforcement. Activation waits until Antigravity (Agy) review capacity is restored (limits are currently exhausted) and a separate owner decision is made.
- Shadow may write only the non-required `independent-review-shadow` check and never an `APPROVED` or `CHANGES_REQUESTED` review. The publisher already returns before `POST /reviews` in shadow (verified against `mctlhq/.github` main `233dc60`).
- No ruleset, App installation, repository variable or required-check change and no change to mctlhq/mctl-gitops#3023 is authorized, no review gate is weakened, no human approval is substituted, and the fallback stays limited to transient no-verdict.
- Cross-repository references are written as `owner/repo#N`. `mctlhq/.github#347` is closed, so coordination applies to `mctlhq/.github#351` only. The register's bare `#3023` means mctlhq/mctl-gitops#3023.

## Context

Issue mctlhq/.github#398 asks for a provider-neutral independent review gate:
Claude reviews first, and Antigravity (Agy) acts as a formal fallback only when
Claude genuinely has no verdict (quota, provider unavailability, timeout). It must
fail closed, never treat a model comment, green CI, owner MFA or a manual advisory
receipt as a GitHub approving review, and must keep every existing required check,
real approval requirement and the merge queue. The 2026-11-26 owner refresh makes
it P1 because the shared Claude quota is exhausted. It also adds mctl-telegram as
a second consumer alongside mctl-gitops, using the same reviewer rather than a
parallel one.

Investigation shows the core mechanism already exists on `mctlhq/.github` main
(233dc60, PRs mctlhq/.github#400 and mctlhq/.github#415). That mechanism is `.github/workflows/review-gate-controller.yml`,
`.github/scripts/review_gate_controller.py` with the six-outcome contract,
`agy-formal-dispatch.yml` and `agy-formal-review.yml` with
`agy_review_publish.py`. None of it is effective yet. Scheduled controller runs
are `skipped`. Both consumer repositories pin a Claude reusable workflow that
predates the outcome classifier, so a quota no-verdict run is indistinguishable
from any other no-verdict run and can never trigger the fallback. The required
check `independent-review` is not in any ruleset. In mctl-gitops, the
always-on formal Agy check `agy-formal-review` is required, and PR-head
reviews are dispatched by hand. mctl-telegram has no review-related required
check, and its last two observed PRs merged with zero reviews. This proposal
therefore does not build a new reviewer. It hardens the merged code and proves
its shadow mode with tests, and it records exactly what is observed and what is
unknown per repository. Turning the gate on (fixture, pilot, enforcement) is a
later, separately gated step: it needs Agy review capacity, which is currently
exhausted, and its own owner decision.

## User stories

- AS the platform owner I WANT PRs to obtain a qualifying independent verdict when Claude quota is exhausted SO THAT review does not stall and no PR is approved on a green-without-verdict job.
- AS the platform owner I WANT an evidence matrix of publishers, required checks, rulesets and identities per repository SO THAT I can authorize each permission or ruleset change separately and knowingly.
- AS a reviewer of shared CI I WANT the fallback to reuse the existing trusted publisher and outcome contract SO THAT no second reviewer or publisher is created.
- AS a PR author I WANT a single stable provider-neutral required check SO THAT I know whether review is satisfied without reading model comments.
- AS a security reviewer I WANT Agy unable to override Claude blocking findings, refusals or ambiguous output SO THAT the fallback cannot be used for provider shopping.
- AS the mctl-telegram maintainer I WANT the repository observed in shadow mode first SO THAT its real review policy is known before anything is enforced.

## Acceptance criteria (EARS)

Outcome contract and trigger

- WHEN the controller evaluates an open, non-draft, same-repository PR against its default branch THE SYSTEM SHALL classify the primary result into exactly one of `PASS`, `BLOCKING_FINDINGS`, `NO_VERDICT_TRANSIENT`, `NO_VERDICT_OTHER`, `STALE`, `UNKNOWN` (plus the existing trusted `SELF_EDIT` deferral), as implemented in `review_gate_controller.py` and emitted by `claude-review.yml` `review_outcome`.
- WHEN Claude posted a trusted, unedited `claude[bot]` `APPROVED` review bound to the live head (and to the live base under strict policy, or to the live `pr_diff_digest_v1`) THE SYSTEM SHALL mark the provider-neutral check successful without dispatching Agy.
- WHEN any `CHANGES_REQUESTED` review from `claude[bot]` or the Agy reviewer App exists on the live head THE SYSTEM SHALL fail the provider-neutral check, even if another provider passes.
- WHEN the latest trusted Claude run for the live head is `NO_VERDICT_TRANSIENT` (quota or rate limit after both tokens, or an allowlisted `timed_out` / `startup_failure` with no verdict review and an unmodified caller) and no Agy dispatch is active for that head THE SYSTEM SHALL dispatch exactly one `agy-formal-dispatch.yml` run pinned to the live `head_sha`.
- IF the Claude outcome is `NO_VERDICT_OTHER`, a refusal, a malformed, truncated or unreadable verdict, or the run comes from an untrusted caller THEN THE SYSTEM SHALL fail the check and SHALL NOT dispatch Agy. The fallback trigger SHALL stay limited to `NO_VERDICT_TRANSIENT` and the existing trusted `SELF_EDIT` deferral; it SHALL NOT be widened to refusals or malformed verdicts.
- IF the consumer's Claude caller pins a `claude-review.yml` commit that does not emit the `Classify outcome:` steps THEN THE SYSTEM SHALL report the distinct reason `caller pinned before outcome classifier`. It SHALL NOT dispatch Agy and SHALL NOT mark the check successful.
- IF a formal Agy result already completed for the exact repository, PR, head and `pr_diff_digest_v1` from the trusted `agy-formal-review.yml` on `.github` main, with an unedited App `APPROVED` review carrying the matching `agy-formal:` marker THEN THE SYSTEM SHALL reuse it instead of dispatching again.
- IF the only Agy evidence is an informational comment, a check from another integration, a carried mark, a forged comment or a PR-uploaded artifact THEN THE SYSTEM SHALL NOT count it.
- IF neither provider yields qualifying evidence THEN THE SYSTEM SHALL leave the provider-neutral check failed or in progress, never successful.

Publication and identity

- WHEN the Agy publisher posts a review THE SYSTEM SHALL bind repository, PR, head, base, source run, attempt, model, digest and verdict. It SHALL re-read live head and base immediately before and after posting, and SHALL dismiss its own approval if either moved.
- WHILE the PR author equals the reviewer App identity THE SYSTEM SHALL fail the check rather than self-approve.
- THE SYSTEM SHALL NOT impersonate a human, request bypass permission, enable `GITHUB_TOKEN` approvals, or substitute an App review for a human approval that policy requires.
- WHEN validating a reusable workflow reference (`review_trust.is_trusted_reusable_ref`) THE SYSTEM SHALL accept `@main` or an exact SHA only if that SHA is reachable from `mctlhq/.github` main AND, once boundary enforcement is switched on (tasks.md 6b), is at or after the owner-approved review-policy version boundary. An unreadable ancestry check SHALL always be treated as untrusted; with enforcement on, an unreadable boundary check or an unknown boundary SHALL be treated as untrusted too.
- WHILE boundary enforcement is off THE SYSTEM SHALL compute and log the boundary predicate without letting it change any trust decision, so that `agy_review_publish.py` on mctl-gitops `merge_group` keeps today's behaviour until the constant is set.
- IF a reviewer SHA is on main but predates the review-policy version boundary (a historical, obsolete revision) THEN THE SYSTEM SHALL treat it as untrusted and SHALL NOT count its verdict or classify its run as a fallback trigger.
- WHILE the Agy model runs THE SYSTEM SHALL keep the reviewer App key out of the model runner and SHALL NOT check out or execute PR-controlled code in privileged jobs.

Concurrency, staleness and merge queue

- WHEN a PR head moves while a formal Agy run is queued or running and its `publish` job has not started THE SYSTEM SHALL cancel the superseded run.
- WHEN duplicate events, replays or concurrent provider results arrive THE SYSTEM SHALL produce at most one effective check per (repository, PR, head, mode, digest) and SHALL never mark an older head successful.
- WHEN the controller or publisher is about to complete the provider-neutral check as successful THE SYSTEM SHALL re-read the live head, base, `pr_diff_digest_v1`, blocking reviews and ownership of the check it is completing. IF any of them moved, a blocking review is present, or a read fails THEN THE SYSTEM SHALL NOT complete the check as successful.
- IF a blocking `CHANGES_REQUESTED` review appears while a PASS is being published THEN THE SYSTEM SHALL dismiss its own just-posted approval (enforce mode only) and leave the check failed.
- IF an event, dispatch or verdict refers to a head, base or digest that is no longer live, or replays an already-consumed run attempt, THEN THE SYSTEM SHALL ignore it for gate completion.
- IF a GitHub API read fails, is partial or is malformed THEN THE SYSTEM SHALL report `UNKNOWN` and write no success. An unreadable state SHALL never count as "no blocking review" or "no active dispatch".
- WHILE the provider-neutral check is required in a merge-queue repository THE SYSTEM SHALL supply that check on the queue commit only by a fresh review or by the existing `carry_proof` rules (queue parents exactly `[base, live PR head]`, identical file set and blobs, trusted head verdict that is not itself carried).
- WHILE migrating a repository THE SYSTEM SHALL keep every existing required check, including `agy-formal-review` in mctl-gitops. Any check is removed only by a separate owner-authorized ruleset change.

Shadow, dry run and observability (in scope)

- WHILE repository variable `AGY_REVIEW_GATE_ENABLED` is not `true` THE SYSTEM SHALL write no check run and dispatch nothing; manual dry runs SHALL use the read-only installation token.
- WHEN a repository is configured `shadow` THE SYSTEM SHALL write only `independent-review-shadow`, which is never a required context, and SHALL post no `APPROVED` or `CHANGES_REQUESTED` review and no dismissal, including in the missing-baseline, merge-queue and error paths. IF that cannot be guaranteed for a path THEN that path SHALL run as dry run only.
- IF a shadow repository lacks baseline protection (stale-review dismissal and strict checks or merge queue) THEN THE SYSTEM SHALL still evaluate and report it as `baseline missing, not enforceable` in shadow, SHALL NOT dispatch a formal Agy run for it (the publisher refuses shadow without a baseline), and enforce mode SHALL keep refusing such a repository.
- WHEN the controller finishes a tick THE SYSTEM SHALL publish metrics `fallback_rate`, per-provider no-verdict counts, `queue_wait_seconds` and `time_to_valid_verdict_seconds`, the last two populated from real timestamps.

Activation (deferred, not part of this implementation)

- WHILE Agy review capacity is not restored, or no separate owner activation decision is recorded, THE SYSTEM SHALL NOT be run in enforce mode anywhere, and no fixture, preview pilot or enforcement step SHALL start.
- WHEN activation is later authorized THE SYSTEM SHALL first be verified in an authorized isolated fixture: effective repository and organization rulesets, check integration IDs, stale-review dismissal, merge-queue behaviour and actual App and `claude[bot]` review counting toward the review requirement. Enforcement SHALL NOT begin on any repository before that evidence is recorded.
- The activation order SHALL be: shared hardening, then shadow, then isolated fixture, then preview pilot, then a separate owner decision on enforcement.

## Out of scope

- Any permission, App installation, ruleset, classic protection, environment, repository-variable or required-check change, and any change to mctlhq/mctl-gitops#3023. Each such change is listed as an owner-gated task with separate explicit authorization.
- Activation: the isolated fixture pilot, the mctl-gitops preview pilot and any enforce mode. They stay in tasks.md as deferred items, gated on restored Agy capacity and a separate owner decision.
- Any weakening of an existing review gate, and any substitution of an App or bot review for a human approval that policy requires.
- Approving, force-merging or re-reviewing mctlhq/mctl-gitops#3023 or any other live PR as part of this work.
- A new reviewer workflow, a second publisher, or a per-PR always-on Agy caller (superseded draft mctlhq/.github#348).
- Release-metadata-only exemptions (for example release-please PRs such as mctlhq/mctl-telegram#1481). They get the same gate. Any lighter policy is a separate owner decision.
- Fixing the merge-queue BEHIND loop itself (mctlhq/.github#351); this proposal only coordinates with it.
- Reworking mctlhq/.github#287 (closed, fixed by the classifier in `claude-review.yml`); this proposal only makes consumers run that fix.

## Open questions

- Does a `claude[bot]` or `mctl-agy-reviewer[bot]` `APPROVED` review count toward mctl-gitops' `required_approving_review_count: 1`? This is unobserved. mctlhq/mctl-gitops#3023 currently has zero reviews and is blocked. The deferred fixture must observe this; nothing may assume it.
- Which revision is the owner-approved review-policy version boundary for trusted reviewer SHAs? It is recorded as a constant on `mctlhq/.github` main, changed only by reviewed PR. Until it is set the predicate is inert (logged, not enforced); because the hardening merge SHA does not exist before that PR merges, the constant is set in a follow-up PR (tasks.md 6b) before any consumer bump.
- What actually satisfied merge of mctlhq/mctl-telegram#1485 and mctlhq/mctl-telegram#1481 (zero reviews, merged by `mashkovd`)? The classic protection endpoint returned HTTP 403 to this run. `enforcement_level: non_admins` suggests admin enforcement exemption, but required-review settings and whether an admin override was used are unknown.
- Is the reviewer App (ID 5732062, `mctl-agy-reviewer`) installed on mctl-telegram? Not observable with this run's token. The plan step 3 installed it on mctl-gitops only.
- Current values of `AGY_REVIEW_GATE_ENABLED` and `AGY_REVIEW_GATE_REPOS` in `.github` (variables API returned HTTP 403). The `skipped` scheduled runs imply `AGY_REVIEW_GATE_ENABLED != 'true'`, but this is inferred, not read.
- The ruleset `bypass_actors` field read back as `null` for mctl-gitops ruleset 18465404. That may be a permission-limited read rather than "no bypass actors".
- Cause of the scheduled controller failure 45754471179 (2026-11-26 04:19 UTC, commit 768949d, before mctlhq/.github#415) was not determined.
- Which isolated fixture repository should host the enforce-mode pilot? None was identified. Deferred with activation; the owner designates or creates one when activation is authorized.
- Final mctl-gitops end state: keep both `agy-formal-review` and `independent-review` required (Agy always runs), or replace `agy-formal-review` with `independent-review` (Agy only on fallback). The proposal migrates additively and leaves the removal to an explicit owner decision.
