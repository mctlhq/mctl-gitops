# Tasks: loki-ruler-path-traversal

- [ ] 1. Confirm the current Loki version deployed in the cluster — DoD: The running Loki image tag is documented (e.g., via `kubectl get deployment/statefulset loki -n <loki-namespace> -o jsonpath='{.spec.template.spec.containers[0].image}'`). The version is confirmed to be below v3.7.1 and therefore affected by CVE-2026-21726. The Loki namespace and deployment name are recorded for use in subsequent tasks.

- [ ] 2. Check current `labs` Loki pod memory usage (depends on 1) — DoD: If Loki runs in the `labs` tenant (which is near its memory limit), current memory usage of Loki pods is retrieved (e.g., via `kubectl top pods -n labs`). If usage exceeds 80% of the configured memory limit, a capacity review is initiated before proceeding and this task is marked blocked. If usage is within safe bounds, the task is marked complete and the rollout may proceed.

- [ ] 3. Update the Loki image tag in the GitOps repository (depends on 2) — DoD: The `loki.image.tag` value (or equivalent) in the Helm values file under `platform-gitops/services/<tenant>/loki/` is updated to `v3.7.1`. If the Loki Ruler is deployed as a separate component (e.g., `loki-ruler` subchart), its image tag is updated in the same commit. The commit message references CVE-2026-21726. PR is opened and approved by a second engineer.

- [ ] 4. Merge and verify the Loki rolling update (depends on 3) — DoD: The PR is merged. ArgoCD detects the diff and triggers a rolling update of Loki pods. All Loki pods report `Running` and `Ready` with the v3.7.1 image. No pods remain on the old image tag (`kubectl get pods -n <loki-namespace> -o jsonpath='{.items[*].spec.containers[0].image}'` shows only v3.7.1).

- [ ] 5. Verify log ingestion and query functionality (depends on 4) — DoD: At least one log stream is successfully ingested into Loki and a LogQL query returns results from the last 5 minutes via the Loki API or Grafana data source. Both `admins` and `labs` tenant log pipelines are confirmed operational.

- [ ] 6. Document resolution in decisions/ ADR (depends on 5) — DoD: A new ADR entry under `context/decisions/` records the version pin, the CVE reference (CVE-2026-21726), the date of remediation, and notes any `labs` memory observations from task 2.

## Tests

- [ ] T1. Path traversal rejection test: Send an unauthenticated HTTP GET request to the Loki Ruler API with a double-URL-encoded path traversal in the namespace parameter (e.g., `GET /loki/api/v1/rules/..%252F..%252Fetc%252Fpasswd`). Confirm the response is an HTTP 4xx error and does not contain file system content. Expected result: HTTP 400 or 403, no file data in response body.

- [ ] T2. Log ingestion smoke test: Push a test log line via the Loki push API (`POST /loki/api/v1/push`) for a test stream label and confirm it is retrievable via a query (`GET /loki/api/v1/query_range`). Run for both `admins` and `labs` tenants if Loki serves both.

- [ ] T3. Grafana data source connectivity: Open the Grafana UI and confirm the Loki data source shows `Data source connected and labels found`. Run a simple Explore query and confirm results are returned within 10 seconds.

- [ ] T4. Version confirmation: Query the Loki `/loki/api/v1/status/buildinfo` endpoint and confirm the version field reports `3.7.1`. Record the output in the PR comments.

- [ ] T5. `labs` memory check post-rollout: If Loki runs in `labs`, query `kubectl top pods -n labs` after the rollout completes and confirm memory usage has not increased materially (more than 10% over pre-upgrade baseline). If usage has increased, open a capacity review issue.

## Rollback
If the Loki rollout introduces a regression (pods fail readiness, log ingestion breaks, queries return errors):

1. Revert the image tag commit in the GitOps repository to the previous Loki version tag and merge to the default branch.
2. ArgoCD detects the revert and triggers a rolling update back to the previous image.
3. Monitor pod readiness and confirm log ingestion resumes before declaring rollback complete.
4. If the ArgoCD sync loop is degraded, use `kubectl set image statefulset/loki loki=grafana/loki:<previous-tag> -n <loki-namespace>` as an out-of-band emergency rollback.
5. If the `labs` tenant experienced an OOMKill during the rollout, check whether memory limits need to be adjusted before re-attempting the upgrade, and open a capacity review issue.
6. Open a new incident ticket referencing the regression before attempting any subsequent upgrade attempt.
