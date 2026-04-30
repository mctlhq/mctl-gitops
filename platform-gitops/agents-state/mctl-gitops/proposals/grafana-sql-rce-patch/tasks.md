# Tasks: grafana-sql-rce-patch

## Step 0 — Confirm scope

- [ ] 1. Search the repository for Grafana image references under `platform-gitops/services/` and
  `platform-gitops/helm-charts/` — run `grep -r "grafana" platform-gitops/services/ --include="*.yaml" -l`.
  DoD: either (a) a Grafana values file is found and its path is recorded, OR (b) no Grafana
  deployment is found and this proposal is closed as N/A with a comment in the PR.

## Phase 1 — Interim mitigation (depends on 1, outcome a)

- [ ] 2. Identify the current Grafana image tag in the values file found in task 1.
  DoD: image tag recorded (e.g., `12.3.5`).

- [ ] 3. Add `sqlExpressions: "false"` to the `grafana.ini.feature_toggles` section of the
  values file (depends on 2). DoD: git diff shows the toggle line; Helm lint passes.

- [ ] 4. Commit the change to a branch and open a PR; ArgoCD syncs after merge (depends on 3).
  DoD: ArgoCD Application shows `Synced`; Grafana pod logs confirm the toggle is inactive.

## Phase 2 — Version upgrade (depends on 4)

- [ ] 5. Select the patched image tag for the current Grafana minor line (see design.md mapping).
  DoD: target tag identified and noted in the PR description.

- [ ] 6. Update `image.tag` in the values file to the patched release; if Grafana is deployed
  in `labs`, verify available memory headroom before proceeding (depends on 5).
  DoD: image tag updated in git; if `labs` memory headroom is < 256 Mi, flag in PR and defer
  the `labs` upgrade.

- [ ] 7. Merge and monitor the ArgoCD rolling restart; validate datasources and dashboards
  post-upgrade (depends on 6).
  DoD: ArgoCD Application `Healthy`; at least one dashboard renders data correctly;
  Grafana `/api/health` returns `{"database":"ok"}`.

## Tests

- [ ] T1. As a Viewer-level user, attempt to use a SQL Expression in a panel — expect an error
  or the feature to be absent from the UI (Phase 1 validation).
- [ ] T2. Spot-check three existing dashboards for correct data rendering after Phase 1 config
  change.
- [ ] T3. After Phase 2 upgrade, confirm `curl -s https://<grafana-host>/api/health` returns
  `{"database":"ok","version":"12.x.x"}` where x.x is the patched release.
- [ ] T4. Confirm ArgoCD Application for Grafana shows `Healthy` and `Synced` after each phase.
- [ ] T5. If deployed in `labs`, confirm `kubectl top pods -n labs` shows memory usage within
  acceptable limits after the Phase 2 upgrade.

## Rollback

**Phase 1 rollback:** Revert the `grafana.ini` feature toggle commit; ArgoCD syncs back. This
re-enables `sqlExpressions` — apply only if dashboards are broken and the risk is accepted.

**Phase 2 rollback:** Revert the image tag commit; ArgoCD syncs to the previous image. If a
database schema migration ran, restore the Grafana database from the snapshot taken before the
upgrade. Snapshot command (SQLite): `kubectl exec -n admins <grafana-pod> -- sqlite3 /var/lib/grafana/grafana.db ".backup /tmp/grafana-pre-upgrade.db"` then `kubectl cp`.
