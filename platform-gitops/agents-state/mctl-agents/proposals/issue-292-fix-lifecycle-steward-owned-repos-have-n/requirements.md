# Fix-only shepherd mode: a route from review findings back to code for steward-owned repos

## Context

PR lifecycle ownership on the mctl platform is partitioned by repository.
`orchestrator/run_shepherd.py` reads `SHEPHERD_SKIP_SERVICES` at import time
(`_skip_services_from_env`, line 316) and `_discover_refs` (line 492) drops
every proposal belonging to a listed service before any other filter runs.
The gitops CronWorkflow lists five services there — `mctl-design`,
`mctl-telegram`, `mctl-gitops`, `mctl-pairdesk`, `mctl-academy` — handing them
to the `pr-steward` that runs in the claude-remote pod. The steward can merge a
green PR and escalate a blocked one, but it has no equivalent of the shepherd's
`address-review` decision: the only code path that turns review findings into a
commit is `run_shepherd.apply_followup` (line 1381), which forks
`orchestrator.run_implementer --review-feedback <bundle>` — a flag reachable
from nowhere else.

The result is a hole in the durable DevLoop for five of fourteen `SERVICES`,
including `mctl-telegram`, the most active issue-driven target. When a reviewer
returns `CHANGES_REQUESTED`, the proposal sits at `implemented` with a blocked
PR indefinitely and a human has to write the patch by hand
(mctlhq/mctl-telegram#486, 2026-09-03). The skip is applied *before*
`service_filter`, so even the DevLoopWorkflow's own in-loop tick —
`_shepherd_tick` in `orchestrator/temporal/workflows/dev_loop.py` (line 976),
which submits `mctl-agents-shepherd` with `{"service", "slug"}` and therefore
runs the shepherd in targeted mode — is a no-op for these repos. The
`review-fixing` status exists in `SHEPHERD_INPUT_STATUSES` and nothing can ever
put these proposals into it.

This proposal splits shepherd ownership by *stage* rather than by repo: a
**fix-only** mode in which the shepherd discovers, reviews and pushes follow-up
commits for a service but is structurally incapable of merging it, leaving
merge to the steward and its per-repo `merge_mode`.

## User stories

- AS the DevLoop, I WANT a review-fix stage for steward-owned repositories SO
  THAT a `CHANGES_REQUESTED` verdict on a `mctl-telegram` PR is answered by a
  follow-up commit instead of stalling until a human notices.
- AS the platform operator, I WANT one command that turns the current review
  findings on a specific PR into a pushed fix SO THAT I do not have to author
  the patch or a findings bundle by hand.
- AS the owner of the ownership split, I WANT the shepherd to keep its hands
  off merge for steward-owned repositories SO THAT `mctl-telegram`'s
  squash-only rule and `mctl-design`'s branch protection stay enforced by the
  actor that knows about them.
- AS the maintainer of `mctl-academy`, I WANT a code-level guarantee that no
  agent can merge its PRs SO THAT content publication stays gated on a human
  CODEOWNER regardless of how the shepherd's environment is configured.
- AS an operator reading `git log` on gitops, I WANT a stalled steward-owned
  proposal to be distinguishable from a healthy one SO THAT a blocked
  security-relevant PR is visible without watching GitHub.

## Acceptance criteria (EARS)

### Fix-only service mode

- WHEN `SHEPHERD_FIX_ONLY_SERVICES` names a service THE SYSTEM SHALL include
  that service's proposals in normal (non-reconcile) discovery in
  `_discover_refs`, exactly as if it were not in `SHEPHERD_SKIP_SERVICES`.
- WHILE a service is in fix-only mode THE SYSTEM SHALL evaluate `decide()` for
  its proposals and SHALL execute the `address-review` decision — building the
  findings bundle and forking `run_implementer --review-feedback` via
  `apply_followup` — unchanged from full mode.
- WHILE a service is in fix-only mode THE SYSTEM SHALL NOT invoke
  `merge_pr()`; a would-be `merge` decision SHALL be returned as the new
  decision `defer-merge` and SHALL leave `.status.yaml`'s `status` untouched.
- WHILE a service is in fix-only mode THE SYSTEM SHALL still apply the
  observation-only decisions `flip-to-merged` and `flip-to-rejected`, so a
  merge performed by the steward is projected into `.status.yaml` on the next
  tick.
- WHILE a service is in fix-only mode THE SYSTEM SHALL still honour
  `MAX_REVIEW_ATTEMPTS` and flip the proposal to terminal `review-stuck` when
  the cap is exhausted.
- WHEN a service is named in both `SHEPHERD_SKIP_SERVICES` and
  `SHEPHERD_FIX_ONLY_SERVICES` THE SYSTEM SHALL treat it as fix-only and SHALL
  print a `warn:` line naming the service, so a gitops rollout that adds the
  new variable before removing the old one converges to the intended
  behaviour.
- WHEN `SHEPHERD_FIX_ONLY_SERVICES` contains a name that is not in
  `config.settings.SERVICES` THE SYSTEM SHALL print a `warn:` line listing the
  unknown names, mirroring `_skip_services_from_env`.
- WHEN `SHEPHERD_FIX_ONLY_SERVICES` is unset or empty THE SYSTEM SHALL behave
  exactly as it does today for every service.

### Never-merge guarantee

- WHILE a service is listed in the in-code constant `NEVER_MERGE_SERVICES`
  (initially `{"mctl-academy"}`) THE SYSTEM SHALL never return the `merge`
  decision for it and SHALL never call `merge_pr()` for it, regardless of
  `SHEPHERD_SKIP_SERVICES`, `SHEPHERD_FIX_ONLY_SERVICES`, `--fix-only`, or any
  other environment input.
- IF `merge_pr()` is reached for a service in `NEVER_MERGE_SERVICES` THEN THE
  SYSTEM SHALL refuse the merge, print an `error:` line, and return
  `(False, None)` rather than executing `gh pr merge`.

### Operator one-shot

- WHEN `run_shepherd` is invoked with `--fix-only` THE SYSTEM SHALL apply
  fix-only mode to every proposal processed in that run, whatever the
  environment lists.
- WHEN `run_shepherd --fix-only --service <svc> --slug <slug>` is invoked for a
  proposal in `implemented` or `review-fixing` with an open PR carrying P1/P2
  findings on the current head SHA THE SYSTEM SHALL fetch the review, build the
  bundle, push a follow-up commit through the implementer, post `@claude
  review`, and increment `review_attempts` — without merging.
- WHEN `--fix-only` is combined with `--reconcile` THE SYSTEM SHALL reject the
  invocation with exit code 2, since reconcile never merges or fixes anything.
- WHEN `--fix-only` is combined with `--dry-run` THE SYSTEM SHALL report the
  discovered proposals without calling the SDK or forking the implementer,
  matching today's dry-run contract.

### Observability

- WHEN a tick returns `defer-merge` THE SYSTEM SHALL print a `info:` line
  naming the service, slug, PR and the reason (`merge owned by pr-steward`),
  and SHALL include the decision in the `=== Shepherd summary ===` block.
- WHEN a tick returns `defer-merge` THE SYSTEM SHALL record `merge_owner:
  pr-steward` in the proposal's `.status.yaml` via the existing
  change-only writer `_update_status_if_changed`, so repeated ticks produce no
  new gitops commits once the field is present.
- WHEN a fix-only proposal is merged or rejected THE SYSTEM SHALL clear
  `merge_owner` in the same write that sets the terminal status.

## Out of scope

- Teaching the `pr-steward` (in `mctl-claude-remote`) to invoke the
  implementer. Option 1 in the issue; rejected in `design.md`.
- Any change to the steward's merge behaviour, its per-repo `merge_mode`, or
  `claude-remote/values.yaml`.
- Adding `mctl-academy` to either the shepherd's fix-only set or the steward.
  Its exclusion from both loops is deliberate; this proposal only hardens the
  guarantee that an agent cannot merge it.
- Changing `SHEPHERD_INPUT_STATUSES`, `RECONCILE_INPUT_STATUSES`, or adding any
  new `.status.yaml` *status* value. `merge_owner` is a field, not a status, so
  `docs/diagrams/archify/facts.yaml`'s status vocabulary is unaffected.
- The gitops-side edit to `cwft-mctl-agents-shepherd.yaml` /
  `cronworkflow-mctl-agents-shepherd.yaml` that actually moves the four repos
  from `SHEPHERD_SKIP_SERVICES` to `SHEPHERD_FIX_ONLY_SERVICES`. That lands in
  `mctl-gitops`; this proposal ships the capability and documents the exact
  edit.
- The mctl-api change that would expose a `fix_only` parameter on
  `mctl_trigger_shepherd`. Documented as a companion follow-up; the `--fix-only`
  CLI flag is the contract it would call.
- Alerting infrastructure (Prometheus rules, Telegram notifications) on stalled
  proposals. This proposal makes the stall *legible* in the log and in
  `.status.yaml`; wiring an alert onto it is separate work.

## Open questions

- Should `mctl-academy` eventually be placed in fix-only mode? Fixing review
  findings is not content publication, and the `NEVER_MERGE_SERVICES` guard
  makes it safe. This proposal leaves Academy fully skipped to stay inside the
  issue's stated scope, and the code is written so flipping it later is a
  one-line gitops change.
- `mctl-gitops` is in the skip list and is also the repository holding
  `agents-state/`. A shepherd fix-up commit on a `feat/agents-*` branch there
  does not touch `agents-state/` on `main`, so no self-interference is
  expected — but the migration should move `mctl-gitops` last and be watched
  for one cycle. Assumed safe here.
- Who resolves a race in which the steward merges the PR while the implementer
  subprocess is mid-push? The implementer's `_branch_exists_on_origin` check
  returns `EXIT_BRANCH_MISSING_ON_ORIGIN` (43), which the shepherd classifies
  as deterministic and which therefore consumes a `review_attempts` slot. The
  design treats this as acceptable (the next tick observes `merged` and flips
  to terminal), but an implementer that distinguished "branch gone because
  merged" from "branch gone because deleted" would be cleaner.
- Should `defer-merge` also post a comment on the PR handing it to the steward?
  Left out to avoid comment spam on every tick; the `.status.yaml`
  `merge_owner` field carries the same information without a per-tick write.
