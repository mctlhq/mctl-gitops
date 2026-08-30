# fix(shepherd): aggregate blocking findings from Claude and Agy reviews

## Context

The Tier 3 PR shepherd (`orchestrator/run_shepherd.py`) decides whether a PR
is mergeable by reading exactly one review bot's signal for "has a required
reviewer responded" (`REVIEW_BOT = "claude[bot]"`), while findings are
collected from a hard-coded `GATING_BOTS = (REVIEW_BOT, CODEX_CONNECTOR_BOT)`
tuple (`orchestrator/run_shepherd.py:84-91`). The repo also runs a second,
independently-blocking review workflow — `.github/workflows/agy-review.yml`,
which calls the reusable `mctlhq/.github` "Agy PR review" workflow with
`blocking: true` — but `run_shepherd.py` has no awareness of it at all: Agy
is not in `GATING_BOTS`, has no parser for its comment format, and cannot
drive `has_responded`.

On `mctlhq/mctl-agents#234` this produced a real gap: Agy reported a P1
path-traversal finding plus three P2 findings; the shepherd's fix bundle
(built from `read_codex_review()` + `decide()` + `apply_followup()`) only
ever saw Claude's review and left Agy's findings unaddressed. After the
follow-up push, Agy still reported two P2 and two P3 findings that the
shepherd never surfaced to the implementer. `mctlhq/mctl-agents#67` set the
precedent for widening gating beyond a single bot (adding
`chatgpt-codex-connector[bot]` to `GATING_BOTS`), but that fix hard-coded a
second bot rather than making the reviewer set declarative, and it did not
address what happens when a required reviewer never responds at all. This
proposal generalizes the gating model so every configured reviewer —
Claude, Agy, and the existing Codex connector — contributes to one
head-pinned, deduplicated, source-attributed finding set, and so a silent or
failed required reviewer can never be mistaken for approval.

## User stories

