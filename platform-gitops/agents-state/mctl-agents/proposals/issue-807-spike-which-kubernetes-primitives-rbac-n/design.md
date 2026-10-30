# Design: issue-807-spike-which-kubernetes-primitives-rbac-n

## Current state

mctl-agents ships a single image (`Dockerfile`: `python:3.12-slim`, Node 22, Go 1.26.7, `gh`, `gcc`, runs as
`app` uid 1000) whose entrypoint runs one agent per Argo step. What isolation that step gets is defined in
mctl-gitops, not in this repo. Inside this repo, isolation is expressed only as declarations and app-layer
checks:

- `orchestrator/resolver.py` (around line 746) refuses an ExecutionProfile unless
  `spec.runtime.sandbox.backend == "argo"`, a `clusterWorkflowTemplate` is named, and `approved: true`. It
  validates *which* CWFT runs the agent, not what that CWFT enforces. `orchestrator/manifest.py` carries
  `sandbox_backend` and `cluster_workflow_template` the same way.
- `orchestrator/exec_budget.py` (ADR 011) enforces USD budgets. `orchestrator/policy_checkpoint.py`
  (ADR 014) and `orchestrator/mcp_guard.py` gate MCP calls. `orchestrator/redaction.py` scrubs output. These
  are in-process controls. A model-driven `Bash` tool runs in the same container and is not mediated by them.
- `docs/adr/007-agent-definition-execution-profile-contract.md` defines the `permissions` block
  (`kubernetes`, `network`, ...) that profiles declare.
- Existing spikes (`docs/spikes/796-rea-investigation-evidence.md` with `tests/test_spike_796_report.py`,
  `docs/spikes/707-pyrefly-type-check.md` with `tests/test_spike_707_report.py`) set the convention this
  spike follows: a report under `docs/spikes/`, one decision token, and a guard test that keeps runtime code
  unchanged.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/argo-workflows/config/sa-and-rbac.yaml`: `mctl-agents-runner` has no Role or
  RoleBinding and `automountServiceAccountToken: false`. `mctl-agents-executor` has a Role limited to
  `workflowtaskresults` create/patch. `argo-workflow-sa` (the workflow-level account) has `secrets: get` and
  `workflows` read/write in `argo-workflows`. **RBAC: enforced for the agent step.**
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`: the spec-level
  `serviceAccountName` is `argo-workflow-sa` (line 36). The `run-implementer` template overrides it with
  `mctl-agents-runner`, `automountServiceAccountToken: false` and `executor.serviceAccountName:
  mctl-agents-executor` (lines 306-309). The pod securityContext sets `runAsNonRoot`, uid/gid 1000 and
  `seccompProfile: RuntimeDefault` (312-318). The container sets `allowPrivilegeEscalation: false` and
  `capabilities.drop: [ALL]` (440-444). No `readOnlyRootFilesystem` is set (0 matches in any
  `cwft-mctl-agents-*.yaml`). Resources: requests `cpu 200m / memory 3Gi / ephemeral 10Gi`, limits
  `cpu 3000m / memory 8Gi / ephemeral 11Gi` (829-830). `activeDeadlineSeconds: 7200` on the step and 28800 at
  spec level. `synchronization.mutex: mctl-agents-proposal-claims`. Credentials are injected as env from
  `secretKeyRef`: `CLAUDE_CODE_OAUTH_TOKEN`, `GITHUB_TOKEN`, `MCTL_TOKEN`, `MCTL_USAGE_WRITER_TOKEN`,
  `MCTL_EVIDENCE_WRITER_TOKEN` (683-745). They are therefore readable by the agent's own shell. Pod labels
  are `app.kubernetes.io/name: mctl-agents`, `mctl.ai/team: admins`. The comment at lines 39-46 says these
  labels exist so that a NetworkPolicy can select agent pods apart from platform workflows "that ... do need
  in-cluster egress". No such policy was found.
