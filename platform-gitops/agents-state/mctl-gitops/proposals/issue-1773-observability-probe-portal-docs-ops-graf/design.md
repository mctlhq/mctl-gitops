# Design: issue-1773-observability-probe-portal-docs-ops-graf

## Current state

- `platform-gitops/infra-components/observability/blackbox/vmprobes.yaml` holds
  seven VMProbes (`mctl-telegram-healthz`, `platform-public-endpoints`,
  `redirect-zones`, `forgejo-healthz`, `zitadel-public`, `erpact-sites`,
  `mctl-api-healthz`). Conventions: one VMProbe per `jobName`, because alert rules
  match on `job`; `module: http_2xx` (or `http_redirect`); `interval: 60s`;
  `vmProberSpec.url: blackbox-exporter.monitoring.svc.cluster.local:9115`. A
  comment above each object explains the target choice. vmagent runs with
  `selectAllByDefault: true` (`bootstrap/templates/observability/monitoring.yaml`),
  so it picks up new VMProbes without a selector.
- `erpact-sites` uses `targets.staticConfig` with five URLs
  `https://erpact-<x>.mctl.ai/api/method/ping`. The Grafana dashboard
  `grafana-dashboards/erpact-tenant-dashboard-configmap.yaml` reads
  `probe_success{job=~"erpact-.*"}`. `vm-rules/erpact-alerts.yaml` defines
  `ErpactSiteDown` (`probe_success{job="erpact-sites"} == 0`, for 5m, warning) and
  `ErpactSiteProbeAbsent`.
- ERPact sites are not declared in this repo.
  `bootstrap/templates/erpact/applications.yaml` only defines the Argo CD
  Applications `erpact-infra`, `erpact-shared`, `erpact-control` and
  `erpact-deployer`, which point at `git.mctl.ai/erpact/mctl-apps`. The deployer
  regenerates `shared-stteam/values.yaml` there for each new site. The only in-repo
  copies of site names are hand-kept: `vmprobes.yaml` and
  `helm-charts/zitadel-iac/iac/erpact.tf`. In the cluster, though, every site is an
  Ingress in namespace `erpact`. The admission policy
  `mctl-external-manifests-ingress-hosts` (`bootstrap/templates/system/admission-policies.yaml`),
  with `externalManifestNamespaces.erpact.hostPattern:
  'erpact-[a-z0-9]([a-z0-9-]*[a-z0-9])?\.mctl\.ai'` in `bootstrap/values.yaml`,
  ensures that every Ingress host there is an ERPact site name.
- Console hosts and their health paths:
  - `app.mctl.ai`: Backstage (`bootstrap/templates/mctl-platform/mctl-portal.yaml`).
    The pod probes use `/.backstage/health/v1/readiness`.
  - `docs.mctl.ai`: `services/admins/mctl-docs/values.yaml` (base-service, port 80,
    default probes `/healthz`, `/readyz`).
  - `ops.mctl.ai`: Argo CD server (`platform-gitops/argocd/values.yaml`,
    `server.ingress.hostname`). argocd-server serves `/healthz` without
    authentication.
  - `grafana.mctl.ai`: `monitoring.yaml` grafana ingress. `/api/health` needs no
    authentication.
  - `agent.mctl.ai`: `bootstrap/templates/mctl-platform/mctl-agent.yaml`
    (base-service, liveness `/healthz`, readiness `/readyz`).
- Alert delivery: Alertmanager config is inline in `monitoring.yaml`. The root
  receiver is `mctl-agent`, and child routes send selected alertname prefixes to
  `telegram`. `ErpactMariadbMemory.*` and `ErpactBackup.*|ErpactRestoreDrill.*` are
  Telegram-only. `MctlApi.*` uses the two-part pattern: a Telegram route with
  `continue: true` plus an entry in the mctl-agent catch-all regex. The probe
  alerts (`ErpactSiteDown`, `ForgejoDown`, ...) match no route and reach
  only mctl-agent.
- Rule tests: `scripts/check-vm-rules.sh` (run in `validate-manifests.yml`) extracts each
  VMRule `.spec` into `vm-rules/tests/generated/` and runs `promtool check rules`
  and `promtool test rules` against `vm-rules/tests/*_test.yaml`.

## Proposed solution

### 1. New VMProbe `platform-consoles`

Add it to `vmprobes.yaml` after `mctl-api-healthz`, with the same shape as
`forgejo-healthz`:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMProbe
metadata:
  name: platform-consoles
  namespace: monitoring
