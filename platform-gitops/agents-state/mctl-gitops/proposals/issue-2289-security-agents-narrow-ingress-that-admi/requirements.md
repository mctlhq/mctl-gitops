# Narrow ingress that admits agent pods from argo-workflows (807 G3)

## Context
mctl-agents step pods run in the `argo-workflows` namespace beside platform
workflow pods (deploy-service, create-tenant, provision-database,
remove-custom-domain, ...). The #807 decision (`HARDEN_IN_PLACE`) keeps that
shared namespace, so the isolation boundary must be carried by pod selectors.
Today six ingress policies admit `argo-workflows` with a selector that also
matches agent pods: either the whole namespace
(`allow-mctl-api-ingress`, `allow-shared-pg-ingress`,
`allow-otel-collector-ingress`, the intra-namespace `podSelector: {}` in
`allow-argo-workflows-ingress`) or every Argo workflow pod
(`allow-vault-ingress`, `allow-backstage-ingress`, via the Argo-owned label
`workflows.argoproj.io/workflow`).

The proposal defines one MCTL-owned agent-pod label contract, validates it in
CI, and rewrites each affected peer so that agent pods keep only the
in-cluster paths the mctl-gitops#2159 traffic inventory
(`docs/runbooks/mctl-agents-egress.md`) says they need, which are mctl-api
:8080 (the global completion exit hook) and the OTel collector :4318. They
lose Vault, Backstage, shared-pg and intra-namespace access to non-agent
pods. Platform workflows and the Argo controller/server keep every path they
use today. Kubernetes NetworkPolicy allows are additive, so each change is
proven against the full set of installed policies, in both directions.

## User stories
- AS a platform security owner I WANT agent pods refused at Vault, Backstage, shared-pg and non-agent pods in `argo-workflows` SO THAT a compromised or prompt-injected agent step cannot reach platform secrets, the forward-auth backend or the shared database over the network.
- AS a platform operator I WANT deploy-service and the other platform workflows to keep Vault, mctl-api, Backstage and shared-pg access SO THAT tightening agent isolation does not break the deploy path.
- AS an mctl-agents maintainer I WANT one documented, CI-validated label that marks a pod as an agent pod SO THAT adding a new agent CWFT cannot silently fall outside the isolation boundary.
- AS a reviewer I WANT CI to fail when a policy broadens an agent selector or reintroduces whole-namespace admission of `argo-workflows` SO THAT the boundary does not erode through later edits.

## Acceptance criteria (EARS)
- THE SYSTEM SHALL treat `app.kubernetes.io/name: mctl-agents`, set in `spec.podMetadata.labels` of an agent ClusterWorkflowTemplate, as the canonical agent-pod label, documented in `docs/runbooks/agent-pod-isolation.md`.
- WHEN a ClusterWorkflowTemplate under `platform-gitops/argo-workflows/cluster-templates/` runs the mctl-agents image (the `workflow.parameters.agent_image` marker, or an image under `ghcr.io/mctlhq/mctl-agents`), or is named `cwft-mctl-agents-*`, THE SYSTEM SHALL fail CI unless its `spec.podMetadata.labels` carries the canonical agent label.
- WHEN a CronWorkflow or WorkflowTemplate that references an agent CWFT sets `podMetadata.labels["app.kubernetes.io/name"]` to any other value, THE SYSTEM SHALL fail CI.
- WHILE the change is installed, THE SYSTEM SHALL admit pods with the canonical agent label in `argo-workflows` to `mctl-api` on TCP 8080 and to the OTel collector on TCP 4317/4318.
- WHILE the change is installed, THE SYSTEM SHALL refuse pods with the canonical agent label in `argo-workflows` at `vault` :8200, `backstage` :7007 and `platform-db` (shared-pg) :5432, even with all other NetworkPolicies in the repository installed.
- WHILE the change is installed, THE SYSTEM SHALL refuse traffic from pods with the canonical agent label to pods without it in `argo-workflows`, including the Argo server.
- WHILE the change is installed, THE SYSTEM SHALL admit non-agent workflow pods in `argo-workflows` to Vault :8200, Backstage :7007, mctl-api :8080 and shared-pg :5432, and admit the Argo workflow-controller and server pods to shared-pg :5432 (workflow archive).
- WHILE the change is installed, THE SYSTEM SHALL keep admitting traffic between non-agent pods inside `argo-workflows` (controller, server, platform workflow pods), and admitting Traefik, monitoring, kube-system, mctl-api and admins as today.
- WHEN a NetworkPolicy in the repository admits a peer `namespaceSelector` matching `argo-workflows` without a `podSelector`, or a peer whose `podSelector` would match a pod carrying the canonical agent label at a destination outside the agent allowlist (mctl-api, OTel collector, agent egress proxy), THE SYSTEM SHALL fail CI.
- WHEN the effective-policy check runs in CI, THE SYSTEM SHALL evaluate the union of every NetworkPolicy selecting each destination (raw manifests and the rendered bootstrap chart) for a synthetic agent pod, a synthetic platform workflow pod and the Argo controller/server, and SHALL fail on any deviation from the expected allow/deny matrix.
- WHEN the validators run with `--selftest`, THE SYSTEM SHALL demonstrate detection of at least these mutations: a missing agent label on an agent CWFT, a namespace-only `argo-workflows` peer, removal of the `NotIn mctl-agents` exclusion, and `podSelector: {}` restored as the intra-namespace source.
- IF a live probe from a pod carrying the canonical agent labels reaches a removed destination, or fails to reach an allowed one, THEN THE SYSTEM SHALL be considered not rolled out and the corresponding policy commit SHALL be reverted.
- WHEN all policy changes are synced, THE SYSTEM SHALL complete one `deploy-service` workflow and one run of each agent kind (implement, investigate, shepherd, run, scout, reconcile, usage-collector, approve, lifecycle-bootstrap) successfully before the change is declared complete.

