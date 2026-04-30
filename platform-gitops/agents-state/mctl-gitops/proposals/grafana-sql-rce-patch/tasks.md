# Tasks: grafana-sql-rce-patch

- [ ] 1. Confirm Grafana deployment status on the platform — DoD: search
         `platform-gitops/apps/` and `platform-gitops/services/` for a Grafana Application
         definition; document result (deployed / not deployed) and the running version if
         deployed, committed as an ADR entry in `context/decisions/`; if not deployed,
         mark all remaining tasks as N/A and close the proposal.

- [ ] 2. (depends on 1, Grafana is deployed) Audit all existing Grafana dashboards for use
         of SQL Expression query types — DoD: list of dashboards using SQL Expressions
         committed to the ADR; if none found, interim mitigation can proceed without user
         impact; if found, dashboard owners notified before the toggle is disabled.

- [ ] 3. (Interim mitigation — depends on 2) Add `feature_toggles.sqlExpressions: false`
         to the Grafana Helm values file under `platform-gitops/services/<tenant>/grafana/`
         — DoD: PR merged; ArgoCD sync completes; Grafana Pod restarts cleanly; a test
         SQL Expression query returns an error response to a Viewer-level account.

- [ ] 4. (depends on 1) Determine the appropriate patched Grafana version for the current
         minor line (v12.1.10, v12.2.8, v12.3.6, v12.4.2, or v13.0.0+) — DoD: target
         version recorded in the ADR; Grafana changelog for that release reviewed for
         breaking changes; any deprecated configuration keys identified and migration steps
         noted.

- [ ] 5. (depends on 3, 4) Update the Grafana image tag in the Helm values file to the
         patched version — DoD: PR merged; ArgoCD sync completes; Grafana Pod `Running`
         with the new image digest; no crash-loop observed; `GET /api/health` returns HTTP
         200.

- [ ] 6. (depends on 5) Check Grafana Pod memory usage post-upgrade and compare against
         `labs` namespace memory headroom if Grafana runs in `labs` — DoD: memory metrics
         confirmed below the `labs` namespace limit; if headroom is insufficient, a memory
         limit is added to the values file and the platform team is alerted.

- [ ] 7. (depends on 5) Update `context/current-version.md` or the relevant service
         manifest to reflect the new Grafana version — DoD: file updated, committed,
         and merged.

## Tests

- [ ] T1. (Post-toggle-disable or post-upgrade) As a Viewer-level Grafana account, attempt
          to submit a SQL Expression query via the Grafana API (`POST /api/ds/query` with
          type `sql`); verify the response is an error (feature disabled) or the request
          does not trigger the vulnerable code path in the patched version — DoD: response
          is not a successful data query execution; Grafana server logs show no SQL
          Expression driver invocation.

- [ ] T2. (Post-upgrade) Verify that all existing dashboards load without errors for a
          Viewer-level account — DoD: spot-check of the five most-used dashboards shows
          no query errors or broken panels in the Grafana UI.

- [ ] T3. Grafana health endpoint check: `GET https://<grafana-host>/api/health` returns
          `{"database":"ok","version":"<patched-version>"}` — DoD: response body confirms
          the patched version string; database status is `ok`.

- [ ] T4. ArgoCD sync check: the Grafana Application in ArgoCD shows `Healthy` and
          `Synced` after the upgrade — DoD: ArgoCD UI / CLI confirms status; no out-of-sync
          resources.

- [ ] T5. (If Grafana runs in `labs`) Verify `labs` namespace total memory usage remains
          below the namespace limit after the upgrade — DoD: `kubectl top pods -n labs`
          or equivalent shows no OOMKilled events; namespace ResourceQuota usage is below
          the limit.

## Rollback
- **Toggle disable rollback:** remove or set `feature_toggles.sqlExpressions: true` in the
  Helm values file; merge and push; ArgoCD syncs the ConfigMap change and restarts Grafana.
  This re-enables the vulnerable feature toggle and should only be done if the toggle
  disable caused a critical dashboard regression, with the upgrade then accelerated.
- **Version upgrade rollback:** revert the image tag commit in `mctl-gitops`; ArgoCD will
  sync the Grafana Deployment back to the previous image on the next sync cycle. Grafana
  persistent data (dashboards stored in the database) is unaffected by a Pod image
  rollback. If the upgrade included a database schema migration, consult the Grafana
  downgrade guide before rolling back.
- In both cases, the toggle disable (task 3) should remain in place as a mitigation while
  the root cause of the regression is investigated.
