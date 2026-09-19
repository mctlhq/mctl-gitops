# Let the shepherd CWFT commit adopted-prs/ state

## Context

`mctlhq/mctl-agents#334` teaches the Tier 3 PR shepherd to adopt same-repo
pull requests that have no proposal behind them, by writing an adoption
record at `<state_dir>/<service>/adopted-prs/pr-<number>/.prref.yaml`. That
record is the only place the adoption loop keeps `review_attempts`,
`harness_failures`, `refusals` and `refusals_head`, so the
`MAX_REVIEW_ATTEMPTS` bound that stops the shepherd re-fixing the same PR
forever holds only if the record survives from one tick to the next. The
#334 design states the caveat plainly: until this issue lands, "every
`.prref.yaml` this code writes lives in the pod's gitops worktree and is
discarded when the tick ends", and a PR "could be re-adopted and re-fixed
indefinitely". That is why the rollout flag `SHEPHERD_ADOPT_PRS` cannot be
turned on before this change is merged.

The durability gate lives in this repository, in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`.
That template filters agents-state writes down to `.status.yaml` in **two**
places, not one: the `run-shepherd` step's inline `COLLECT` Python builds the
Argo artifact handoff from a `:(glob)…/.status.yaml` pathspec and an `ALLOWED`
regex, and the `commit-and-push` step re-validates the unpacked handoff,
refuses anything outside that subtree, and stages with the same pathspec. An
adoption record is dropped at the first filter today and would be rejected by
the second if only the first were widened, so both have to move together and
in that order.

## User stories

- AS the Tier 3 PR shepherd I WANT the adoption record I write during a tick
  to reach `mctl-gitops` main SO THAT the review-attempt counters I depend on
  survive to the next tick and `MAX_REVIEW_ATTEMPTS` actually bounds my work.
- AS the operator who owns the `SHEPHERD_ADOPT_PRS` rollout I WANT the gitops
  side of the durability contract merged first SO THAT enabling the flag does
  not create an unbounded re-fix loop against a proposal-less PR.
- AS a reviewer of `mctl-gitops` I WANT the widened staging filter to stay as
  narrow as the old one SO THAT the shepherd's push-to-main credentials still
  cannot write anything but agent state.

## Acceptance criteria (EARS)

- WHEN a shepherd tick writes
  `platform-gitops/agents-state/<service>/adopted-prs/pr-<number>/.prref.yaml`
  into its worktree THE SYSTEM SHALL include that file in the `changes`
  artifact handed off by `run-shepherd` to `commit-and-push`.
- WHEN `commit-and-push` unpacks a handoff containing such a `.prref.yaml`
  THE SYSTEM SHALL accept it, stage it, commit it, and push it to
  `mctl-gitops` main in the same commit as any `.status.yaml` flips from the
  same tick.
- WHEN a shepherd tick writes no adoption state THE SYSTEM SHALL commit and
  push exactly what it committed before this change, with no empty commit and
  no non-zero exit from the staging step.
- IF the adopted-prs pathspec matches no file in the checkout THEN THE SYSTEM
  SHALL NOT pass that pathspec to `git add` (a `git add` pathspec that matches
  nothing exits 128, and `set -e` is active in that script).
- WHILE validating a handoff THE SYSTEM SHALL refuse any path that is neither
  `platform-gitops/agents-state/**/.status.yaml` nor
  `platform-gitops/agents-state/<service>/adopted-prs/pr-<n>/.prref.yaml`,
  and SHALL keep refusing symlinks and special files exactly as it does today.
- WHILE staging THE SYSTEM SHALL use pathspecs rooted at the repository root
  (`platform-gitops/agents-state/*/adopted-prs/*/**`), because the script runs
  from `/workdir/mctl-gitops` and a bare `*/adopted-prs/*/**` matches nothing
  from there.
- WHEN an adoption record is deleted in the worktree THE SYSTEM SHALL carry
  that deletion through `deleted.lst` and apply it on main, the same way a
  deleted `.status.yaml` is carried today.
- IF a handoff contains a file under `adopted-prs/` that is not a
  `pr-<n>/.prref.yaml` record THEN THE SYSTEM SHALL fail the commit step
  rather than push it.
- WHILE this change is in flight THE SYSTEM SHALL leave the
  `mctl-gitops-main-writes` mutex on `commit-and-push` unchanged, along with
  the 5-attempt rebase-and-retry push loop and the commit-message shape.

## Out of scope

- Any change to `mctl-agents`: the writer, the `.prref.yaml` schema, the
  `SHEPHERD_ADOPT_PRS` / `SHEPHERD_ADOPT_REPOS` /
  `SHEPHERD_ADOPT_MAX_PRS_PER_TICK` defaults, and the decision to flip the
  flag on all belong to `mctlhq/mctl-agents#334` and its follow-up.
- Setting `SHEPHERD_ADOPT_PRS` in this template's `env:` block. This proposal
  only makes the state durable; enabling the feature is a separate, later
  commit, deliberately so that the ordering in the issue's acceptance list is
  observable in git history.
- `cwft-mctl-agents-implement.yaml` and `cwft-mctl-agents-reconcile.yaml`.
  Both carry their own `.status.yaml`-only filters, and neither writes
  adoption records — the shepherd is the only adopter by design (#334: "the
  implementer never adopts; only the shepherd does").
- `scripts/validate-agents-state-approval.py`. It globs
  `*/proposals/*/.status.yaml` and therefore never sees `adopted-prs/`; no
  change is needed and none should be made.
- Lifecycle-ownership integration (ADR-010 phase 3 hand-off between the
  reconciler and the shepherd).

## Open questions

- The issue specifies the pathspec as `':(glob)*/adopted-prs/*/**'`. Taken
  literally that matches nothing: `commit-and-push` runs after
  `cd /workdir/mctl-gitops`, git pathspecs resolve relative to the current
  directory, and `:(glob)`'s `*` does not cross `/`. This was measured, not
  assumed. This proposal reads the issue as specifying the *shape* and uses
  the rooted form `:(glob)platform-gitops/agents-state/*/adopted-prs/*/**`.
  Proceeding on that reading.
- The issue's scope mentions only "the commit step". The `run-shepherd`
  COLLECT filter is the earlier and stricter gate, and widening only the
  commit step would change nothing observable. This proposal treats "the
  shepherd CWFT commit path" as both filters. Proceeding.
- `#334` does not say whether an adoption record is ever deleted (for example
  once the adopted PR merges). The deletion path is handled here because
  `deleted.lst` already exists and widening its validator is one regex; if
  records are in fact never deleted, that path is simply unexercised.
- Whether a future record ever lands directly at `adopted-prs/<something>`
  rather than under `pr-<n>/` is unknown. This proposal fails closed on that
  shape; if #334 later adds an index file there, the regex must be widened
  again in this repository first.
