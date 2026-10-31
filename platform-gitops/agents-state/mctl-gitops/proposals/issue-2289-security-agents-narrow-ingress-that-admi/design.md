# Design: issue-2289-security-agents-narrow-ingress-that-admi

## Current state

### Agent pods and their label
Every agent ClusterWorkflowTemplate sets a workflow-level pod label in
`spec.podMetadata.labels`:

```yaml
podMetadata:
  labels:
    app.kubernetes.io/name: mctl-agents
    mctl.ai/team: admins
```

This label is present in `cwft-mctl-agents-{approve,implement,investigate,reconcile,run,scout,shepherd,usage-collector}.yaml`
and `wft-lifecycle-bootstrap.yaml` (all in
`platform-gitops/argo-workflows/cluster-templates/`). The CronWorkflows
(`cwft-mctl-agents-daily.yaml`, `cronworkflow-mctl-agents-{incidents,scout,shepherd,usage-collector}.yaml`)
reach those templates via `workflowTemplateRef` and set no podMetadata of
their own. The comment in `cwft-mctl-agents-implement.yaml` (lines 36-46)
already gives the label two purposes: the Promtail/Loki `app` label, and "a
selector that picks out agent pods without catching platform workflows". The
#2159 egress proxy relies on it (`allow-agent-ingress` in
`infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml`),
and so does the planned stage C egress policy
(`docs/runbooks/mctl-agents-egress.md`). No CI check enforces it today.
`scripts/validate-agent-pod-security.py` finds agent steps by the
`workflow.parameters.agent_image` marker but checks only securityContext.

### Policies that admit agent pods today
| Policy (file) | Destination | `argo-workflows` peer today |
|---|---|---|
| `allow-argo-workflows-ingress` (`argo-workflows/config/networkpolicy.yaml`) | every pod in `argo-workflows` | `podSelector: {}`, all pods in the namespace |
| `allow-vault-ingress` (`bootstrap/templates/core-infra/vault-netpol.yaml`) | vault :8200 | ns `argo-workflows` AND `workflows.argoproj.io/workflow Exists` |
| `allow-backstage-ingress` (`bootstrap/templates/mctl-platform/backstage-netpol.yaml`) | backstage :7007 | same as vault |
| `allow-mctl-api-ingress` (`bootstrap/templates/mctl-platform/mctl-api-netpol.yaml`) | mctl-api, all ports | namespace only |
| `allow-shared-pg-ingress` (`infra-components/data/cnpg/shared/networkpolicy.yaml`) | platform-db :5432 | namespace only |
| `allow-otel-collector-ingress` (`infra-components/observability/otel-collector/networkpolicy.yaml`) | otel-collector :4317/4318 | namespace only |

A repository-wide search for `kind: NetworkPolicy` finds no other policy in
the `vault`, `backstage`, `mctl-api`, `platform-db` or `argo-workflows`
namespaces. The other `monitoring` policies (grafana, vmsingle,
vmalertmanager, vmauth) select other pods by label, not the collector. The
tenant chart's policies live in tenant namespaces. External charts may
still render policies of their own, so the union must also be checked live
(task 2).

### What each client actually uses (from the #2159 inventory and the templates)
- Agent pods: in-cluster, only `otel-collector.monitoring:4318`
  (`OTEL_EXPORTER_OTLP_ENDPOINT` in `cwft-mctl-agents-implement.yaml:848` and
  `cwft-mctl-agents-investigate.yaml:793`) and `mctl-api.mctl-api:8080`. The
  latter comes from the global completion hook
  (`cwft-global-workflow-completion-hook.yaml:98`, attached to every
  workflow by `workflowDefaults.spec.hooks.exit` in
  `bootstrap/templates/core-infra/argo-workflows.yaml:186`). Incidents and
  other mctl-api calls in agent CWFTs use the public `https://api.mctl.ai`,
  which is egress through the proxy, not in-cluster ingress. No agent CWFT
  references Vault, Backstage, shared-pg or the Argo server. The only
  `vault` mentions are comments, and secrets come from the ESO-synced
  `mctl-agents-secrets`.
- Vault clients from `argo-workflows`: `tpl-vault-write.yaml`,
  `wft-create-tenant.yaml`, `wft-provision-database.yaml`,
  `wft-delete-tenant-safe.yaml`, `wft-bootstrap-platform.yaml`,
  `wft-smoke-test.yaml`, `cwft-rotate-github-token.yaml`,
  `cwft-zitadel-login-consolidation.yaml`, all platform templates.
- Backstage clients: `wft-remove-custom-domain.yaml`.
- shared-pg clients: the workflow controller and server (workflow archive,
  `persistence.postgresql.host: shared-pg-rw.platform-db.svc` in
  `argo-workflows.yaml:102-138`) and `wft-provision-database.yaml`.
