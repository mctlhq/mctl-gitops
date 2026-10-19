# Design: issue-1980-governance-productionize-policy-approval

## Current state

### Checkpoint code exists, but deployment never enables it

The checkpoint code lives in mctl-agents. That source is not in this clone, so the
description below comes from the accepted and merged proposals that this repository
records under `platform-gitops/agents-state/mctl-agents/proposals/`:

- `orchestrator/policy_checkpoint.py` (ADR 014):
  - `ActionRequest -> decide() -> ALLOW | DENY | REQUIRE_APPROVAL`.
  - `decide()` never raises. Evaluator, identity and approval-lookup failures map to DENY codes in `UNDECIDED_CODES`.
  - Every decision emits a `POLICY_DECISION` line.
  - `BUILTIN_POLICY` is closed-world. MCP read verbs are ALLOW behind a grant, and every other `mcp__mctl__*` tool hits `mctl-mcp-default-approval` (REQUIRE_APPROVAL).
  - Sources: `issue-556-.../design.md` lines 5-24 and `issue-198-.../design.md` lines 1-80.
- `orchestrator/action_approvals.py`:
  - `MctlApiApprovals` is the durable approval client against mctl-api.
  - It is selected only by `MCTL_POLICY_APPROVALS=mctl-api`.
  - If the variable is unset, empty or `none`, the backend is `NO_APPROVALS` and REQUIRE_APPROVAL simply blocks (`issue-198-.../design.md` line 58).
