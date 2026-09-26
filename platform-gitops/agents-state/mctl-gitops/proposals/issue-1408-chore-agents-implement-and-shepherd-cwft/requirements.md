# Implement and shepherd CWFTs accept optional Temporal/WorkItem correlation parameters

## Context

`cwft-mctl-agents-investigate.yaml` already accepts five optional,
empty-by-default parameters — `work_item_id`, `execution_id`,
`temporal_workflow_id`, `temporal_run_id`, `execution_request_id` — and binds
each one to the runner container as `WORKFLOW_*` env (gitops#1279; see
`spec.arguments.parameters` lines 92-129 and `run-investigator`'s
`container.env` lines 583-592). The model-usage producer inside the agent image
(`mctl-agents` `orchestrator/usage_ledger.py:138-142`) reads that env and
stamps the resulting usage records with the WorkItem and the Temporal
workflow/run that caused the run. `cwft-mctl-agents-implement.yaml` and
`cwft-mctl-agents-shepherd.yaml` declare none of those parameters: their
runners bind only `WORKFLOW_NAME` (implement line 658, shepherd line 683,
both commented as "the join key of this run's usage records to its
`agent_executions` row"). So when a DevLoopWorkflow submits an implement or a
shepherd stage, the usage records it produces can be joined to an Argo run name
but not to the WorkItem, the execution, or the Temporal workflow/run — which is
owner decision 4 of mctlhq/.github#50.

This proposal mirrors gitops#1279 onto the two remaining agent stage templates,
with one deliberate difference: the values travel **through env only**. The
investigator additionally forwards them as CLI flags because
`run_issue_investigator.py` grew `--work-item-id` / `--temporal-workflow-id`
etc. (mctl-agents#267, #461, #451); `run_implementer.py` and `run_shepherd.py`
have no such flags, so appending them would make argparse exit non-zero on
every run. Env-only also keeps the values out of every shell line, which is the
injection case gitops#1279 was careful about and which
`scripts/validate-shell-param-interpolation.py` enforces in CI.

## User stories

- AS the usage/governance owner of mctlhq/.github#50 I WANT implementer and
  shepherd usage records to carry the Temporal workflow id, the Temporal run
  id, the WorkItem id, the execution id and the execution-request id SO THAT
  one DevLoop cycle's spend can be attributed end to end instead of only for
  its investigate stage.
- AS the dev-loop control plane (DevLoopWorkflow) I WANT to pass those
  identifiers as ordinary Argo workflow parameters when I submit the implement
  or shepherd CWFT SO THAT I do not have to invent an out-of-band correlation
  channel or rely on the runner deriving an id it cannot know.
- AS a platform operator running `mctl_trigger_implementer`, the shepherd cron
  (`cronworkflow-mctl-agents-shepherd.yaml`) or a hand-submitted Workflow
  I WANT a submit that passes none of the new parameters to behave exactly as
  it does today SO THAT this is a zero-behaviour-change change for every
  existing caller.
- AS a reviewer of this repo I WANT the new values to be unable to reach a
  shell command line SO THAT a hostile or malformed identifier cannot execute
  inside a pod that mounts the write-capable gitops deploy key and a GitHub
  token.

## Acceptance criteria (EARS)

- WHEN a Workflow is submitted against `mctl-agents-implement` or
  `mctl-agents-shepherd` THE SYSTEM SHALL accept the optional parameters
  `work_item_id`, `execution_id`, `temporal_workflow_id`, `temporal_run_id`
  and `execution_request_id`, each declared in `spec.arguments.parameters`
  with `value: ""`.
- WHEN the runner container of `run-implementer` or `run-shepherd` starts THE
  SYSTEM SHALL export those five parameters as `WORKFLOW_WORK_ITEM_ID`,
  `WORKFLOW_EXECUTION_ID`, `WORKFLOW_TEMPORAL_WORKFLOW_ID`,
  `WORKFLOW_TEMPORAL_RUN_ID` and `WORKFLOW_EXECUTION_REQUEST_ID`, each bound
  exactly once, via `env:` with `value: "{{workflow.parameters.<name>}}"`.
- WHILE any of the five parameters holds a value THE SYSTEM SHALL keep that
  value out of every interpreted block: no `{{workflow.parameters.work_item_id}}`
  (or the other four) may appear in `container.args`, `script.source`,
  `container.command` or any `initContainers` command in either template.
- WHEN a submit omits all five parameters (or passes them as empty strings)
  THE SYSTEM SHALL build byte-identical argv to what it builds today —
  `python -m orchestrator.run_implementer [--service X] [--slug Y]
  --max-proposals N` and `python -m orchestrator.run_shepherd [--service X]
  [--slug Y] [--dry-run]` — and SHALL NOT change any other step
  (`commit-and-push`, `post-deploy-verify`, `assert-attempt`,
  `notify-telegram`) or any commit message or incident fingerprint.
- WHEN all five parameters are set, including to values carrying shell
  metacharacters (`; touch /tmp/pwned ;`, `a" ; id ; "b`) THE SYSTEM SHALL
  build the same argv as in the omit-all case and SHALL NOT execute any part
  of the values.
- WHILE the fallback attempt (`implement-fallback` / the shepherd's account-2
  retry) runs THE SYSTEM SHALL expose the same five env values as the primary
  attempt, because both attempts instantiate the same runner template.
- IF the shepherd's in-pod implementer subprocess runs (the `review-fixing`
  path) THEN THE SYSTEM SHALL let it inherit the same five env values, with no
  additional threading.
- WHEN CI runs THE SYSTEM SHALL prove the above by executing a new test
  (`tests/test_cwft_implement_shepherd_work_context_env.py`) that extracts the
  argv-building block verbatim from each template and exercises omit-all,
  set-all and injection cases, wired into
  `.github/workflows/validate-manifests.yml` beside the existing
  "Unit-test the investigate CWFT's optional work-context argv" step.
- WHILE this change is in effect THE SYSTEM SHALL keep
  `scripts/validate-shell-param-interpolation.py` passing with no new entry in
  its `BASELINE` or `CONSTRAINED` sets.

## Out of scope

- Making the DevLoopWorkflow (or any other caller) actually pass the values —
  that is a `mctl-agents` child of mctlhq/.github#50 which depends on this
  change landing first.
- Any change to `orchestrator/usage_ledger.py`, `run_implementer.py` or
  `run_shepherd.py`; no `agent_image` bump is part of this proposal.
- Adding CLI flags (`--work-item-id` and friends) to the implementer or
  shepherd entry points.
- `cwft-mctl-agents-investigate.yaml`, `cwft-mctl-agents-run.yaml`,
  `cwft-mctl-agents-reconcile.yaml`, `cwft-mctl-agents-approve.yaml` and the
  incident templates.
- Validating or normalising the identifier values (shape, prefix, existence).
  Empty means absent; anything non-empty is carried verbatim.
- mctl-api's operations registry (a different repository): whether
  `mctl_trigger_implementer` exposes the parameters is tracked there.

## Open questions

- Does the usage producer treat an env var set to `""` the same as an absent
  one? After this change the five vars are always present on implement and
  shepherd pods, empty for every current caller. `cwft-mctl-agents-investigate`
  has shipped exactly this shape since gitops#1279 and its records are
  correct, so the reasonable interpretation is yes; task 9 verifies it on one
  real post-merge record rather than assuming.
- A shepherd tick submitted without `service`/`slug` can act on several
  proposals belonging to different WorkItems, while the five parameters are
  per-submit. The reasonable interpretation: the values describe the DevLoop
  that submitted the tick, so a DevLoop-submitted shepherd run is expected to
  also pass `slug` (or `service`); an unfiltered cron tick passes nothing and
  is unaffected. Recorded here for the owner; no gitops-side enforcement is
  proposed.
- Ordering against the caller: Argo rejects a submit carrying a parameter the
  template does not declare, so this change must land (and ArgoCD must sync)
  before the `mctl-agents` DevLoop change starts sending the values. Assumed,
  not enforced from this repo.