- AS the mctl-agents platform operator I WANT every configured gating
  reviewer's P1/P2 findings to block merge SO THAT a defect one reviewer
  misses (like the #234 path-traversal finding Claude did not flag) still
  stops the PR.
- AS the mctl-agents platform operator I WANT reviewer sources declared in
  one place instead of hard-coded bot logins SO THAT adding or removing a
  gating reviewer (as happened for the Codex connector in #67, and now for
  Agy) does not require re-deriving the has_responded/parsing logic from
  scratch.
- AS a proposal author waiting on shepherd SO THAT I never see a PR merge
  while a required reviewer's finding on the current head is unaddressed,
  and SO THAT I never see the shepherd stall forever because a reviewer
  silently failed to post anything.
- AS a human triaging a stuck PR I WANT the merge/attempt evidence to show
  which reviewers actually responded and which findings were cleared SO
  THAT I can tell "Agy never ran" apart from "Agy approved."

## Acceptance criteria (EARS)

- WHEN the shepherd evaluates a PR THE SYSTEM SHALL build the gating
  reviewer set from a declarative registry that includes at minimum Claude
  review (`claude[bot]`) and Agy PR review, rather than branching on one
  hard-coded primary-bot constant.
- WHEN the shepherd fetches PR reviews and comments THE SYSTEM SHALL parse
  Agy's top-level marker/comment format into normalized findings carrying
  severity, file path (when present), message, proposed fix (when present),
  source name, source URL (the comment's `html_url`), and the head SHA the
  finding was reviewed against.
- WHEN any configured gating reviewer has posted a P1 or P2 finding anchored
  to the PR's current head SHA THE SYSTEM SHALL return the `address-review`
  decision, and THE SYSTEM SHALL forbid the `merge` decision while any such
  finding remains.
- WHEN the same underlying defect is reported by more than one configured
  reviewer THE SYSTEM SHALL deduplicate it into a single finding in the
  bundle passed to the implementer, WHILE preserving the list of reviewers
  that reported it (source attribution is never dropped, even when merged).
- WHEN a PR's head SHA advances past a finding's recorded head SHA (a
  follow-up push landed) THE SYSTEM SHALL exclude that finding from the
  current decision, mirroring the existing `findings_p1_p2(at=head_sha)`
  behavior for Claude and the Codex connector.
- IF a required gating reviewer's workflow fails, times out, or has not
  posted any response for the current head THEN THE SYSTEM SHALL NOT treat
  that silence as approval: THE SYSTEM SHALL return `wait` while the
  no-response window is within policy, and SHALL flip the proposal to
  `review-stuck` once that window is exceeded, exactly as an unresolved
  P1/P2 does today for the address-review retry cap.
- WHEN the shepherd runs `apply_followup` to build the implementer's review
  bundle THE SYSTEM SHALL include every current-head P1/P2 blocker from
  every required reviewer, not only Claude's.
- WHEN the shepherd merges a PR THE SYSTEM SHALL record, alongside the
  existing `merged_at`/`merge_commit` fields in `.status.yaml`, which
  configured reviewers responded on the merged head and how many findings
  from each were cleared.
- WHILE a PR is open and under shepherd control THE SYSTEM SHALL keep
  `decide()` a pure function of its inputs (PR snapshot, aggregated review,
  `now`) so the new reviewer-timeout policy is testable with hand-built
  fixtures, consistent with the existing design constraint documented at
  `orchestrator/run_shepherd.py:1044-1056`.

## Out of scope

- Changing Copilot's status from observed-only/advisory to gating —
  `read_copilot_review()` stays non-blocking (`design.md L100-108`,
  referenced at `orchestrator/run_shepherd.py:1006-1011`).
- Treating a green GitHub Actions workflow conclusion (e.g. the Agy job
  simply completing) as equivalent to an approving semantic review — a
  completed workflow with zero findings is not proof Agy actually reviewed
  the diff; only an explicit Agy comment/marker on the current head counts.
- Adding further gating reviewers beyond Claude, the Codex connector, and
  Agy in this change — the registry is built for extensibility but this
  proposal only populates it with the three real sources that exist today.
- Any change to `MAX_REVIEW_ATTEMPTS`, the merge settle window
  (`SHEPHERD_MERGE_SETTLE_MIN`), the dev-loop ownership sweep
  (`_dev_loop_owns`), or the reconcile/status-projection machinery
  (`reconcile_one`) — those are independent of reviewer aggregation.
- Building a generic plugin API for third-party reviewer definitions
  (config file, dynamic loading). The declarative registry is an in-module
  Python data structure, not an externally configurable plugin system.

## Open questions

- Agy's exact bot/actor login (as it appears in `user.login` on
  `gh api .../reviews`, `.../pulls/<n>/comments`, and
  `.../issues/<n>/comments`) is not visible from this clone — the reusable
  workflow lives in `mctlhq/.github` and PR #234's raw API payloads were not
  available to this investigation. Recorded assumption: the implementer
  SHALL confirm the actual login (and whether Agy posts as a review, a
  line-anchored review comment, or a top-level issue comment) by pulling
  the real event payloads from `mctlhq/mctl-agents#234` via `gh api` before
  writing the parser, and SHALL treat the login as a named constant
  (`AGY_BOT`) exactly like `REVIEW_BOT` and `CODEX_CONNECTOR_BOT`.
- The issue does not specify Agy's literal severity-marker syntax (badge,
  bold prefix, or a custom "top-level marker" block, per the issue's own
  wording). Recorded assumption: the parser SHALL be written defensively —
  reuse `_extract_severity()`'s multi-pattern approach and extend it with
  whatever concrete markers PR #234's payload shows, rather than guessing a
  single format.
- The issue does not specify how long the shepherd should wait for a
  required reviewer before flipping to `review-stuck` on a *no-response*
  path (as opposed to the existing `MAX_REVIEW_ATTEMPTS` cap on
  *address-review* loops). Recorded assumption: reuse the same
  `MAX_REVIEW_ATTEMPTS`-style tick-counter pattern, scoped per head SHA, at
  a default of 3 ticks (~15 minutes at the 5-minute cron cadence), so a
  never-configured or perpetually-broken reviewer workflow cannot wedge a
  proposal forever, without introducing a second unrelated timeout
  constant family.
- Whether Agy is meant to be `required` (gating on silence, like Claude) or
  merely a second gating-on-findings source (like the Codex connector,
  which gates on findings but never drives `has_responded`) is not fully
  explicit in the issue. The issue's acceptance criteria say "a reviewer
  workflow failure or missing response has an explicit policy" in the
  general case, and `agy-review.yml` sets `blocking: true`. Recorded
  assumption: Agy is configured as `required=True` (drives its own
  no-response timeout, like Claude) since `blocking: true` is the
  strongest available signal that the org intends Agy to be a required
  gate, not an advisory one like Copilot or the best-effort Codex
  connector.

## Contract corrections before acceptance (authoritative)

