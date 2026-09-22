# Design: incident-5ae3a90e

## Diagnosis
No skill matched this alert type, so no automated rule exists for
"argocd_app_degraded" — that is why it escalated rather than being handled
inline. Independent evidence gathered here: the labs-mctl-telegram ArgoCD
Application reports health=Degraded / syncStatus=Synced as of 01:10Z, while
the running workload (base-service + the 10-minute synthetic canary) has been
serving requests and passing every probe throughout the same window, with no
application-level errors in its logs. That rules out the deployed
base-service/canary Deployment as the source of the Degraded status.

`platform-gitops/services/labs/mctl-telegram/values.yaml` declares a one-shot
`batch/v1 Job` named `labs-mctl-telegram-local-mode-flip-1` under
`extraObjects` (unconditional — no `renderIf` gate, unlike the two demo
CronJobs in the same file). Its own pod logs show it ran at 23:51:20Z, ~32
minutes before the incident's `created_at` (00:23:19Z) and close to when
AlertManager says the app first went Degraded (created_at minus the alert's
stated 30m duration puts the onset at roughly 23:53Z) — a plausible temporal
match. The first two pod attempts (backoffLimit: 2) failed with `psql: error:
connection to server at "shared-pg-rw.platform-db.svc.cluster.local"
... Connection refused` — a transient outage against the shared Postgres
cluster. The third attempt succeeded: it flipped `telegram_accounts` row 43
to `mode='local'` and printed the confirming `UPDATE 1` / row dump.

The Job therefore reached `status.succeeded=1` and is functionally complete,
but it also carries `status.failed=2` in its history, and its own code
comments confirm this was deliberate: "The RETURNING plus an explicit
emptiness check makes a no-op UPDATE a failed Job in ArgoCD rather than a
silent 'UPDATE 0'" — i.e. this Job's designed failure mode is specifically to
surface as ArgoCD Degraded. It has `ttlSecondsAfterFinished: 86400` (24h), so
it is still present in-cluster and still part of what ArgoCD evaluates for
this Application's health, well past the point where its one-time purpose
(the account-mode migration) was already accomplished and confirmed.

This is the best available candidate given the tools accessible here (no
kubectl/resource-tree access to directly confirm which specific object
ArgoCD's health aggregation is currently flagging as Degraded) — treat as
medium confidence, not certain.

## Proposed Fix
File: `platform-gitops/services/labs/mctl-telegram/values.yaml`

Remove the one-shot Job block and its dedicated explanatory comment (the
"One-shot: move the pilot account to Local Bridge mode." section through the
end of the Job spec — comment starting at the line `# One-shot: move the
pilot account to Local Bridge mode.` and the `- apiVersion: batch/v1` /
`kind: Job` / `metadata.name: labs-mctl-telegram-local-mode-flip-1` block
immediately after it, ending just before the next comment
`# labs-mctl-telegram-canary-rbac.yaml, which explains why at length.`) from
the `extraObjects:` list.

The migration this Job performed is already done and confirmed (row 43,
mode=local). Deleting the manifest is the git-reviewable equivalent of the
Job's own stated intent ("done through git so the decision is reviewable
rather than typed into a psql prompt") now that there is nothing left for it
to do, and it removes a completed-but-partially-failed resource from what
ArgoCD has to evaluate for this Application.

## Scope
Minimal. Only removes the single already-completed one-shot Job resource
(and its comment block) from this service's values.yaml. No other field,
env var, or resource in this file is touched.

## Confidence: MEDIUM
The temporal correlation (Job's failed attempts at 23:51:20-21Z vs. the
alert's implied Degraded-onset around 23:53Z) is strong, and the Job's own
comments confirm its failure mode is designed to read as ArgoCD-Degraded, but
this was not verified against the live Kubernetes resource tree (no kubectl
access from this agent). If ArgoCD is still Degraded after this change syncs,
the next escalation should widen the search to other resources owned by this
Application.
