# Tasks: cwe532-log-credential-sanitization

- [ ] 1. Identify active log-shipper — DoD: Confirmed whether the cluster DaemonSet agent is
  Fluentd, Vector, or another implementation; the relevant ConfigMap name and namespace are
  documented in the PR description.

- [ ] 2. Draft scrubbing transform configuration (depends on 1) — DoD: A ConfigMap patch is
  written (Fluentd `<filter>` stanza or Vector `remap` transform) implementing the three regex
  rules for `?password=`, `?token=`, and `Authorization:` across the admins, labs, and ovk
  namespaces; the patch is committed to mctl-gitops under the correct overlay path.

- [ ] 3. Deploy transform to admins namespace first (depends on 2) — DoD: ConfigMap applied and
  DaemonSet reloaded on admins; log lines from openclaw pods in admins no longer contain plaintext
  secrets in the forwarded backend; no gap in log forwarding observed.

- [ ] 4. Deploy transform to labs namespace (depends on 3) — DoD: Same verification as task 3 for
  labs; openclaw pod memory and CPU metrics in labs are unchanged (confirm via mctl metrics that
  the labs openclaw container is not affected by the DaemonSet-side work).

- [ ] 5. Deploy transform to ovk namespace (depends on 4) — DoD: Same verification as task 3 for
  ovk; s3-sync canary and restore-state probe remain green throughout; no application pod was
  restarted.

- [ ] 6. Assess and apply NetworkPolicy on log-aggregation backend (depends on 2, parallel with
  3-5) — DoD: Either a NetworkPolicy restricting ingress to the log backend is applied and
  validated, or existing policy is confirmed sufficient and that finding is documented.

- [ ] 7. Document retirement gate (depends on 5) — DoD: A comment or label is added to the
  ConfigMap patch referencing the `upgrade-to-2026-5-2` proposal; the retirement checklist
  (revert ConfigMap, reload DaemonSet, verify no logging gaps) is written into the
  upgrade-to-2026-5-2 task list.

## Tests

- [ ] T1. Synthetic credential injection — send a test HTTP request with a `?token=test-secret`
  query parameter to an openclaw pod in each of admins, labs, and ovk; confirm that the string
  `test-secret` does not appear in any log line forwarded to the backend (query the backend
  directly with a literal search for `test-secret`).

- [ ] T2. Authorization header redaction — send a test request with `Authorization: Bearer
  test-bearer-value` to a pod in each namespace; confirm `test-bearer-value` is absent from
  forwarded log lines.

- [ ] T3. Non-sensitive fields preserved — verify that for the same test requests, status code,
  HTTP method, URL path (without the sensitive parameter value), and timestamp fields are present
  and correct in forwarded log lines.

- [ ] T4. Multi-occurrence per line — craft a request that produces a log line containing both
  `?token=` and `Authorization:` in the same line (e.g., an internal redirect log); confirm both
  are redacted in the single forwarded line.

- [ ] T5. Labs resource baseline — before and after ConfigMap reload in labs, confirm via mctl
  metrics that openclaw container memory usage in the labs namespace is unchanged (DaemonSet-only
  change must not bleed into pod limits).

- [ ] T6. Log-forwarding continuity — during DaemonSet reload, confirm via backend query that no
  log lines from the openclaw pods are dropped (buffer flush is complete before reload takes
  effect).

- [ ] T7. s3-sync canary and restore-state probe health — after deploying the transform to ovk,
  confirm both the s3-sync canary and the restore-state readiness probe remain in a passing state
  with no flap.

- [ ] T8. Retirement smoke test — after the upgrade to openclaw 2026.5.2 is confirmed healthy,
  revert the ConfigMap patch and verify that the application's own redaction (now in 2026.5.2)
  continues to suppress `?password=`, `?token=`, and `Authorization:` values in forwarded lines.

## Rollback

If any step from tasks 3-5 produces an unexpected result (log forwarding gap, DaemonSet crash
loop, unexpected redaction of benign content, or any openclaw pod restart), roll back as follows:

1. Revert the ConfigMap change in mctl-gitops by reverting the relevant commit and pushing; ArgoCD
   will sync the previous ConfigMap within its normal reconciliation window (or trigger a manual
   sync).
2. Reload the DaemonSet agent by deleting its pods (`kubectl rollout restart daemonset/<name> -n
   <log-shipper-namespace>`); buffered events are re-flushed from node buffers on startup.
3. Confirm log forwarding resumes by tailing the backend for lines from openclaw pods.
4. openclaw application pods are NOT restarted at any point; the restore-state probe and s3-sync
   canary are unaffected by this rollback.
5. If the NetworkPolicy (task 6) caused connectivity issues between the DaemonSet agent and the
   backend, revert the NetworkPolicy manifest in the same PR revert and re-sync ArgoCD.
6. Open a follow-up ticket to diagnose the failure before re-attempting deployment.
