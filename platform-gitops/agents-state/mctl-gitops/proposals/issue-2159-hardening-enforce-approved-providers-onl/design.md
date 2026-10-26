# Design: issue-2159-hardening-enforce-approved-providers-onl

## Current state

**Policy layer.**
- `platform-gitops/argo-workflows/config/networkpolicy.yaml` holds `allow-argo-workflows-ingress`:
  `podSelector: {}`, `policyTypes: [Ingress]`.
- No egress policy exists in `argo-workflows`, so every pod there, agent or platform, has
  unrestricted egress.
- `platform-gitops/bootstrap/templates/core-infra/argo-workflows.yaml` (around line 225) refers to
  that file as the namespace's NetworkPolicy.

**Agent pod selector.** These CWFTs set `spec.podMetadata.labels`:
`app.kubernetes.io/name: mctl-agents` and `mctl.ai/team: admins`.
- `cwft-mctl-agents-implement.yaml` (lines 39-50) also carries the comment that the label exists so a
  NetworkPolicy can pick out agent pods.
- `-investigate`, `-shepherd`, `-run`, `-scout`, `-reconcile`, `-usage-collector` and `-approve`.

The CronWorkflows and `cwft-mctl-agents-daily.yaml` start these through
`workflowTemplateRef` (`mctl-agents-run`, `-scout`, `-shepherd`, `-usage-collector`), so they
inherit the labels. The workflow-default exit hook `global-workflow-completion-hook`, configured in
`bootstrap/templates/core-infra/argo-workflows.yaml`, runs inside each workflow. Its pod therefore
also carries the agent labels.

**CNI.**
- `infrastructure/k3s-preview/kube.tf` (kube-hetzner) sets no `cni_plugin`, so the cluster runs the
  k3s default: flannel plus the embedded kube-router NetworkPolicy controller. That controller
  matches by IP only and has no FQDN rules.
- `infrastructure/k3s-prod/` contains only a README placeholder.
- `helm-charts/tenant/templates/networkpolicy.yaml` (`allow-cluster-egress`) records a measured
  quirk of this datapath: Service DNAT happens before egress filtering. A connection to
  `kubernetes.default` (10.43.0.1:443) is therefore matched against 10.255.0.0/24:6443.
- `helm-charts/tenant/values.yaml` lists the node subnets (10.0.0.0/24 workers, 10.255.0.0/24
  control plane) and `nodePublicCIDRs`.
- The Hetzner cloud firewall allows outbound DNS, NTP, ICMP, 80, 443 and 2465 only (`kube.tf`
  `extra_firewall_rules`).

**Traffic inventory.** Taken from the CWFT env and scripts; unknowns are marked.

