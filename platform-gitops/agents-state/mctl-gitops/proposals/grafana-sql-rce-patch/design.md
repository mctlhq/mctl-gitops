# Design: grafana-sql-rce-patch

## Current state
Per `context/architecture.md`, Grafana is listed under "Dependencies for researcher" as
`prometheus/prometheus + grafana/loki (if templated)`, indicating that Grafana may be
deployed via the platform's Helm-templated services. If deployed, it would follow the
standard `helm-charts/base-service` pattern with a values file at
`platform-gitops/services/<tenant>/grafana/values.yaml` and an ArgoCD Application
definition under `platform-gitops/apps/`. The Grafana Deployment would carry the service
account and credentials provisioned by the base chart — which may include cluster-scoped
read access for metric discovery.

Whether or not Grafana is currently deployed, the `sqlExpressions` feature toggle
(introduced in Grafana v11.6.0) is enabled by default in affected versions unless
explicitly set to `false` in `grafana.ini` or the Helm values. The CVE exploit chain is:
Viewer account → SQL Expression query → data source config overwrite → RCE on Grafana Pod.

The current Grafana version on the platform (if deployed) is unknown and must be
confirmed as part of the remediation tasks.

## Proposed solution
**Step 0 — Deployment confirmation.**
Before any code change, confirm whether Grafana is deployed on the platform. Check
`platform-gitops/apps/` and `platform-gitops/services/` for a Grafana Application
definition. If not present, close with a documented non-deployment confirmation (ADR entry).

**Primary path — Version upgrade.**
Upgrade Grafana to the lowest patched release compatible with the current minor line:
- If running v12.1.x → upgrade to v12.1.10.
- If running v12.2.x → upgrade to v12.2.8.
- If running v12.3.x → upgrade to v12.3.6.
- If running v12.4.x → upgrade to v12.4.2.
- If running v11.x or earlier → upgrade to v12.1.10 (minimum patched baseline) or v13.0.0.

The image tag is updated in the Helm values file. ArgoCD syncs the rolling update to the
Grafana Deployment. This is the definitive fix.

**Interim mitigation — Disable `sqlExpressions` feature toggle.**
If an immediate version upgrade is not feasible (e.g., blocked by other Grafana
configuration migration work), add the following to the Grafana configuration in the Helm
values:

```
grafana.ini:
  feature_toggles:
    sqlExpressions: false
```

This prevents the exploit precondition from being met without requiring a Pod image change.
The interim mitigation can be applied independently and should be applied immediately if
the upgrade cannot be completed within 24 hours of this proposal being accepted.

Both the interim mitigation and the full upgrade are complementary; applying the toggle
disable first and then upgrading is the safest sequencing.

## Alternatives

**Alternative 1 — Restrict Viewer role to remove data source access.**
Remove data source query permissions from the Viewer role in Grafana RBAC so Viewer
accounts cannot submit SQL Expression queries. Dropped because Grafana's RBAC does not
offer granular enough control to block SQL Expression submission while preserving normal
Viewer dashboard access; this would effectively degrade the Viewer experience and is a
non-standard configuration that must be maintained through future Grafana upgrades.

**Alternative 2 — Network policy to block Grafana egress to SSH/exec endpoints.**
Apply a NetworkPolicy restricting Grafana Pod egress so that even if RCE is triggered, the
attacker cannot reach external hosts. Dropped because the CVE grants RCE on the Grafana
host itself (not a remote target); a NetworkPolicy cannot prevent local command execution
on the Pod, and the broader risk is lateral movement from the Grafana service account, not
outbound SSH.

**Alternative 3 — Remove Grafana from the platform until patched.**
Temporarily delete the Grafana Application from ArgoCD. Dropped because it causes a
complete observability outage for all users and is disproportionate given that the interim
mitigation (toggle disable) is low-risk and can close the attack vector within minutes.

## Platform impact

**Migrations**
- Version upgrade: Grafana minor-to-minor upgrades are generally backward compatible for
  dashboards, data sources, and alerting rules. A cross-major upgrade (e.g., v11 → v12)
  requires reviewing the Grafana v12 migration guide for any deprecated configuration keys.
- Toggle disable: no data migration; a ConfigMap or `grafana.ini` key change only.

**Backward compatibility**
- Disabling `sqlExpressions` will break any dashboards that currently use SQL Expression
  query types. Audit existing dashboards for SQL Expression usage before disabling.
- The version upgrade preserves the SQL Expressions feature with the security fix applied,
  so dashboard compatibility is unaffected post-upgrade.

**Resource impact**
- Grafana runs in the `admins` namespace (if templated to admins) or potentially in `labs`.
  The `labs` tenant is close to its memory limit. If Grafana runs in `labs`, verify that
  the upgraded image does not have a significantly larger memory footprint than the current
  version. Grafana v12.x images are typically 300-400 Mi at rest; if `labs` memory headroom
  is below this, flag to the platform team before deploying in `labs`. Prefer deploying
  observability tooling in `admins` where memory headroom is not constrained.
- No new sidecar containers or additional Pods are introduced by this fix.

**Risks and mitigations**
- Risk: Grafana not actually deployed — proposal tasks reveal no Grafana Application.
  Mitigation: close via documented non-deployment ADR entry; no code changes required.
- Risk: version upgrade breaks an existing dashboard or plugin.
  Mitigation: review Grafana changelog for the target version; test in a non-production
  context if available; roll back via git revert if dashboards fail post-upgrade.
- Risk: disabling `sqlExpressions` breaks an undocumented dashboard in production.
  Mitigation: audit dashboards for SQL Expression usage before applying the toggle change
  (task 2 in tasks.md); communicate the change to dashboard owners.
- Risk: `labs` memory exhaustion if Grafana is running there and the new image is larger.
  Mitigation: check Grafana Pod memory usage before and after the upgrade; set a memory
  limit in values.yaml that does not exceed `labs` available headroom.