- A grep across the other agent CWFTs (`-investigate`, `-reconcile`, `-run`, `-scout`, `-shepherd`,
  `-usage-collector`) found `mctl-agents-runner`, `seccompProfile` and `drop: ["ALL"]` in each.
  `cwft-mctl-agents-approve.yaml` uses only `argo-workflow-sa` with `alpine/git` and no model, so it is out of
  scope as an agent step. `cwft-mctl-agents-investigate.yaml` deliberately carries no `MCTL_TOKEN`
  (line 797, mctl-agents#717).
- `$MCTL_GITOPS_ROOT/argo-workflows/config/networkpolicy.yaml`: one policy, `allow-argo-workflows-ingress`,
  with `podSelector: {}` and `policyTypes: [Ingress]`. It allows ingress from every pod in the namespace,
  plus traefik, kube-system, monitoring, mctl-api and admins. **No Egress policy selects agent pods.** A
  grep for `egress` under `argo-workflows/` found only comments.
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/implementer-default/profile.yaml`: `tools` includes
  `Bash`, `WebSearch`, `WebFetch`, `mcp__mctl__*`. `permissions.kubernetes: none` is enforced by RBAC above.
  `permissions.network: approved-providers-only` is **declared but not enforced** at the pod layer.
  `runtime.sandbox: {backend: argo, clusterWorkflowTemplate: mctl-agents-implement, approved: true}`.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/core-infra/vault-netpol.yaml`: admits ingress from the whole
  `argo-workflows` namespace (for provision-database, create-tenant and deploy-service). The selector is
  namespace-wide, so agent pods can reach Vault at the network layer. They hold no Kubernetes token to log in
  with, so this is a defence-in-depth gap, not a direct path.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api-netpol.yaml`: admits `argo-workflows`
  (line 35). Agents legitimately need this.
- `$MCTL_GITOPS_ROOT/argo-workflows/config/local-workdir-quota.yaml`: the only ResourceQuota in
  `argo-workflows`, and it covers only `argo-workdir-local` storage-class requests (48Gi). No compute,
  pod-count or LimitRange quota was found for the namespace.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/core-infra/argo-workflows.yaml`: the namespace is created with
  `CreateNamespace=true`, with no `managedNamespaceMetadata`. No `pod-security.kubernetes.io/*` label for
  `argo-workflows` was found anywhere in gitops. PSA labels exist only in `helm-charts/tenant`. The live
  labels were **not observed**.
- A grep for `RuntimeClass|gvisor|kata` across `platform-gitops` found 0 matches. **No sandbox runtime.**
- `$MCTL_GITOPS_ROOT/tenants/admins/values.yaml`: `podSecurityLevel: "restricted"`,
  `allowClusterEgress: true`, `allowInternetEgress: true`. This applies to the Temporal workers
  (`services/admins/mctl-agents-worker{,-exec,-implement}`). For example `-implement/values.yaml` has
  `automountServiceAccountToken: false`, `replicaCount: 1` and small limits (250m / 128Mi).
- mctl MCP tools: not used in this run. All findings come from the gitops checkout. Live cluster state
  (namespace labels, CNI, actual pod specs) was not observed and is listed under Open questions.

## Proposed solution

This is a spike, so it delivers evidence and a decision proposal. It does not deliver a platform change.
There are three artefacts, all in mctl-agents.

### 1. `tools/agent_isolation_audit.py`: a reproducible, read-only static auditor

- CLI: `python -m tools.agent_isolation_audit --gitops-root <path-to-platform-gitops> [--format json|md]`.
- It loads YAML with `yaml.safe_load_all` (PyYAML is already a dependency, used in `orchestrator/resolver.py`)
  from a fixed file set: `argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`,
  `argo-workflows/config/{sa-and-rbac,networkpolicy,local-workdir-quota}.yaml`,
  `agent-platform/execution-profiles/*/profile.yaml`, and every `kind: NetworkPolicy` document whose ingress
  admits `kubernetes.io/metadata.name: argo-workflows`.
- It identifies agent steps as templates whose `container.image` is `{{workflow.parameters.agent_image}}`,
  and for each one checks:
  - identity: `serviceAccountName == mctl-agents-runner` and `automountServiceAccountToken is False`, and
    that the runner SA has no RoleBinding in `sa-and-rbac.yaml`;
  - pod security: `runAsNonRoot`, `seccompProfile.type == RuntimeDefault`, `allowPrivilegeEscalation is False`,
    `capabilities.drop` contains `ALL`, and `readOnlyRootFilesystem` (reported, expected `absent` today);
  - sandbox runtime: `runtimeClassName` (expected `absent`);
  - resources: cpu, memory and ephemeral-storage requests and limits, `activeDeadlineSeconds`, `synchronization`;
  - credentials: env var names sourced from `secretKeyRef`. Names only, never values;
  - egress: whether any NetworkPolicy in `argo-workflows` with `Egress` in `policyTypes` has a `podSelector`
    matching the template's `podMetadata.labels`;
  - east-west: whether the namespace ingress policy uses `podSelector: {}` (agent to platform pod
    reachable), and which other namespaces' policies admit the whole `argo-workflows` namespace.
- It cross-checks profiles: for each `permissions.network` value other than unrestricted, it emits
  `declared-not-enforced` when the egress check above fails.
- Output rows follow the matrix schema `{primitive, scope, status, severity, source, field, detail,
  recommendation}`, with `status` in `enforced|partial|absent|not-observed`. A missing input file yields
  `not-observed`, never `absent`.
- It is pure: no network, no subprocess, no Kubernetes client, and nothing written except stdout. It lives in
  `tools/` next to `tools/check_agent_bindings.py` and is not imported by `orchestrator/`.

### 2. `docs/spikes/807-agent-isolation-k8s.md`: the report

Sections follow the #796 layout: Environment and versions (gitops commit audited), Primitive catalogue (what
each primitive defends against for a non-deterministic agent with a shell), Current-state matrix (auditor
output plus hand-verified rows), Ranked gaps, Follow-ups, Decision.

