# Let the shepherd CWFT commit `adopted-prs/` state

## Context

`mctlhq/mctl-agents#334` teaches the Tier 3 shepherd to adopt same-repo PRs
that have no proposal, recording each one as
`<state_dir>/<service>/adopted-prs/pr-<number>/.prref.yaml`. That record is the
only place the adoption loop's bounds live — `review_attempts`,
`harness_failures`, `refusals`, `refusals_head` and the evidence list. The
shepherd ClusterWorkflowTemplate in this repository
(`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`)
carries the state a tick produces back to `main` through a fixed allow-list of
paths that names `.status.yaml` and nothing else. Every gate on that path —
the collector's pathspec and `ALLOWED` regex in `run-shepherd`, the handoff
validators, the out-of-scope guard, the change detector, and the `git add` —
is scoped to `platform-gitops/agents-state/**/.status.yaml`. An adoption record
would therefore be written into the pod's ephemeral gitops worktree and
discarded when the tick ends, so `MAX_REVIEW_ATTEMPTS` would not hold across
ticks and one PR could be re-adopted and re-fixed indefinitely.

The `#334` proposal states this dependency explicitly and ships the feature
default-off because of it (`agents-state/mctl-agents/proposals/issue-334-feat-lifecycle-adopt-proposal-less-same/design.md`,
"The durability caveat, stated plainly"). That makes this change a
prerequisite for enabling `SHEPHERD_ADOPT_PRS` in production, not a companion
to it, and it belongs here because the commit path is a gitops artefact.

## User stories

- AS the Tier 3 shepherd I WANT the `adopted-prs/` records I write during a
  tick to reach `mctl-gitops` `main` SO THAT my attempt, refusal and harness
  counters survive to the next tick and the adoption loop stays bounded.
- AS a platform operator I WANT the adoption records to be ordinary reviewable
  files in git SO THAT I can see which PRs the shepherd took ownership of, and
  `git rm -r` them to undo an adoption.
- AS a platform operator I WANT a tick that adopts nothing to commit exactly
  what it committed before SO THAT widening the allow-list introduces no empty
  commits and no new noise on `main`.
- AS a reviewer of this repository I WANT the widened allow-list to stay as
  narrow as the state it must carry SO THAT an agent-written worktree cannot
  push arbitrary paths to `main` through the shepherd's deploy key.

## Acceptance criteria (EARS)

- WHEN a shepherd tick writes
  `platform-gitops/agents-state/<service>/adopted-prs/pr-<number>/.prref.yaml`
  into its gitops worktree THE SYSTEM SHALL include that path in the
  `run-shepherd` handoff artifact, stage it in `commit-and-push`, and push it
  to `mctl-gitops` `main`.
- WHEN a shepherd tick updates an existing `.prref.yaml` in place THE SYSTEM
  SHALL commit the modification, so the counters advance rather than reset.
- WHEN a shepherd tick both flips a proposal's `.status.yaml` and writes an
  adoption record THE SYSTEM SHALL commit both in the same commit under the
  existing `chore(agents): shepherd ...` message.
- WHEN a shepherd tick writes no `.status.yaml` change and no adoption record
  THE SYSTEM SHALL report `activity=none` and exit 0 without creating a
  commit, exactly as it does today.
- WHEN a shepherd tick writes an adoption record and no `.status.yaml` change
  THE SYSTEM SHALL still create a commit and report `activity=yes`, rather
  than short-circuiting on "no `.status.yaml` updates".
- WHEN the collector in `run-shepherd` hands off a deletion of an adoption
  record THE SYSTEM SHALL carry it in `deleted.lst` and apply it with
  `git rm -- ':(literal)<path>'` against the fresh clone.
- IF the handoff contains any path that is neither
  `platform-gitops/agents-state/.+/.status.yaml` nor a file under
  `platform-gitops/agents-state/<service>/adopted-prs/<record>/` THEN THE
  SYSTEM SHALL refuse the handoff and exit non-zero, in both the collector's
  `ALLOWED` check and `commit-and-push`'s `BAD` / `BAD_DEL` checks.
