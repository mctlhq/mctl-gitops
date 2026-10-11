# Design: issue-1810-hardening-ingress-networkpolicies-for-pl

## Current state

Tenant side. `platform-gitops/helm-charts/tenant/templates/networkpolicy.yaml`
renders `default-deny-all`, `allow-intra-namespace`, `allow-cluster-egress`
(egress to all RFC1918, no port restriction), internet-egress variants,
`allow-ingress-from-traefik` and `allow-ingress-from-monitoring` into each
tenant namespace. Tenant pods can therefore reach every in-cluster Service
unless the destination namespace has an ingress policy.

Existing platform ingress allowlists (all `podSelector: {}`, `policyTypes:
[Ingress]`, one `from` list of namespace selectors, each peer commented):

- `platform-gitops/bootstrap/templates/core-infra/vault-netpol.yaml`
  (`allow-vault-ingress`, ns `vault`).
- `platform-gitops/infra-components/data/cnpg/shared/networkpolicy.yaml`
  (`allow-shared-pg-ingress`, ns `platform-db`; port-scoped 5432/9187, already
  lists `temporal` as a DB client).
- `platform-gitops/argo-workflows/config/networkpolicy.yaml`
  (`allow-argo-workflows-ingress`).
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-netpol.yaml`
  (`allow-mctl-api-ingress`).
- `platform-gitops/infra-components/observability/grafana-access/networkpolicy.yaml`
  (`grafana-ingress`, Grafana pods only in `monitoring`).

So of the issue's list, `vault` and `platform-db` are already done; `temporal`,
`argocd`, `backstage` and the rest of `monitoring` (Loki, VictoriaMetrics,
Alertmanager) are not. No NetworkPolicy targets `namespace: temporal`,
`argocd`, `backstage`, or Loki anywhere in the repo.

Temporal. `platform-gitops/bootstrap/templates/data/temporal.yaml` deploys the
official chart 1.2.0 (server 1.31.0) into ns `temporal`, frontend as a
ClusterIP Service, with a second source
`platform-gitops/infra-components/data/temporal/` (contains
`externalsecret.yaml` and `tenant-namespace-job.yaml`, the PostSync Job
`temporal-namespaces-bootstrap` that dials the frontend from inside `temporal`).
`bootstrap/templates/data/temporal-web.yaml` deploys the UI via base-service
into the same namespace, behind Traefik (`temporal.mctl.ai`,
`admins-temporal-web.mctl.ai`) with Backstage forward-auth.

Every `temporal-frontend.temporal.svc.cluster.local:7233` reference in the
repo (grep for `temporal-frontend` / `7233`):

| Client | Namespace | Source |
|---|---|---|
| temporal-web | temporal | `bootstrap/templates/data/temporal-web.yaml` |
| temporal-namespaces-bootstrap Job | temporal | `infra-components/data/temporal/tenant-namespace-job.yaml` |
| mctl-api (`TEMPORAL_NAMESPACE: mctl-agents`) | mctl-api | `bootstrap/templates/mctl-platform/mctl-api.yaml:238` |
| mctl-agents-worker / -exec / -implement | admins | `services/admins/mctl-agents-worker*/values.yaml` |
| kuptsi-app API + `temporal-worker` sidecar (`TEMPORAL_NAMESPACE: kuptsi`) | labs (tenant) | `services/labs/kuptsi-app/values.yaml:37,112` |

Argo Workflow templates under `platform-gitops/argo-workflows/` pass
`temporal_workflow_id`/`temporal_run_id` parameters but set no
`TEMPORAL_ADDRESS`. Monitoring scrapes the mctl-agents workers' SDK metrics in
`admins` (`bootstrap/templates/mctl-platform/mctl-agents-worker-monitor.yaml`),
not the Temporal server; no scrape of ns `temporal` was found.

Admission. `bootstrap/templates/system/admission-policies.yaml` defines
`mctl-tenant-networkpolicy-allowlist`, a ValidatingAdmissionPolicy bound only
to namespaces with label `mctl.me/tenant`; CI runs
`scripts/validate-tenant-networkpolicy-allowlist.py` over the bootstrap render
(`.github/workflows/validate-manifests.yml`, #1484). Policies in platform
namespaces are not constrained by it.

Deployed state checked:

- `mctl_get_service_config(labs, kuptsi-app)`: deployed, base-service, image
  0.2.27, host `labs-kuptsi-app.mctl.ai` — confirms a live tenant Temporal
  client exists.
- `mctl_list_services(admins)`: complete=true; `mctl-agents-worker`,
  `mctl-agents-worker-exec`, `mctl-agents-worker-implement` deployed at
  mctl-agents 1.73.0 and Synced.
- `$MCTL_GITOPS_ROOT/services/*/*/values.yaml` grep for `temporal`: only the
  three admins workers and `labs/kuptsi-app` reference it.
- `platform-gitops/tenants/labs/values.yaml` and `admins/values.yaml`: no
  `teams`, so the Kubernetes namespaces are `labs` and `admins`.
- Not observed: live network flows into `temporal` (no flow-log or Hubble tool
  available in this read-only run), whether the CNI on k3s-preview enforces
  NetworkPolicy for the temporal pods today, and whether Argo Workflow pods
  dial Temporal at runtime. These are recorded under Open questions and
  verified by task 1 before merge.

## Proposed solution

### Phase 1 (this PR): `temporal`

Add `platform-gitops/infra-components/data/temporal/networkpolicy.yaml`. That
directory is already the temporal Application's second source, so no
Application change is needed (same "picked up automatically" pattern as
`cnpg/shared/networkpolicy.yaml`). Sketch:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-temporal-ingress
  namespace: temporal
  annotations:
    # Before the schema/bootstrap hooks so they are never raced.
    argocd.argoproj.io/sync-wave: "-1"
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        # frontend<->history<->matching<->worker membership/gRPC, schema Job,
        # temporal-namespaces-bootstrap Job, temporal-web -> frontend.
        - podSelector: {}
        # temporal.mctl.ai UI (temporal-web:8080).
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: traefik
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
        # DevLoop start/signal/query (TEMPORAL_ADDRESS in mctl-api.yaml).
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: mctl-api
        # mctl-agents-worker{,-exec,-implement} poll their task queues.
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: admins
    # The one tenant client: kuptsi-app API and its temporal-worker sidecar.
    # Separate rule so the port restriction applies to it only.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: labs
          podSelector:
            matchLabels:
              app.kubernetes.io/instance: labs-kuptsi-app
      ports:
        - protocol: TCP
          port: 7233
```

