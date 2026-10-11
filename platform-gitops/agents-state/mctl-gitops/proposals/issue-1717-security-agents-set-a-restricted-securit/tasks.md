# Tasks: issue-1717-security-agents-set-a-restricted-securit

- [ ] 1. Add `scripts/validate-agent-pod-security.py` (PyYAML, executable,
  `--selftest` and `--dir` flags) that globs `cwft-mctl-agents-*.yaml`,
  finds every template whose `container`/`script` image contains
  `workflow.parameters.agent_image`, and checks the pod-level
  (`runAsNonRoot: true`, `runAsUser: 1000`, `fsGroup: 1000`,
  `seccompProfile.type: RuntimeDefault`), container-level
  (`allowPrivilegeEscalation: false`, `capabilities.drop` contains `ALL`,
  `runAsNonRoot` not false) and initContainer (`allowPrivilegeEscalation:
  false`, `drop: [ALL]`) rules; fails on zero matches. — DoD: `--selftest`
  passes; running it against the unchanged repo fails, naming all six
  templates.
- [ ] 2. Wire the validator into `.github/workflows/validate-manifests.yml`
  next to "Validate Argo local workdir invariants" (`--selftest`, then the
  real run). (depends on 1) — DoD: step present, `set -euo pipefail`, same
  pattern as `validate-implement-worker-singleton.py`.
- [ ] 3. In `cwft-mctl-agents-usage-collector.yaml` `collect-usage`: add the
  template-level pod `securityContext` and the container-level
  `securityContext`, with a short comment citing mctl-gitops#1717. — DoD:
  validator passes for this file.
- [ ] 4. In `cwft-mctl-agents-reconcile.yaml` `run-reconcile`,
  `cwft-mctl-agents-run.yaml` `run-orchestrator`,
  `cwft-mctl-agents-investigate.yaml` `run-investigator`,
  `cwft-mctl-agents-shepherd.yaml` `run-shepherd` and
  `cwft-mctl-agents-implement.yaml` `run-implementer`: add the pod and agent
  container `securityContext`, and the explicit root-but-trimmed
  `securityContext` on the `clone-gitops` initContainer
  (`runAsUser: 0`, `runAsNonRoot: false`, `allowPrivilegeEscalation: false`,
  `drop: [ALL]`, `add: [CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID]`). Keep
  `chown -R 1000:1000 /workdir` unchanged. Do not touch `commit-and-push`,
  `assert-attempt`, `notify-telegram`, `post-deploy-verify`. (depends on 1) —
  DoD: validator, `scripts/validate-local-workdir.py`, yamllint and
  kubeconform in `validate-manifests.yml` all green.
- [ ] 5. Confirm `cwft-mctl-agents-daily.yaml` and
  `cronworkflow-mctl-agents-*.yaml` need no change (they only
  `workflowTemplateRef` the CWFTs) and say so in the PR description. — DoD:
  noted in PR.
- [ ] 6. After merge and ArgoCD sync (~3 min), run one real workflow of each:
  usage-collector (`dry_run=true` acceptable), reconcile (`mctl_trigger_reconcile
  dry_run=true`), run (`mctl_trigger_single_service`), shepherd
  (`mctl_trigger_shepherd dry_run=true` then one real tick), investigate
  (`mctl_trigger_issue`), implement (one DevLoop implementer run). (depends
  on 3, 4) — DoD: all Succeeded; `kubectl get pod -o
  jsonpath='{.spec.securityContext}{.spec.containers[*].securityContext}'`
  on each agent pod shows the settings; agent wrote under `/workdir`.
- [ ] 7. Optionally trim the `clone-gitops` capability add list to what the
  runs in task 6 proved necessary (at minimum `CHOWN`), re-running one
  template to confirm. (depends on 6) — DoD: either trimmed and re-verified,
  or left as-is with the reason in the PR.
- [ ] 8. File follow-up issues: (a) label `argo-workflows` with
  `pod-security.kubernetes.io/warn: restricted` and `audit: restricted`;
  (b) make `clone-gitops` fully non-root (drop redundant `apk add`,
  `HOME=/tmp`, rely on `fsGroup`, update `validate-local-workdir.py`). —
  DoD: issues linked from #1717.

## Tests

- [ ] T1. `scripts/validate-agent-pod-security.py --selftest`: hardened
  fixture passes; fixtures with the pod block removed, with
  `allowPrivilegeEscalation` removed, with `capabilities.drop` removed, and
  with an initContainer lacking `drop: [ALL]` each fail.
- [ ] T2. Red-then-green proof: run the validator against `main` before
  task 3/4 (fails on six templates), and against the branch after (passes).
  Record both outputs in the PR.
- [ ] T3. `scripts/validate-local-workdir.py` still passes (chown handoff
  string retained).
- [ ] T4. `helm`/kubeconform and yamllint steps in `validate-manifests.yml`
  and `yamllint.yml` pass on the edited CWFTs.
- [ ] T5. Live acceptance runs from task 6, including `jsonpath` inspection of
  each rendered agent pod.

## Rollback

Revert the PR (single `git revert` of the merge commit) and let ArgoCD sync;
new submissions use the old templates immediately after sync, and in-flight
runs are unaffected because Argo snapshots templates at submit time. If only
one template misbehaves (e.g. the `clone-gitops` init fails on `apk add`),
the narrower fix is to widen that initContainer's `capabilities.add` or revert
just that file; the validator must be relaxed in the same revert only if the
agent-container block itself is removed.
