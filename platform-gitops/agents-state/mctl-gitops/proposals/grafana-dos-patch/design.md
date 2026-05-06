# Design: grafana-dos-patch

## Current state

Grafana is listed as "if templated" in `context/architecture.md`. It may be deployed as an
ArgoCD-managed Application under `platform-gitops/services/<tenant>/grafana/` using the
`helm-charts/base-service` chart with a Grafana-specific `values.yaml`. The exact running
version is not confirmed in this repository's static files and must be discovered at
execution time.

CVE-2026-27880 is a memory exhaustion denial-of-service vulnerability affecting Grafana
v12.1.0 and later. Unlike CVE-2026-27876 (RCE, covered by `grafana-sql-rce-patch`), there
is no toggle-based interim mitigation for the DoS vector: the only fix is upgrading to a
patched release. The patched release set is identical for both CVEs: v12.1.10, v12.2.8,
v12.3.6, v12.4.2, and v11.6.14.

The existing proposal `grafana-sql-rce-patch` may or may not have been executed. This
proposal is designed to operate correctly in three scenarios:

1. `grafana-sql-rce-patch` has not been executed — this proposal performs the full upgrade.
2. `grafana-sql-rce-patch` has been executed and Grafana is already on a patched release —
   this proposal confirms the DoS CVE is also resolved by the same version and closes with
   a verification-only result.
3. `grafana-sql-rce-patch` applied only the toggle mitigation (Phase 1) without the version
   upgrade (Phase 2) — this proposal performs the version upgrade.

Tenant `labs` is near its memory quota. If Grafana runs in `labs`, any memory increase from
the version upgrade must be measured.

## Proposed solution

### Step 0 — Confirm deployment scope (prerequisite)

Search `platform-gitops/services/` and `platform-gitops/helm-charts/` for any Grafana image
reference. If none is found, this proposal is closed as not applicable and the finding is
documented in the PR description. No further steps are taken.

If a deployment is found, note the tenant namespace (admins or labs), the current image tag,
and whether it falls in the vulnerable range (v12.1.0 through v12.1.9, v12.2.x through
v12.2.7, v12.3.x through v12.3.5, or v12.4.x through v12.4.1).

### Step 1 — Coordinate with `grafana-sql-rce-patch` status

Check whether a patched Grafana image is already running (i.e., whether
`grafana-sql-rce-patch` Phase 2 has been executed):

- If the current image tag is already at a patched release (v12.1.10+, v12.2.8+, v12.3.6+,
  or v12.4.2+), proceed directly to Step 3 (verification only).
- If the image is on a vulnerable tag, proceed to Step 2.

### Step 2 — Upgrade Grafana image tag to a patched release

Select the target patched release within the same minor line as the current deployment:

| Current minor | Target patched |
|---------------|---------------|
| v12.1.x       | v12.1.10      |
| v12.2.x       | v12.2.8       |
| v12.3.x       | v12.3.6       |
| v12.4.x       | v12.4.2       |
| v11.6.x       | v11.6.14      |
| Older         | v12.1.10      |

Update the `image.tag` field in the Grafana `values.yaml`. Commit; ArgoCD syncs and triggers
a rolling restart. If this action is taken concurrently with `grafana-sql-rce-patch` Phase 2,
a single combined commit covering both CVEs is preferred to avoid version churn.

If Grafana is deployed in `labs`, record memory consumption of the Grafana pod before and
after the upgrade (via `kubectl top pods -n <labs-namespace>` or a Prometheus query). If the
post-upgrade memory exceeds the pre-upgrade value by more than 20 percent, flag the delta
as a risk note for the `labs` quota in the PR description.

### Step 3 — Verification

After ArgoCD syncs:

1. Confirm the ArgoCD Application for Grafana shows `Synced` and `Healthy`.
2. Confirm the running image version string or digest matches the patched release target.
3. Confirm existing dashboards continue to render (smoke test: load the Grafana home
   dashboard and at least one data-source-backed panel).
4. Confirm no OOM events appear in the pod events for the Grafana pod within 10 minutes of
   restart.

## Alternatives

**A. Add rate limiting at the ingress layer to prevent memory exhaustion.**
An ingress rate limit (e.g., via NGINX annotation or an Istio policy) would reduce the
attacker's ability to trigger the exhaustion, but it does not eliminate the vulnerability.
A sufficiently slow or distributed attack would still succeed. This is useful as defense-in-
depth hardening but is not a substitute for the version patch. Dropped as primary mitigation;
may be added as separate hardening.

**B. Reduce Grafana replica count to 1 and rely on Kubernetes restart loops.**
If Grafana is killed by OOM, Kubernetes will restart it. This provides availability via
crash-restart but does not prevent service interruption or cascading memory pressure on
other `labs` workloads during the crash cycle. Not acceptable as a security remediation.
Dropped.

**C. Disable Grafana entirely until the patch is applied.**
Zero risk of the DoS if Grafana is not running. However, Grafana provides the primary
platform observability dashboard, so disabling it eliminates monitoring visibility during
the patching window. Acceptable only if the vulnerability is being actively exploited and
the patch cannot be applied within 24 hours. Dropped as standard path; noted as an
emergency option.

## Platform impact

- **Migrations:** The Grafana SQLite or PostgreSQL database may undergo a schema migration on
  upgrade. Before applying the image tag update, snapshot the Grafana database (SQLite file
  or a `pg_dump`). A failed migration requires a database restore to roll back. This risk
  applies regardless of patch version but is noted here for completeness.
- **Backward compatibility:** Patch releases within the same minor line are backward-compatible
  for Grafana configurations, dashboards, and datasource definitions. No breaking changes are
  expected between v12.x.n and v12.x.n+k for the patch ranges listed.
- **Resource impact for `labs`:** If Grafana runs in `labs`, the memory footprint of the
  upgraded image is unknown until Step 2 completes. The `labs` tenant is near its memory
  quota. A Grafana image upgrade is typically bounded to a container image layer diff of
  50–100 MB on disk; runtime memory impact is generally minimal for patch releases. However,
  if the upgrade is co-occurring with `argocd-v3-4-upgrade-plan-v2` (which also touches
  `labs` memory), the combined effect on the `labs` quota must be assessed. This is flagged
  as a risk. If margin in `labs` is under 256 Mi, raise the risk explicitly before applying
  the upgrade.
- **Risks and mitigations:**
  - Risk: Grafana database schema migration fails mid-upgrade, leaving Grafana in a broken
    state. Mitigation: database snapshot before upgrade; rollback path is a database restore
    plus image tag revert.
  - Risk: Upgrading Grafana in `labs` pushes the namespace over its memory quota and causes
    OOM kills for other `labs` workloads. Mitigation: measure memory before and after; if
    margin is insufficient, defer the `labs` upgrade until quota is increased or coordinated
    with the `labs` memory reduction work.
  - Risk: `grafana-dos-patch` and `grafana-sql-rce-patch` produce conflicting image tags if
    executed independently. Mitigation: coordinate execution; prefer a single combined PR
    that sets the same patched image tag for both CVEs.