## Out of scope
- `allow-agent-ingress` of the #2159 egress proxy (`infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml`). It admits agent pods only by design; the auditor finding is owned by mctlhq/mctl-agents#921 and mctl-gitops#2292.
- Agent egress enforcement (#2159 stage C, `networkpolicy-agents-egress.yaml`). This proposal is ingress-side only. The two complement each other.
- Adding ingress policies to namespaces that have none (mctl-gitops#1810).
- Non-`argo-workflows` peers in the same policies (kube-system, monitoring, traefik, admins, tenant namespaces). Their entries are left as they are.
- Agent code running outside `argo-workflows`, e.g. the `admins/mctl-agents-worker*` Temporal workers. They are tenant-namespace workloads, not Argo step pods.
- Admission control that would prevent forging the label (#800).

## Open questions
- Does kube-router (k3s) enforce `matchExpressions` with `NotIn` on peer pod selectors the way the API defines it? The design relies on it. Task 2 proves it with a live probe before any policy merges. If it does not, the fallback is a positive `mctl.ai/workload-class: platform` label on platform templates (see design Alternatives).
- Is `spec.podMetadata` of the referenced CWFT applied to the global completion exit-hook pod (`global-workflow-completion-hook`, set in `workflowDefaults.spec.hooks`)? The design assumes yes (workflow-level podMetadata covers all of a workflow's pods), so agent hook pods are agents and must keep mctl-api :8080. A live check is in the tests.
- Under `workflowRestrictions.templateReferencing: Strict`, can a submitter (mctl-api, CronWorkflows) override `podMetadata.labels` on a Workflow that references an agent CWFT? If so, an agent workflow could be submitted without the label and fall into the platform side of a `NotIn` selector. The CI check covers in-repo CronWorkflows; runtime submissions by mctl-api need a test.
- The exact pod labels of the Argo workflow-controller and server, needed for the shared-pg archive peer, come from the upstream chart (`app.kubernetes.io/component: workflow-controller` / `server` are expected) and must be confirmed live. This run could not read cluster objects.
- Do agent pods ever need agent-to-agent pod traffic in `argo-workflows`? Nothing found in the CWFTs suggests it, so the design admits none. If the #2159 stage A log shows a need, add a dedicated agent-to-agent policy.
- The #807 report (`docs/spikes/807-agent-isolation-k8s.md`) lives in mctlhq/mctl-agents and is not in this clone. The gap list here comes from the issue body and the files themselves.
