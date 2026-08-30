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
  Adding Agy parsing adds no new network calls — Agy's comments already
  arrive on the same three endpoints the shepherd already polls.
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