| Destination | Port | Used by | Evidence |
|---|---|---|---|
| kube-dns (kube-system) | 53 udp/tcp | all | implicit |
| Kubernetes API (10.255.0.0/24) | 6443 | Argo `init`/`wait` executors in every pod | Argo emissary executor; tenant chart comment |
| Cloudflare R2 `6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com` | 443 | executor artifact and log archive, every pod | `artifactRepository.s3.endpoint` in `core-infra/argo-workflows.yaml`; `s3.key` artifacts in `notify-telegram` |
| `otel-collector.monitoring.svc.cluster.local` | 4318 | investigate, implement | `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `mctl-api.mctl-api.svc.cluster.local` | 8080 | completion exit hook | `cwft-global-workflow-completion-hook.yaml:98` |
| `api.mctl.ai` (public, via Cloudflare) | 443 | implement, investigate, run, usage-collector, shepherd | `MCTL_API_BASE_URL`; incident and resolve `curl` calls |
| `api.anthropic.com` | 443 | every model-running step | `CLAUDE_CODE_OAUTH_TOKEN` |
| other Anthropic hosts (telemetry, OAuth) | 443 | Claude Code CLI | **unknown** |
| `api.github.com` | 443 | all | 18 references in the CWFTs |
| `ssh.github.com` | 443 (SSH) | clone, commit and push steps | `cwft-mctl-agents-implement.yaml:363` (`Hostname ssh.github.com`, `Port 443`) |
| `github.com`, `codeload.github.com`, `objects.githubusercontent.com`, `raw.githubusercontent.com` | 443 | agent `git`/`gh` over https, tarballs | CWFT URLs; codeload and objects **inferred** |
| `ghcr.io` | 443 | not pod egress: images are pulled by kubelet on the node | `imagePullSecrets: ghcr-credentials` |
| `api.telegram.org` | 443 | notify steps in every CWFT | `curl ... api.telegram.org` |
| `dl-cdn.alpinelinux.org` | 443/80 | `apk add openssh-client curl jq` in alpine steps | e.g. `cwft-mctl-agents-implement.yaml:359,1204` |
| `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org`, `proxy.golang.org`, `sum.golang.org` | 443 | implementer test runs | issue requirement; actual use **unknown** (depends on the target repo) |
| scout feed hosts | 443 | scout | `agents/_scout/sources.yaml` in mctl-agents, **unknown here** |
| Temporal | n/a | none observed | only `temporal_*` correlation parameters |

`workflows.mctl.ai` appears only as a link string (`UI_URL`) and is never fetched.

**Profiles.** The implementer, issue-investigator and service-agent profiles grant `WebFetch`,
which reaches arbitrary hosts.

**Deployed state checked:**
- `mctl_list_recent_agent_runs`: refused ("admin group membership required"). No workflow logs were
  observed. The inventory comes from manifests only, and log-derived traffic is unknown.
- `$MCTL_GITOPS_ROOT` (`/workdir/mctl-gitops/platform-gitops`) has the same layout as the clone,
  including `agent-platform/execution-profiles/`. It contains no agent egress policy.
- Live NetworkPolicies and the live CNI were not observed: no cluster access in this run. The CNI
  finding rests on `kube.tf` defaults and the tenant chart's measured comments.

## Proposed solution

The cluster's CNI matches by IP only, while the approved providers are named by hostname. The
allowlist therefore lives in a forward proxy, and the NetworkPolicy only forces agent pods through
that proxy.

### 1. Egress proxy: `mctl-agents-egress` namespace

- Add a new ArgoCD-managed bundle at `platform-gitops/bootstrap/templates/mctl-platform/mctl-agents-egress-proxy.yaml`.
  It contains a Namespace, a ConfigMap, a Deployment with 2 replicas, a PodDisruptionBudget, a
  Service named `agent-egress-proxy` on port 3128, and NetworkPolicies.
- The proxy is Squid. Its config:
  - `acl allowed_hosts dstdomain` built from the inventory list, one hostname per line in the
    ConfigMap.
  - `http_access allow CONNECT allowed_hosts SSL_ports`; plain HTTP only to `dl-cdn.alpinelinux.org`.
  - Deny everything else.
  - `access_log` to stdout, so Promtail and Loki record every denied host.
- Proxy namespace policies:
  - Ingress: only from `argo-workflows` pods labelled `app.kubernetes.io/name: mctl-agents`.
  - Egress: DNS, plus 0.0.0.0/0 on 80 and 443, excluding 10.0.0.0/8 and `nodePublicCIDRs`.
- Resources: requests 50m CPU and 64Mi, limits 500m and 256Mi.

### 2. Agent egress policy: `argo-workflows/config/networkpolicy-agents-egress.yaml`

Synced by the same application as `networkpolicy.yaml`.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mctl-agents-egress
  namespace: argo-workflows
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: mctl-agents
  policyTypes: [Egress]
  egress:
    - to: [{namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: kube-system}}}]
      ports: [{port: 53, protocol: UDP}, {port: 53, protocol: TCP}]
    - to: [{ipBlock: {cidr: 10.255.0.0/24}}]   # kube API after DNAT; see tenant chart
      ports: [{port: 6443, protocol: TCP}]
    - to: [{namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: monitoring}},
            podSelector: {matchLabels: {<otel-collector labels>}}}]
      ports: [{port: 4318, protocol: TCP}]
    - to: [{namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: mctl-api}}}]
      ports: [{port: 8080, protocol: TCP}]
    - to: [{namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: mctl-agents-egress}}}]
      ports: [{port: 3128, protocol: TCP}]
```

- Platform pods match no egress policy, so they stay non-isolated for egress. This is standard
  NetworkPolicy semantics.
- The existing ingress policy is unchanged.

### 3. Point agent pods at the proxy

Edit each agent CWFT.

**Main containers.** Add to the agent-image steps and the alpine steps:
- `HTTPS_PROXY`, `HTTP_PROXY` and lowercase equivalents, set to
  `http://agent-egress-proxy.mctl-agents-egress.svc.cluster.local:3128`;
