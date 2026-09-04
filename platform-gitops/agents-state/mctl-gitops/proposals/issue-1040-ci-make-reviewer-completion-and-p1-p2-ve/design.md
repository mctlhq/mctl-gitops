# Design: issue-1040-ci-make-reviewer-completion-and-p1-p2-ve

## Current state

Branch protection for this repo is ruleset `18465404` ("`main-protection`"),
referenced in `docs/runbooks/github-app-scope-audit.md` and
`docs/soc2/compensating-controls.md` — it is not stored as code in this
repo (`CLAUDE.md`: "the current GitHub connector can inspect rulesets but
cannot mutate the admin/ruleset configuration"). Per
`docs/soc2/compensating-controls.md` and `docs/soc2/risk-register.md`, it
already has `current_user_can_bypass=never` for the repo owner (the gitops
admin-bypass path is deliberately closed, unlike `api`/`agent`/`agents`/
`web`), and requires one approving review (`require_code_owner_review:
false`, per `.github/CODEOWNERS`'s own comment, since the sole account with
write access is also the PR author on most changes).

Two independent reviewer workflows already run on every PR:

- `.github/workflows/claude-review.yml` — triggers on
  `pull_request: [opened, reopened, synchronize, ready_for_review]` and
  `issue_comment: [created]`; calls the reusable
  `mctlhq/.github/.github/workflows/claude-review.yml@0ca555b...`; posts as
  `claude[bot]`. `docs/soc2/compensating-controls.md` documents its P1/P2
  output as "a second reader, not a second human" — i.e. advisory today.
- `.github/workflows/agy-review.yml` — triggers on
  `pull_request: [opened, reopened, synchronize, ready_for_review]`; calls
  the reusable `mctlhq/.github/.github/workflows/agy-review.yml` with
  `blocking: false` ("Staged rollout: Agy evidence is reviewed manually
  until proposal #240 delivers exact-head markers, backfill, and
  repository-level gating" — the comment in this repo's own workflow file);
  posts as `github-actions[bot]` with an `<!-- agy-review -->` marker
  (documented in `platform-gitops/platform-skills/catalog/review-watch/
  SKILL.md`, which a human/agent uses today to *manually* poll for these
  two bots' completion — the exact workaround this issue wants to make
  unnecessary).

Neither workflow's completion nor its verdict feeds `main-protection`.
`.github/workflows/auto-merge.yml` shows the adjacent, narrower gap for
`claude/*`-authored PRs specifically: it merges on the *first* `approved`
`pull_request_review` event, with no awareness of Agy at all. `#1038` is the
general-case version of that same race for a human-authored PR.

The sibling proposal `mctlhq/mctl-agents#240`
(`platform-gitops/agents-state/mctl-agents/proposals/
issue-240-fix-shepherd-aggregate-blocking-findings/`) independently found
the same root gap one layer down: the Tier 3 PR shepherd's own merge
decision (`orchestrator/run_shepherd.py`, a different repo) hard-codes
`GATING_BOTS = (claude[bot], chatgpt-codex-connector[bot])` and has no
Agy awareness either. That proposal's investigation is directly relevant
prior art — it confirms Agy's marker currently carries no head SHA or run
ID (`<!-- agy-review -->` alone), which is why exact-head correlation by
comment text is fragile — but its design spiraled through many
"authoritative corrections" (dispatch-intent correlation IDs, run-attempt
authority orderings, PR-lifecycle-generation fencing, backfill dispatch)
because it is solving a *harder* problem: an external, stateful poller that
must remain correct across ticks, restarts, and retroactive backfill onto
already-open PRs. This design deliberately does not import that machinery.

## Proposed solution

Add one new GitHub Actions workflow, `.github/workflows/review-gate.yml`,
that publishes a single commit status (`context: review-gate`) on the PR's
head SHA. That status — not either reviewer workflow's own job conclusion —
is the one check registered as required on `main-protection`, matching the
issue's suggested shape ("this avoids trying to make each heterogeneous
reviewer workflow itself a branch-protection contract").

**Why a commit status instead of a check run / long polling job.** Two
independent reviewer workflows finish at unpredictable, unrelated times.
Modeling `review-gate` as a single long-running job that polls both to
completion would either burn Actions minutes idling on `sleep`, or need its
own timeout/retry state machine duplicating what `deploy-signal.py`
already demonstrates should instead be a scheduled sweep. A commit status
authored by short-lived, event-triggered jobs is the standard GitHub
pattern for exactly this "wait for N heterogeneous producers, output one
verdict" shape, and required status checks accept plain commit statuses.

**Triggers, three of them, each a small job in `review-gate.yml`:**

1. `pull_request: [opened, reopened, synchronize, ready_for_review]` —
   immediately POSTs `pending` for the new head SHA. This exists so the
   required check is visibly present (not just missing) the moment a push
   happens, and so a stale `success` from a previous head is explicitly
   superseded rather than left to be silently reused (`IF a required
   reviewer's terminal result...` / the new-push invalidation acceptance
   criterion). The pending state's description records the timeout deadline
   (now + 45 minutes) so the sweep job (below) has a durable anchor without
   its own datastore.
2. `workflow_run: [claude-review.yml, agy-review.yml], types: [completed]`
   — the evaluator. On firing:
   - Resolve the PR and its **current** head SHA from the API (never trust
     `workflow_run.head_sha` alone as "still current" — a later push may
     have already superseded it; re-check `GET /pulls/{n}` and bail out,
     posting nothing, if the run's `head_sha` no longer matches the PR's
     live head). This is the mechanism that satisfies "a new push
     invalidates the previous verdict": an evaluator run for a superseded
     head simply has nothing left to say, and the `pull_request` trigger
     above has already re-armed `pending` for the real current head.
   - For each required reviewer workflow (`claude-review.yml`,
     `agy-review.yml`), query `GET /actions/runs?head_sha=<sha>` filtered
     to that workflow file and take the newest run. This is the
     authoritative head-SHA binding — it comes from GitHub's own Actions
     run metadata, not from parsing marker text, which is what let
     `mctl-agents#240`'s design avoid needing the reusable workflow to
     embed `head_sha`/`run_id` in its comment at all. If any required
     run for the current head is not yet `completed`, stop here — leave
     `review-gate` `pending` (do nothing; the other trigger will fire the
     evaluator again when that run finishes).
   - Once every required run for the current head is `completed`, read
     that bot's posted output for the current head: reviews, line-anchored
     PR review comments, and top-level issue comments, filtered by actor
     login and, for comments without a `commit_id`, by timestamp >= the
     winning run's `created_at` (the same time-window heuristic
     `orchestrator/run_shepherd.py`'s `read_codex_review` already uses for
     Claude's top-level "No P1/P2 findings" comment, per the `#240` design
     doc's description of it — reused here rather than reinvented).
     Extract severity with the same two-shape pattern that design doc
     documents (`**P1 —`/`P1:` bold-or-bare markers, `![P1 Badge]`-style
     badges); Agy's concrete marker shape is confirmed against a real
     payload during implementation (see `requirements.md` Open questions
     and `tasks.md` T1).
   - `run.conclusion != 'success'` with no parseable "clean" verdict is
     treated as reviewer failure, not reviewer silence-equals-approval —
     satisfies "quota/tooling failure is not success."
   - Any required reviewer's P1/P2 → POST `failure`, message names which
     reviewer and how many P1/P2. All required reviewers clean → POST
     `success`.
3. `schedule: */10 * * * *` — the timeout sweep. Lists open PRs with a
   `pending` `review-gate` status whose recorded deadline (from trigger 1's
   description) has passed, and flips them to `failure` with a message
   naming the reviewer(s) that never reached a terminal run — satisfies
   "quota/tooling failure is not success... fail closed or explicitly
   require human override." This mirrors `deploy-signal.yml`'s own
   rationale for using a schedule rather than trusting only in-path
   triggers: "a check that only runs when the pipeline runs cannot see the
   pipeline failing to run at all" applies identically to "a reviewer
   workflow that never starts."

**P1/P2 only, P3 untouched.** `review-gate`'s severity extraction only
drives pass/fail on P1/P2, per the issue's explicit invariant #6. No P3
gating exists in this repo's CI today (checked: no `P3`/`P4` reference in
any `.github/workflows/*`), so there is nothing to preserve here beyond
not accidentally starting to fold P3 into this check — `review-gate`
explicitly ignores severities below P2 rather than defaulting to "block on
anything found."

**Making Agy required is a paired one-line change.** `.github/workflows/
agy-review.yml`'s `blocking: false` currently disagrees with what
`review-gate` will enforce once it requires Agy to be terminal-and-clean.
This proposal flips it to `blocking: true` alongside adding `review-gate`,
so the reusable workflow's own signal and this repo's new aggregate check
agree (see `requirements.md` Open questions for why `required=True` is the
recorded assumption).

**Human override, given `current_user_can_bypass=never`.** Per
`docs/soc2/compensating-controls.md` / `risk-register.md`, the repo owner
cannot ruleset-bypass a stuck `review-gate` on this repo — `emergency-
change.md`'s "ruleset bypass" allowed action does not currently apply
here. The override is instead: an operator manually POSTs a `success`
(or, to unstick a wedged `pending`, first `failure` then `success` once
resolved) commit status for `review-gate` at the specific SHA via `gh api
repos/mctlhq/mctl-gitops/statuses/{sha}` — an ordinary repo write, not a
ruleset action, so it works even with bypass closed. This is documented as
an explicit override path (task 6) rather than left implicit, and it still
goes through `emergency-change.md`'s existing afterward-writeup
requirement.

## Alternatives

1. **Make each reviewer workflow's own job the required check** (i.e.
   register `claude-review` and `agy-review`'s job conclusions directly as
   two separate required checks, no aggregate). Rejected — this is exactly
   what the issue's "Suggested shape" argues against: reviewer job
   conclusion (did the job run without erroring) is not the same signal as
   review verdict (did it find a P1/P2), so a red job for an unrelated
   infra reason and a P1 finding both need to block, while a green job with
   a P1 finding must NOT pass — two heterogeneous workflows would each need
   to independently learn to fail their own job on P1/P2, and Agy's
   `blocking: false` staged-rollout comment shows that reusable workflow
   isn't designed to be that contract on its own.