spec:
  jobName: platform-consoles
  interval: 60s
  module: http_2xx
  vmProberSpec:
    url: blackbox-exporter.monitoring.svc.cluster.local:9115
  targets:
    staticConfig:
      targets:
        - https://app.mctl.ai/.backstage/health/v1/readiness
        - https://docs.mctl.ai/
        - https://ops.mctl.ai/healthz
        - https://grafana.mctl.ai/api/health
        - https://agent.mctl.ai/healthz
```

All five go in one job because they share an alert, a severity and a route. The
`instance` label already names the host, which matches what the file header asks for
("the job label is what the alert rules match on"). The comment above the object
states, for each target, why that path needs no login. Each path is a real health
endpoint, not a login redirect, so `http_2xx` (`follow_redirects` default) is the
right module. The paths are confirmed by hand before merge (task 1). A path that
answers differently is replaced, and the replacement is recorded in the PR.

### 2. Alerts `vm-rules/platform-console-alerts.yaml`

A new VMRule `mctl-platform-console-alerts`, group `mctl.platform-consoles`:

- `PlatformConsoleDown`: `probe_success{job="platform-consoles"} == 0`, `for: 5m`,
  `severity: warning`, `service: platform`. The description points to
  `probe_http_status_code` and to the pod or Application for each host.
- `PlatformConsoleProbeAbsent`: `absent(probe_success{job="platform-consoles"})`,
  `for: 15m`, warning. This keeps the per-job absence pattern of `ForgejoProbeAbsent`.

The rules go in a separate file, not in `blackbox-alerts.yaml`, so that the
`PlatformConsole.*` prefix is one routing unit, as with `forgejo-alerts.yaml` and
`zitadel-alerts.yaml`.

### 3. Telegram route

In `monitoring.yaml`, before the mctl-agent catch-all routes, add:

```yaml
- receiver: telegram
  matchers:
    - alertname =~ "PlatformConsole.*"
```

The route is Telegram-only and has no `continue`. One target, `agent.mctl.ai`, is
mctl-agent itself, so an agent-routed alert about it would go to the component that
is down. The other four are console outages that mctl-agent cannot fix. This is the
same reasoning as the `ErpactMariadbMemory.*` route. The prefix match is
deliberate, as in the other routes: the next rule added to the file cannot
quietly fall back to agent-only.

### 4. ERPact sites discovered from Ingresses

Replace `targets.staticConfig` on `erpact-sites` with Kubernetes ingress
discovery:

```yaml
spec:
  jobName: erpact-sites
  interval: 60s
  module: http_2xx
  vmProberSpec:
    url: blackbox-exporter.monitoring.svc.cluster.local:9115
  targets:
    ingress:
      namespaceSelector:
        matchNames: [erpact]
      selector: {}
      relabelingConfigs:
        # One target per host, whatever paths the Ingress lists.
        - sourceLabels: [__meta_kubernetes_ingress_path]
          regex: "/|/\\*|"
          action: keep
        - sourceLabels: [__address__]
          targetLabel: __param_target
          replacement: "https://${1}/api/method/ping"
        - sourceLabels: [__param_target]
          targetLabel: instance
```

(Exact relabeling field names follow the operator version in the cluster. The
implementer checks the generated scrape config with
`kubectl -n monitoring get secret vmagent-... -o jsonpath='{.data.vmagent\.yaml\.gz}' | base64 -d | gunzip`
or the vmagent `/config` page, and confirms on `/targets` that the targets are
the URLs listed above.)

Why this satisfies the issue's "follow the source of truth":

- The sites' source of truth is outside this repo (mctl-apps). The Ingress set is
  what the deployer's commits produce once Argo CD applies them, so it is the
  closest object in this repo's control plane. The host-pattern admission policy
  guarantees it contains nothing but `erpact-*.mctl.ai` sites. A site created by
  `mctl_erpact_create_site` is probed about 3 minutes (the Argo CD poll) plus one
  SD cycle after it exists.
- `instance` keeps exactly the current form `https://<host>/api/method/ping`, so
  dashboard history, `ErpactSiteDown`, the existing `erpact-alerts_test.yaml` and
  the `erpact-tenant-dashboard` are unchanged.
- Path deduplication (the `keep` on the root path) stops one host with several
  Ingress paths from producing several identical targets. If the bench Ingresses turn out
  to have no `/` path, the implementer changes this to a `labeldrop`/`keep` on a
  unique key, and the PR records which key was used.

vmagent needs list/watch on `networking.k8s.io/ingresses` in `erpact`. The
VictoriaMetrics operator's vmagent ClusterRole includes ingresses. The implementer
confirms this with `kubectl auth can-i list ingresses.networking.k8s.io -n erpact
--as=system:serviceaccount:monitoring:<vmagent-sa>`. If the check fails, a
Role/RoleBinding in `erpact` granting only `get,list,watch` on ingresses is added to
`bootstrap/templates/erpact/` (this chart already owns `networkpolicy.yaml` there).

