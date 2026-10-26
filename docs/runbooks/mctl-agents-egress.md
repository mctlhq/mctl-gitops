# mctl-agents egress proxy (issue #2159, gap G1 of mctl-agents#807)

Every mctl-agents ExecutionProfile declares `permissions.network:
approved-providers-only`. The cluster CNI (flannel + kube-router) matches
NetworkPolicy by IP only, so the hostname allowlist lives in a forward proxy
(`agent-egress-proxy`, Squid, namespace `mctl-agents-egress`) and a later
NetworkPolicy forces agent pods through it.

## Rollout status

| Stage | State | What it does |
|---|---|---|
| A. Observe | this change | Proxy forwards everything and logs every host. Agent CWFTs route through it. No NetworkPolicy. Agent reach is unchanged. |
| B. Allowlist | not started | Squid ACL switches to the `dstdomain` list below. |
| C. Enforce | not started | `argo-workflows/config/networkpolicy-agents-egress.yaml` (default-deny egress for pods labelled `app.kubernetes.io/name: mctl-agents`). |

Stages B and C are separate PRs and need the stage A log reviewed first.

## What stage A changes

- `bootstrap/templates/mctl-platform/mctl-agents-egress-proxy.yaml`: namespace,
  Squid ConfigMap (allow-all), 2-replica Deployment, PDB, Service
  `agent-egress-proxy:3128`, proxy-namespace NetworkPolicies.
- Every container in the eight agent CWFTs (implement, investigate, shepherd,
  run, scout, reconcile, usage-collector, approve) gets `HTTP(S)_PROXY`,
  `NO_PROXY` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`.
- `socat` is added to the `apk add` lines and the `ssh.github.com` ssh config
  gets a `ProxyCommand` through the proxy (`%%h`/`%%p` because the config is
  written with `printf`).
- NOT changed: the Argo `init`/`wait` executors. The design proposes a
  workflow-level `podSpecPatch`; whether it reaches the executor containers
  was not verified (task 2 needs a live probe). The executors keep direct
  egress to Cloudflare R2 and the kube API. Stage C cannot be enforced until
  task 2 is done, or the Cloudflare ipBlock fallback is chosen.

## Traffic inventory (candidate allowlist)

Derived from manifests and `mctl-agents/agents/_scout/sources.yaml`; no workflow
logs were observable. Rows marked unknown are to be closed from the stage A log.

| Host | Port | Used by | Evidence |
|---|---|---|---|
| `6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com` | 443 | executors, all CWFTs (direct in stage A) | `artifactRepository` in `core-infra/argo-workflows.yaml` |
| `api.mctl.ai` | 443 | implement, investigate, run, usage-collector, shepherd | `MCTL_API_BASE_URL`, curl calls |
| `api.anthropic.com` | 443 | implement, investigate, shepherd, run, scout, reconcile | `CLAUDE_CODE_OAUTH_TOKEN` |
| other Anthropic hosts (telemetry, OAuth) | 443 | Claude Code CLI | unknown; telemetry disabled by env |
| `api.github.com` | 443 | all | many references |
| `ssh.github.com` | 443 | clone/push steps (ssh) | ssh config in each CWFT |
| `github.com`, `codeload.github.com`, `objects.githubusercontent.com`, `raw.githubusercontent.com` | 443 | git/gh over https | codeload/objects inferred |
| `api.telegram.org` | 443 | notify steps | curl in each CWFT |
| `dl-cdn.alpinelinux.org` | 80/443 | `apk add` in alpine steps | CWFT scripts |
| `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org`, `proxy.golang.org`, `sum.golang.org` | 443 | implementer test runs | unknown, depends on target repo |
| `feed.infoq.com`, `thenewstack.io`, `blog.cloudflare.com`, `github.blog` | 443 | scout | `_scout/sources.yaml` (enabled sources) |
| `www.anthropic.com`, `claude.com` | 443 | none (sources disabled) | `_scout/sources.yaml`, `enabled: false` |
| in-cluster: kube-dns 53, kube API 10.255.0.0/24:6443, `otel-collector.monitoring` 4318, `mctl-api.mctl-api` 8080 | | all / investigate+implement / completion hook | direct, in `NO_PROXY`, not proxied |

Per CWFT: all eight use github, telegram, anthropic (where a model runs) and
alpine; the completion exit hook runs in each workflow and only talks to
mctl-api in-cluster. WebFetch in the implementer, investigator and service
agent profiles reaches arbitrary hosts and will be refused at stage B; accept
and record the denied hosts, or drop WebFetch (reviewer decision).

## Reading the log

Squid writes its access log to stdout, shipped to Loki:

    {namespace="mctl-agents-egress", app_kubernetes_io_name="agent-egress-proxy"}

CONNECT lines show the target `host:port`; denials (stage B onward) show
`TCP_DENIED/403`.

## Adding a host (stage B onward)

PR against the `agent-egress-proxy` ConfigMap `dstdomain` list; ArgoCD syncs it,
then restart the Deployment (`kubectl -n mctl-agents-egress rollout restart
deploy/agent-egress-proxy`) since Squid reads config at start.

## Rollback

- Stage A: revert the CWFT commit (removes the proxy env, `socat` and
  `ProxyCommand`), wait about 3 minutes for ArgoCD (Argo snapshots templates at
  submit time), then remove the proxy bundle. If the proxy itself is down and
  runs fail, the CWFT revert alone restores today's behaviour.
- Stage B: revert the ACL commit. Stage C: revert the single NetworkPolicy file.
