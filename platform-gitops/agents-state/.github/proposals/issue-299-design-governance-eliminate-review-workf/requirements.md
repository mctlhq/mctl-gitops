# Independent review evidence gate without workflow bootstrap deadlocks

## Context

Every mctlhq repository calls the shared reviewer
`mctlhq/.github/.github/workflows/claude-review.yml` with a pinned commit SHA.
When the pin is bumped, the bump edits the caller's entry workflow. The new
reviewer then refuses to review the PR that installs it: its "Detect
entry-workflow self-edit" step predicts the `claude-code-action` refusal and
exits 1, so the check fails closed. The only other path is `@claude review`,
which runs the old default-branch copy. Old pins predate the
`Reviewed head=<sha> base=<sha>` evidence line, so they cannot produce the
evidence that later runs and the merge automation trust.

Six open Dependabot PRs are stuck this way, all one-line bumps to
`69d0f1e1803b4c35d1c1e93f4e8b78f6816b6e4a`: mctl-pairdesk#91, mctl-docs#188,
mctl-api#908, mctl-agent#200, mctl-loyalty#47 and mctl-gitops#2356. The merge
decision also rests on mutable GitHub metadata: a `claude[bot]` review body can
be edited, and GitHub re-anchors approvals onto new merge heads (.github#283).

The issue asks for a versioned, independent evidence-verification gate. The gate
verifies four things:
- immutable attempt provenance;
- the exact head, base and content of the change;
- an authorized reviewer;
- the review verdict.

It reads them from the review-receipt infrastructure that already exists:
- ADR 025 / `orchestrator/review_receipts.py` in mctl-agents#905;
- `internal/reviewreceipts`, `internal/reviewstore` and
  `execution_attempt_v1` in mctl-api#895, #896 and #897.

GitHub review state is never an input. The gate also needs two more things:
- a narrowly scoped, audited, time-bound owner-authorized recovery path, which
  must not be a standing bypass;
- a documented one-time bootstrap for the six PRs.

This proposal is the design and the in-repo reference model only. It stops for
human approval before any implementation.

## User stories

- AS a repository maintainer I WANT a routine reviewer pin bump to pass the
  review gate without disabling any protection SO THAT the reviewer stays
  current in all callers.
- AS the org owner I WANT the merge gate to trust only sealed review receipts
  bound to the exact commits SO THAT edited, moved or forged GitHub approvals
  cannot satisfy it.
- AS a security reviewer I WANT a PR that rewrites the reviewer to be unable to
  review itself into a PASS SO THAT the reviewer cannot be subverted through
  its own update.
- AS the org owner I WANT a single-use, expiring, two-person recovery grant
  bound to one exact change SO THAT a broken or bootstrapping gate can be
  unblocked without a standing bypass.
- AS an auditor I WANT every gate decision, receipt and recovery grant to be
  recorded with its inputs SO THAT I can reconstruct why a change was allowed
  to merge.
- AS an operator I WANT a written, step-by-step bootstrap for the six blocked
  PRs SO THAT they are merged once, by a human, with exact SHA checks and
  post-merge verification.

## Acceptance criteria (EARS)

Evidence and verdict

- THE SYSTEM SHALL decide the gate only through `EvaluateReviewGate`, the
  single evaluator in mctl-api `internal/reviewreceipts/gate.go`, which mirrors
  mctl-agents `evaluate_review_gate`. It SHALL apply that evaluator to a new
  ReviewSubject kind, `pull_request`, under a new contract version. It SHALL
  NOT add a second, independent evaluator or trust store.
- THE SYSTEM SHALL bind a `pull_request` subject to all of these values:
  - `repository`;
  - `pr_number`;
  - `base_ref`;
  - `merge_base_sha`;
  - `head_sha`.
  Each SHA SHALL be a full 40- or 64-character lowercase hex string.
  `base_sha` (the base tip observed at review time) and `diff_digest`
  (`pr_diff_digest_v1`) SHALL be recorded as provenance.
- WHEN the gate evaluates a PR THE SYSTEM SHALL read the live head, base ref
  and merge base from GitHub at evaluation time. It SHALL compare them with each
  receipt's subject binding by canonical bytes.
- IF the live head, base ref or merge base cannot be read, or a read is
  partial, THEN THE SYSTEM SHALL report the gate as `unknown` and post a
  non-success check.
- IF no receipt matches the live binding THEN THE SYSTEM SHALL report
  `missing` (no receipts at all) or `stale` (receipts only for other bindings).
  Either answer SHALL post a non-success check.
- IF the PR's base ref is retargeted, or the head changes because of a push or
  an update-branch merge, THEN THE SYSTEM SHALL treat every earlier receipt as
  historical and SHALL NOT report `satisfied` until a receipt for the new
  binding exists.
- THE SYSTEM SHALL NOT read GitHub pull-request review state, review bodies,
  `reviewDecision` or the `Reviewed head= base=` line as gate input. A forged,
  edited, dismissed or re-anchored approval SHALL have no effect on the gate.
- IF the receipt store, the policy file or GitHub is unavailable THEN THE SYSTEM
  SHALL report the gate as `unknown` and SHALL NOT post success.

Reviewer authorization and provenance

- WHEN a reviewer run submits a review request or receipt THE SYSTEM SHALL
  authenticate it with a GitHub Actions OIDC token (audience
  `https://api.mctl.ai`). It SHALL accept the submission only when all of these
  hold:
  - the `repository` claim equals the subject repository;
  - the `job_workflow_ref` claim names
    `mctlhq/.github/.github/workflows/claude-review.yml`;
  - the git blob SHA of that file at `job_workflow_sha` is listed as an
    accepted reviewer version in the gate policy.
- THE SYSTEM SHALL record the attempt provenance on the request and receipt as
  immutable rows. The provenance is these claims: `run_id`, `run_attempt`,
  `job_workflow_sha`, the reviewer blob SHA, `workflow_ref`, `workflow_sha`,
  `event_name`, `actor` and `repository_id`.
- IF a receipt's OIDC run (`run_id`, `run_attempt`, `job_workflow_sha`) differs
  from the run that opened its request, or its nonce was already consumed,
  THEN THE SYSTEM SHALL refuse the receipt.
- IF the PR's changed-file list includes the entry workflow path named in the
  receipt's `workflow_ref`, and that `workflow_ref` was not loaded from the
  default branch, THEN THE SYSTEM SHALL refuse the receipt as
  `review_entry_untrusted`.
- IF the reviewer's principal appears in the request's `author_actors` THEN THE
  SYSTEM SHALL classify the receipt as not independent.
- THE SYSTEM SHALL derive the receipt verdict from the reviewer run's own
  executed tool calls in its execution output, never from the model's prose or
  from GitHub. The verdict is the last successful review POST bound to the
  pinned head.
  - `APPROVE` SHALL map to `PASS`.
  - `REQUEST_CHANGES` SHALL map to `CHANGES_REQUESTED`.
  - Anything else, including no verdict, SHALL map to `UNOBSERVABLE`.

Routine pin upgrades and self-update

- WHEN a caller PR changes only the `uses:` pin of `claude-review.yml` from one
  accepted reviewer version to another THE SYSTEM SHALL let the gate be
  satisfied by a receipt from any accepted reviewer version run from the
  default-branch entry workflow. It SHALL NOT require any change to
  rulesets, branch protection or bypass lists.
- WHEN a PR in mctlhq/.github modifies `claude-review.yml` THE SYSTEM SHALL
  accept a receipt only from a reviewer whose blob is already accepted in the
  policy. A receipt produced by the PR's own modified reviewer SHALL be refused.
- WHILE an accepted reviewer version is in the policy, until its `not_after`
  date, THE SYSTEM SHALL keep accepting its receipts. This keeps version N-1
  usable while callers move to version N.
- IF a change to the gate policy would leave zero accepted reviewer versions,
  or would remove every version currently pinned on a caller's default branch,
  THEN THE SYSTEM SHALL fail the policy file's validation in CI.

Recovery (no standing bypass)

- WHEN a direct human platform admin requests a recovery grant THE SYSTEM SHALL
  bind the grant to one exact `pull_request` subject binding. It SHALL record a
  reason and a tracking issue, cap the TTL at 24 hours, and create an `aar_`
  action approval of kind `review-gate:recovery` whose `artifact_hash` is the
  subject binding digest.
- THE SYSTEM SHALL count a recovery grant only when all of these hold:
  - it was approved by a direct human admin who is neither the requester nor
    the PR author;
  - it is unexpired and unconsumed;
  - its binding equals the live binding;
  - the repository is eligible in the gate policy;
  - a manual review receipt with outcome `PASS` exists for the same binding,
    from a reviewer who is not the PR author.
- WHEN a PR satisfied by a recovery grant is merged, or the grant's TTL
  passes, THE SYSTEM SHALL mark the grant consumed or expired. A consumed or
  expired grant SHALL never satisfy the gate again.
- THE SYSTEM SHALL write an audit entry for each of these events:
  - a recovery grant is requested, approved, refused, evaluated, consumed or
    expired;
  - a gate decision is posted.
  Each entry SHALL carry the subject binding and the grant id.
- THE SYSTEM SHALL NOT merge a PR, enable auto-merge, or change a ruleset,
  branch protection or bypass list, through the gate or the recovery grant.

Same-revision reconsideration

- WHEN a write-access human explicitly re-triggers review on an unchanged
  binding THE SYSTEM SHALL open a new request with a new nonce. The newest
  receipt in ingest order SHALL decide, which is the existing gate rule. Every
  earlier receipt SHALL remain in the pool and in the audit trail.
- WHILE a reconsideration request is open THE SYSTEM SHALL keep the gate at its
  previous decision until the new receipt is ingested. A failed
  reconsideration run SHALL NOT turn an earlier `CHANGES_REQUESTED` into
  `satisfied`.

Rollout and the six PRs

- THE SYSTEM SHALL ship receipt emission in `claude-review.yml` behind a
  `receipt-mode` input (`off` | `shadow` | `enforce`), with `off` as the
  default. With `off`, the reusable workflow's observable behaviour SHALL be
  unchanged.
- THE SYSTEM SHALL document a one-time bootstrap procedure for the six PRs in
  `docs/governance/review-evidence-gate-bootstrap.md`. The procedure SHALL
  cover:
  - exact head, base and merge-base SHA capture;
  - a diff-tree check that the only change is the `uses:` pin, moving to
    `69d0f1e1803b4c35d1c1e93f4e8b78f6816b6e4a`;
  - independent human review;
  - an owner recovery grant;
  - a human merge with `--match-head-commit`;
  - audit;
  - post-merge verification.
  Nothing in the procedure SHALL be automated into a merge or a protection
  change.
- THE SYSTEM SHALL include regression tests for each of these cases:
  - a self-update of the reviewer;
  - each of the six caller pin bumps;
  - malicious, edited, stale and re-anchored approvals;
  - receipt tampering and replay;
  - a changed base;
  - same-revision reconsideration;
  - recovery-grant misuse.

## Out of scope

- Merging, approving or re-reviewing the six PRs, and changing any ruleset,
  branch protection, bypass list or required-check configuration. Those are
  human steps in the documented procedure, taken after approval.
- Implementing the mctl-api and mctl-agents changes inside this repository.
  They are cross-repo follow-ups, filed as issues by task 9.
- Migrating mctl-agents `run_shepherd.GATING_BOTS` and the pr-steward skill
  (mctl-claude-remote `skills/pr-steward/SKILL.md`) away from GitHub review
  state. This is a recommended follow-up, not a deliverable here.
- The agy reviewer (`agy-review.yml`). It is non-blocking (`blocking: false`)
  and is not a merge gate.
- Fixing .github#283 itself. Its dedup hardening stays as it is, as a
  cost-saving dedup, not as a merge gate.

## Open questions

- Which component treats the six PRs as blocked. On mctl-api, mctl-gitops,
  mctl-pairdesk, mctl-docs and mctl-agent, the rulesets require one approval and
  build checks, and do not require `claude-review / review`. Each PR shows
  `reviewDecision=APPROVED`, from an old-pin `@claude review` run without the
  evidence line. mctl-api#908 and mctl-pairdesk#91 report
  `mergeStateStatus=UNSTABLE`; mctl-gitops#2356 reports `UNKNOWN`. The visible
  blocker is the failed `claude-review / review` check plus the pr-steward
  green/evidence requirement. Whether another, invisible rule (for example an
  org ruleset) applies was not observable. The design does not depend on the
  answer.
- Whether mctl-loyalty has any rules. `GET rules/branches/main` returned `[]`.
  That could mean no rules, or rules this token cannot see.
- Which check surface to use. The design uses a check run posted by mctl-api
  through the mctl GitHub App, required with an app `integration_id`. The
  ruleset field exists and is used today: mctl-gitops requires
  `reserved-hosts` with `integration_id: 15368`. Two facts were not observed:
  - whether mctl-app has `checks: write`;
  - whether mctl-api receives `pull_request` webhooks.
  The alternative is an org "required workflow" from mctlhq/.github (see
  Alternatives in design.md).
- How strictly to bind the base. This proposal binds to `merge_base_sha` plus
  `base_ref`. Advancing the base tip without touching the head keeps the diff
  identical and does not invalidate the receipt. Retargeting or update-branch
  does invalidate it. The owner may prefer strict base-tip binding, which
  matches the current `Reviewed head= base=` semantics, at the cost of
  re-reviewing every open PR on every base push.
- Whether the six PRs should wait for the gate's per-repo cut-over (the default
  in this design), or be merged earlier by the owner under the current rulesets,
  following the same procedure without the gate's recovery grant. That is an
  owner decision.
- The precise references of mctl-api#917 and mctl-agents#975 named in the
  issue. Neither proposal was found in gitops agents-state under those
  repositories. mctl-agents#917 is an unrelated Claude-Ultra spike.