2. **Reuse `mctl-agents#240`'s full design** (declarative reviewer
   registry, dispatch-intent correlation IDs, run-attempt authority
   ordering, PR-lifecycle-generation fencing, durable finding-history
   persistence) directly in this repo's CI. Rejected for scope — that
   design solves a materially harder problem (a stateful external poller
   across many repos, over many ticks, needing retroactive backfill onto
   already-open PRs across a fleet) than "does this one repo's required
   check for this one PR's current head see two known reviewers finish."
   `review-gate` gets the exact-head guarantee for free from Actions run
   metadata (§ Proposed solution) without needing marker-embedded
   `head_sha`/`run_id`, a correlation-ID system, or a backfill dispatch
   endpoint. If a future need for cross-repo, tick-based aggregation
   emerges, that remains `#240`'s problem to solve independently; nothing
   here blocks it.

3. **Long-running polling job instead of `workflow_run` + schedule.** A
   single job triggered on `pull_request` that loops `gh api` calls until
   both reviewers finish or a timeout is hit. Rejected — ties up an Actions
   runner for up to 45 minutes per PR doing nothing but sleeping, and
   duplicates the sweep/timeout logic a scheduled job already models more
   cheaply and more visibly (a `pending` status is inspectable at any time
   without opening a live log).

## Platform impact