### 5. Guard: `ErpactSiteUnprobed`

Discovery can fail silently, for example through RBAC or a relabel regex that drops
everything. `ErpactSiteProbeAbsent` only catches the case where every series is
missing. A host-level comparison against kube-state-metrics covers the partial case:

```promql
group by (host) (kube_ingress_path{namespace="erpact"})
unless on (host)
group by (host) (
  label_replace(probe_success{job="erpact-sites"}, "host", "$1", "instance", "https://([^/]+)/.*")
)
```

The rule is `for: 15m`, warning, in `vm-rules/erpact-alerts.yaml` group
`erpact.availability`. This is the in-cluster version of the issue's fallback
"a check that fails when a site in the source of truth has no probe target". A
CI-time check cannot be built, because CI cannot read the private mctl-apps repo
or the cluster. The implementer verifies that `kube_ingress_path` (default
kube-state-metrics `ingresses` collector) exists with a `host` label. If it does not,
the rule uses `kube_ingress_info` joined through `kube_ingress_tls`, or is reduced to a
count comparison, and the PR says so.

### 6. Route ERPact site alerts to Telegram as well

Add `- receiver: telegram, continue: true, matchers: alertname =~ "ErpactSite.*"`
and append `ErpactSite.*` to the mctl-agent catch-all regex. This is the two-part
pattern used for `MctlApi.*`: a person hears about a down site, and mctl-agent
still opens its incident. The step is independent and can be dropped (see Open
questions in requirements.md).

## Alternatives

1. **Keep `staticConfig`, add the three missing sites, and add a CI check against
   the source of truth.** This was dropped as the primary design. The source of truth
   is the private Forgejo repo `erpact/mctl-apps`, which CI in this repo cannot
   read without new credentials, and the issue explicitly prefers no
   hand-kept list. A CI check against `helm-charts/zitadel-iac/iac/erpact.tf`
   would only compare two hand-kept lists.
2. **Have the ERPact deployer (in mctl-apps) also create a VMProbe or a
   `blackbox-probe` label per site.** This was dropped. It needs code outside this repo,
   and project erpact (`bootstrap/templates/projects/project-erpact.yaml`) does
   not admit `operator.victoriametrics.com` kinds from the tenant repo. Widening
   that is a security decision this issue does not need.
3. **Add the five consoles to `platform-public` so they inherit
   `PublicEndpointDown` (critical).** This was dropped. `platform-public` is reserved for front
   doors that page as critical, and the file already splits `git.` and `auth.` into
   their own warning jobs for this reason. A separate job also gives the consoles their own
   Telegram route without changing the existing critical path.
4. **One VMProbe per console** (five jobs). This was dropped. All five share severity, `for`
   and route, so per-host jobs would only multiply the absence rules. `instance`
   already identifies the host.

## Platform impact

- **Migrations / compatibility:** none. `job="erpact-sites"` and the instance
  format are unchanged, so existing dashboards, rules and tests keep working.
  New series: 5 consoles plus 3 extra ERPact sites, each with about 15 blackbox series.
  Resource impact is negligible (8 extra HTTP requests per minute from blackbox-exporter).
- **Risk: discovery returns zero targets** (RBAC, wrong selector). Mitigation:
  `ErpactSiteProbeAbsent` (existing) fires after 15m, `ErpactSiteUnprobed` names the
  hosts, and verification on vmagent `/targets` before merge is a task.
- **Risk: a non-site Ingress appears in `erpact`.** The host-pattern policy
  restricts hosts to `erpact-*.mctl.ai`. A non-Frappe host would show as down, be
  noticed, and be handled with an Ingress label plus a `selector`.
- **Risk: a newly created site is probed before its restore finishes.** It then
  shows as down for a few minutes. `ErpactSiteDown` needs 5m, and site creation is
  minutes long, so one warning at creation is possible. This is acceptable and
  documented in the rule description.
- **Risk: Cloudflare SBFM challenges probe traffic from Hetzner** to hosts
  outside the skip list in `infrastructure/cloudflare/zones/mctl-ai/firewall.tf`.
  Mitigation: the in-cluster hand check (task 1) uses the same egress path. If a
  challenge (403) is observed, the target is held back and a firewall PR is opened.
- **Risk: Telegram noise during portal deploys.** The 5m `for` rides out a normal
  rolling deploy. The 2026-10-10 deploy outage is exactly the kind of event that should alert.
