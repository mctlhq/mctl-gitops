# Design: issue-240-fix-shepherd-aggregate-blocking-findings

## Current state

All shepherd logic lives in one module, `orchestrator/run_shepherd.py`
(2110 lines), backed by `tests/test_run_shepherd.py` and a narrow sub-agent
prompt at `agents/_shepherd/.claude/agents/shepherd.md`.

Reviewer awareness today is two hard-coded module-level constants
(`orchestrator/run_shepherd.py:83-91`):

```python
REVIEW_BOT = "claude[bot]"
CODEX_CONNECTOR_BOT = "chatgpt-codex-connector[bot]"
GATING_BOTS = (REVIEW_BOT, CODEX_CONNECTOR_BOT)
```

`COPILOT_BOT = "copilot-pull-request-reviewer[bot]"` (line 252) is tracked
separately and is intentionally never gating.

`read_codex_review(pr: PRSnapshot) -> CodexReview` (lines 842-1003) is the
single aggregation point. It makes three `gh api` calls — PR reviews,
line-anchored PR review comments, and top-level issue comments — and for
each item:

- Skips any actor not in `GATING_BOTS`.
- Sets `has_responded = True` **only** when the actor is `REVIEW_BOT` and
  (a) a review/comment is anchored to `commit_id == pr.head_sha`, (b) a
  "No P1/P2 findings" issue comment postdates `pr.head_pushed_at`, or (c) a
  `+1` reaction on the latest `@claude review` trigger postdates
  `pr.head_pushed_at`. The Codex connector's presence/absence never touches
  `has_responded` (comment at lines 85-89, 858-861, 970-973) because its
  trigger is best-effort.
- Extracts severity via `_extract_severity(body)` (lines 816-839), which
  recognizes Codex's `![P1 Badge]` markers and Claude's `**P1 —`/`P1:`
  bold-or-bare-line markers, and appends a `CodexFinding` (lines 378-393:
  `body, path, line, commit_id, created_at, severity, author`).

`CodexReview.findings_p1_p2(at: str)` (lines 409-421) is how staleness is
enforced: a finding whose `commit_id` is set and does not equal the current
head is dropped; findings without a `commit_id` (top-level issue comments)
were already time-filtered against `head_pushed_at` when collected.

`decide(pr, codex_review, now=None) -> tuple[str, Any]` (lines 1044-1081) is
the pure decision function: merged/closed short-circuits first, then
`is_draft`, then **only Claude's `has_responded`** gates on "codex still
parsing" (`if not codex_review.has_responded: return ("wait", None)`), then
`findings_p1_p2(at=pr.head_sha)` — pooled across every `GATING_BOTS` member
— routes to `address-review` if non-empty, then merge-state/checks/settle
window gate `merge`.

`read_copilot_review()` (lines 1006-1038) is a structurally separate,
never-gating reader that duplicates the same two `gh api` calls
(`/reviews`, `/pulls/<n>/comments`) purely to log Copilot's activity in
`process_one`'s per-tick info line (lines 1450-1463).

`apply_followup()` (lines 1229-1318) takes whatever `findings` `decide()`
returned as its `address-review` payload, converts them with
`_format_bundle_via_sdk()` into `{"p1": bool, "p2": bool, "summaries": [...]
}` via the `shepherd` sub-agent (`agents/_shepherd/.claude/agents/
shepherd.md`), and forks `python -m orchestrator.run_implementer
--review-feedback <bundle.json>`. The sub-agent prompt explicitly tells the
model findings carry Codex's `![Pn Badge]` shape and to ignore Copilot.