- **Migrations.** None — no data migration. `review-gate.yml` is additive;
  existing workflows are untouched except the `agy-review.yml` `blocking`
  flag flip.
- **Backward compatibility.** Until an admin registers `review-gate` as a
  required status check on the `main-protection` ruleset (explicitly
  out of scope, per `requirements.md`), this change is inert — it posts an
  informational status that nothing yet requires. This makes the rollout
  naturally staged: merge and observe `review-gate` results on real PRs for
  a period before making it required, rather than making a bug in this
  workflow immediately block all merges.
- **Resource impact.** Three small jobs per PR event plus one lightweight
  scheduled sweep every 10 minutes; negligible compared to
  `validate-manifests.yml`'s existing per-PR cost.
- **Risks + mitigations.**
  - *Total lockout risk*, given `current_user_can_bypass=never` for this
    ruleset: once required, a bug in `review-gate` itself (not the
    reviewers it watches) could block every merge with no ruleset-level
    escape hatch. Mitigated by (a) the staged rollout above — observe
    before requiring — and (b) the documented manual-commit-status
    override path, which does not depend on ruleset bypass at all. Task 6
    adds this to `emergency-change.md` explicitly so it isn't only in this
    design doc.
  - *Agy marker format unconfirmed from this clone* (see `requirements.md`
    Open questions) — the parser could silently find zero findings if the
    real format differs from the recorded assumption. Mitigated the same
    way `#240`'s task list already commits to: capture one real Agy
    payload via `gh api` before finalizing the parser, and add it as a
    fixture so a future format drift fails the self-test instead of
    passing silently (see `tasks.md` T1, following this repo's own
    `--selftest` convention used by `scripts/validate-*.py`).
  - *`workflow_run` PR resolution gap*: `workflow_run` events do not
    reliably populate `pull_requests[]` for all trigger shapes. Mitigated
    by resolving the PR via `GET /repos/.../commits/{sha}/pulls` instead of
    trusting the event payload's `pull_requests` array.
  - *Rollout on already-open PRs*: any PR open before `review-gate` is
    registered as required has no status yet. Unlike `#240`'s shepherd
    (which needed a backfill-dispatch endpoint because it manages a fleet
    of already-open PRs across services), a single repo's open PRs are few
    and each gets a fresh `pending` the moment it is next pushed to
    (trigger 1) or can be manually re-triggered by an empty
    `workflow_dispatch`-style push; no backfill machinery is required here.
