# Agent pod isolation in argo-workflows (mctl-gitops#2289, #807 G3)

mctl-agents step pods run in the `argo-workflows` namespace beside platform
workflow pods. The #807 decision (`HARDEN_IN_PLACE`) keeps that shared
namespace, so the boundary is carried by pod selectors. Egress side:
`docs/runbooks/mctl-agents-egress.md` (#2159). This runbook is the ingress side.

## Status

| Step | Issue | State |
|---|---|---|
| A. Label contract, validators, probe, this runbook | #2289 | this change. No NetworkPolicy changes. |
| B. Narrow the six ingress policies | #2301 | not started. Gated by T6 below and by the NotIn pre-check. |

## The label contract

- Canonical agent-pod label: `app.kubernetes.io/name: mctl-agents`, set in
  `spec.podMetadata.labels` of an agent ClusterWorkflowTemplate (or
  WorkflowTemplate).
- It is a security selector, not only a Loki/Promtail label. Do not relabel or
  repurpose it. `allow-agent-ingress` of the egress proxy and the planned
  stage C egress policy already select on it.
- A template is an agent template if it is named `mctl-agents-*` (file
  `cwft-mctl-agents-*`), is `lifecycle-bootstrap`, or runs the mctl-agents image
  (`workflow.parameters.agent_image` or `ghcr.io/mctlhq/mctl-agents`).
  `zitadel-login-consolidation` uses the image only as a Python runtime for a
  Vault job and is exempt on purpose: it must NOT carry the label.
- `scripts/validate-agent-pod-labels.py` (CI) fails when an agent template lacks
  the label, when a CronWorkflow/Workflow referencing one overrides it, or when a
  non-agent template carries it.
- Adding an agent CWFT: set the label; CI tells you if you forgot.

## Selector shapes (used by #2301)

- Agent pod: `app.kubernetes.io/name In [mctl-agents]`.
- Non-agent workflow pod: `workflows.argoproj.io/workflow Exists` AND
  `app.kubernetes.io/name NotIn [mctl-agents]`.

`NotIn` also matches pods without the key, so platform templates need no edits.
That shape is fail-open for an agent template that loses its label: CI is what
closes the gap, which is why the label validator exists before any policy moves.

## In-cluster destination allowlist for agent pods

| Destination | Port | Why |
|---|---|---|
| `mctl-api` (ns `mctl-api`) | TCP 8080 | global completion exit hook |
| `otel-collector` (ns `monitoring`) | TCP 4317/4318 | OTLP export |
| `agent-egress-proxy` (ns `mctl-agents-egress`) | TCP 3128 | all external egress |

Agent pods have no need of Vault, Backstage, shared-pg or other pods in
`argo-workflows` (#2159 traffic inventory). To add a path, justify it from the
inventory, then add it for the agent selector only, in its own PR.

## CI checks

- `scripts/validate-agent-ingress-isolation.py` evaluates the UNION of all
  NetworkPolicies (raw manifests plus the rendered bootstrap chart) for
  synthetic agent, agent-hook, platform-workflow, controller and server pods
  against an allow/deny matrix. Step A enforces the `today` matrix (the current
  state, including that agents still reach Vault, Backstage and shared-pg).
  #2301 switches the default to `target` and empties `NAMESPACE_ONLY_BASELINE`.
  `--matrix target` shows the remaining distance.
- It also rejects a peer that admits `argo-workflows` by namespace alone.
- Both validators run `--selftest` first (missing label, namespace-only peer,
  removed NotIn exclusion, `podSelector: {}` intra-namespace, and a second
  policy that re-admits the namespace).

## Live checks (operator, cluster-admin)

None of these could be run from the repository. Record results on #2301.

1. `kubectl get netpol -A` for vault, backstage, mctl-api, platform-db,
   monitoring, argo-workflows: confirm nothing beyond the repository policies.
2. Labels of the workflow-controller and server pods (the matrix assumes
   `app.kubernetes.io/component: workflow-controller` / `server`).
3. A live agent completion-hook pod carries `app.kubernetes.io/name: mctl-agents`
   and reaches mctl-api :8080 (T5).
4. Scratch policy in a scratch namespace using `NotIn` on a peer podSelector:
   confirm kube-router enforces it. If not, stop and use the positive
   `mctl.ai/workload-class: platform` alternative.
5. Baseline: `scripts/probe-agent-ingress.sh`, compare with the `today` matrix.
6. T6, HARD GATE for #2301: submit a Workflow with a `workflowTemplateRef` to an
   agent CWFT and a `podMetadata` override of `app.kubernetes.io/name`. Either the
   label is kept or the submission is refused under `templateReferencing: Strict`.
   Result: NOT YET RUN. If the override succeeds, write
   `STEP_B_BLOCKED: label override possible` here and on #2301; #2301 must not
   start until admission control (mctlhq/mctl-agents#800 or equivalent) prevents
   it or the design switches to the positive platform label.

## Rollback

Step A changes no NetworkPolicy. Reverting it removes the validators, probe
script and this runbook only. If a validator blocks an urgent fix, revert its CI
wiring in `.github/workflows/validate-manifests.yml`, not a policy.