PR #234 proves Agy currently posts a top-level `github-actions[bot]` comment with `<!-- agy-review -->`, but no `commit_id` or reviewed head SHA.

- Agy SHALL NOT count as a current-head response until its machine marker carries the exact reviewed head SHA. Timestamp/latest-comment inference is forbidden.
- First update `mctlhq/.github` so success, findings and reviewer-failure comments include `head_sha:<40-hex>` and `run_id`; then pin mctl-agents to that reviewed shared-workflow commit. This is prerequisite to `required=True`.
- Dispatch SHALL match actor plus Agy marker because `github-actions[bot]` is shared.
- Missing, malformed, failed or stale-head Agy evidence means wait then bounded `review-stuck`, never approval.
- Persist `reviewer_wait_head_sha` and per-source wait counters; reset all atomically on head change.
- Deduplicate by exact path+line+normalized message, or exact normalized-message hash when location is absent. No fuzzy collapse of unlocated findings.

## P1 rollout and run-authority corrections (authoritative)

- Agy markers SHALL include exact 40-hex `head_sha`, Actions `run_id`, and `run_attempt` (or equivalent monotonically ordered attempt identity).
- For a PR head, the authoritative Agy result SHALL be the newest non-superseded Agy workflow execution ordered by run number/ID and run attempt. A marker from an older run cannot approve or block once a newer run exists. A newer queued or in-progress run blocks merge; the newest completed failure blocks and follows the bounded wait-to-`review-stuck` policy; only the newest completed PASS whose marker identity and SHA match may approve.
- Before Agy becomes `required=True`, the rollout SHALL enumerate every open target PR, dispatch or rerun the pinned Agy workflow for its current head, and verify a new-format current-head marker. Updating the reusable-workflow pin alone is insufficient because it does not trigger existing pull requests.
- Legacy Agy comments without the marker identity remain non-authoritative. PR #234 is an explicit rollout fixture and must receive a current-head rerun before required gating is enabled.

## Agy outcome and executable backfill corrections (authoritative)

- The authoritative Agy marker SHALL distinguish `clean`, `findings`, and `reviewer_error`; gating SHALL use the marker's semantic outcome and payload, not the Actions conclusion alone.
- A current-head authoritative `findings` marker with parseable P1/P2 findings SHALL return `address-review`, even when the blocking Actions run concludes `failure`. A `reviewer_error` marker or failed run without valid findings SHALL follow bounded wait-to-`review-stuck`. Neither case may approve.
- The pinned mctl-agents caller workflow SHALL provide an executable, permission-checked backfill entry point (for example `workflow_dispatch` with PR number and exact head SHA). It SHALL validate that the supplied SHA is still the PR's current head before invoking the pinned reusable workflow.
- Rollout SHALL use that entry point for every already-open PR and record the resulting run identity and exact-head marker before enabling required gating.

## Explicit review target and Actions authority corrections

- A manual backfill run SHALL execute trusted workflow code from the default branch while taking explicit `repository`, `pr_number`, and exact `head_sha` inputs. It SHALL fetch and review that exact commit (for example the validated `refs/pull/<n>/head` object), never infer the target from `GITHUB_SHA` or a missing `pull_request` event.
- The caller SHALL validate immediately before review and before publishing the marker that the PR's live head still equals the supplied SHA. The reusable workflow and reviewer receive the explicit target SHA and PR number; every comment and marker is posted to that PR and bound to that SHA.
- Authoritative run selection SHALL query GitHub Actions run metadata, including queued/in-progress runs and rerun attempts. The additional paginated/cached Actions lookup is required and replaces any earlier same-call-count/no-new-network-call constraint.

## Dispatch-run correlation correction

- Authority lookup SHALL NOT filter `workflow_dispatch` runs by Actions `head_sha`, because it represents the dispatch ref rather than the reviewed PR head.
- Each backfill dispatch SHALL carry a cryptographically unique correlation ID plus explicit PR number and reviewed head SHA. Trusted workflow metadata (for example `run-name`) SHALL expose that correlation ID before comments are posted, and a durable dispatch-intent record SHALL bind it to repository, PR, SHA, workflow identity, and creation time.
- Queued/in-progress dispatch runs SHALL be joined to that intent by workflow identity, event type, trusted default-branch ref, correlation ID, and time window; completed results additionally require marker `run_id`, `run_attempt`, correlation ID, PR, and exact reviewed SHA. PR-triggered runs may continue to use Actions `head_sha`.
