# Tasks: issue-1980-governance-productionize-policy-approval

- [ ] 1. Confirm the companion facts in mctl-agents before writing the manifests. Establish three things: the first release whose `action_approvals.py` and `MctlApiApprovals` read `MCTL_POLICY_APPROVALS=mctl-api`; the credential that `ActionApprovalClient` uses (`MCTL_TOKEN` or a dedicated token); and how an unknown value is handled. — DoD: the three facts are recorded in the PR description, and `MIN_APPROVALS_VERSION` is chosen and is at most `1.86.1`, or a version bump is planned.
- [ ] 2. Inventory every mctl-agents surface: each template in `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml` whose container runs the mctl-agents image or `{{inputs.parameters.agent_image}}`, plus `platform-gitops/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`. Also confirm which images `cwft-mctl-agents-approve.yaml` and `cwft-mctl-agents-daily.yaml` run. — DoD: a complete list with template names, matching what the test in task 4 discovers.
- [ ] 3. Add `platform-gitops/governance/policy-checkpoint-coverage.yaml` (schema `mctl-policy-coverage/v1`) as specified in design §1. Classify worker-control, investigate, implement, shepherd, reconcile and run as governed. Classify worker-exec and worker-implement as `no-model-session`, usage-collector according to its env (`no-model-session`), approve and daily according to task 2, and each model-running template's Bash transport as `bypass-open` with `tracked_by`. (depends on 2) — DoD: every surface from task 2 has exactly one entry, and every non-governed entry has a `boundary` and a `reason`.
- [ ] 4. Add `tests/test_policy_checkpoint_coverage.py`, modelled on `tests/test_cwft_execution_trace_env.py`, implementing checks 1-7 from design §3, and wire it into `.github/workflows/validate-manifests.yml` next to the execution-trace step. (depends on 3) — DoD: the test runs in CI, fails on the current main (the governed surfaces lack the env), and passes once task 5 lands.
- [ ] 5. Declare the checkpoint on governed surfaces in two PRs, following the staged rollout in design §2:
  - (a) `cwft-mctl-agents-investigate.yaml` run-investigator env gets `MCTL_POLICY_APPROVALS: mctl-api`, with a comment citing ADR 014 and this issue. Add the approval-writer credential only if task 1 requires it.
  - (b) After T5 evidence, do the same for implement, shepherd, reconcile, run and `services/admins/mctl-agents-worker/values.yaml`.

  (depends on 1, 4) — DoD: each PR passes `validate-manifests.yml`, and Argo CD shows the templates and worker synced.
- [ ] 6. File the companion issues and link their numbers in the manifest's `tracked_by`:
  - mctl-agents: strip `MCTL_TOKEN` from the SDK Bash/subprocess env, and make an unknown `MCTL_POLICY_APPROVALS` value fail closed via `configured_policy()` if it does not already.
  - mctl-api: governed operations called by the `mctl-agent` principal require a redeemed approval receipt.

  — DoD: issues are open under mctlhq/.github#181, and no `bypass-open` entry lacks a real issue reference.
- [ ] 7. Write `docs/runbooks/policy-checkpoint-coverage.md`. It covers how to read the manifest, how to add a surface, the meaning of each boundary, the positive and negative deployment checks (T5, T6), how to find the approval request in mctl-api, and how to roll back. Add a pointer to it in `CLAUDE.md` next to the agents-app runbook reference. (depends on 3) — DoD: the runbook is merged, and the deployment evidence links are filled in after T5 and T6.

## Tests

- [ ] T1. Unit test (CI): on current main, the coverage test reports FAIL for every governed surface missing `MCTL_POLICY_APPROVALS`. After task 5, it reports PASS.
- [ ] T2. Unit test (CI, synthetic fixture): a new `cwft-mctl-agents-*.yaml` container with the mctl-agents image and no manifest entry makes the test fail, and the failure names the template.
- [ ] T3. Unit test (CI, synthetic fixture): a governed surface with `MCTL_POLICY_APPROVALS` set to `none`, `""` or a `valueFrom`, or a non-governed `no-mctl-token` surface that still maps `MCTL_TOKEN`, each fail with the surface named.
- [ ] T4. Unit test (CI): a stale manifest entry pointing at a removed template fails, and a `bypass-open` entry without `tracked_by` fails.
- [ ] T5. Deployment check (positive): after 5(a) syncs, submit `cwft-mctl-agents-investigate` against a sandbox issue. Expected: `POLICY_DECISION` lines show the mctl-api backend, and a non-read MCP attempt produces REQUIRE_APPROVAL with an `approval_ref` that is visible in mctl-api. Record the run name in the runbook.
- [ ] T6. Deployment check (negative, fail-closed): a one-off submit in which the approval store is unreachable or the approval credential is invalid. Expected: DENY with an `UNDECIDED_CODES` code in `POLICY_DECISION` and in the evidence `PolicyDecisionRef`, and the action does not execute. Record the run name in the runbook.

## Rollback

- Revert the PR from task 5. Removing `MCTL_POLICY_APPROVALS` returns the surfaces to `NO_APPROVALS`, where REQUIRE_APPROVAL still blocks, so the rollback stays fail-closed.
- At the same time, change the affected manifest entries to `governed: false` with boundary `bypass-open` and a `tracked_by` reference to the rollback reason. The coverage test will not accept a governed surface without the env, so the rollback stays explicit instead of silent.
- Wait about 3 minutes for Argo CD to sync before submitting new runs. In-flight Argo runs keep the template snapshot they were submitted with.
- If the CI test itself misbehaves, revert the `validate-manifests.yml` step. The manifest and env declarations can stay.

## Owner review notes (2026-10-19)
These notes are part of the approved scope. The implementation PRs state how each one is handled.
- [ ] R1. Every `tracked_by` reference points at a real, open issue before the manifest merges. Do task 6 before the PR that adds the manifest (task 3), or land both in the same PR.
- [ ] R2. Resolve Open questions 1 and 2 from mctl-agents main before task 5. `ActionApprovalClient` reads `MCTL_TOKEN`, so no new approval-writer token or Vault key is expected; confirm this. Check whether `configured_policy()` already fails closed on an unknown `MCTL_POLICY_APPROVALS` value (`_MisconfiguredApprovals`). If it does, drop that part of the mctl-agents companion issue and cite the existing code instead.
- [ ] R3. The PR states plainly that acceptance criterion 2 (governed transports cannot be bypassed) is not closed by this change. The Bash / `MCTL_TOKEN` path stays `bypass-open` and is tracked by the companion issues.
- [ ] R4. The mctl-api companion ("governed operations require a redeemed approval receipt") borders on mctlhq/mctl-api#721. Do not open a competing issue: if it falls inside #721's scope, add it to #721 as a comment. Otherwise file it with an explicit link to #721 and a stated boundary.
- [ ] R5. The shepherd manifest entry notes that the shepherd pod forces `NO_APPROVALS` by design (`run_shepherd.py`). Task 5(b) waits for the T5 evidence on the investigator only; that evidence is not presented as covering the other surfaces.
