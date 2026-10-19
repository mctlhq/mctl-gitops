# Policy checkpoint coverage (mctl-agents)

Issue: mctlhq/.github#181. Design: ADR 014 in mctl-agents. Manifest:
`platform-gitops/governance/policy-checkpoint-coverage.yaml`. CI:
`tests/test_policy_checkpoint_coverage.py` (`validate-manifests.yml`).

## What this controls

The checkpoint gates `mcp__*` tool calls of a model session. With
`MCTL_POLICY_APPROVALS=mctl-api` a non-read `mcp__mctl__*` call creates or
redeems a durable approval request in mctl-api. Unset, empty or `none`, the
backend is `NO_APPROVALS` and REQUIRE_APPROVAL simply blocks. An unrecognised
value fails closed (`APPROVAL_UNKNOWN`, an `UNDECIDED_CODES` DENY). The client
authenticates with `MCTL_TOKEN`; no extra token or Vault key exists. It needs
mctl-agents >= 1.86.1 (`min_approvals_version`, mctlhq/mctl-agents#714).

There is no park-and-resume: a REQUIRE_APPROVAL hit blocks the action and
leaves an approval request behind.

## Reading the manifest

Each entry is one execution surface: a worker values file or a template of a
`cwft-mctl-agents-*.yaml` whose container runs the mctl-agents image.

- `governed: true`: must set `MCTL_POLICY_APPROVALS: mctl-api` as a literal.
  `rollout: staged` means the env is not deployed yet; it is flipped after the
  investigator evidence below, then the marker is removed.
- `governed: false` needs a `boundary`: `no-model-session`, `no-mctl-token`,
  `operator-operation` (all checked mechanically) or `bypass-open` (a known
  gap, needs `tracked_by`; CI prints `bypass-open: N` on every run).

Known gap, stated plainly: the Bash and `MCTL_TOKEN` path of every
model-running template is `bypass-open`. The checkpoint does not gate Bash, so
"governed transports cannot be bypassed" is NOT achieved by this manifest.
Tracked by mctlhq/mctl-agents#717 and mctlhq/mctl-api#723 (separate from
mctlhq/mctl-api#721). The shepherd pod forces `NO_APPROVALS` by design
(`run_shepherd.py`), so investigator evidence does not cover it.

## Adding a surface

1. Add a container or worker that runs the mctl-agents image. CI fails naming it.
2. Add one manifest entry. Governed: add the env. Not governed: give boundary
   and reason, plus `tracked_by` for `bypass-open`.
3. A stale entry (removed template) also fails CI.

## Deployment checks

Wait about 3 minutes after merge for Argo CD to sync; running workflows keep
the template they were submitted with.

- Positive (T5): submit `cwft-mctl-agents-investigate` against a sandbox
  issue. `POLICY_DECISION` lines must show the mctl-api backend, and a non-read
  MCP attempt must yield REQUIRE_APPROVAL with an `approval_ref` visible in the
  mctl-api action approvals. Run: _to be filled in after rollout._
- Negative (T6): a one-off submit with the approval store unreachable or an
  invalid approval credential. Expected DENY with an `UNDECIDED_CODES` code in
  `POLICY_DECISION` and the evidence `PolicyDecisionRef`; the action must not
  run. Run: _to be filled in after rollout._

Find the approval request in mctl-api by the `approval_ref` from the
`POLICY_DECISION` line (`mctl_get_workflow_logs` on the run).

## Rollback

Revert the PR that added the env. Removing it returns the surface to
`NO_APPROVALS`, which stays fail-closed. In the same change set the manifest
entry to `governed: false`, `boundary: bypass-open`, with `tracked_by` naming
the rollback reason; CI rejects a governed surface without the env. If the CI
step itself misbehaves, revert only its step in `validate-manifests.yml`.
