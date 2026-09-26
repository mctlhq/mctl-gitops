# Design: admins-tenant-resource-usage-anomaly

## Current state
Per `context/architecture.md`, mctl-portal runs in tenant `admins` on Kubernetes,
deployed via Docker → mctl-gitops → ArgoCD, with usage observed through the
Prometheus/Loki/Grafana stack (surfaced in-portal via the custom `observability`
plugin) and reported externally via mctl metrics tooling. Across the 2026-09-05,
-12, and -19 cycles, tenant `admins` reported ~67.5% CPU-limit and ~65% mem-limit
usage against a stable 10 CPU / 5Gi quota, with pod count steady at 7 of 12. On
2026-09-26, the same tenant reported 16.5% CPU-limit and ~30.7% mem-limit usage,
with pod count unchanged (still 7). ArgoCD reports `Healthy`/`Synced` at an unchanged
revision (`2.6.3`) for four consecutive cycles, and `mctl_list_incidents` returns no
open incidents. In the same set of cycles, `mctl_get_service_logs` for mctl-portal
has independently returned 0 lines for four consecutive cycles, which is already
tracked as an open, unresolved gap in `proposals/portal-log-pipeline-gap/`.

No single existing proposal covers unexplained resource-usage drops; this is a new
diagnostic gap sitting alongside two already-open metrics-integrity gaps
(`portal-log-pipeline-gap` and `argocd-service-field-gap`), all touching the same
service/tenant identity.

## Proposed solution
Treat this strictly as a staged investigation, not a fix, since three plausible and
materially different root causes exist and premature remediation risks acting on the
wrong one:

1. **Rule out a metrics-reporting artifact first.** Query the raw
   Prometheus/kube-state-metrics data for the `admins` namespace directly (bypassing
   whatever aggregation mctl metrics tooling applies) for both the 09-19 and 09-26
   windows, and compare against the reported tenant-level percentages. If raw and
   reported figures diverge, the anomaly is in the reporting/aggregation layer, not
   the workload itself — and this should be checked jointly with the
   `portal-log-pipeline-gap` investigation, since both symptoms could stem from the
   same broken label/scrape/query path against the `admins` namespace.
2. **Check workload health.** If raw metrics confirm the drop is real, inspect
   per-pod state in `admins`: restart counts, container `Last State` (e.g.,
   `OOMKilled`, `CrashLoopBackOff`), and per-pod CPU/mem usage trend across the four
   cycles. A crash-loop or repeated OOM-restart pattern can depress *average*
   resource usage even with a stable pod *count*, because a crashing container spends
   less wall-clock time actively consuming its limit.
3. **Check for a legitimate deploy/config change.** Even though ArgoCD's revision
   marker (`2.6.3`) is unchanged, check mctl-gitops history and any Argo Workflow
   provisioning activity in `admins` for the window between 09-19 and 09-26 for
   resource-request/limit edits, HPA target changes, or other tenant workloads
   (mctl-portal is one of several services in `admins`, per the 9/10 services figure)
   that scaled down independently of mctl-portal's own revision.
4. **Cross-reference `portal-log-pipeline-gap`.** That proposal's step 4 (Loki label
   matching) and this proposal's step 1 (raw metrics vs. reported) target the same
   underlying question — whether tenant/service labeling or a shared collector is
   broken for `admins`/mctl-portal. Run these checks together and share findings
   between the two proposals; if a shared root cause is found, consolidate the fix
   into whichever proposal is further along, and close the other as a duplicate with
   a cross-reference.
5. **Document and close.** Regardless of outcome, record the classification
   (legitimate change / workload health issue / pipeline defect) in this proposal's
   requirements.md acceptance criteria and open a follow-on proposal only if
   remediation work is needed — this proposal's own scope ends at diagnosis.

## Alternatives
- **Assume it is benign (workload rightsizing) and close without investigation** —
  rejected: a drop of this magnitude (CPU-limit usage falling by more than 4x) with
  no corresponding deploy event in ArgoCD's revision history is exactly the kind of
  signal that should not be dismissed, especially given the concurrent, unexplained
  logging gap on the same service.
- **Immediately treat it as a crash-loop and restart the affected pods** — rejected:
  premature; if the true cause is a metrics-pipeline defect (shared with
  `portal-log-pipeline-gap`), restarting healthy pods would not fix anything and
  could mask the real signal or cause unnecessary disruption to a `Healthy`/`Synced`
  service.
- **Fold this directly into `portal-log-pipeline-gap` as one investigation instead of
  a separate proposal** — considered, but rejected for now: the two symptoms
  (resource usage vs. log volume) are distinct enough, and the shared-cause
  hypothesis is not yet confirmed, that tracking them as two proposals with explicit
  cross-references keeps each one's scope and acceptance criteria clear; they can be
  merged later if step 4 above confirms a single root cause.

## Platform impact
- **Migrations:** None. This is a read-only diagnostic effort; no schema, config, or
  deployment changes are proposed here.
- **Backward compatibility:** No impact. No production behavior changes as part of
  this proposal.
- **Resource impact (especially `labs`):** None. mctl-portal and this investigation
  are scoped entirely to tenant `admins`; tenant `labs`' quota/usage change this
  cycle (a quota increase that eased its near-saturation) is unrelated and not
  touched by this work.
- **Risks and mitigations:**
  - *Risk:* the investigation concludes it is a crash-loop or OOM pattern that has
    been silently degrading mctl-portal availability without tripping an incident.
    *Mitigation:* per the acceptance criteria, immediately flag this as a
    service-health issue (separate from this diagnostic proposal) rather than
    treating the investigation as complete once identified.
  - *Risk:* the investigation confirms a shared root cause with
    `portal-log-pipeline-gap` but the two proposals drift out of sync (one gets fixed,
    the other doesn't, based on stale assumptions).
    *Mitigation:* explicit cross-reference in both proposals' documents (this one
    already references `portal-log-pipeline-gap`); whichever investigation
    concludes first should update the other before either is marked resolved.
  - *Risk:* over-investigating a benign metric fluctuation consumes effort
    disproportionate to impact.
    *Mitigation:* step 1 (raw metrics comparison) is a low-cost first check; if it
    shows the raw data matches the reported drop and step 3 finds a legitimate
    explanation (e.g., a sibling service's scale-down), the investigation should stop
    there rather than proceeding through all steps unconditionally.
