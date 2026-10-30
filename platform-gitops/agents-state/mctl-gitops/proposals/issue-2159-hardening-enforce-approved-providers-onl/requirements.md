# Enforce approved-providers-only egress for mctl-agents step pods

## Context

Every mctl-agents ExecutionProfile under `platform-gitops/agent-platform/execution-profiles/*/profile.yaml`
declares `permissions.network: approved-providers-only`. Nothing in the cluster enforces it.
The `argo-workflows` namespace has one NetworkPolicy, `allow-argo-workflows-ingress`
(`platform-gitops/argo-workflows/config/networkpolicy.yaml`), and it covers ingress only. An agent
step pod, which holds a Claude OAuth token, a GitHub App token and a Telegram bot token in its env,
can open a connection to any host on the internet and to any in-cluster address. Spike
mctlhq/mctl-agents#807 recorded this as gap G1.

The agent CWFTs already stamp `app.kubernetes.io/name: mctl-agents` on their pods through
`spec.podMetadata.labels`. They did this so a NetworkPolicy could select agent pods without also
selecting the platform workflows that share the namespace (deploy-service, create-tenant, ...).
The cluster's CNI enforces NetworkPolicy by IP only: k3s ships flannel with the embedded kube-router
policy controller, and `infrastructure/k3s-preview/kube.tf` does not override the CNI. This proposal
therefore adds default-deny egress for agent pods only. In-cluster destinations are reached
directly. Public destinations go through a host-allowlisting forward proxy. The rollout is staged,
and one revert undoes it.

## User stories

- AS a platform operator I WANT agent step pods to reach only the hosts their profiles approve SO
  THAT a prompt-injected or compromised agent cannot exfiltrate its tokens to an arbitrary host.
- AS a platform operator I WANT platform (non-agent) workflow pods in `argo-workflows` left alone SO
  THAT deploy-service, create-tenant and the other platform workflows keep their in-cluster egress.
- AS an agent maintainer I WANT a written traffic inventory per CWFT SO THAT the allowlist rests on
  evidence, and a missing host shows up as a visible proxy denial rather than a silent run failure.
- AS an on-call engineer I WANT one revert to restore today's egress SO THAT a broken allowlist
  never blocks the agent pipeline for longer than one ArgoCD sync.

## Acceptance criteria (EARS)

- WHEN the policy is applied THE SYSTEM SHALL select, in `argo-workflows`, only pods labelled
  `app.kubernetes.io/name: mctl-agents`, with `policyTypes: [Egress]`.
- WHILE a pod in `argo-workflows` does not carry `app.kubernetes.io/name: mctl-agents` THE SYSTEM
  SHALL leave its egress exactly as it is today.
- WHILE an agent step pod runs THE SYSTEM SHALL allow egress only to:
  - kube-dns on port 53 (UDP and TCP);
  - the Kubernetes API, on the control-plane subnet port 6443, for the Argo init and wait executors;
  - the OTel collector in `monitoring` on port 4318;
  - mctl-api in `mctl-api` on port 8080, used by `cwft-global-workflow-completion-hook`;
  - the agent egress proxy on its listen port.
- WHEN an agent pod sends an HTTPS or CONNECT request through the proxy to a host on the inventory
  allowlist THE SYSTEM SHALL forward it.
- IF an agent pod requests a host that is not on the allowlist THEN THE SYSTEM SHALL refuse the
  request at the proxy (HTTP 403) and log the denied host.
- IF an agent pod opens a direct connection to any public IP, or to any in-cluster address outside
  the list above THEN THE SYSTEM SHALL drop it at the NetworkPolicy layer.
- WHEN the change is staged THE SYSTEM SHALL pass a two-way probe from a pod that carries the agent
  labels: an allowlisted host succeeds through the proxy, and both a non-allowlisted host and a
  direct connection fail.
- WHEN the policy is enforced THE SYSTEM SHALL complete one real run of each agent kind:
  `implement`, `investigate`, `shepherd`, `run`, `scout`, `reconcile`, `usage-collector` and
  `approve`.
- WHEN the change is reverted in one commit THE SYSTEM SHALL restore today's egress behaviour
  after the next ArgoCD sync.

## Out of scope

- Short-lived credentials instead of env tokens (G2).
- Narrowing east-west traffic for non-agent pods (G3).
- Namespace Pod Security Admission (G4).
- A sandbox runtime (G5).
- Quotas (G6).
- Adding an FQDN-capable CNI such as Cilium. Its cost is weighed under Alternatives.
- Changes to mctl-agents application code beyond honouring the standard `HTTPS_PROXY` and
  `NO_PROXY` variables.

## Open questions

- **Scout feed hosts.** They live in `agents/_scout/sources.yaml` in mctl-agents, which is not in
  this repo, so they are unknown here. Task 1 reads them before the allowlist is finalised.
- **WebFetch.** The implementer, issue-investigator and service-agent profiles grant `WebFetch`.
  Claude Code's WebFetch fetches client-side, so it reaches arbitrary hosts. Under this policy,
  WebFetch to a non-allowlisted host fails with a tool error. That is consistent with
  `approved-providers-only`. Proposed default: accept the failures and record the denied hosts.
  The alternative is to drop `WebFetch` from the profiles; that is a reviewer decision.
- **Claude Code side traffic.** Calls beyond `api.anthropic.com`, such as telemetry, OAuth refresh
  or update checks, cannot be determined from this repo. Proposed default: set
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` and let the observe-only stage reveal anything left.
- **Executor proxying.** The Argo `init` and `wait` executors upload and download artifacts to
  Cloudflare R2. The proposal routes them through the proxy with a workflow-level `podSpecPatch`.
  If the cluster's Argo version does not merge that patch into the executor containers, the
  fallback is an ipBlock for Cloudflare's published ranges on 443. That fallback is weaker: it
  admits any Cloudflare-fronted host.
- **Temporal.** No CWFT env reaches Temporal directly; the `temporal_*` parameters only correlate
  IDs. Recent workflow logs could not be read (admin-only, refused), so "not used" is inferred
  from the manifests, not observed.