- IF the fresh checkout in `commit-and-push` shows a change outside those two
  allow-listed shapes THEN THE SYSTEM SHALL refuse to commit and exit
  non-zero, preserving today's out-of-scope guard.
- IF the handoff contains a symlink or a special file THEN THE SYSTEM SHALL
  refuse it, unchanged from today.
- WHILE `commit-and-push` runs THE SYSTEM SHALL hold only the
  `mctl-gitops-main-writes` mutex at template level, retry `git push` at most
  five times with `git pull --rebase` between attempts, and fail after the
  fifth — all unchanged.
- WHILE this change is unmerged THE SYSTEM SHALL leave
  `SHEPHERD_ADOPT_PRS` unset in `cronworkflow-mctl-agents-shepherd.yaml`, and
  the ordering (`this` before enablement) SHALL be recorded on both
  `mctlhq/mctl-gitops#1278` and `mctlhq/mctl-agents#334`.
- WHEN the repository's CI runs on a pull request THE SYSTEM SHALL execute a
  unit test that drives the shepherd commit script's extracted logic against a
  throwaway git repository and asserts the adoption-only, mixed, empty and
  refused cases.

## Out of scope

- Any change to `mctlhq/mctl-agents`: the writer, the `.prref.yaml` schema,
  the `SHEPHERD_ADOPT_*` env contract, and the discovery glob are `#334`.
- Turning adoption on. Setting `SHEPHERD_ADOPT_PRS` / `SHEPHERD_ADOPT_REPOS`
  on `cronworkflow-mctl-agents-shepherd.yaml` is a separate, later commit that
  this change unblocks.
- `cwft-mctl-agents-reconcile.yaml` and `cwft-mctl-agents-implement.yaml`,
  which stage the same `.status.yaml`-only allow-list. Neither writes adoption
  records, so neither is widened here.
- `cwft-mctl-agents-run.yaml`, which already stages all of
  `platform-gitops/agents-state/` and so needs no change either way.
- Any ArgoCD, mutex, PVC, resource, TTL, artifact-key or `notify-telegram`
  change; the post-deploy-verify step; and the two `assert-attempt` /
  fallback-token behaviours.
- Reading, rendering or alerting on adoption records anywhere else (mentor
  digest, `mctl-api`, Backstage). Nothing but the shepherd reads them.

## Open questions

- The issue names the pathspec as `':(glob)*/adopted-prs/*/**'`. Measured
  against real git: a `:(glob)` pathspec is resolved relative to the process's
  working directory (the repository root in both scripts here), and `*` does
  not cross `/`, so that literal expression matches **nothing** —
  `platform-gitops/agents-state/mctl-web/adopted-prs/pr-42/.prref.yaml` is not
  matched by it. Interpretation taken: the issue quotes the shape relative to
  `<state_dir>`, and the pathspec to use is
  `':(glob)platform-gitops/agents-state/*/adopted-prs/*/**'`, matching the
  `*/proposals/*/**` shape `cwft-mctl-agents-investigate.yaml` already uses.
- Whether the allow-list should admit only `.prref.yaml` or any file inside
  `adopted-prs/pr-<number>/`. Interpretation taken: the whole record
  directory, mirroring the investigate template's
  `^platform-gitops/agents-state/[^/]+/proposals/[^/]+/[^/]+` regex, so that a
  later `#334` revision adding a sibling file inside the record does not turn
  into a hard refusal in this repository. The staging pathspec and the
  validation regex must describe the same set; that equality is the invariant,
  not the exact tightness.
- Whether a tick whose only change is an adoption record should report
  `activity=yes` to `notify-telegram`. Interpretation taken: yes — it is real
  durable work, and `activity` exists to distinguish a working tick from an
  idle one.
- Whether adoption records should ever be pruned once a PR merges. `#334`
  states no code path touches `adopted-prs/` again after a terminal status.
  Interpretation taken: no pruning here; the deletion channel is wired only so
  an operator-side `git rm` is not fought by the pipeline.
