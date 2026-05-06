# Tasks: grafana-dos-patch

- [ ] 1. Confirm Grafana deployment existence and current version — DoD: A search of
  `platform-gitops/services/` and `platform-gitops/helm-charts/` for Grafana image
  references is complete. If no deployment is found, a PR is opened documenting the
  "not applicable" finding with the search commands used and their output; this proposal
  is closed. If a deployment is found, the tenant namespace, current image tag, and
  vulnerable/patched status are documented in a comment on this task (or in
  `platform-gitops/agents-state/grafana-dos-patch/deployment-check.md`).

- [ ] 2. Check `grafana-sql-rce-patch` execution status (depends on 1, only if deployment
  found) — DoD: The current running Grafana image tag is compared against the patched
  release table. The outcome is one of: (a) already patched — proceed to task 5; (b) not
  yet patched — proceed to task 3. The outcome is documented.

- [ ] 3. Record Grafana pod memory baseline if running in `labs` (depends on 2, only if
  upgrade required and Grafana is in `labs`) — DoD: `kubectl top pods` output (or equivalent
  Prometheus query) for the Grafana pod in `labs` is captured and committed to
  `platform-gitops/agents-state/grafana-dos-patch/labs-grafana-memory-baseline.txt`.
  Timestamp and current image tag are included.

- [ ] 4. Update Grafana image tag to patched release in values file (depends on 2 or 3)
  — DoD: The `image.tag` field in the Grafana `values.yaml` is updated to the target
  patched release (v12.1.10, v12.2.8, v12.3.6, v12.4.2, or v11.6.14 as appropriate per
  the design table). If `grafana-sql-rce-patch` Phase 2 has not been executed, this commit
  resolves both CVE-2026-27876 and CVE-2026-27880; the commit message references both
  proposal slugs. The PR is reviewed and merged. A Grafana database snapshot is taken
  before merging (see rollback section).

- [ ] 5. Verify ArgoCD Application health post-sync (depends on 4, or immediately after
  task 2 if already patched) — DoD: The ArgoCD Application for Grafana shows `Synced` and
  `Healthy`. `kubectl get pods -n <grafana-namespace>` shows the Grafana pod running the
  expected patched image tag. No `OOMKilled` events appear in `kubectl describe pod` for the
  Grafana pod within 10 minutes of restart.

- [ ] 6. Run smoke test for dashboard rendering (depends on 5) — DoD: The Grafana home
  dashboard loads without error. At least one data-source-backed panel renders data. No
  JavaScript console errors related to the upgrade are observed. This can be a manual check
  or an automated HTTP probe against the Grafana `/api/health` endpoint returning HTTP 200.

- [ ] 7. Measure and document memory delta for `labs` (depends on 5, only if Grafana is in
  `labs`) — DoD: Post-upgrade Grafana pod memory is recorded via `kubectl top pods` (or
  Prometheus) and committed to
  `platform-gitops/agents-state/grafana-dos-patch/labs-grafana-memory-post-upgrade.txt`.
  The delta versus task 3 baseline is computed. If the increase is greater than 20 percent
  or the `labs` namespace total would breach quota, this is flagged as a risk note in the
  PR and escalated to the platform team.

- [ ] 8. Document CVE closure (depends on 5, 6, 7) — DoD: A summary is committed to
  `platform-gitops/agents-state/grafana-dos-patch/closure.md` containing: the upgrade
  timestamp, the pre- and post-upgrade image tags, confirmation that CVE-2026-27880 is
  resolved by the patched release, and any memory delta findings from task 7.

## Tests

- [ ] T1. Grafana Application is `Synced` and `Healthy` in ArgoCD — run
  `argocd app get <grafana-app-name>` and assert `Sync Status: Synced` and
  `Health Status: Healthy`. Run within 10 minutes of pod stabilization.

- [ ] T2. Running image tag matches the expected patched release — run
  `kubectl get pod <grafana-pod> -n <namespace> -o jsonpath='{.spec.containers[0].image}'`
  and assert the tag is one of v12.1.10, v12.2.8, v12.3.6, v12.4.2, or v11.6.14.

- [ ] T3. No OOM events on Grafana pod post-upgrade — run `kubectl describe pod <grafana-pod>`
  and assert no `OOMKilled` reason appears in the `Last State` or `Events` sections within
  10 minutes of pod start.

- [ ] T4. Grafana `/api/health` returns HTTP 200 — curl or wget the Grafana health endpoint
  and assert a 200 response. This confirms the server is up and not in a crash loop caused
  by the upgrade.

- [ ] T5. `labs` namespace memory quota not breached (if applicable) — query total memory
  consumption for the `labs` namespace after the upgrade and assert it is below the tenant
  quota. If it breaches quota, this test fails and the issue must be resolved before the
  proposal is closed.

## Rollback

**If the upgrade has not yet been applied (tasks 1–3):** No rollback needed; the image tag
has not changed.

**If the image tag was updated but the ArgoCD sync has not yet completed:** Revert the
commit that updated the image tag. ArgoCD detects the revert on the next reconciliation
and restores the previous tag.

**If ArgoCD has synced and the Grafana pod has restarted on the new image but a regression
is detected (e.g., dashboard failure or crash loop):**

1. Revert the image tag commit in the repository. ArgoCD syncs back to the previous tag on
   the next reconciliation.
2. If the regression is a database schema migration failure (Grafana fails to start and logs
   show migration errors): restore the Grafana database from the snapshot taken in task 4
   before reverting the image tag, then revert the image tag.
3. If Grafana cannot be restored via the above steps, scale the Grafana Deployment to 0
   replicas temporarily (`kubectl scale deployment grafana --replicas=0 -n <namespace>`)
   to stop the crash loop, restore the database, revert the image tag, and then scale back
   up.

**If Grafana runs in `labs` and the upgrade causes OOM kills of other pods:** Scale the
Grafana Deployment to 0 replicas in `labs` immediately to release memory, then follow the
rollback steps above. Alert the `labs` team that Grafana is temporarily unavailable.