- `NO_PROXY=.svc,.svc.cluster.local,.cluster.local,10.43.0.0/16,kubernetes.default`;
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`.

`apk`, `curl`, `git`, `gh`, Python `urllib` and the Claude Code CLI all honour these variables.

**SSH over 443 to `ssh.github.com`.** The `~/.ssh/config` written in the clone and push steps
(e.g. `cwft-mctl-agents-implement.yaml:363`) gains `ProxyCommand socat - PROXY:<proxy>:%h:%p,proxyport=3128`.
`socat` is added to the existing `apk add --no-cache openssh-client ca-certificates` line, which
itself runs through the proxy. `ssh.github.com` is on the allowlist.

**Argo executors.** Add a workflow-level `podSpecPatch` that sets the same proxy and `NO_PROXY`
env on the `init` and `wait` containers. The executors then reach R2 through the proxy, with the
R2 hostname allowlisted, and reach the kube API directly (in `NO_PROXY`, allowed on 6443). If
Task 2 shows the patch does not reach the executor containers, the fallback is an ipBlock for
Cloudflare's published IPv4 ranges on 443, recorded as a residual risk.

### 4. Staged rollout

| Stage | Change | Gate |
|---|---|---|
| A. Observe | Deploy the proxy with an allow-all ACL that logs every host. Set the proxy env in the CWFTs. Apply no NetworkPolicy. | One run of each agent kind. Compare the logged hosts with the inventory and close the unknowns. |
| B. Allowlist | Switch Squid to the allowlist; still no NetworkPolicy. | Denials appear only for hosts that are expected to be refused. |
| C. Enforce | Apply `mctl-agents-egress`. | Two-way probe (Tests T1-T4), then one real run of each agent kind. |

Each stage is a separate PR, so stage C's revert is a single-file revert.

## Alternatives

1. **IP-range rules only, no proxy.** Allow 0.0.0.0/0 on 443 minus RFC1918 and the node public IPs,
   or GitHub `meta` ranges, Anthropic's published range and Cloudflare ranges.
   - Rejected as the end state. "All public 443" does not meet approved-providers-only.
   - Curated ranges drift: GitHub's change, and the npm and PyPI CDNs (Fastly, Cloudflare) are
     shared with arbitrary third parties.
   - Kept as the executor fallback only.
2. **Switch to Cilium (FQDN policies with a DNS proxy).**
   - Rejected for this issue: it replaces the CNI of a live single-control-plane cluster, a
     disruptive kube-hetzner change.
   - It is far larger than G1 and affects every tenant.
   - Worth revisiting once a CNI migration is planned for other reasons.
3. **Platform-wide proxy through `executor.env` in the workflow-controller config.**
   - Rejected: it would route platform workflows through the proxy as well, which the issue
     forbids.
4. **Sidecar proxy per agent pod.**
   - Rejected: the sidecar would sit in the same pod as the agent, so the agent could bypass it,
     and a NetworkPolicy cannot tell the containers apart.

## Platform impact

- **Migrations.** None: there is no data, and the change is manifests only.
- **Backward compatibility.** Platform workflow pods are unaffected. Agent pods depend on the proxy.
  Each `agent_image` must honour `HTTPS_PROXY`; Node, Python and git all do by default.
- **Resources.** About 100m CPU and 128Mi of requests across 2 proxy replicas.
- **Risks and mitigations.**
  - A missing host breaks a run. Mitigation: stages A and B observe before enforcing, and the proxy
    logs the denied host.
  - Proxy outage stops agent runs. Mitigation: 2 replicas and a PDB. Agent runs are retryable and
    non-latency-critical.
  - Datapath DNAT quirk. Mitigation: the kube API rule targets 10.255.0.0/24:6443, as the tenant
    chart does, and probe T3 checks it.
  - WebFetch to arbitrary hosts now fails. This is intended under the declared profile and is
    listed under Open questions.
  - Residual: allowlisted hosts such as `api.github.com` and `raw.githubusercontent.com` can still
    carry data out to an attacker-controlled repository. Narrowing that needs per-path or per-org
    controls and is out of scope.
- **Observability.** Squid's access log in Loki gives a per-host egress record for agent runs,
  which does not exist today.
