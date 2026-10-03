# Design: portal-log-pipeline-gap

## Current state
Per `context/architecture.md`, mctl-portal's observability stack is
Prometheus/Loki/Grafana, exposed inside the portal via a custom `observability`
plugin (explicitly protected — must not be removed). Service logs for mctl-portal in
`admins` are queried via `mctl_get_service_logs`, which has returned 0 lines for two
consecutive daily research cycles (2026-09-05, 2026-09-12) despite the service being
reported Healthy/Synced (ArgoCD revision `2.6.3`, unchanged across both cycles) and
despite no open incidents (`mctl_list_incidents` returns count=0). Resource usage in
`admins` is flat and unremarkable across the same window, which argues against an
OOM/crash-loop explanation and toward a pipeline or query-side gap.

## Proposed solution
Treat this as a staged investigation followed by a targeted fix, rather than a single
code change, since the root cause is not yet known:

1. **Reproduce with known traffic.** Generate a controlled request against
   mctl-portal (e.g., a manual login, a scaffolder action) and immediately query
   `mctl_get_service_logs` for that window, to rule out "logs exist but query window
   is wrong."
2. **Check application-side log emission.** Verify the Backstage backend's configured
   log level and output stream (stdout/stderr vs. file) inside the running pod, since
   Backstage backends default to structured logging that must be captured by the
   node's log driver to reach the shipper.
3. **Check the shipper/agent.** Verify whether the log-shipping agent (e.g.,
   Promtail or equivalent, depending on the platform's Loki setup) is running on the
   node(s) hosting mctl-portal pods and is correctly scraping/labeling this
   workload's logs.
4. **Check Loki-side storage/retention and label matching.** Confirm the Loki query
   used by `mctl_get_service_logs` targets the correct labels (namespace, tenant,
   service name) — this ties into the same metadata-gap family as the ArgoCD
   `service` field being null (see `argocd-service-field-gap`); a mislabeled or
   missing `service` label could independently explain both symptoms.
5. **Apply the fix** at whichever layer is identified, and validate with a repeat of
   step 1.

Given the possible overlap with the ArgoCD `service`-field gap (both are metadata/
labeling issues touching the same service identity), the investigation in step 4
should explicitly check whether fixing `argocd-service-field-gap` first resolves or
narrows this issue.

## Alternatives
- **Assume it's a benign query artifact and drop it** — rejected: it has now
  persisted for two consecutive cycles with a Healthy/Synced service, which is a
  pattern, not noise; ignoring it risks a real blind spot during an incident.
- **Immediately increase log verbosity across the board without diagnosis** —
  rejected: could increase log volume/cost without addressing the actual break, and
  risks masking the real root cause (e.g., if the shipper is down, more verbose logs
  still won't arrive).
- **Replace the logging pipeline entirely (new backend/vendor)** — rejected as
  disproportionate; no evidence yet that Loki itself is at fault versus a
  configuration or labeling gap, and a wholesale replacement is out of scope per the
  architecture's existing Prometheus/Loki/Grafana investment.

## Platform impact
- **Migrations:** None expected. If the fix is a shipper/agent config change, it is a
  configuration update, not a data migration.
- **Backward compatibility:** No impact on existing portal functionality; this is an
  observability-only change.
- **Resource impact (especially `labs`):** mctl-portal runs only in `admins`; `labs`
  is unaffected. If the fix involves raising log verbosity, monitor `admins` log
  volume/storage impact, but no change to `labs` resource usage is anticipated.
- **Risks and mitigations:**
  - *Risk:* the investigation surfaces a genuinely broken shipper affecting other
    services in `admins` too, widening scope beyond mctl-portal.
    *Mitigation:* if discovered, immediately flag to the platform/gitops owner as a
    tenant-wide issue rather than silently scoping the fix to mctl-portal only.
  - *Risk:* changing log level/output in production masks or loses logs during the
    transition.
    *Mitigation:* validate any config change in a lower environment first, per the
    WHILE-clause in requirements.md.
