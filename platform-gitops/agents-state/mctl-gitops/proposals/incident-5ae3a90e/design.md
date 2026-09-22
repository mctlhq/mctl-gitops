# Design: incident-5ae3a90e

## Confidence: LOW

## Diagnosis
`labs-mctl-telegram` is reported Degraded by ArgoCD (syncStatus stays Synced —
this is a resource-health problem, not drift). The main service is healthy
throughout: base-service MCP tool calls and the 10-minute canary CronJob both
succeed continuously before, during and after the alert window. The actual
unhealthy resource is a separate one-shot Job defined in
`platform-gitops/services/labs/mctl-telegram/values.yaml` under
`extraObjects`: `labs-mctl-telegram-local-mode-flip-1`. It ran on the last
sync, failed twice (`backoffLimit: 2`) at 2026-09-21T23:51:20Z with
`psql: error: connection ... port 5432 failed: Connection refused` against
`shared-pg-rw.platform-db.svc.cluster.local`, and reached a terminal Failed
state. That Job carries no `argocd.argoproj.io/hook` annotation, so ArgoCD
tracks it as an ordinary managed resource; its Job health check reports
Degraded for a Failed Job, and that propagates to the whole Application,
which is what the `ArgoCDApplicationDegraded` alert (and, independently, the
`mctl-agents-shepherd-1790033940` post-deploy-verify gate) observed.

The "Connection refused" is most likely a short-lived blip against the shared
Postgres (the same host/credentials the long-lived service pods and the
canary use worked without interruption immediately before and after this
Job's two attempts), rather than a lasting outage or a NetworkPolicy that
specifically blocks Job pods — but this responder has no direct visibility
into the shared-pg-rw pod's own status/events to confirm that, hence LOW
confidence.

This Job also has real side effects outside Kubernetes: on success it flips
one specific Telegram account's `telegram_accounts.mode` to `'local'`
(see the long comment above the Job in values.yaml). A human should confirm
that retrying it is still desired before it runs again.

## Proposed Fix
In `platform-gitops/services/labs/mctl-telegram/values.yaml`, under
`extraObjects`, the `labs-mctl-telegram-local-mode-flip-1` Job:

1. Add ArgoCD hook annotations so a one-shot admin Job like this cannot pin
   the Application's health long-term the next time it (or something like
   it) fails:
   ```yaml
   metadata:
     name: labs-mctl-telegram-local-mode-flip-1
     annotations:
       argocd.argoproj.io/hook: Sync
       argocd.argoproj.io/hook-delete-policy: HookSucceeded,HookFailed
   ```
2. Separately, to clear the currently Failed execution: since Kubernetes Jobs
   are immutable, rename this entry to `labs-mctl-telegram-local-mode-flip-2`
   (following the existing `-1` suffix convention already in the resource
   name) so ArgoCD creates a fresh Job against the now-apparently-healthy
   database, rather than trying to patch the immutable, already-Failed `-1`
   Job in place.

Step 2 re-runs a Job with a real side effect (see Diagnosis). A human/the
implementer should verify this is still wanted — e.g. check whether the
account was already flipped by a prior, unlogged attempt — before assuming a
retry is correct. If not, the safer subset of this fix is step 1 alone plus
manually deleting the stuck `-1` Job out-of-band, which stops it from
blocking future Application health without re-running the side-effecting
command.

## Scope
Minimal: one `extraObjects` entry in one values.yaml file. No application
code change. No change to the shared Postgres or NetworkPolicies.