- Intra-`argo-workflows`: the file comment names controller-to-pod, artifact
  passing and the wait sidecar. With the emissary executor, the wait sidecar
  talks to the kube API and artifacts go to Cloudflare R2. Neither is
  pod-to-pod inside the namespace, and no agent template dials another pod
  there.

Deployed state checked:
- `mctl_list_services(team=admins)`: 8 catalogue services, all Synced,
  including `mctl-agents-worker`, `mctl-agents-worker-exec` and
  `mctl-agents-worker-implement` (image `ghcr.io/mctlhq/mctl-agents:1.112.2`).
  These are tenant-namespace workers, outside this proposal.
- `$MCTL_GITOPS_ROOT/tenants/` lists admins, commerce-proof, erpact, karabu,
  labs, mctl, namax66. No service config there is touched by this change.
- Live NetworkPolicy objects, pod labels of the Argo controller/server and
  kube-router's `NotIn` behaviour were NOT observable: no `kubectl` in this
  run, and the mctl MCP tools expose no NetworkPolicy or argo-workflows pod
  read. They are recorded as open questions and gated by task 2. They were
  not assumed absent.

## Proposed solution

### 1. Label contract (no behaviour change)
- Canonical agent label: `app.kubernetes.io/name: mctl-agents`, set only in
  `spec.podMetadata.labels` of agent CWFTs. It is MCTL-owned, already on
  every agent template, and already the selector of `allow-agent-ingress`
  and planned stage C, so one contract serves both directions of #807.
  `workflows.argoproj.io/workflow` (Argo-owned) remains only as a way to say
  "a workflow pod, not the controller/server". It never marks a pod as an
  agent.
- New `scripts/validate-agent-pod-labels.py`, with `--selftest`, wired into
  `.github/workflows/validate-manifests.yml` next to "Validate agent pod
  security context". It fails when:
  - an agent CWFT lacks the label. A template is an agent CWFT if it is named
    `cwft-mctl-agents-*` / `wft-lifecycle-bootstrap`, contains the
    `workflow.parameters.agent_image` marker, or uses an image under
    `ghcr.io/mctlhq/mctl-agents`. The detection is shared with
    `validate-agent-pod-security.py`;
  - a CronWorkflow/Workflow referencing an agent CWFT sets
    `podMetadata.labels["app.kubernetes.io/name"]` to another value;
  - a non-agent template carries the label. That pod would lose platform
    paths, and it blurs the contract.
- Document the contract in `docs/runbooks/agent-pod-isolation.md`, linked
  from `CLAUDE.md` and the egress runbook. The document lists the label, the
  agent allowlist of in-cluster destinations, and how to add a path.

### 2. Two selector shapes used everywhere
- Agent pod: `app.kubernetes.io/name In [mctl-agents]`.
- Non-agent workflow pod: `workflows.argoproj.io/workflow Exists` AND
  `app.kubernetes.io/name NotIn [mctl-agents]`. `NotIn` also matches pods
  without the key, which is all platform workflow pods today. No edits to
  ~30 platform templates are needed.

The `NotIn` shape is fail-open for an agent template that loses its label.
CI (step 1) is what closes that gap. That trade-off is chosen over a
positive platform label; see Alternatives.

### 3. Per-destination changes
| Policy | New `argo-workflows` peer(s) | Effect on agents |
|---|---|---|
| `allow-vault-ingress` | non-agent workflow pods | lose Vault |
| `allow-backstage-ingress` | non-agent workflow pods | lose Backstage |
| `allow-shared-pg-ingress` | (a) non-agent workflow pods; (b) controller + server pods by their chart labels (confirmed live in task 2) | lose shared-pg |
| `allow-mctl-api-ingress` | workflow pods (`workflows.argoproj.io/workflow Exists`), in a separate rule limited to TCP 8080 | keep 8080 (completion hook); controller/server lose it, nothing uses it |
| `allow-otel-collector-ingress` | workflow pods (`workflows.argoproj.io/workflow Exists`) on 4317/4318 | keep. Agents are on the inventory, and so are platform workflow pods |
| `allow-argo-workflows-ingress` | intra-namespace source becomes `podSelector: {matchExpressions: [{key: app.kubernetes.io/name, operator: NotIn, values: [mctl-agents]}]}`. External namespace peers unchanged | agent pods can no longer open connections to any pod in `argo-workflows` (server, controller, platform workflow pods, other agent pods) |

Each changed peer keeps namespace AND pod selectors in one element (ANDed),
in line with the #1818 convention already used in vault/backstage. Each file
gets a comment that names the contract runbook and #2289. The tenant-namespace
peer of `allow-vault-ingress` is untouched, because agent pods never run in
tenant namespaces.

No agent-to-agent allow is added: nothing in the templates needs it. If the
#2159 stage A log shows otherwise, a separate `allow-agent-intra-ingress`
policy (spec.podSelector = agent, from = agent) is the documented way to add
it.

