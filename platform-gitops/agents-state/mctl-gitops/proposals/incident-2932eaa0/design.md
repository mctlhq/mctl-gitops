# Design: incident-2932eaa0

## Diagnosis
The ArgoCD Application `labs-mctl-telegram` has reported health=Degraded /
syncStatus=Synced continuously since at least 2026-09-28T23:31-23:58Z (per two
independent `mctl-agents-shepherd` runs that observed it "newly Degraded" in
that window — see the sibling proposals for incidents
argo-mctl-agents-shepherd-744786f6-1790640590 and
argo-mctl-agents-shepherd-92f3bc8a-1790639911) through at least
2026-09-29T01:10:00Z, i.e. well over an hour.

However, the workload that actually serves traffic is healthy the whole time:
the canary CronJob (`*/10 * * * *`) and the base-service pod
(`labs-mctl-telegram-base-service-5c945f9444-4qslh`, stable pod identity
across the whole window — no restarts) both report successful probes and MCP
tool calls at every sample point from 00:50 to 01:10 UTC. No skill matched
this ticket in mctl-agent (escalated with an empty diagnostic rule), and no
error/warning lines for the main workload were found in Loki.

`syncStatus=Synced` with `health=Degraded` and an otherwise-healthy Deployment
means a DIFFERENT resource tracked by this Application is unhealthy, not the
main Deployment/pods. The values file
(`platform-gitops/services/labs/mctl-telegram/values.yaml`) defines one
resource in `extraObjects` that both (a) can fail terminally and (b) would
produce no service-request log line: the one-shot `batch/v1 Job`
`labs-mctl-telegram-local-mode-flip-1` (lines ~535-621), which runs a single
SQL UPDATE to flip Telegram account `8745115872` into Local Bridge mode and
explicitly `exit 1`s if the target user or an active (non-revoked)
`telegram_accounts` row is missing. ArgoCD reports a Job Degraded once it
exhausts `backoffLimit` (2 here) without succeeding, and that stays Degraded
until `ttlSecondsAfterFinished` (86400s / 24h) elapses and the Job is pruned —
which matches an outage that has now lasted over an hour with zero customer
impact.

This is the leading hypothesis, not a confirmed one: this agent has no
kubectl/ArgoCD-resource-tree access, so the Job's actual pod status/events
could not be inspected directly. The same values.yaml file documents an
extensive, ongoing history of Telegram session-revocation issues for exactly
this class of account (reviewer/demo session drops), which is consistent
with — but does not prove — the Job's precondition failing.

## Confidence: LOW
Verify which resource ArgoCD is actually reporting as Degraded (ArgoCD UI
resource tree for Application `labs-mctl-telegram`, or
`kubectl -n labs describe job labs-mctl-telegram-local-mode-flip-1`) before
applying the fix below. If a different resource is the actual cause, this
proposal does not apply — capture the real cause and re-diagnose.

## Proposed Fix
In `platform-gitops/services/labs/mctl-telegram/values.yaml`, remove the
`labs-mctl-telegram-local-mode-flip-1` Job block from `extraObjects` (the
whole `- apiVersion: batch/v1 / kind: Job / metadata.name:
labs-mctl-telegram-local-mode-flip-1` entry and its trailing comment). A
`Job`'s `metadata.name` is immutable, so ArgoCD cannot "retry" a failed run by
resyncing the same manifest — leaving it in place only keeps the exhausted Job
(and the Application's health) red for up to 24h. If the underlying account
flip still needs to happen, redo it as a new Job with an incremented name
(e.g. `labs-mctl-telegram-local-mode-flip-2`) once the precondition it failed
on is independently confirmed fixed (an active, non-revoked
`telegram_accounts` row for TG_ID 8745115872).

## Scope
Minimal. Only the one confirmed-failing resource is touched, and only after
the verification step above confirms it is in fact the Degraded resource.
