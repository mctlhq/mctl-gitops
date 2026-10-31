# Tasks: issue-2289-security-agents-narrow-ingress-that-admi

- [ ] 1. Add `docs/runbooks/agent-pod-isolation.md`: the canonical label `app.kubernetes.io/name: mctl-agents` (set in `spec.podMetadata.labels`), the in-cluster destination allowlist for agent pods (mctl-api :8080, otel-collector :4317/4318, agent-egress-proxy :3128), the two selector shapes, and how to add a path. Link it from `CLAUDE.md` and `docs/runbooks/mctl-agents-egress.md`. — DoD: runbook merged; it names #2289, #2159 and #807.
- [ ] 2. Live pre-check (operator, cluster-admin): `kubectl get netpol -A` for vault, backstage, mctl-api, platform-db, monitoring and argo-workflows; record the labels of the workflow-controller and server pods; confirm a live agent completion-hook pod carries `app.kubernetes.io/name: mctl-agents`; apply a scratch policy using `NotIn` in a scratch namespace and probe it to confirm kube-router honours it. — DoD: results recorded in this proposal's PR and on mctl-gitops#2301; open questions in requirements.md closed or escalated. If `NotIn` is not honoured, stop and switch to the positive-label alternative.
- [ ] 3. Add `scripts/validate-agent-pod-labels.py` with `--selftest`. Reuse agent-step detection from `scripts/validate-agent-pod-security.py` (move the shared helper to `scripts/lib/`). Wire it into `.github/workflows/validate-manifests.yml`. (depends on 1) — DoD: passes on main; selftest proves detection of a missing label, a CronWorkflow override and a non-agent template carrying the label.
- [ ] 4. Add `scripts/validate-agent-ingress-isolation.py` with `--selftest`. It evaluates the union of all repository NetworkPolicies (raw manifests plus the rendered bootstrap chart already produced for `validate-tenant-networkpolicy-allowlist.py`) for synthetic agent, agent-hook, platform-workflow, controller and server pods against the expected matrix, plus the "no namespace-only `argo-workflows` peer" lint. The matrix starts at today's state and is tightened by each policy PR. Add `scripts/probe-agent-ingress.sh` for the live two-pod probe. (depends on 3) — DoD: CI green on main; selftest catches the mutations listed in design section 4, including the "second policy re-admits" case.
- [ ] 5. Out of scope: the policy changes (former tasks 5-10) are
  mctl-gitops#2301. Post the results of task 2, T5 and T6 on #2301. — DoD:
  no NetworkPolicy file changes in this proposal's PR; the validator matrix
  equals today's state.

## Tests
- [ ] T1. `scripts/validate-agent-pod-labels.py --selftest` and the plain run, in CI.
- [ ] T2. `scripts/validate-agent-ingress-isolation.py --selftest` and the plain run, in CI. The matrix must show agent: allow mctl-api:8080, otel:4318, proxy:3128; deny vault:8200, backstage:7007, platform-db:5432, argo-server, platform workflow pod. Platform workflow pod: allow vault, backstage, mctl-api, platform-db, otel, argo-server. Controller and server: allow platform-db:5432.
- [ ] T3. Mutation test: a selftest fixture adds an extra policy that re-admits all of `argo-workflows` at vault. The check must fail, which proves the union is evaluated.
- [ ] T4. Live probe (`scripts/probe-agent-ingress.sh`) as a baseline of today's state, recorded on #2301. Probes after each policy change belong to #2301.
- [ ] T5. Live check that an agent workflow's exit-hook pod carries the canonical label and reaches mctl-api :8080.
- [ ] T6. Live check (or documented refusal) that a Workflow submitted with a `workflowTemplateRef` to an agent CWFT and a podMetadata override of `app.kubernetes.io/name` either keeps the canonical label or is refused under `templateReferencing: Strict`. Record the result in the runbook. HARD GATE for #2301: if the override succeeds, write `STEP_B_BLOCKED: label override possible` in the runbook and on #2301, and #2301 must not start until admission control (mctlhq/mctl-agents#800 or equivalent) prevents it or it switches to the positive platform label.
- [ ] T7. `helm lint platform-gitops/helm-charts/tenant` and the bootstrap chart render plus kubeconform (existing `validate-manifests.yml`) stay green.

## Rollback
This proposal changes no NetworkPolicy; reverting its PR removes only the
validators, probe script and runbook. For the policy steps see #2301.
The text below applies to #2301: each policy change is its own PR touching one file, so revert that PR. The
Applications that apply these files (root-app, shared-pg, otel-collector)
prune and re-sync the previous policy within about 3 minutes. Revert in
reverse order of the #2301 steps if several need undoing. Deploy-service depends on
Vault and mctl-api, so if a deploy-service run fails after task 5 or 8,
revert that PR first and investigate afterwards. The validators (tasks 3-4)
change nothing at runtime. If they block an urgent fix, revert their CI
wiring, not the policies. After any rollback, update the static check's
expected matrix in the same revert so CI stays green.