### 4. Static check of all policies combined (CI)
New `scripts/validate-agent-ingress-isolation.py`, with `--selftest`, in
`validate-manifests.yml`. It:
1. Loads every NetworkPolicy from raw manifests under `platform-gitops/` and
   from the rendered bootstrap chart. CI already renders it for
   `validate-tenant-networkpolicy-allowlist.py`, so the same `bootstrap.yaml`
   is reused.
2. Builds synthetic source pods, each with its namespace labels: agent
   workflow pod, agent exit-hook pod, platform workflow pod, Argo controller
   and Argo server.
3. For each destination (vault, backstage, mctl-api :8080, platform-db :5432,
   otel :4318, an argo-server pod, a platform workflow pod, the egress proxy
   :3128), evaluates the union of all policies whose `spec.podSelector`
   selects it: allowed if any ingress rule matches source and port.
4. Compares with a checked-in expected matrix (in the script). Any extra
   allow for an agent source is a failure, and so is a missing allow for a
   platform source.
5. Lint rule: any peer whose `namespaceSelector` can match `argo-workflows`
   (by name or by `Exists`/empty selector) without a `podSelector` fails,
   except in the egress-proxy policy, which is scoped by `podSelector`
   anyway.

Selftest mutations: drop the `NotIn`, restore `podSelector: {}`, remove the
podSelector from a peer, delete the label from one agent CWFT, and add a
second policy that admits the namespace. The last one proves the union is
evaluated, not one file at a time.

### 5. Live proof (rollout gate)
A probe script `scripts/probe-agent-ingress.sh` (operator-run, needs
cluster-admin kubeconfig, not CI) starts two short-lived pods in
`argo-workflows`. One carries the canonical labels plus a
`workflows.argoproj.io/workflow: probe-agent` label; the other carries only
`workflows.argoproj.io/workflow: probe-platform`. Both run `nc -z -w 3` against
every matrix destination and print allow/deny, then the pods are deleted.
The script runs before any policy change (baseline, and to confirm kube-router
`NotIn` support on a scratch policy) and after each policy PR syncs.

### Rollout order
One PR per step, each gated by the probe plus a deploy-service run:
1. Contract + validators (the static check's expected matrix starts at
   today's state, then tightens with each PR).
2. otel-collector and mctl-api: the lowest risk, since agents keep both.
3. Backstage.
4. shared-pg (after confirming controller/server labels).
5. Vault.
6. `allow-argo-workflows-ingress` intra-namespace.
Then one deploy-service workflow and one run of each agent kind.

## Alternatives
- **Positive platform label** (`mctl.ai/workload-class: platform` on every
  non-agent template, with destinations admitting only that label). This is
  fail-closed for agents, but needs edits to ~30 templates plus the
  tenant-namespace deploy-service steps. A missed template breaks deploys
  silently in production, which is the outcome the rollback note warns
  about. Kept as the fallback if kube-router mishandles `NotIn`.
- **Dedicated new label** (`mctl.ai/agent: "true"`) instead of reusing
  `app.kubernetes.io/name`. The semantics are clearer, but it would be a
  second contract next to the one #2159 already uses for the egress proxy
  and stage C, and the two could drift. Reusing one CI-validated label is
  simpler. The runbook states that the label is a security selector, so a
  Loki relabel cannot silently repurpose it.
- **Move agents to their own namespace.** This is the cleanest boundary, but
  #807 decided `HARDEN_IN_PLACE`, so it is out of scope.
- **Rely on Argo's `workflows.argoproj.io/workflow` plus workflow-name
  prefixes.** Labels cannot be prefix-matched, and Argo owns the semantics.
  Rejected, as the issue requires.

## Platform impact
- No migration. Changes are selectors in six existing policies plus two
  scripts, one runbook and CI steps. Argo CD applies them through root-app
  and the shared-pg/otel Applications, all of which prune, so reverting a
  file restores the previous policy.
- Backward compatibility: platform workflow pods match `NotIn` because they
  lack the key, so they keep all paths. The risk is a template that is not
  an agent but carries the label. CI rejects that.
- Risk: kube-router `NotIn` semantics. Mitigated by the task 2 scratch-policy
  probe before any production policy is touched.
- Risk: agent exit-hook pods not carrying podMetadata. They would then look
  like platform pods and still pass, so nothing breaks, but the boundary
  would be weaker there. The probe and a check of a live hook pod's labels
  catch this.
- Risk: a runtime submitter overriding podMetadata on an agent workflow. The
  agent then gains platform reach, the same as today (no regression). This is
  tracked under #800 admission control.
- Risk: the Argo controller/server losing shared-pg breaks the workflow
  archive and the server UI's archived list. Mitigated by confirming labels
  first, plus a probe from those pods' perspective via the static check, and
  watching controller logs after sync.
- Resource impact: none at runtime. CI gains two Python checks, each running
  in seconds.
