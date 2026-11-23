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

## Markerless authoritative-run correction

- Once a newer run is correlated to the current PR/head dispatch intent, it SHALL remain authoritative in queued, in-progress, and completed states even if it never posts a marker. It SHALL never disappear from selection and reveal an older PASS.
- A completed correlated run without a valid semantic marker SHALL be treated as `reviewer_error`: it blocks merge and follows the bounded wait-to-`review-stuck` policy. A marker is required only to establish semantic `clean` or `findings`; absence cannot approve.
- Correlation for a markerless completed run SHALL use the durable intent plus trusted workflow ID/event/ref/run-name correlation and run ID/attempt metadata. Cleanup of dispatch intents occurs only after the result is durably consumed or explicitly superseded by a newer correlated run.

## Pending-intent and reviewer-wait identity corrections

- A durable current-head dispatch intent SHALL itself be newer pending authority from creation time, before an Actions run is visible. It SHALL block approval by every older PASS until correlated, explicitly superseded, or durably resolved as dispatch/reviewer failure.
- Lost responses and delayed run visibility SHALL use bounded correlation retries. Exhaustion records a `reviewer_error` for that intent and follows bounded wait-to-`review-stuck`; it never deletes the intent and reveals an older PASS.
- Reviewer wait state SHALL be keyed by `{source, head_sha, authority_identity}`, where authority identity is pending correlation ID or authoritative `run_id:run_attempt`. When authority changes on the same head, that source's wait counter SHALL reset atomically so the new execution receives its full bounded response window.

## Exact-PR authority and durable clearance corrections

- For `pull_request`-triggered executions, authoritative Agy run selection SHALL match the exact target PR association, head repository, head ref, workflow identity, and exact reviewed `head_sha`; SHA equality alone is insufficient.
- A valid authoritative `findings` marker containing no P1/P2 findings SHALL count as a successful, nonblocking response. P3/P4 findings SHALL remain advisory evidence but SHALL NOT trigger `address-review` or missing-reviewer timeout.
- The shepherd SHALL persist exact per-source P1/P2 finding history across head changes. On a later clean merged head, `cleared_findings` identities and counts SHALL be derived idempotently from that prior-head history, not solely from the final current-head `AggregatedReview`.
- Persisted history and clearance derivation SHALL survive restart, avoid double-counting repeated observations, and retain source attribution plus the head on which each blocker was observed and cleared.

## Same-head lifecycle-event authority correction

- A same-head `ready_for_review` or `reopened` lifecycle event SHALL invalidate earlier Agy authority from the event timestamp/generation, before the resulting Actions run is indexed.
- The shepherd SHALL read the PR lifecycle timeline (or an equivalent durable event projection) and treat the newest relevant event as pending authority until a matching Agy run created after that event is visible and resolved. Older same-head PASS evidence cannot approve during this gap.
- Event-to-run correlation SHALL include exact PR, head repository/ref/SHA, workflow identity, and run creation time after the lifecycle event. Bounded missing-run handling follows the existing fail-closed reviewer-error policy.

## Trusted outcome, authority ordering, and rollback corrections

- Agy comments SHALL still contain exact reviewed head_sha, run_id, run_attempt, PR number, correlation ID where applicable, and semantic outcome for operator evidence. The comment actor/marker is not by itself trusted authorization: gating SHALL obtain the semantic verdict/findings payload from an immutable artifact (or equivalently integrity-protected output) produced by the correlated trusted reusable-workflow run, verify its digest/identity through the Actions API, and require it to agree with the comment. Missing, forged, or disagreeing evidence fails closed as reviewer_error.
- Authority SHALL have one durable total order across lifecycle generations, dispatch intents, and correlated runs. Before allocating a dispatch intent, synchronize and persist the latest PR lifecycle watermark; the new intent is allocated in the next serialized generation. A subsequently observed reopened/ready_for_review event with a new event identity advances the generation and supersedes that intent even if Actions indexing is delayed. A delayed duplicate or event at/below the persisted watermark cannot supersede newer authority. Correlated runs inherit, never invent, their intent/event generation.
- Blocking-finding history SHALL be keyed by stable source plus exact finding identity, independent of head. Reviewed heads/run identities are an idempotent observation set on that record. Repeated observations of one unresolved blocker across heads produce one history/clearance record; genuinely distinct exact identities remain separate.
- Rollback SHALL first disable repository-level Agy required gating, stop new backfill dispatches, settle or explicitly supersede all pending intents/runs, and persist their terminal evidence. Only after that drain may the parser/aggregator and reusable-workflow pin be reverted. Re-enabling gating requires a new verified current-head backfill; stale pre-rollback authority is never revived.