`process_one()` (lines 1395-1617) is the per-proposal outer state machine:
it calls `find_pr_for_proposal` → `read_codex_review` + `read_copilot_review`
→ `decide()`, then applies one of `wait` / `flip-to-merged` /
`flip-to-rejected` / `address-review` (bounded by `MAX_REVIEW_ATTEMPTS = 3`,
line 284) / `merge`. There is no timeout path for "a required reviewer
never responded" distinct from the address-review retry cap — a PR stuck
on `has_responded=False` forever simply returns `wait` on every tick,
indefinitely (this is the gap the issue's "explicit policy: wait/retry or
review-stuck" acceptance criterion targets).

Separately, `.github/workflows/agy-review.yml` already wires a second,
independent review workflow into this repo, calling the reusable
`mctlhq/.github/.github/workflows/agy-review.yml` with `blocking: true` and
repo-specific conventions. `run_shepherd.py` has zero code paths that read
Agy's output — it is neither in `GATING_BOTS` nor has a parser for its
comment shape. `#67`'s CHANGELOG entry ("gate merges on
chatgpt-codex-connector[bot] P1/P2 findings", closes #67) is the precedent
for widening gating, and its test suite
(`tests/test_run_shepherd.py:896-1028`) is the template this proposal's
tests follow — but #67 hard-coded a second bot into the same two constants
rather than introducing a declarative registry, which is exactly what this
issue's first acceptance criterion asks to fix.

## Proposed solution

Generalize the two hard-coded constants (`REVIEW_BOT`, `CODEX_CONNECTOR_BOT`
+ the `GATING_BOTS` tuple) into one declarative reviewer registry, and widen
`CodexReview`/`CodexFinding` into a source-agnostic aggregate that any
number of gating reviewers can contribute to. Concretely, in
`orchestrator/run_shepherd.py`:

1. **Declarative reviewer registry.** Replace the bare constants with a
   small `ReviewerSource` dataclass:

   ```python
   @dataclass(frozen=True)
   class ReviewerSource:
       name: str            # "claude", "agy", "codex-connector"
       bot_login: str       # GitHub actor login
       required: bool       # drives no-response timeout when True
       drives_response_signal: bool  # eligible to flip has_responded_by(name)
   ```

   `GATING_REVIEWERS: tuple[ReviewerSource, ...]` becomes the single source
   of truth, replacing `GATING_BOTS`:

   ```python
   REVIEW_BOT = "claude[bot]"           # kept as a named constant — reused
   CODEX_CONNECTOR_BOT = "chatgpt-codex-connector[bot]"  # by ReviewerSource.bot_login
   AGY_BOT = "<confirmed from #234 payload>"  # see requirements.md Open questions

   GATING_REVIEWERS = (
       ReviewerSource("claude", REVIEW_BOT, required=True, drives_response_signal=True),
       ReviewerSource("agy", AGY_BOT, required=True, drives_response_signal=True),
       ReviewerSource("codex-connector", CODEX_CONNECTOR_BOT, required=False, drives_response_signal=False),
   )
   ```

   This keeps the existing, deliberate #67 policy (the connector gates on
   findings but never blocks on silence) expressible as data
   (`required=False`) instead of a code branch, and makes Agy declarative
   from day one, satisfying the issue's first acceptance criterion.

2. **Widen the finding shape.** Extend `CodexFinding` with the fields Agy's
   format needs that Claude/the connector's badge-style findings did not
   require: `source: str` (the `ReviewerSource.name`, replacing/augmenting
   the existing `author` bot-login field so the bundle can say "Agy" not
   `agy[bot]`), `proposed_fix: str | None`, `url: str | None` (the
   comment's `html_url`), and `reviewed_head_sha: str | None` — populated
   from `commit_id` when GitHub supplies one (line-anchored comments,
   reviews) and otherwise parsed out of Agy's own top-level marker text
   when it is a plain issue comment lacking `commit_id` metadata. This is
   why the issue calls out "reviewed head SHA" as something Agy's parser
   must normalize itself: unlike Claude's `**P1 —` markers (which always
   ride on a review or line comment that already carries `commit_id`),
   Agy's declared "top-level marker/comment format" may need to self-report
   the head it reviewed inside the comment body for the freshness check in
   `findings_p1_p2` to work at all.