Expected ranked gaps from the evidence above, to be confirmed by the auditor:

| # | Gap | Severity | Recommended primitive |
|---|---|---|---|
| G1 | No egress control on agent pods; `approved-providers-only` declared but not enforced. With credentials in env (G2) and untrusted prompt input, a prompt injection can exfiltrate tokens to any host. | high | Default-deny egress NetworkPolicy selecting `app.kubernetes.io/name: mctl-agents`. Allow DNS, mctl-api, otel-collector and Temporal if needed. Allow external providers through FQDN policy (Cilium) or an egress proxy, depending on the CNI. |
| G2 | Long-lived credentials (`CLAUDE_CODE_OAUTH_TOKEN`, `GITHUB_TOKEN`, `MCTL_TOKEN`, writer tokens) are env vars readable by the agent's `Bash`. | high (with G1), medium (without) | Short-lived scoped tokens (the existing `GITHUB_TOKEN_FILE` rotation pattern). Longer term, a credential-injecting egress proxy so the agent never holds the secret. |
| G3 | Shared namespace with platform workflows; ingress `podSelector: {}` and the Vault, mctl-api and backstage policies admit the whole namespace. | medium | Ingress policy that refuses agent-to-non-agent pod traffic, and Vault netpol narrowed to non-agent pods. Alternatively a dedicated `mctl-agents-runs` namespace. |
| G4 | No namespace-level PSA enforcement found for `argo-workflows`; posture is per-template only, so a new CWFT that forgets it is not rejected. `readOnlyRootFilesystem` is unset. | medium | `pod-security.kubernetes.io/enforce: restricted` on a dedicated agent namespace (platform helper steps run as root, so not on `argo-workflows` itself), plus a CI check in mctl-gitops. |
| G5 | No sandbox runtime. Model-driven shell shares the node kernel. | medium (risk accepted today, needs owner decision) | gVisor `RuntimeClass` on a labelled node pool. The spike documents a compatibility checklist (Go `-race`, Node, git) and does not install anything. |
| G6 | No compute ResourceQuota or LimitRange in `argo-workflows`; fan-out is bounded only by mutexes and Argo parallelism. | low | ResourceQuota (pods, limits.cpu, limits.memory) on the agent namespace, sized from the existing per-pod limits times the max concurrency. |
| -- | RBAC / SA token | enforced | None. Keep `mctl-agents-runner` binding-free, and add the auditor check to CI in a follow-up. |

