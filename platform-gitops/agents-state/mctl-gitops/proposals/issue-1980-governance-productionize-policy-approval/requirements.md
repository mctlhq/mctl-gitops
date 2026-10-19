# Productionize policy approval checkpoint coverage in GitOps declarations

## Context

The decision-assurance audit (mctlhq/.github#182, finding G5 / P4) found that
mctl-agents ships a canonical policy checkpoint (`orchestrator/policy_checkpoint.py`,
ADR 014) and a durable mctl-api-backed approval store
(`orchestrator/action_approvals.py`, selected with `MCTL_POLICY_APPROVALS=mctl-api`).
However, nothing in mctl-gitops turns that store on. No `MCTL_POLICY_*` variable is
set on any of the three Temporal workers in `platform-gitops/services/admins/` or on
any `cwft-mctl-agents-*.yaml` ClusterWorkflowTemplate. As a result, every deployed
execution runs `BUILTIN_POLICY` with `NO_APPROVALS`. The audit also found that some
supported entry points are outside the checkpoint. The Bash tool in agent sessions and
the mentor path in `cwft-mctl-agents-run.yaml` both run in containers that hold
`MCTL_TOKEN`, the static admin service token, so a model could reach mctl-api without
passing through the MCP `PreToolUse` hook.

This proposal makes the checkpoint an explicit, CI-enforced production contract in
mctl-gitops. It adds a machine-readable classification of every mctl-agents
execution surface as governed or non-governed. Every governed surface declares the
canonical checkpoint configuration. A validation test fails the PR when a surface
is unclassified or when a governed surface drifts. Fail-closed behaviour is
pinned and evidenced. The work reuses the existing ADR 014 policy and the mctl-api
approval contract and adds no second policy engine. Code changes in mctl-agents and
mctl-api are filed as companion issues, not done in this repository.

## User stories

- AS a platform operator I WANT every mctl-agents deployment to explicitly declare
  whether it is governed and how its checkpoint is configured SO THAT I can audit
  governance from GitOps alone, without reading pod environments.
- AS a governance reviewer I WANT CI to reject a manifest change that drops or
  weakens the checkpoint on a governed surface SO THAT the checkpoint cannot be turned
  off silently by an ordinary values edit.
- AS a security reviewer I WANT each non-governed transport, such as Bash in an agent
  session or the mentor digest, to be classified explicitly with its enforced boundary
  SO THAT it is never mistaken for governed execution.
- AS an on-call engineer I WANT an unavailable or misconfigured approval store to
  refuse governed actions with a typed decision code SO THAT a failure is visible in
  `POLICY_DECISION` lines and evidence, not silently allowed.

## Acceptance criteria (EARS)

- THE SYSTEM SHALL keep one classification manifest,
  `platform-gitops/governance/policy-checkpoint-coverage.yaml`. For each mctl-agents
  execution surface, the manifest records the surface (worker values file, or CWFT
  file plus template name), `governed: true|false`, the required checkpoint env
  for governed surfaces, and, for non-governed surfaces, a `boundary` and a `reason`.
- WHILE a surface is classified `governed: true`, its rendered container env SHALL
  contain `MCTL_POLICY_APPROVALS: mctl-api` and SHALL NOT contain any value that
  selects `NO_APPROVALS` (unset, empty or `none`).
- WHEN a PR adds a container that runs the `ghcr.io/mctlhq/mctl-agents` image, or
  adds a worker under `platform-gitops/services/admins/mctl-agents-worker*`, without
  a classification entry, THE SYSTEM SHALL fail `validate-manifests.yml`.
- WHEN a PR removes or changes the checkpoint env on a governed surface, THE SYSTEM
  SHALL fail `validate-manifests.yml` and name the surface and the missing key.
- WHEN a classification entry names a surface that no longer exists, THE SYSTEM
  SHALL fail validation, so that stale entries cannot hide coverage gaps.
- IF a surface is classified `governed: false`, THEN its entry SHALL name an
  enforceable boundary. Examples: "holds no MCTL_TOKEN", "read-only MCP grant only",
  or "no model session". CI SHALL check that boundary against the manifest wherever
  it can be checked mechanically, for example by asserting that `MCTL_TOKEN` is absent
  from that container's env.
- IF the approval store is unreachable or returns an error during a governed
  decision, THEN THE SYSTEM SHALL return DENY with an `UNDECIDED_CODES` code in the
  `POLICY_DECISION` line and in `PolicyDecisionRef`, never ALLOW. This is the
  existing `decide()` contract, pinned here by a recorded deployment check.
- IF `MCTL_POLICY_APPROVALS` holds an unrecognised value on a governed surface, THEN
  THE SYSTEM SHALL fail closed. CI rejects the value statically, and at runtime
  mctl-agents treats the misconfiguration as DENY (companion requirement on
  mctl-agents if the current code does not already do this).
- WHILE an agent session holds the Bash tool and `MCTL_TOKEN` in the same process
  environment, THE SYSTEM SHALL classify that session's Bash transport as
  `governed: false` with the boundary `bypass-open`. CI SHALL treat any `bypass-open`
  entry as a tracked exception that references an open companion issue, so the gap
  stays visible until it is closed.
- WHEN the change is deployed, THE SYSTEM SHALL produce recorded evidence (runbook
  section plus a linked run) of one governed REQUIRE_APPROVAL action creating an
  approval request in mctl-api, and of one DENY with a typed code when the store
  cannot be reached.

## Out of scope

- Changing any rule in `BUILTIN_POLICY` (for example flipping `github-pr-merge` to
  REQUIRE_APPROVAL), or setting `MCTL_POLICY_MERGE_APPROVAL=require` /
  `SHEPHERD_MERGE_APPROVAL_SERVICES`. Each of these is a separate policy decision
  under ADR 014 and is listed under Open questions.
- Implementing code in mctl-agents (removing `MCTL_TOKEN` from the environment of the
  SDK Bash subprocess, a startup assertion for misconfigured approvals) or in mctl-api
  (a server-side approval requirement on governed operations). These are filed as
  companion issues and referenced from the manifest.
- A new policy engine, a new approval store, or a new decision vocabulary.
- Governance of non-mctl-agents workloads such as tenant services or platform
  workflows like `wft-deploy-service`.

## Open questions

1. **Minimum mctl-agents version.** All surfaces run `ghcr.io/mctlhq/mctl-agents:1.86.1`.
   This run could not verify that 1.86.1 reads `MCTL_POLICY_APPROVALS=mctl-api` and
   creates requests through `MctlApiApprovals`. The mctl-agents source was not
   available here. The proposal pins a `MIN_APPROVALS_VERSION` constant in the test.
   Its value must be confirmed against the mctl-agents changelog before merge.
2. **Which mctl-api credential the approval client uses.** `ActionApprovalClient`
   presumably authenticates with `MCTL_TOKEN`. If it needs a dedicated
   approval-writer token (following the precedent of `MCTL_EVIDENCE_WRITER_TOKEN` and
   `MCTL_USAGE_WRITER_TOKEN`), a new Vault key and ExternalSecret entry are needed.
   This was not observed.
3. **Ticket volume.** Turning the store on makes every REQUIRE_APPROVAL hit, for
   example any non-read `mcp__mctl__*` call by the model, create a real approval
   request instead of only blocking. The expected rate is unknown. The recommended
   approach is to roll out on one surface first (the investigator).
4. **The mentor and service-agent runs (`cwft-mctl-agents-run.yaml`).** The proposal
   classifies them as governed because they hold `MCTL_TOKEN` and MCP tools. If the
   owner wants them read-only instead (no `MCTL_TOKEN`, `governed: false` with the
   boundary "no MCTL_TOKEN"), the comment at that template's `MCTL_TOKEN` entry
   ("agents degrade gracefully") suggests that would work. This needs an owner
   decision. The default chosen here is governed.
5. **Merge gating.** Whether the shepherd merge should also be put behind approval
   (`MCTL_POLICY_MERGE_APPROVAL=require`) is left to a separate decision.