Header comment states the threat (no client auth, so the network is the only
boundary), the client table with file references, and rollback (delete the
file). The `admins` namespace is allowed whole, matching how
`mctl-api-netpol.yaml` and `argo-workflows/config/networkpolicy.yaml` treat it
(platform workloads, not tenant apps). `argo-workflows` is deliberately not
listed unless task 1 observes a connection from it.

Why namespace-wide `podSelector: {}` rather than only the frontend: the
history/matching/worker gRPC ports (7234/7235/7239) and membership ports are
just as unauthenticated as 7233; selecting all pods closes them too, and
intra-namespace traffic keeps the server cluster working. The existing
allowlists use the same shape, so reviewers recognise it.

Why the release label for kuptsi-app: base-service sets
`app.kubernetes.io/instance: {{ .Release.Name }}` (`base-service/templates/_helpers.tpl:38`)
and the ApplicationSet releases tenant services as `<team>-<service>`
(consistent with `labs-kuptsi-app-base-service-db-creds` in its values). The
implementer must confirm the live label value before merge (task 1).

### Phase 2 (one follow-up PR each, same shape)

Order by exposure: `backstage` (forward-auth endpoint used by every public
service, `backstage.backstage.svc:7007`), then `argocd`, then `monitoring`
(Loki, vmsingle/vminsert, Alertmanager; Grafana already covered). Each PR:

