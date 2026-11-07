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

Transport entries (`kind: transport`, the agent's Bash and other tool
subprocesses) are `bypass-open`; `no-mctl-token` once their surface's
container maps no `MCTL_TOKEN` and its image is at least the entry's
`min_image_version` (both checked); or `no-shell-session` when the surface
keeps the token but has a `fixed_run_mode`, a literal image and at least the
entry's `min_image_version`, the first release whose session is built
without Bash (all checked). `investigate-bash` is `no-mctl-token`:
the investigator's MCP and REST calls use its scoped run token
(mctlhq/mctl-agents#717 option c), so a tool can reach only what the
`investigate` scope admits.

`mctl-agents-run` is split by mode. `run-orchestrator` (full, mentor-only,
single-service) maps no `MCTL_TOKEN`, so these modes run with no `mcp__mctl__*`
tools, and the mentor loses its cross-check reads. That half is
`run-orchestrator-bash`, `no-mctl-token`. `run-bash`, `bypass-open`, is the other
half. `run-incident-responder` keeps the token because resolving
incidents needs mctl-api, and it sets `RUN_MODE` as a literal, so no workflow
parameter can start a service-agent mode in that pod. CI checks the literal,
the routing, that no other template in the file maps `MCTL_TOKEN`, and the
profile's tool list (`fixed_run_mode`, `execution_profile`).

That split does not close the path. A profile not listing Bash, like the SDK's
`allowed_tools`, is a permission list and removes nothing: the responder session
still exposes Bash, and only the CLI permission mode limits what it runs. CI
cannot see this, because it reads the profile and not the session. The entry
therefore belongs to the `incident-responder` surface, and it cannot return to
`no-mctl-token`, because that surface keeps the token.

Closing it uses `no-shell-session`. mctlhq/mctl-agents#1024 builds the
responder session from a tool list without Bash, and lets it write only its
state directory. The image must be one no caller can choose, so
`run-incident-responder` takes a literal image instead of
`{{workflow.parameters.agent_image}}`, and CI requires the literal (check 7).
The incident loop stops sending an image pin (mctlhq/mctl-agents#1031), and
mctl-api no longer declares one for the operation (mctlhq/mctl-api#944). The
release bump rewrites the literal together with the parameter default.
`run-bash` flips to `no-shell-session`, with `min_image_version` set to the
release carrying #1024, only once:

1. that release is out, and the literal is at or above it;
2. a real responder run shows no `Bash` in the session's init tool list,
   the mctl MCP server connected, and its proposal files written, or an
   incident acknowledged or resolved.

What it rests on: the CLI's own protected paths (settings and `.git` files
are not writable from a session without Bash). Re-check that on every
claude-agent-sdk bump. The responder's static token is
mctlhq/mctl-agents#737, a separate gap. A responder pod with no token exits
successfully having done nothing, so after any change here confirm that a run
actually processed an incident.

Known gap, stated plainly: the Bash and `MCTL_TOKEN` path of the remaining
model-running templates (implement, shepherd, the incident responder) is
`bypass-open`. The checkpoint does not gate Bash, so
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
