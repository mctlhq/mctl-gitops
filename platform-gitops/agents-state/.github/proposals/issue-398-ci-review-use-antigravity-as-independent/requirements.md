# Provider-neutral independent review gate: activate the Claude-primary / Agy-fallback controller for mctl-gitops and mctl-telegram

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
(233dc60, PRs #400 and #415). That mechanism is `.github/workflows/review-gate-controller.yml`,
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
therefore does not build a new reviewer. It closes the gaps between the merged
code and an effective, evidence-backed, owner-gated pilot, and it records exactly
what is observed and what is unknown per repository.

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
- IF the Claude outcome is `NO_VERDICT_OTHER`, a refusal, a malformed, truncated or unreadable verdict, or the run comes from an untrusted caller THEN THE SYSTEM SHALL fail the check and SHALL NOT dispatch Agy.
- IF the consumer's Claude caller pins a `claude-review.yml` commit that does not emit the `Classify outcome:` steps THEN THE SYSTEM SHALL report the distinct reason `caller pinned before outcome classifier`. It SHALL NOT dispatch Agy and SHALL NOT mark the check successful.
- IF a formal Agy result already completed for the exact repository, PR, head and `pr_diff_digest_v1` from the trusted `agy-formal-review.yml` on `.github` main, with an unedited App `APPROVED` review carrying the matching `agy-formal:` marker THEN THE SYSTEM SHALL reuse it instead of dispatching again.
- IF the only Agy evidence is an informational comment, a check from another integration, a carried mark, a forged comment or a PR-uploaded artifact THEN THE SYSTEM SHALL NOT count it.
- IF neither provider yields qualifying evidence THEN THE SYSTEM SHALL leave the provider-neutral check failed or in progress, never successful.

Publication and identity

- WHEN the Agy publisher posts a review THE SYSTEM SHALL bind repository, PR, head, base, source run, attempt, model, digest and verdict. It SHALL re-read live head and base immediately before and after posting, and SHALL dismiss its own approval if either moved.
- WHILE the PR author equals the reviewer App identity THE SYSTEM SHALL fail the check rather than self-approve.
- THE SYSTEM SHALL NOT impersonate a human, request bypass permission, enable `GITHUB_TOKEN` approvals, or substitute an App review for a human approval that policy requires.
- WHEN validating a reusable workflow reference (`review_trust.is_trusted_reusable_ref`) THE SYSTEM SHALL accept `@main` or an exact SHA only if that SHA is reachable from `mctlhq/.github` main. An unreadable ancestry check SHALL be treated as untrusted.
- WHILE the Agy model runs THE SYSTEM SHALL keep the reviewer App key out of the model runner and SHALL NOT check out or execute PR-controlled code in privileged jobs.

Concurrency, staleness and merge queue

- WHEN a PR head moves while a formal Agy run is queued or running and its `publish` job has not started THE SYSTEM SHALL cancel the superseded run.
- WHEN duplicate events, replays or concurrent provider results arrive THE SYSTEM SHALL produce at most one effective check per (repository, PR, head, mode, digest) and SHALL never mark an older head successful.
- WHILE the provider-neutral check is required in a merge-queue repository THE SYSTEM SHALL supply that check on the queue commit only by a fresh review or by the existing `carry_proof` rules (queue parents exactly `[base, live PR head]`, identical file set and blobs, trusted head verdict that is not itself carried).
- WHILE migrating a repository THE SYSTEM SHALL keep every existing required check, including `agy-formal-review` in mctl-gitops. Any check is removed only by a separate owner-authorized ruleset change.

Activation and observability

- WHILE repository variable `AGY_REVIEW_GATE_ENABLED` is not `true` THE SYSTEM SHALL write no check run and dispatch nothing; manual dry runs SHALL use the read-only installation token.
- WHEN a repository is configured `shadow` THE SYSTEM SHALL write only `independent-review-shadow`, which is never a required context.
- IF a shadow repository lacks baseline protection (stale-review dismissal and strict checks or merge queue) THEN THE SYSTEM SHALL still evaluate and report it as `baseline missing, not enforceable` in shadow. Enforce mode SHALL keep refusing such a repository.
- WHEN the controller finishes a tick THE SYSTEM SHALL publish metrics `fallback_rate`, per-provider no-verdict counts, `queue_wait_seconds` and `time_to_valid_verdict_seconds`, the last two populated from real timestamps.

## Out of scope

- Any permission, App installation, ruleset, classic protection, environment or repository-variable change. Each is listed as an owner-gated task with separate explicit authorization.
- Approving, force-merging or re-reviewing mctlhq/mctl-gitops#3023 or any other live PR as part of this work.
- A new reviewer workflow, a second publisher, or a per-PR always-on Agy caller (superseded draft #348).
- Release-metadata-only exemptions (for example release-please PRs such as mctl-telegram#1481). They get the same gate. Any lighter policy is a separate owner decision.
- Fixing the merge-queue BEHIND loop itself (#351); this proposal only coordinates with it.
- Reworking #287 (closed, fixed by the classifier in `claude-review.yml`); this proposal only makes consumers run that fix.
- Production activation (enforce mode) in any repository without a separate owner GO_IMPLEMENT and independent review.

## Open questions

- Does a `claude[bot]` or `mctl-agy-reviewer[bot]` `APPROVED` review count toward mctl-gitops' `required_approving_review_count: 1`? This is unobserved. mctl-gitops#3023 currently has zero reviews and is blocked. The pilot must observe this; nothing may assume it.
- What actually satisfied merge of mctl-telegram#1485 and #1481 (zero reviews, merged by `mashkovd`)? The classic protection endpoint returned HTTP 403 to this run. `enforcement_level: non_admins` suggests admin enforcement exemption, but required-review settings and whether an admin override was used are unknown.
- Is the reviewer App (ID 5732062, `mctl-agy-reviewer`) installed on mctl-telegram? Not observable with this run's token. The plan step 3 installed it on mctl-gitops only.
- Current values of `AGY_REVIEW_GATE_ENABLED` and `AGY_REVIEW_GATE_REPOS` in `.github` (variables API returned HTTP 403). The `skipped` scheduled runs imply `AGY_REVIEW_GATE_ENABLED != 'true'`, but this is inferred, not read.
- The ruleset `bypass_actors` field read back as `null` for mctl-gitops ruleset 18465404. That may be a permission-limited read rather than "no bypass actors".
- Cause of the scheduled controller failure 45754471179 (2026-11-26 04:19 UTC, commit 768949d, before #415) was not determined.
- Which isolated fixture repository should host the enforce-mode pilot? None was identified. The proposal assumes the owner designates or creates one.
- Final mctl-gitops end state: keep both `agy-formal-review` and `independent-review` required (Agy always runs), or replace `agy-formal-review` with `independent-review` (Agy only on fallback). The proposal migrates additively and leaves the removal to an explicit owner decision.