- Allowlist derived from live traffic and grep, starting from the always-on
  set `traefik`, `kube-system`, `monitoring`, intra-namespace.
- `backstage`: additionally every namespace whose Traefik middleware calls
  forward-auth arrives via Traefik, so traefik suffices for that path;
  `mctl-api` and `argo-workflows` if they call the Backstage API.
- `argocd`: `argo-workflows` and `mctl-api` (if they call argocd-server),
  `admins`. Repo-server/redis/controller stay intra-namespace.
- `monitoring` (Loki/VM): promtail/otel-collector sources, Grafana is in-ns,
  `admins` if mctl-agents reads Loki; tenant namespaces must NOT be
  allowlisted wholesale on Loki's push/query ports — if tenants need log or
  metric push, scope by port like `otel-collector/networkpolicy.yaml` does.
- Where an upstream chart owns the namespace (argo-cd, loki), prefer a raw
  manifest next to the Application (as `vault-netpol.yaml` does) over chart
  `networkPolicy.create` flags, so all allowlists share one reviewed shape.

### Phase 3: live verification (each phase)

A short probe documented in the policy's header and run after sync: from an
ephemeral pod in a tenant namespace (e.g. `ovk` via `kubectl run --rm` with
`nc -zvw3 temporal-frontend.temporal 7233`) expect timeout; from `mctl-api`,
`admins` and the kuptsi-app pod expect connect; then exercise a DevLoop
start/signal/query and open `temporal.mctl.ai`.

### Coordination with #1484

The new policy lives in `temporal`, which has no `mctl.me/tenant` label, so
`mctl-tenant-networkpolicy-allowlist` does not apply and no entry is added. It
is also outside the bootstrap render that
`validate-tenant-networkpolicy-allowlist.py` reads. Phase 2 policies likewise
target non-tenant namespaces. The policy is still rendered/validated by the
kubeconform steps if the implementer adds `infra-components/data/temporal` to
the raw-manifest validation (check `validate-manifests.yml` coverage).

## Alternatives

1. Temporal client auth (mTLS / authorizer) first. Stronger, but needs cert
   issuance for five client workloads and code changes in mctl-api,
   mctl-agents and kuptsi-app. Kept as step 4; a NetworkPolicy is a
   same-day, gitops-only reduction of exposure.
2. Select only the frontend pods (`app.kubernetes.io/component: frontend`).
   Leaves history/matching/worker ports open cluster-wide and depends on chart
   label stability; dropped.
3. Cluster-wide default-deny for all platform namespaces at once (or a
   CiliumClusterwideNetworkPolicy). One change could break Traefik, scrape and
   control-plane paths across every namespace simultaneously, and the cluster
   uses plain `networking.k8s.io/v1` policies everywhere; dropped in favour of
   the issue's one-namespace-per-PR rollout.
4. Exclude kuptsi-app and move it behind an API. It is a live tenant client
   (verified); denying it would break a production workload. Kept allowed,
   narrowed to the pod and port.

## Platform impact

- No migration, no Application or chart change; one new manifest synced by
  the existing temporal Application.
- Risk: an unknown Temporal client breaks (e.g. a workflow pod or an
  unlisted admin tool). Mitigation: task 1 inventory of live connections and
  CI-free rollback by reverting one file; DevLoopWorkflows are durable, so a
  short outage of a client only delays activities, it does not lose state.
- Risk: kubelet probes. Probes originate from the node, not a pod; on k3s
  these are allowed by the CNI's host exemption, and `kube-system` is listed
  as the other allowlists do.
- Risk: label mismatch on kuptsi-app silently blocks it. Mitigation: verify
  the live label (task 1) and probe from that pod (T3).
- Resource impact: none.
- Residual risk: until client auth exists, kuptsi-app can still reach the
  `mctl-agents` Temporal namespace; admins-namespace workloads remain trusted.
