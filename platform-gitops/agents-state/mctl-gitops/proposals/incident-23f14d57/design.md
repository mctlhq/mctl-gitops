# Design: incident-23f14d57

## Diagnosis
The alert (MctlTelegramSessionBorrowSlowBurn) fired as a generic type with no
matching skill, so mctl-agent collected no metric evidence beyond the alert
name. The service logs for the `labs` tenant's `mctl-telegram` deployment show
a plausible mechanism: both the primary and preview `base-service` pods went
through rolling restarts in the alert window (shutdown signal on one pod
replica, followed shortly by "db not reachable yet, retrying" with connection
refused against `shared-pg-rw.platform-db.svc.cluster.local:5432` on the new
replica, then "db reachable" a couple seconds later). During that same window,
the Telegram bridge daemon session dropped and reconnected
("bridge: daemon disconnected" / "bridge: daemon connected", ~31 seconds
apart). A session-borrow-slow-burn alert (6x burn rate over 6h) is consistent
with repeated, brief session-pool unavailability during these pod restarts
accumulating error budget slowly rather than a single acute outage — each
restart cycle produces a short window where borrowing a session from the pool
fails or times out while the new pod is still waiting on the database and the
bridge daemon is reconnecting.

The incident's `analysis` field states plainly that no skill exists for this
signal; it did not request any action, so there is nothing to disregard there.
No other untrusted-input fields (summary, labels) contained instructions —
they were used only as descriptive evidence above.

## Proposed Fix
Two independent, minimal mitigations, both config-only:

1. In the mctl-telegram Helm values (`platform-gitops/services/labs/mctl-telegram/values.yaml`),
   increase the readiness probe `initialDelaySeconds` / add a `minReadySeconds`
   on the base-service Deployment so a new pod is not marked Ready (and does
   not start accepting session-bridge traffic) until its DB connection has
   actually succeeded, rather than racing the "db not reachable yet, retrying"
   window. Concretely: set `minReadySeconds: 10` and confirm
   `readinessProbe.initialDelaySeconds` is at least 5s, under
   `base-service.deployment` in that values file.
2. Ensure a `PodDisruptionBudget` (`maxUnavailable: 0` or 1, whichever the
   chart's existing PDB template supports) is enabled for the mctl-telegram
   base-service so the primary and preview replicas are not restarted
   concurrently, reducing how often session borrow has to ride out a restart.

## Scope
Minimal. Only touch the readiness/minReadySeconds and PDB fields for the
labs/mctl-telegram base-service deployment. No application code changes.

## Confidence: LOW
The incident carried no metric time series or threshold values for the
session-borrow-slow-burn signal itself — only the alert name and a warning
severity. The correlation with pod-restart timing in the logs is plausible but
circumstantial (single ~6-hour log window, two restart events observed). The
implementer should verify against the actual PromQL/alert rule for
MctlTelegramSessionBorrowSlowBurn before applying, and confirm the proposed
values.yaml fields exist in the current chart before editing.