The report proposes `HARDEN_IN_PLACE` (G1, G2, G3, G6 inside `argo-workflows` using the existing label
selector) as the default. It escalates to `DEDICATED_AGENT_NAMESPACE` if the CNI or PSA findings make
in-place hardening impractical. `SANDBOX_RUNTIME_REQUIRED` is recorded as a separate, later decision. The
final token is the #807 owner's call, so the report merges as `STATUS: DRAFT` unless the owner records one.

### 3. `tests/test_agent_isolation_audit.py` and `tests/test_spike_807_report.py`

- The auditor tests run on small fixture YAMLs under `tests/fixtures/agent_isolation/` that cover:
  enforced RBAC, missing egress, an egress policy that does select the label, `declared-not-enforced`, a
  missing file reported as `not-observed`, and a template missing `drop: [ALL]`.
- The report guard is modelled on `tests/test_spike_796_report.py`. It requires either a draft marker or
  exactly one token, requires that the spike changed no `orchestrator/`, `config/` or `agents/_manifests/`
  file, and requires that every matrix row in the report has a source path.

## Alternatives

1. **A report only, with no tooling.** This is the cheapest option, but the matrix would be a hand-made
   snapshot that goes stale the moment mctl-gitops changes, and reviewers could not re-derive it. It was
   dropped because the auditor is small and makes both the spike and future regressions checkable.
2. **Live probing (run a test pod in `argo-workflows` that attempts egress, Vault and API access).** This
   gives ground truth on the CNI and live labels, but it mutates the production cluster, needs write access
   this run does not have, and conflates the spike with the fix. It was dropped for the spike and written up
   as an optional, owner-run probe procedure inside the report's follow-ups.
3. **Implement the hardening directly in mctl-gitops (egress NetworkPolicy now).** Deny-by-default egress
   without a confirmed traffic inventory (npm, PyPI and the Go proxy during implementer test runs, GitHub,
   Anthropic, mctl-api, OTel) would break agent runs. It also belongs to mctl-gitops, not this repo. It was
   dropped in favour of scoped follow-up issues that carry a traffic list and a rollback note.

## Platform impact

- **Migrations / backward compatibility:** none. A new tool, a doc, tests and fixtures. No runtime code,
  manifest, profile or CWFT changes. The guard test enforces this.
- **Resource impact:** none at runtime. The auditor runs offline in seconds.
- **Risks and mitigations:**
  - *The report states a gap that is not real in the live cluster* (for example a PSA label applied
    out-of-band, or a cluster-wide CNI policy not in gitops). Mitigation: every such row is `not-observed`
    or explicitly scoped to "in gitops", and the owner-run probe procedure is the confirmation step.
  - *The report is a map of weaknesses.* It describes only configuration already visible in the gitops repo
    and contains no exploit steps or secret values. The auditor reads env var names, never values. If the
    owner prefers, the ranked-gaps section can be held back until G1 is fixed. This is recorded as a
    reviewer choice.
  - *The auditor's agent-step heuristic (`agent_image` parameter) misses a template.* Mitigation: the
    auditor also lists every CWFT file it read and every template it classified as agent or non-agent, so an
    omission is visible.