## Amendment 2026-11-10: owner-required behaviour and current facts (authoritative)

This amendment supersedes any conflicting text above. Code references are to
`mctlhq/mctl-agents` `origin/main` at `46ccddc`; the line numbers in the
original text above are stale (the module is now about 5,400 lines).

### Owner-required invariant

A P1 or P2 from ANY required reviewer on the CURRENT head blocks merge, no
matter how green CI is and no matter what another reviewer concluded. The
decision lives in `decide()`, which both the shepherd tick and the gated merge
activity (`orchestrator/temporal/activities/pr_merge.py`) call, so one fix
covers both merge paths.

### Reviewers that exist today

- Required reviewers: Claude (`claude[bot]`) and Agy (`github-actions[bot]`
  plus an Agy marker).
- Copilot review is gone (subscription cancelled 2026-10-01). It must not be
  waited on and must not gate. Its observe-only read may be deleted.
- The Codex connector is silent and is not a gate (last review in the org on
  2026-09-22; Auto review is off). The declarative config SHALL NOT wait on it
  and SHALL NOT list it as required. If it does post a P1/P2 on the current
  head, that finding still counts like any bot finding (existing #67
  behaviour), but its silence is never a wait.

### Reproductions the tests must encode (live evidence)

| Case | Head | What happened | Required outcome |
|---|---|---|---|
| mctl-agents#234 | n/a | Agy alone had the P1 (path traversal) and three P2; the fix bundle followed Claude only | Agy-only P1 produces `address-review`; the bundle carries every current-head blocker |
| mctl-agents#409 | `143312e4` | Claude APPROVED with 0 P1/P2; Agy alone had a P2; shepherd logged `codex_*`, `connector_*`, `copilot_*` inputs, no `agy_*`, and chose `wait` | `address-review` pinned to that head |
| mctl-api#968 | `48405b17` | Claude APPROVED 20:25:58Z; Agy `<!-- VERDICT: FAIL:P1,P2 -->` 20:37:07Z on the same head; CI green; merged 20:44:36Z by the mctl-agents app | never `merge`; blocked while the verdict stands |
| mctl-api#995 | `6884e9a2` | see the exact sequence below | never `merge`; blocked while the verdict stands |

Exact mctl-api#995 sequence (UTC, 2026-11-10), head `6884e9a2844458eccb4bd768ceb7801242b562ce`:

1. 05:04:47 first commit `dd7d02ca`; 05:05:23 PR opened.
2. 05:08:05 Claude CHANGES_REQUESTED on `dd7d02ca` (2 P2). 05:12:22 Agy PASS on `dd7d02c`.
3. 05:25:04 fix commit `4998ef15`. 05:26:25 Claude CHANGES_REQUESTED (1 P2). 05:34:12 Agy `FAIL:P2` on `4998ef1`.
4. 05:40:14 fix commit `6884e9a2` (the final head). 05:41:44 Claude APPROVED, 0 P1/P2, 2 P3.
5. 05:40:30 to 05:44:53 every required check green on the final head (`claude-review / gate`, `claude-review / review`, `lint`, `test`, `agent-trailer / check`, CodeQL, Trivy, govulncheck).
6. 05:48:53 Agy review on the SAME head: `_Model: ... commit \`6884e9a\`._`, one P2 (`Store.EnableWireVersions` never invoked at startup, so reads fail closed), trailer `<!-- VERDICT: FAIL:P2 -->`. The `agy-review / review` job nevertheless concluded `success` at 05:48:58.
7. No later push, no later reply and no human comment on the PR. 06:07:38 merged by the mctl-agents app, 19 minutes after the Agy FAIL.

The regression scenario for #995 is therefore: the blocking verdict arrives AFTER
the Claude approval and AFTER required checks are green, on the same head, and
the merge must still not happen. The scenario also covers the settle window
(the Agy comment landed 8 minutes after the push) and the next tick after it.

### Agy evidence contract (what counts as a current-head Agy review)

The "contract corrections" above assumed Agy comments carry no reviewed head.
That is no longer true. Two shapes exist in production and both bind to a head:

- mctlhq shared workflow: first line `<!-- agy-review -->`, header line
  `_Model: <model> . commit \`<7 hex>\`._`, ends with one
  `<!-- VERDICT: PASS|FAIL:P1|FAIL:P2|FAIL:P1,P2 -->` trailer. The reader
  already exists (`_AGY_COMMIT_RE`, `_AGY_VERDICT_RE`, `_parse_agy_findings`).
- Livri shared workflow (`Livri-app/.github`): first line
  `<!-- agy-review sha=<40 hex> -->`, and a `... failed -->` variant for a
  reviewer failure. Exact full-SHA equality.

Requirements:

- The actor must be `github-actions[bot]` AND the first line must be the Agy marker (the actor login is shared).
- Head binding: a `commit` prefix of at least 7 hex must match the current head AND no other head seen on the PR; a multi-head match is ambiguous and counts as missing. A `sha=` value must equal the full 40-hex head; a shorter value is not authoritative. A comment with neither is NOT authoritative (no timestamp inference), so it counts as "missing". A marker quoted inside a finding body is ignored: only the first line of the comment counts.
- The verdict trailer is the semantic result; the LAST trailer in the comment wins (a finding may quote one). The `agy-review` job conclusion is never the verdict.
- `FAIL:P1`, `FAIL:P2` or `FAIL:P1,P2` on the current head is a blocker by itself. If findings parse, each becomes a normalized finding. If none parse, the shepherd SHALL synthesize one blocker carrying the verdict, comment URL and head, and route to `address-review`. An unparsed verdict never degrades to `wait` or to clean.
- `PASS` with parseable P1/P2 items is contradictory; treat the items as blockers.
- If several Agy comments are bound to the same head (a rerun), the newest by `created_at` then id is authoritative.
- A `FAIL` verdict naming only P3 is non-blocking.
- A `failed` marker, a no-verdict "did not produce a review" comment, or no bound comment at all means the required reviewer has not responded: `wait`, then bounded `review-stuck`. Never approval, never merge.
- A comment bound to an older head is ignored for blocking, and its absence on the new head is a wait, not a pass.
- Normalized fields: severity, file, message, proposed fix, source (`agy`), URL (`html_url`), reviewed head SHA, comment id.

### Reads: could not observe is not observed absent

- A failed, partial or malformed read of reviews, inline comments, issue comments or reactions SHALL yield an explicit unknown state for the affected reviewer, not an empty list. Today `read_codex_review` and `_read_agy_advisory`-style reads degrade failures to `[]` (`run_shepherd.py:2251`, `2310`, `2344`, `2418`).
- With any gating read unknown, `decide()` returns a distinct non-merge outcome (for example `review-unknown`), bounded by the existing counter pattern into `review-stuck`. A later page failing after earlier pages succeeded is a failed read.
- Pagination: every list read goes through the list-aware helper (`_gh_api_list`), never concatenated `--paginate` output.

### Merge evidence

Before a merge is attempted, and again in the `merged` status write, record per required reviewer: responded or not, the bound comment id or URL, the verdict, the head SHA it was bound to, and which findings were cleared. A merge whose evidence lacks a bound verdict for every required reviewer SHALL be refused.

### Acceptance additions

- Mutation-verified definition of done: every regression test below is shown to FAIL with the fix reverted (remove the agy input from `decide()` and watch each fail), and the detector is shown green on a converged input and red on a deliberate mutation.
- When one instance is found, sweep the whole module for the class: every read in `run_shepherd.py` and `pr_merge.py` that degrades an error to an empty collection.

### Unchanged exceptions

Manual admin merge for `claude-review.yml` pin bumps, release-please PRs, `NEVER_MERGE_SERVICES` and `needs_human_kind` agent-definition PRs are unchanged. This work only adds refusals.

### Capability and rollout

- Agy is required only where the repo has an `agy-review.yml` caller with `blocking: true`. Repos with no Agy workflow or `blocking: false` default to `required=False`; required is opt-in explicit data.
- Before enabling required gating: list open PRs whose current head has no bound Agy comment and either re-trigger Agy or accept the wait.
- Reviewer state can change between the last read and the merge call. `--match-head-commit` pins the head, not reviewer state. The merge path re-aggregates and re-decides immediately before merging; the remaining window (a verdict landing after that read) is accepted.

### Unchanged non-goals

Required-check normalization stays in #411. `MAX_REVIEW_ATTEMPTS` and the settle window are untouched.

### Owner decisions (not decided by this amendment)

See the PR description. They are D1 to D6 and the draft deliberately leaves each open.
