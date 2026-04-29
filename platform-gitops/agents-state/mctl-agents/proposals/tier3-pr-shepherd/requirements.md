# Tier 3 PR shepherd — drive implementer-opened PRs to merge

## Context
The proactive R&D pipeline now produces work end-to-end:
- Tier 1 — researcher / analyst / spec-writer write proposal triplets into
  `platform-gitops/agents-state/<svc>/proposals/<slug>/`.
- Tier 2 — `orchestrator.run_implementer` turns an `accepted` proposal into a
  branch + commit + opened PR in the matching sibling repo, then flips
  `.status.yaml` to `implemented` with a `pr:` URL.

What's missing is the second half of the lifecycle. After a PR opens, a
human still has to:
1. Read the codex review (and Copilot review) when it lands, decide whether
   each finding is real, and either dismiss it or push a follow-up commit.
2. Merge the PR once review is clean and CI is green.

Either of those steps blocking on a human means the pipeline stalls — the
proposal sits in `implemented` with an open PR for hours or days. The point
of the proactive pipeline is end-to-end autonomy on small, low-risk changes
(typical implementer PRs are one-line dependency bumps), so the merge
decision should be automatable for the same class of change.

This proposal adds **Tier 3 — the PR shepherd**. A new orchestrator module
that runs on a 5-minute cron, picks up every implementer-opened PR, drives
it through any codex review iterations, and merges it once it's clean and
green. Deploy watch and rollback (the natural Tier 4) are deliberately
out of scope here so the first version stays small.

## User stories
- AS the platform owner I WANT implementer-opened PRs to be auto-merged
  when codex says "no major issues" and CI is green SO THAT I do not have
  to babysit dependency-bump PRs to merge.
- AS the platform owner I WANT codex P1 / P2 findings on an implementer PR
  to be turned into a follow-up commit by the implementer SO THAT I do not
  have to context-switch into each PR to push the small fix myself.
- AS the platform owner I WANT to see in `.status.yaml` exactly which
  state the shepherd is in for every accepted proposal SO THAT a stuck
  pipeline is observable from `git log` of mctl-gitops main.

## Acceptance criteria (EARS)
- WHEN the cron fires AND a proposal exists with `.status.yaml status=implemented`
  AND its `pr:` URL points to an open PR THE SYSTEM SHALL evaluate the PR
  and decide one of: `wait` (codex still pending), `address-review` (P1/P2
  findings exist), or `merge` (clean review + green CI).
- WHEN the decision is `merge` THE SYSTEM SHALL invoke `gh pr merge --merge
  --delete-branch` with the PR's identifier, then update the proposal's
  `.status.yaml` to `status: merged` with `merged_at:` and `merge_commit:`
  set.
- WHEN the decision is `address-review` THE SYSTEM SHALL invoke the
  Tier 2 implementer with the same `service` / `slug` and the codex
  feedback attached as additional context, expecting a follow-up commit
  on the same branch (no new branch, no new PR). The proposal's
  `.status.yaml` SHALL transition to `status: review-fixing` for the
  duration of the followup, then back to `status: implemented` once the
  followup commit lands so the next cron tick re-evaluates.
- WHEN the decision is `wait` THE SYSTEM SHALL leave the proposal in its
  current state and exit cleanly so the next cron tick retries.
- IF the PR has been merged outside the shepherd (human merged it) AND
  the proposal is still `implemented` THE SYSTEM SHALL flip the proposal
  to `merged` and record the merge commit so subsequent ticks do not
  attempt to re-merge.
- IF the PR has been closed without merging THE SYSTEM SHALL flip the
  proposal to `status: rejected` with a `notes:` field explaining the
  closure (taken from the closing comment if any) so the proposal does
  not loop forever.
- WHILE running the shepherd SHALL respect a per-iteration budget cap
  (env `SHEPHERD_BUDGET_USD`, default `$1.00`) and exit cleanly with a
  warning if the cap is reached, so a stuck cron does not run away on
  Claude tokens.
- WHEN the shepherd exits THE SYSTEM SHALL print a one-line summary per
  proposal in the form `<service>/<slug>: <decision>` so the workflow
  log is greppable.

## Out of scope (defer to a Tier 4 follow-up)
- ArgoCD sync watching after merge — the shepherd does not verify the
  deploy. It stops at `merged`. Tier 4 will read ArgoCD application
  health and flip `merged → deployed` (or open a rollback PR).
- Anything beyond `merge` strategy on the PR. No squash, no rebase.
  The platform's CLAUDE.md mandates `--merge` and the shepherd inherits
  that.
- Cross-PR coordination. The shepherd processes each proposal
  independently. If two proposals open PRs that conflict, the shepherd
  will simply rebase-on-merge fail one of them and that proposal stays
  in `implemented` for human triage.
- Proposals where the implementer never opened a PR (status stayed
  `in-progress` or `error`). Those need the `--force` re-run from the
  Tier 2 path; the shepherd does not retry implementer crashes.
- Fanning out to unbounded review tools (Sonarcloud, Snyk, etc.). The
  shepherd reads codex + Copilot + GitHub CI checks; that is enough
  for the dependency-bump class of change this pipeline actually opens.
