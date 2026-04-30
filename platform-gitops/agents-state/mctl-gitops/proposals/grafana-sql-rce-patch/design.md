# Design: grafana-sql-rce-patch

## Current state

Grafana is listed as "if templated" in `context/architecture.md`. It may be deployed as an
ArgoCD-managed Application under `platform-gitops/services/admins/grafana/` (or similar) using
the `helm-charts/base-service` chart with a Grafana-specific `values.yaml`. Version is unknown
until the repo is searched.

CVE-2026-27876 exploits the `sqlExpressions` feature toggle, which is enabled by default in
affected versions. A Viewer-level user can craft a SQL expression that triggers a plugin data
source config overwrite, leading to code execution in the Grafana server process. Since the
server may run with a `cluster-admin` or elevated service account on a shared cluster, the blast
radius extends beyond Grafana to the entire Kubernetes cluster.

## Proposed solution

### Step 0 — Confirm deployment scope (prerequisite)

Search `platform-gitops/services/` and `platform-gitops/helm-charts/` for any Grafana image
reference. If not found, close the proposal as N/A.

### Phase 1 — Interim mitigation: disable sqlExpressions toggle

1. Locate the Grafana `values.yaml` (expected path:
   `platform-gitops/services/admins/grafana/values.yaml`).
2. Add or ensure the following in the `grafana.ini` section:
   ```yaml
   grafana.ini:
     feature_toggles:
       sqlExpressions: "false"
   ```
3. Commit; ArgoCD syncs; Grafana reloads config (no pod restart required for ini changes in
   most Helm chart versions — confirm with the chart docs).

This closes the RCE attack vector immediately without a version upgrade.

### Phase 2 — Version upgrade to a patched release

1. Determine the current `image.tag` in the Grafana values file.
2. Select the appropriate patched release within the same minor line where possible:
   - v12.1.x → v12.1.10
   - v12.2.x → v12.2.8
   - v12.3.x → v12.3.6
   - v12.4.x → v12.4.2
   - Any older version → v12.1.10 (minimum patched)
3. Update `image.tag` in the values file; commit; ArgoCD triggers a rolling restart.
4. Validate dashboards, alerting rules, and datasource connectivity post-upgrade.

## Alternatives

**A. Restrict all Viewer access** — Disabling Viewer logins removes the attack surface but breaks
the observability use-case for all non-admin users. Dropped.

**B. Network policy egress block from Grafana pods** — Prevents outbound SSH from the RCE payload
but does not prevent the config overwrite step or local data exfiltration. Dropped as incomplete.

**C. Remove Grafana entirely** — No Grafana means no CVE exposure, but also no platform
observability. Dropped unless Step 0 finds no deployment (in which case the proposal is N/A).

## Platform impact

- **Migrations:** Phase 1 is a `grafana.ini` config change; Phase 2 is an image tag bump. Both
  are git-commit-driven and ArgoCD-synced.
- **Backward compatibility:** Dashboards that rely on the SQL Expressions feature will stop
  functioning during Phase 1; expected to be zero on this platform (feature is experimental).
  Phase 2 rolling restart has no downtime if Grafana has `replicas > 1`.
- **Resource impact for `labs`:** If Grafana is deployed in `labs`, a version upgrade may change
  the image size by ~50–100 MB. Given `labs` is near its memory limit, verify headroom before
  applying Phase 2 to the `labs` namespace. Flag as risky if margin is under 256 Mi.
- **Risks:** Grafana database schema migrations can occur on upgrade; a failed migration requires
  a database restore. Mitigate by snapshotting the Grafana SQLite/PostgreSQL DB before Phase 2.
