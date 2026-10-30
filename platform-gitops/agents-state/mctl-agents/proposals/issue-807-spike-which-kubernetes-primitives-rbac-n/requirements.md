# Spike #807: Kubernetes isolation primitives for non-deterministic agents, and a gap analysis of mctl's current setup

## Context

Issue mctl-agents#807 is a scout-generated spike. It asks which Kubernetes primitives (RBAC, NetworkPolicy,
sandbox runtimes, quotas, and related pod-security controls) are needed to run non-deterministic AI agents
safely, and where mctl's current setup falls short. The expected outcome is a gap analysis of agent isolation
on Kubernetes. Related issues: #747, #760, #670.

It matters because the mctl-agents step pods (`cwft-mctl-agents-implement`, `-investigate`, `-shepherd`,
`-run`, `-scout`, `-reconcile`, `-usage-collector` in mctl-gitops) run a model-driven session with a `Bash`
tool on input the platform does not control (issue text, PR diffs, review comments). A first read of the
deployed manifests shows that the RBAC layer is already least-privilege, but the profile-level declaration
`permissions.network: approved-providers-only` (for example
`agent-platform/execution-profiles/implementer-default/profile.yaml`) is not backed by any egress
NetworkPolicy. The pods also share the `argo-workflows` namespace with platform workflows. The spike has to
turn findings like these into a reproducible, evidence-backed matrix and a ranked list of follow-ups. It does
not change the platform.

## User stories

- AS a platform owner I WANT a primitive-by-primitive matrix of what agent pods are and are not isolated by
  SO THAT I can prioritise hardening work by evidence, not intuition.
- AS a security reviewer I WANT each finding to cite the exact gitops file and field it was derived from
  SO THAT I can verify it and re-run the analysis after a change.
- AS an mctl-gitops maintainer I WANT concrete, scoped follow-up issues (egress policy, namespace pod
  security, quotas, sandbox runtime) SO THAT each can be implemented and rolled back on its own.
- AS the owner of #807 I WANT the report to propose exactly one decision token SO THAT the spike closes with
  a recorded verdict.

## Acceptance criteria (EARS)

- WHEN the spike PR is merged THE SYSTEM SHALL contain `docs/spikes/807-agent-isolation-k8s.md` with a gap
  matrix covering at least these primitives: RBAC / ServiceAccount token exposure, NetworkPolicy egress,
  NetworkPolicy east-west (intra-namespace) and cross-namespace reachability, Pod Security (namespace PSA
  label plus per-container securityContext, including `readOnlyRootFilesystem`), sandbox runtime
  (RuntimeClass such as gVisor or Kata), ResourceQuota / LimitRange / per-pod limits / deadlines /
  concurrency, and credential exposure to the agent process.
- WHEN a matrix row is written THE SYSTEM SHALL record its status as one of `enforced`, `partial`, `absent`
  or `not-observed`, the source file and field it came from, a severity (`high`, `medium`, `low`), and the
  recommended primitive.
- IF a fact could not be read from the gitops checkout or the live cluster (for example the CNI in use or the
  live namespace labels) THEN THE SYSTEM SHALL mark that row `not-observed` and SHALL NOT report it as
  `absent`.
- WHEN `tools/agent_isolation_audit.py --gitops-root <platform-gitops>` runs THE SYSTEM SHALL read only the
  mctl-agents ClusterWorkflowTemplates, `argo-workflows/config/sa-and-rbac.yaml`,
  `argo-workflows/config/networkpolicy.yaml`, `argo-workflows/config/local-workdir-quota.yaml`, the
  NetworkPolicies that admit the `argo-workflows` namespace, and `agent-platform/execution-profiles/*/profile.yaml`,
  and SHALL emit the machine-derivable rows of the matrix as JSON (and as Markdown with `--format md`).
- WHILE the audit tool runs THE SYSTEM SHALL perform no network calls, no Kubernetes API calls and no writes
  outside stdout.
- IF an ExecutionProfile declares `permissions.network: approved-providers-only` and no NetworkPolicy with
  `policyTypes` containing `Egress` selects the agent pods (`app.kubernetes.io/name: mctl-agents` in
  `argo-workflows`) THEN THE SYSTEM SHALL report a `declared-not-enforced` finding for that profile.
- IF an agent step template that runs the agent image lacks any of `runAsNonRoot: true`,
  `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`,
  `automountServiceAccountToken: false` or `serviceAccountName: mctl-agents-runner` THEN THE SYSTEM SHALL
  report that template and the missing field.
- WHEN the report is finalised THE SYSTEM SHALL carry either the marker `STATUS: DRAFT` or exactly one
  decision token from `NO_CHANGE`, `HARDEN_IN_PLACE`, `DEDICATED_AGENT_NAMESPACE` and
  `SANDBOX_RUNTIME_REQUIRED`, enforced by `tests/test_spike_807_report.py`.
- WHEN the report lists follow-ups THE SYSTEM SHALL give each one a target repository, the exact file(s) to
  change, an expected-traffic list (for egress allowlists), and a rollback note.
- WHILE this spike is open THE SYSTEM SHALL NOT change any file under `orchestrator/`, `config/` or
  `agents/_manifests/`, enforced by the same guard test.

## Out of scope

- Applying any change to mctl-gitops (NetworkPolicies, namespace labels, RuntimeClass, quotas). Those are
  follow-up issues the report files or drafts.
- Live probes against the production cluster (for example running an egress test pod). The report may
  describe a probe procedure for the follow-up; it does not run one.
- Choosing or installing a sandbox runtime (gVisor, Kata) on the nodes.
- Application-layer controls that already have their own ADRs and issues: USD budgets (ADR 011,
  `orchestrator/exec_budget.py`), MCP policy checkpoint (ADR 014, `orchestrator/policy_checkpoint.py`),
  capability gateway (ADR 017). The report references them only to show the defence-in-depth layering.
- Tenant workloads in `helm-charts/tenant`; only mctl-agents agent execution and the Temporal workers in the
  `admins` tenant are in scope.

## Open questions

- Which CNI does the cluster run, and does it support FQDN-based egress (Cilium `CiliumNetworkPolicy`
  `toFQDNs`)? No CNI configuration was found in the gitops checkout. Vanilla NetworkPolicy is IP-based, so
  an "approved providers only" allowlist for api.anthropic.com, github.com and package registries may need
  an egress proxy instead. The report proceeds by presenting both options.
- What labels does the live `argo-workflows` namespace carry? It is created by Argo CD `CreateNamespace=true`
  (`bootstrap/templates/core-infra/argo-workflows.yaml`) with no `managedNamespaceMetadata`, and no
  `pod-security.kubernetes.io/*` label was found for it in gitops. The live labels were not observed.
- Do the Temporal workers (`services/admins/mctl-agents-worker*`) ever run a model-driven shell in-process,
  or do they only submit Argo workflows? The spike assumes they only orchestrate and records it as an
  assumption to verify.
- What egress does an implementer legitimately need (npm, PyPI, Go module proxy, GitHub, Anthropic,
  mctl-api, the OTel collector)? The spike derives a first list from the Dockerfile and the CWFT env, but it
  needs owner confirmation before any deny-by-default policy is applied.
- The issue lists #747, #760 and #670 as related, but their scope could not be read offline. Only #760 is
  referenced in the clone (`docs/spikes/757-duet-sessions.md`, as per-conversation sessions). The reviewer
  should confirm there is no overlap.