- `orchestrator/options.py` installs `_PolicyCheckpointHook` as the SDK `PreToolUse` hook for `MCP_TOOL_CALL` only.
- The merge gate (mctl-agents#519, status `merged`, PR mctl-agents#524) adds `MCTL_POLICY_MERGE_APPROVAL=require`. Its design states that `MCTL_POLICY_APPROVALS=mctl-api` "must also be set on the worker" (`issue-519-.../design.md` line 316).
- The human-approval Temporal wait (mctl-agents#198) was `rejected`: PR mctl-agents#484 was closed unmerged. A REQUIRE_APPROVAL hit therefore creates or redeems an approval request but has no durable park-and-resume.

### Deployment surfaces of mctl-agents in this repository

- **Temporal workers** (`platform-gitops/services/admins/`): `mctl-agents-worker`, `mctl-agents-worker-exec` and `mctl-agents-worker-implement`, all on image tag `1.86.1`.
  - Their `env:` blocks carry `TEMPORAL_*`, `MCTL_TRACE_*`, `LOG_LEVEL`, `LIFECYCLE_ROLLOUT_MODE`, `GITHUB_TOKEN_FILE`, `EXECUTION_REQUEST_DISPATCHER` and `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`.
  - None of them sets any `MCTL_POLICY_*` variable.
  - `-exec` and `-implement` hold only `MCTL_TOKEN` and start no agent session. Their own comments say "No GitHub, no agent SDK".
- **ClusterWorkflowTemplates** (`platform-gitops/argo-workflows/cluster-templates/`). All default to `agent_image` `ghcr.io/mctlhq/mctl-agents:1.86.1`:
  - `cwft-mctl-agents-investigate.yaml` runs `python -m orchestrator.run_issue_investigator`.
  - `cwft-mctl-agents-implement.yaml` runs `orchestrator.run_implementer`.
  - `cwft-mctl-agents-shepherd.yaml` runs `orchestrator.run_shepherd`.
  - `cwft-mctl-agents-reconcile.yaml` runs `run_shepherd --reconcile`, with no model.
  - `cwft-mctl-agents-run.yaml` runs `orchestrator.run_all`, with `RUN_MODE` set to `full`, `mentor-only` or `single-service`. This is the mentor path.
  - `cwft-mctl-agents-usage-collector.yaml` runs `run_usage_collector`, with no model.
  - `cwft-mctl-agents-approve.yaml` and `cwft-mctl-agents-daily.yaml` are `sh` steps.
  - The cron entry points `cronworkflow-mctl-agents-{incidents,shepherd,usage-collector}.yaml` reach these templates.
  - No template sets any `MCTL_POLICY_*` variable. A repo-wide grep outside `agents-state/` for `MCTL_POLICY` returns nothing.
- **The bypass transport.** The model-running containers (investigate, implement, shepherd, run) hold `MCTL_TOKEN`, from secret `mctl-agents-secrets` key `mctl-token`, which is the static admin service token.
  - The templates' own comments confirm the agent holds Bash, for example `cwft-mctl-agents-investigate.yaml` lines 499-531 and `cwft-mctl-agents-run.yaml` lines 323 and 343.
  - Because the `PreToolUse` checkpoint gates only `mcp__*` calls, a model can run `curl -H "Authorization: Bearer $MCTL_TOKEN" .../api/v1/operations/<op>/execute` from Bash. That call never reaches the checkpoint. This is the "Bash/mentor" gap the audit names.
- **Existing CI pattern to reuse.**
  - `tests/test_cwft_execution_trace_env.py` reads every `cwft-mctl-agents-*.yaml` and `services/admins/mctl-agents-worker*` values file. It asserts env invariants, including a minimum image version `MIN_SCOPED_VERSION`.
  - It is wired into `.github/workflows/validate-manifests.yml` ("Unit-test the mctl-agents CWFTs' execution-trace env").
  - `MCTL_EVIDENCE_AMENDMENT_2: "true"` in `cwft-mctl-agents-investigate.yaml` shows the precedent for a feature env flag declared per template.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` contains `admins`, `karabu` and `labs`. `services/admins/` contains `mctl-agents-worker`, `mctl-agents-worker-exec`, `mctl-agents-worker-implement`, `mctl-design`, `mctl-docs`, `mctl-web` and `umami`.
- `services/admins/mctl-agents-worker/values.yaml`, `-exec/values.yaml` and `-implement/values.yaml` were read: there is no `MCTL_POLICY_APPROVALS`, no `MCTL_POLICY_MERGE_APPROVAL` and no other `MCTL_POLICY_*` variable, and the image tag is `1.86.1` on all three.
- A repo-wide grep for `MCTL_POLICY` (excluding `agents-state/`) matched nothing. Prior proposals mention the variable only as future rollout steps.
- No mctl MCP tool calls were made. The gitops checkout answers the configuration question, and live pod environments were not observed. A live env could differ from GitOps only through manual drift, which is not checked here.
- The mctl-agents source (exact accepted values of `MCTL_POLICY_APPROVALS`, the credential used by `ActionApprovalClient`, and the release that first shipped `MctlApiApprovals`) was not available. These gaps are recorded under Open questions in requirements.md.

## Proposed solution

### 1. Coverage manifest: one declared contract

Add `platform-gitops/governance/policy-checkpoint-coverage.yaml` (schema `mctl-policy-coverage/v1`). Each entry classifies one execution surface:

```yaml
schema: mctl-policy-coverage/v1
policy: mctl-agents/policy/v1          # ADR 014 BUILTIN_POLICY; no new engine
approvals_backend: mctl-api            # the only accepted governed value
surfaces:
  - id: worker-control
    kind: worker
    path: services/admins/mctl-agents-worker/values.yaml
    governed: true                     # runs DevLoopWorkflow, merge-watch, dispatcher
  - id: investigate
    kind: cwft
    path: argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml
    template: run-investigator
    governed: true
  - id: investigate-bash
    kind: transport
    of: investigate
    governed: false
    boundary: bypass-open              # Bash + MCTL_TOKEN in the same env
    tracked_by: mctlhq/mctl-agents#<companion>
    reason: PreToolUse gates mcp__* only; Bash can call mctl-api with MCTL_TOKEN
  - id: worker-exec
    kind: worker
    path: services/admins/mctl-agents-worker-exec/values.yaml
    governed: false
    boundary: no-model-session         # submit_and_wait only; no agent SDK
    reason: executes operations already decided by the control worker's checkpoint
  # ... implement, shepherd, run (full/mentor-only/single-service), reconcile,
  #     usage-collector (no-model-session, no MCTL_TOKEN), approve, daily
```

The `boundary` values form a closed set:

| boundary | meaning | how CI checks it |
|---|---|---|
| `no-model-session` | no SDK session, so no model-selected actions | container command is not an agent entry point; `CLAUDE_CODE_OAUTH_TOKEN` is absent |
| `no-mctl-token` | cannot call mctl-api as the admin principal | `MCTL_TOKEN` is absent from env and envFrom secret data |
| `operator-operation` | deterministic step behind an admin-only mctl-api operation | the image is not mctl-agents, or no model token is present |
| `bypass-open` | a known gap, kept visible | `tracked_by` must be set; every run prints a warning count |

Surfaces: the three workers, plus every template in each `cwft-mctl-agents-*.yaml` whose container runs the mctl-agents image. The mentor path is classified as part of `run`, which covers all three `RUN_MODE` values in one container.

### 2. Governed surfaces declare the canonical checkpoint

Every surface marked `governed: true` gets this env entry:

```yaml
- name: MCTL_POLICY_APPROVALS
  value: mctl-api
```

In worker values it is written as `MCTL_POLICY_APPROVALS: mctl-api`. Each entry has a comment citing ADR 014, this issue and the manifest.

Governed surfaces: `mctl-agents-worker`, investigate, implement, shepherd, reconcile and run.

- **Rollout order.** The flag goes on the investigator first. The rest follow in a second PR after one observed approval request (requirements Open question 3).
- **Credential.** If the approval client needs a token other than `MCTL_TOKEN`, add `MCTL_APPROVAL_WRITER_TOKEN` from `mctl-agents-secrets` with `optional: false`. This follows the `MCTL_EVIDENCE_WRITER_TOKEN` pattern but deliberately does not set it optional: a governed surface must not start without approval evidence capability.
- **No policy rules change.** `MCTL_POLICY_MERGE_APPROVAL` stays unset (Out of scope).

### 3. CI enforcement: `tests/test_policy_checkpoint_coverage.py`

The test follows the structure of `tests/test_cwft_execution_trace_env.py`: read from the templates, never restated, print PASS/FAIL, exit non-zero on failure. It asserts the following:

1. Every container in `cwft-mctl-agents-*.yaml` whose image is `{{inputs.parameters.agent_image}}` or `ghcr.io/mctlhq/mctl-agents:*`, and every `services/admins/mctl-agents-worker*/values.yaml`, has exactly one entry in the manifest.
2. Every manifest `path`/`template` still exists. Stale entries fail.
3. Governed surfaces carry `MCTL_POLICY_APPROVALS` equal to `approvals_backend` (`mctl-api`) as a literal value, not a `valueFrom` that could resolve empty. Any other value is a failure.
4. On governed surfaces, the image default meets `MIN_APPROVALS_VERSION`.
5. Each non-governed boundary is checked mechanically according to the table in §1.
6. Any `bypass-open` entry must have `tracked_by`. The test prints a summary line `bypass-open: N` so the gap appears in every CI log.
7. No container anywhere in the repository sets `MCTL_POLICY_APPROVALS` to `none` or an empty value. Turning governance off must go through a manifest edit that is reviewed, not a stray env.

The test is wired into `validate-manifests.yml` next to the execution-trace step.

### 4. Fail-closed and typed evidence

Fail-closed behaviour already exists in `decide()`, which maps approval-lookup errors to an `UNDECIDED_CODES` DENY carried in `PolicyDecisionRef.code`. This proposal does not re-implement it. It pins it with two records:

- **Static.** The test rejects a missing or unknown backend value on governed surfaces.
- **Runtime.** A runbook procedure in `docs/runbooks/policy-checkpoint-coverage.md` covers two cases:
  - **Positive.** Submit `cwft-mctl-agents-investigate` against a sandbox issue. The `POLICY_DECISION` lines must show approvals backend `mctl-api`. A non-read `mcp__mctl__*` attempt must yield REQUIRE_APPROVAL with an `approval_ref` that can be seen in mctl-api action-approvals.
  - **Negative.** Submit the same template with `mctl_api_url` / network to mctl-api blocked (or an invalid approval token in a one-off parameter). This must yield DENY with an undecided code and no action taken.
  - The run names and logs are linked in the PR and in the runbook as deployment evidence.
- **Runtime misconfiguration.** If mctl-agents currently treats an unknown `MCTL_POLICY_APPROVALS` value as `NO_APPROVALS` instead of DENY, a companion issue asks for `configured_policy()` to apply its existing misconfigured-DENY policy to it.

### 5. Closing or classifying the transport gaps

- **Bash in agent sessions** is classified as `bypass-open` with a companion issue on mctl-agents. That issue asks for `MCTL_TOKEN` to be stripped from the SDK subprocess and Bash environment (the orchestrator keeps it in-process). A complementary mctl-api issue asks that governed operations called by the `mctl-agent` service principal require a redeemed approval receipt, which makes the checkpoint non-bypassable server-side.
  - When either fix lands, the entry flips to `no-mctl-token` or is removed, and CI then verifies it.
  - This keeps the gap explicit and impossible to mistake for governed execution, which satisfies acceptance criterion 5, without pretending GitOps alone can close it.
- **Mentor and service agents** (`cwft-mctl-agents-run.yaml`) are classified governed. The same Bash entry (`run-bash`, `bypass-open`) applies.
- **`worker-exec` and `worker-implement`** are `no-model-session`. They execute operations already admitted by the control worker's checkpoint.

## Alternatives

1. **Only add `MCTL_POLICY_APPROVALS=mctl-api` to the env blocks.** This is the smallest change, but nothing would stop a later values edit from removing it, and it says nothing about the non-governed transports. Dropped: it fails acceptance criteria 2 and 5.
2. **A Kyverno or admission policy that rejects mctl-agents pods without the env.** Enforced at admission, but it adds a cluster policy engine dependency for one invariant, gives late feedback (at sync, not at PR), and still cannot express a classification. Dropped in favour of PR-time CI. It could be layered on later.
3. **Remove `MCTL_TOKEN` from the model-running containers in GitOps now.** This would close the Bash bypass immediately, but the orchestrator in the same container needs the token for evidence, usage and MCP. The token is only separable inside the process, which is mctl-agents code. Dropped as a GitOps change and filed as a companion instead.

## Platform impact

- **Migrations.** None. No schema or store changes. The manifest and test are new files.
- **Backward compatibility.** Enabling `mctl-api` approvals turns REQUIRE_APPROVAL hits from a silent block into a real approval request. Behaviour stays fail-closed, because there is no automatic resume (mctl-agents#198 was rejected), so a pending request still blocks that action.
- **Resource impact.** One mctl-api approval create or read per REQUIRE_APPROVAL hit, with up to about 20 s of synchronous wait in the hook (ADR 014 Consequences). No new pods.
- **Risks and mitigations.**
  - *Image too old to understand the flag.* The `MIN_APPROVALS_VERSION` gate in CI covers this. The value must be confirmed (Open question 1).
  - *Approval request flood.* Staged rollout, investigator first, and the mctl-api request rate is observed before widening.
  - *Missing approval credential blocks runs.* Intended under fail-closed. The runbook documents the Vault key.
  - *A `bypass-open` entry is accepted forever.* It requires `tracked_by` and is printed in every CI run. The parent epic mctlhq/.github#181 tracks closure.