3. **One fetch, dispatch-by-login.** Replace the three separate
   `GATING_BOTS`-filtered loops inside `read_codex_review` (renamed
   `read_gating_reviews` for clarity, since "codex" no longer describes
   what it aggregates) with a single pass over the same three already-
   fetched endpoints (`/reviews`, `/pulls/<n>/comments`,
   `/issues/<n>/comments`) that dispatches each item to whichever
   `ReviewerSource` matches `login`, then to a per-source parser function:
   `_parse_claude_finding`, `_parse_connector_finding` (both thin wrappers
   over today's `_extract_severity`-based logic, unchanged behavior), and a
   new `_parse_agy_finding` for Agy's marker format. `has_responded` becomes
   per-source (`responses: dict[str, bool]`, keyed by `ReviewerSource.name`)
   instead of one bare bool, so `decide()` can evaluate every `required`
   source independently rather than special-casing Claude.
   `read_copilot_review`'s duplicate `/reviews` + `/pulls/<n>/comments`
   fetch is folded into the same single pass (Copilot classified as
   `required=False, drives_response_signal=False`, findings-count-only, no
   parser needed) so the module makes one round of `gh api` calls per tick
   instead of two.

4. **Deduplicate with attribution.** Add
   `_dedupe_findings(findings: list[CodexFinding]) -> list[CodexFinding]`:
   group by `(path, line)` when both are present (the strongest available
   key — same file/line reported by two reviewers is almost certainly the
   same defect); when either is absent, group by a normalized (whitespace-
   collapsed, lowercased) prefix of `body`/message. Merge each group into
   one finding that keeps the highest severity seen (`P1` over `P2`) and a
   `sources: list[str]` field (all contributing `ReviewerSource.name`
   values) instead of the single `author`/`source` string — satisfying "no
   source attribution dropped." This is a deliberately conservative
   heuristic: under-merging (two findings survive that are really the same
   defect) is an acceptable false negative — the PR still blocks, just with
   one redundant line in the bundle — whereas over-merging (two distinct
   defects collapse into one) would be a correctness regression. Prefer
   the stricter path/line key and only fall back to the fuzzy text key when
   neither reviewer supplied a location.

5. **No-response timeout, not just no-response wait.** Extend
   `decide()`'s signature to accept the aggregated per-source
   `responses: dict[str, bool]` and a per-source elapsed-wait figure it can
   compare against a new constant `REVIEWER_RESPONSE_TIMEOUT_TICKS`
   (default 3, mirroring `MAX_REVIEW_ATTEMPTS`'s "3 strikes" shape from
   `orchestrator/run_shepherd.py:281-284`). Because `decide()` must stay
   pure (no wall-clock reads beyond the existing injected `now`), the tick
   count is tracked the same way `review_attempts` already is: a new
   `.status.yaml` field, `reviewer_wait_ticks`, reset to `0` whenever
   `pr.head_sha` changes (a fresh push resets every reviewer's clock,
   symmetric with how `findings_p1_p2(at=head_sha)` already discards
   stale findings) and incremented by `process_one` each tick a required
   reviewer has not yet responded. When a required source's tick count
   exceeds the timeout, `process_one` flips the proposal to
   `review-stuck` with a note naming the silent reviewer — reusing the
   existing `review-stuck` terminal status and its human-triage contract,
   rather than inventing a new status value. This directly satisfies "an
   explicit policy: wait/retry or review-stuck, never silently treat it as
   approval."

6. **Bundle carries every required reviewer's blockers.** No change needed
   to the shape of the `address-review` payload itself (`decide()` already
   returns the pooled, head-filtered findings list to `apply_followup`) —
   widening `GATING_REVIEWERS` to include Agy is sufficient once step 3's
   dispatch loop populates `findings` from all three sources. Update
   `agents/_shepherd/.claude/agents/shepherd.md` to (a) mention Agy's
   marker format alongside Codex's badge format so the summarizer does not
   mis-parse it, and (b) instruct the model to fold each finding's
   `sources` list into its one-line summary (e.g. "[P1, claude+agy]
   ...") so a human reading the implementer's follow-up commit message can
   see which reviewers agreed.

7. **Merge evidence.** In `process_one`'s `flip-to-merged` branch (lines
   1468-1476), add a `review_evidence` dict to the `update_status(...,
   "merged", ...)` call: `{source_name: {"responded": bool,
   "cleared_findings": int}}` built from the final `AggregatedReview` right
   before merge. This is additive to `.status.yaml` — no schema migration,
   since `update_status`/`update_status_file` already do read-modify-write
   preserving unknown keys (`orchestrator/run_shepherd.py:475-491`).

## Alternatives

1. **Repeat the #67 pattern: add `AGY_BOT` as a third hard-coded gating
   bot, no registry.** Rejected — it is the fastest patch but reproduces
   exactly the anti-pattern the issue's first acceptance criterion names
   ("rather than hard-coded as one primary bot"). It also does nothing for
   the no-response timeout gap, since that gap exists independently of how
   many bots are hard-coded.

2. **Move reviewer configuration into `config/settings.py` (or a YAML file
   under `config/`) instead of a Python tuple in `run_shepherd.py`.**
   Considered because `config/settings.py` already centralizes `SERVICES`,
   `SHEPHERD_DIR`, `SHEPHERD_MODEL`, etc. Rejected for this proposal: the
   per-source behavior (parser function, response-signal rules) is code,
   not data — externalizing only the login/required/drives-response fields
   to settings while leaving parsers in `run_shepherd.py` would split one
   concept across two files for no operational benefit (nobody reconfigures
   gating reviewers without a code change to teach the parser their
   format anyway). The out-of-scope section already excludes building a
   true external plugin system; an in-module dataclass tuple satisfies
   "configured declaratively" without that larger investment.

3. **Treat Agy's GitHub Actions workflow conclusion (success/failure) as
   the response signal instead of parsing its posted comment.** Rejected —
   explicitly a non-goal in the issue ("Treating a successful GitHub
   Actions workflow conclusion as equivalent to an approving semantic
   review"). A green workflow run only proves the job executed, not that
   Agy reviewed the diff and found nothing; the response signal must come
   from an actual comment/marker on the current head, same as Claude's
   `has_responded` rules today.

4. **Give every required reviewer its own independent decision function
   instead of pooling into one `decide()`.** Considered, since it would let
   each reviewer's wait/timeout policy vary independently. Rejected for
   this pass — `decide()`'s single-pass precedence order (merged → closed →
   draft → any-required-reviewer-silent → any-current-head-P1/P2 → mergeable
   state → checks → settle window) is already exercised by the full
   existing test suite and documented as intentionally linear at
   `orchestrator/run_shepherd.py:1044-1056`; splitting it would touch far
   more of the module than this issue's scope justifies. Per-source
   dictionaries (`responses`, `reviewer_wait_ticks`) get the same
   granularity without restructuring the control flow.

## Platform impact

- **Backward compatibility.** `.status.yaml` gains two new optional fields
  (`reviewer_wait_ticks`, `review_evidence`) via the existing
  read-modify-write helpers — old files without them parse fine (`_load_status`
  already defaults missing fields). No change to the `pr:`/`status:`/
  `review_attempts:` fields other proposals in flight already rely on.
  `CodexFinding.author` is widened rather than removed (kept for any
  external tooling that reads it) with `source`/`sources` added alongside.
- **Migrations.** None — no database, no schema versioning in this repo
  path; `.status.yaml` is per-proposal Git-tracked YAML.
- **Resource impact.** Folding `read_copilot_review`'s duplicate fetch into
  the unified pass (step 3) is a net *decrease* in `gh api` calls per tick
  (two fetches of `/reviews` and `/pulls/<n>/comments` become one each).
  Agy authority adds one cached, paginated Actions-runs lookup per relevant tick so queued/in-progress runs, workflow identity, conclusions, and rerun attempts are observable.
- **Risks + mitigations.**
  - *Wrong Agy bot login or comment shape* (flagged in requirements.md's
    Open Questions) would make the parser silently find zero findings.
    Mitigation: task list requires pulling PR #234's real API payloads via
    `gh api` before writing `_parse_agy_finding`, and the #234-reproduction
    test (see tasks.md T-reproduce-234) fails loudly if the parser finds
    nothing on that fixture.
  - *Dedup heuristic collapsing two distinct defects into one* (Alternative
    considered in step 4). Mitigation: prefer the strict path/line key,
    fall back to fuzzy text matching only when no location is available,
    and add a unit test asserting two different-path findings never merge.
  - *New no-response timeout interacting badly with the existing
    `MAX_REVIEW_ATTEMPTS` cap* — a proposal could theoretically hit both
    counters. Mitigation: the two counters are orthogonal
    (`reviewer_wait_ticks` only increments on `wait`-because-silent;
    `review_attempts` only increments on `address-review`), and
    `_load_status`/`update_status` already tolerate any combination of
    fields; add a test asserting both counters can coexist and each
    independently drives its own `review-stuck` flip.
  - *Rollout risk to already-open PRs mid-review-cycle*: a PR that today
    reads `has_responded=True` from Claude alone would, post-change, also
    wait on Agy. Mitigation: since `agy-review.yml` already runs on every
    PR (`on: pull_request: types: [opened, reopened, synchronize,
    ready_for_review]`) and is `blocking: true` at the GitHub-check level,
    every in-flight PR already has (or will shortly get) an Agy comment;
    worst case a proposal spends one extra tick in `wait` until Agy's
    existing job posts, which is the same "wait one more tick" cost #67
    already accepted for the Codex connector.

## Accepted design correction (authoritative)

This section supersedes assumptions that an existing Agy comment can be head-pinned.

Change the reusable `mctlhq/.github/.github/workflows/agy-review.yml` first so PASS/FAIL and reviewer-error comments carry PR head SHA and run ID in the marker; bump mctl-agents' pinned reusable-workflow commit. `ReviewerSource` matches `github-actions[bot]` plus marker. Only an exact 40-hex marker SHA equal to `PRSnapshot.head_sha` satisfies Agy response; legacy comments remain visible but non-gating evidence.

Persist `reviewer_wait_head_sha` and `reviewer_wait_ticks: {source: count}`. Reset on head change. Failure marker increments Agy's missing/failed counter and never approves. `decide()` remains pure. Dedup is exact and conservative, never fuzzy for unlocated findings. The mctl-agents change cannot merge until real pinned PASS and FAIL fixtures prove current-head parsing.

## P1 authoritative-run and backfill design correction

The reader joins marker comments to Actions runs by `run_id`, `run_attempt`, workflow identity, repository, and exact PR `head_sha`. For the current head it selects the newest non-superseded run using the Actions run ordering plus attempt number. Once a newer run is queued, in progress, or completed, comments from every older run are ignored for gating. This makes old-PASS/new-FAIL and old-FAIL/new-PASS deterministic; a rerun attempt supersedes earlier attempts of the same run.

Rollout is two-phase. First merge the shared-workflow marker change and bump the pinned reusable-workflow SHA. Then enumerate all open mctl-agents PRs/proposals and explicitly dispatch or rerun that pinned workflow against each current head. A proposal may switch Agy to `required=True` only after its head has a joined new-format marker from the authoritative run. PR #234 must be exercised in this backfill. Workflow-pin changes alone do not satisfy this phase because they do not emit a `pull_request` synchronize event for existing heads.

## Semantic failure and dispatch correction

Agy posts an explicit semantic marker outcome: `clean`, `findings`, or `reviewer_error`. The aggregator first selects the authoritative current-head run/attempt, then interprets its marker. `findings` with valid P1/P2 payload drives `address-review` regardless of the blocking job's failure conclusion. `reviewer_error`, missing/malformed payload, or infrastructure failure produces bounded wait then `review-stuck`. Actions conclusion is supporting execution evidence, never a substitute for the semantic marker.

The mctl-agents pinned caller gains a manual backfill path such as `workflow_dispatch(pr_number, head_sha)`. It resolves the PR through GitHub, fails closed unless `head_sha` exactly equals the live PR head, and invokes the same pinned reusable Agy workflow. The rollout enumerator dispatches this entry point for open PRs and joins each returned run ID/attempt to its marker before enabling `required=True`.

## Explicit target checkout and Actions lookup correction

The dispatch wrapper runs trusted YAML from the default branch but never treats the dispatch ref's `GITHUB_SHA` as the reviewed code. It resolves `pr_number`, verifies the supplied 40-hex SHA equals the API's current PR head, fetches/checks out that exact commit in detached mode for analysis, and passes explicit repository/PR/head inputs to the pinned reusable workflow. Before posting results it rechecks the live head; a changed head suppresses the marker and fails closed. Comments target the explicit PR number and markers carry the explicit reviewed SHA.

Run authority requires a paginated Actions-runs query filtered to the Agy workflow and current PR head, including queued/in-progress runs and every `run_attempt`. Cache that result within one shepherd tick, then join it to marker comments by run ID/attempt. This deliberate API call supersedes the earlier same-or-fewer-call assertion and the claim that Agy adds no network calls.

## Dispatch intent and run-correlation correction

Backfill creates a durable dispatch intent `{correlation_id, repository, pr_number, reviewed_head_sha, workflow_id, created_at}` before calling GitHub. The trusted caller accepts the correlation ID and sets an immutable `run-name` containing it plus PR/SHA metadata. Authority lookup queries the Agy workflow without an Actions-head filter for `workflow_dispatch` events, then matches queued/in-progress runs to the intent by workflow ID, event, trusted default-branch ref, correlation ID/run-name, and bounded creation window. This makes an in-progress backfill visible before it posts a marker.

On completion, the marker must repeat correlation ID, explicit reviewed SHA, PR number, run ID, and run attempt. Those fields are joined to the exact run and intent; any disagreement fails closed. Pull-request-triggered runs remain separately selected by their real Actions `head_sha`. Thus default-branch `GITHUB_SHA` is never confused with the reviewed target.

## Markerless completed-run authority correction

The authority selector first orders correlated runs, then interprets evidence. Correlation is independent of marker presence and survives run completion. Therefore a newer completed dispatch that fails before commenting remains selected through its durable intent, trusted run-name correlation, workflow identity, run ID, and attempt. Missing/malformed semantic output maps to `reviewer_error`, blocks merge, and advances the bounded reviewer-error wait policy; it never falls back to an older PASS. Only valid `clean` or `findings` markers can produce those semantic outcomes. Dispatch intent retention lasts until durable consumption or explicit supersession.

## Pre-run authority and wait-key correction

Authority is selected from the union of durable dispatch intents and correlated Actions runs. A newly created current-head intent immediately supersedes older runs and remains a blocking pending authority while dispatch is in flight or GitHub has not indexed the run. Bounded correlation retries either attach the run or durably classify the intent as `reviewer_error`; neither path falls back to an older PASS. Explicit supersession links the old intent to its successor before cleanup.

Persist reviewer waits under `reviewer_wait_key = <source>:<head_sha>:<authority_identity>`. Pending intent uses its correlation ID; after correlation, authority identity becomes `run_id:run_attempt`. The correlation transition transfers a zeroed/full response window rather than inherited ticks. Any newer rerun/attempt atomically replaces the key and resets only that source's counter; other sources remain unchanged.

## Exact-PR authority and durable evidence correction

For `pull_request`-triggered Agy executions, matching the workflow and commit SHA is not sufficient: two pull requests can share a commit. Authority selection SHALL additionally require the target PR association and the expected head repository and ref. A run associated with another PR, repository, or ref is unrelated even when its `head_sha` is identical.

A valid authoritative `findings` marker that contains no P1/P2 findings is a successful, nonblocking reviewer response. Its P3/P4 findings remain advisory evidence in the aggregate and merge record, but they neither trigger `address-review` nor consume the missing-reviewer timeout.

The shepherd SHALL durably retain per-source blocking-finding history when P1/P2 findings are observed, keyed by stable exact finding identity and reviewed head. When a later current head is clean and merged, merge evidence SHALL idempotently derive `cleared_findings` records and counts from that history rather than only from the final head-filtered aggregate. Restarts and repeated reconciliation must not lose or double-count prior-head clearance evidence.

## Same-head lifecycle fence correction

Authority selection includes a PR lifecycle generation derived from the latest `ready_for_review` or `reopened` timeline event. Such an event immediately supersedes prior same-head Agy evidence. Until Actions indexes a matching run created after the event, the generation is pending authority and blocks merge. The run joins only when PR number, head repository/ref/SHA, workflow identity, and creation time all match; missing correlation is bounded and fail-closed. This mirrors dispatch-intent fencing without requiring a webhook race-free Actions listing.

## Trusted semantic output and unified authority generation

Marker comments remain required, human-readable exact-head/run evidence, but they are not the security boundary because another workflow using github-actions[bot] could forge them. The trusted reusable workflow publishes an immutable semantic-result artifact (or equivalently integrity-protected run output) containing schema version, repository, PR, reviewed head, run ID/attempt, correlation ID, outcome, and findings. Shepherd selects the authoritative Actions run, fetches and validates that run-bound payload and its digest/identity through Actions, then requires the comment fields to agree. A marker without the trusted payload, or any mismatch, maps to bounded reviewer_error; it can never expose an older PASS.

Persist a proposal-scoped monotonic authority_generation and lifecycle-event watermark under one serialized state update. Dispatch creation first refreshes the lifecycle timeline, records its watermark, then allocates the next generation to the intent. Each newly observed reopened/ready_for_review event identity advances the generation and supersedes earlier intents/runs; duplicates or events already covered by the watermark do not. A correlated run inherits its parent intent/event generation. This defines both overlap orders deterministically and keeps the newest generation pending until its own trusted result is available.

Finding history uses (source, exact_finding_identity) as the record key and stores heads/runs as deduplicated observations. Clearance is derived once per stable blocker identity. Rollback is coordinated: turn off required caller/check policy, stop dispatch creation, drain or supersede pending authorities, persist terminal evidence, and only then revert the reader/pin. Re-enable only after fresh current-head backfill.
