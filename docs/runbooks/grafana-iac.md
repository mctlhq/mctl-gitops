# Grafana configuration as code (grafana.mctl.ai)

Grafana state that its Helm values cannot express (folder permissions, and
the tenant organizations with their datasources and dashboards, per
mctlhq/mctl-gitops#1601) is declared in an OpenTofu root and applied by an
in-cluster Job, not clicked in the UI.

| Piece | Where |
| --- | --- |
| OpenTofu root (folder ACLs, tenant orgs, their dashboards as `*.json`) | `platform-gitops/helm-charts/grafana-iac/iac/` |
| Job, CronJob, guard | `platform-gitops/helm-charts/grafana-iac/` |
| Argo CD Application, namespace `grafana-iac` | `platform-gitops/bootstrap/templates/observability/grafana-iac.yaml` |
| Admin credential, tenant metrics passwords and pull secret (ExternalSecrets), the Job's NetworkPolicies | `platform-gitops/infra-components/observability/grafana-iac/` |
| Authorization strip on the Ingress, Grafana's NetworkPolicy | `platform-gitops/infra-components/observability/grafana-access/` |
| `[auth.basic]`, brute-force protection, no external snapshots or public dashboards, Ingress annotation | `platform-gitops/bootstrap/templates/observability/monitoring.yaml` |
| Image | `platform-gitops/images/grafana-iac/Dockerfile` |

## How the Job authenticates

Creating organizations needs a Grafana *server admin*, and in OSS a service
account can never be one, so the Job signs in as the built-in `admin` user
with HTTP basic auth. The password is Vault `secret/platform/grafana`
(`admin-password`), the same value Grafana seeded the user from when its
database was created on shared-pg (#1608). Nothing is minted or stored by
hand.

Basic auth is only usable in-cluster, from this Job:

- The public Ingress strips `Authorization` (middleware
  `monitoring/grafana-strip-authorization`). A password or bearer token sent
  to grafana.mctl.ai never reaches Grafana; browsers use the session cookie.
- Grafana's NetworkPolicy `monitoring/grafana-ingress` admits port 3000 from
  traefik, the `grafana-iac` pods and vmagent only.
- The login form stays disabled (`disable_login_form`): `POST /login` answers
  `auth.client.notConfigured`, so no browser path takes a password.
- Brute-force protection is on: 5 failed attempts lock the username for 5
  minutes. Only this Job can send a password, so a lockout means its
  credential is wrong; the Job fails with a 401 until it is fixed.

## What it owns

| Resource | State |
| --- | --- |
| Main Org folder `Internal` permissions | Admin role only; the default Viewer and Editor items are removed. The folder itself is created by the dashboards sidecar from the `grafana_folder` annotation. |

| Org `erpact` | Created here; members are NOT managed here (see below). |
| Its datasource `VictoriaMetrics` (uid `erpact-metrics`) | The org's only and default datasource: VMAuth user `erpact` (`vmauth-grafana-tenants.monitoring.svc:8427`), which adds `namespace="erpact"` to every query. Password from Vault `platform/grafana-tenants/erpact` (`metrics-password`) as a sensitive variable. |
| Its folder `ERPact`, with the dashboards `erpact-overview.json` and `erpact-workloads.json` | Members (Editor) can view, not edit; their own dashboards go to General. `erpact-overview.json` is the same dashboard Main Org gets from `erpact-tenant-dashboard-configmap.yaml`; change both. |

The folder permissions, the datasource and the dashboards are authoritative: a
change made in the UI is reverted by the next hourly run (`:47`).

**Tenant org membership is the ZITADEL sign-in's job** (`org_mapping`, #1601
step 5). The provider reads every member back into `admins` / `editors` /
`viewers`, so `grafana_organization` ignores those lists: left in the plan,
they would remove signed-in members and print their email addresses in the
Job log. Until step 5 maps the tenant roles, nobody but the server admin is
in the org.

**Tenant isolation lives in VMAuth, not in Grafana.** An Editor can query the
datasource freely (Explore, the datasource proxy, `/api/ds/query`), but every
request reaches VictoriaMetrics with `extra_label=namespace=erpact`. Editors
cannot add or change a datasource in OSS (403), so they cannot point a query
anywhere else. The org has no logs yet (Loki multi-tenancy, #1601 step 3).

## Guard

The Job plans, then refuses to apply when the plan has an action outside
`allowedActions` (`no-op read create update`) or deletes an address not
listed in `allowedDeletes` (empty). To remove something deliberately, list the
exact address in `allowedDeletes` in the PR that removes it, and empty the
list again once it has applied.

## Checks

- Last run: `kubectl -n grafana-iac logs job/grafana-iac` (PostSync) or the
  newest `grafana-iac-<n>` Job from the CronJob. `grafana-iac: no changes`
  is the converged state.
- Edge: `curl -s -o /dev/null -w '%{http_code}' -u admin:x https://grafana.mctl.ai/api/org`
  must be `401` with any password (the header never arrives).
- Tenant isolation, from inside the Grafana pod as VMAuth user `erpact`:
  `kube_pod_info{namespace="monitoring"}` must return no series, and
  `/api/v1/label/namespace/values` only `["erpact"]`.

## Rollback

- Folder ACL: remove the resource with its address in `allowedDeletes`; the
  folder keeps whatever permissions it had, nothing is reset.
- Basic auth: `auth.basic.enabled: false` in `monitoring.yaml`. The Job then
  fails with a 401 and changes nothing. Keep the strip and the NetworkPolicy;
  they cost nothing with basic auth off.
- A tenant org: list `grafana_organization.erpact` and everything in it
  (datasource, folder, folder permission, dashboards) in `allowedDeletes` in
  the revert PR; deleting the org deletes its members' dashboards too.
- The whole root: delete the Application. State stays in the
  `tfstate-default-grafana-iac` Secret until the namespace goes.
