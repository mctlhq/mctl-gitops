# Design: incident-2932eaa0

## Diagnosis
No skill matched this alert type, so mctl-agent collected evidence but never
diagnosed it. Investigation shows the labs-mctl-telegram Deployment and its
synthetic canary CronJob are fully healthy for the entire window around and
after the alert (no errors, every 10-minute canary probe ok, every MCP tool
call ok) — this rules out the actual serving workload as the cause. The
separate labs-mctl-telegram-preview ArgoCD Application (a distinct, permanent
service, not an ephemeral preview — mctl_list_previews confirms zero tracked
ephemeral previews for this team/service) is independently reported Healthy,
ruling out cross-contamination from that stack too.

That leaves the resources declared in
`platform-gitops/services/labs/mctl-telegram/values.yaml` under
`extraObjects`. Most of them (the demo-session-refresh and
demo-reviewer-watch CronJobs) are gated behind
`renderIf: DEMO_REVIEWER_ENABLED == "true"`, which is currently `"false"`, so
they are pruned and cannot be the cause. One Job is NOT gated by any
renderIf and is unconditionally part of desired state on every sync:
`labs-mctl-telegram-local-mode-flip-1` (lines ~535-621). Its own comment block
documents that it is a one-shot migration ("move the pilot account to Local
Bridge mode") targeting Telegram account 8745115872, and that it is
deliberately written to fail loudly — "RETURNING plus an explicit emptiness
check makes a no-op UPDATE a failed Job in ArgoCD rather than a silent
'UPDATE 0'" — whenever that account has no active (non-revoked)
`telegram_accounts` row at apply time. account 8745115872 is the same
App-Directory demo/reviewer identity that other comments in this same file
describe as prone to session revocation (e.g. auto-triggered
`disconnect_telegram_account` calls) while `DEMO_REVIEWER_ENABLED` is off and
nobody is actively maintaining its session.

A Job that reaches BackoffLimitExceeded (backoffLimit: 2 here) is reported
Degraded by ArgoCD's default Job health check, and Application health is the
worst of all its resources' health — so one stuck failed Job is sufficient to
make the whole labs-mctl-telegram Application show Degraded while every
serving pod is fine. Because this Job has `ttlSecondsAfterFinished: 86400`
(24h) and no ArgoCD hook annotations, a failed run lingers as a Degraded
resource for up to 24 hours before Kubernetes garbage-collects it — consistent
with the sustained, multi-hour Degraded window seen here across two
independent, unrelated deploys.

By contrast, the sibling file `vault-cleanup.yaml` in the same directory shows
the established pattern for one-shot/lifecycle Jobs in this repo: it is
annotated as an ArgoCD hook with `hook-delete-policy: HookSucceeded` so it
never lingers as a plain resource. `labs-mctl-telegram-local-mode-flip-1` was
never given the same treatment.

## Confidence: LOW
This is a strong circumstantial inference from the gitops config, the
observed Application-vs-workload health split, and the Job's own documented
failure semantics — but it was not possible to directly query the Job's live
Kubernetes status/conditions (no kubectl/ArgoCD resource-tree access from
this agent) to confirm it is in fact the specific resource ArgoCD is counting
as Degraded. The implementer should confirm via `kubectl -n labs get job
labs-mctl-telegram-local-mode-flip-1 -o yaml` (or the ArgoCD UI resource tree
for the labs-mctl-telegram Application) before/while applying the fix.

## Proposed Fix
File: `platform-gitops/services/labs/mctl-telegram/values.yaml`
Job block: `extraObjects[].metadata.name: labs-mctl-telegram-local-mode-flip-1`
(currently at approximately lines 535-621).

Add ArgoCD hook annotations to this Job's `metadata`, matching the existing
convention already used in this directory's `vault-cleanup.yaml`, so a
finished run (success OR failure) is deleted immediately instead of lingering
for up to 24h and dragging down Application health:

Current:
```yaml
  - apiVersion: batch/v1
    kind: Job
    metadata:
      name: labs-mctl-telegram-local-mode-flip-1
      labels:
        app.kubernetes.io/name: mctl-telegram
        app.kubernetes.io/part-of: mctl-platform
        mctl.me/component: local-mode-flip
```

New:
```yaml
  - apiVersion: batch/v1
    kind: Job
    metadata:
      name: labs-mctl-telegram-local-mode-flip-1
      annotations:
        argocd.argoproj.io/hook: PostSync
        argocd.argoproj.io/hook-delete-policy: HookSucceeded,HookFailed
      labels:
        app.kubernetes.io/name: mctl-telegram
        app.kubernetes.io/part-of: mctl-platform
        mctl.me/component: local-mode-flip
```

If the implementer confirms (via kubectl/ArgoCD UI) that this Job is
currently sitting Failed, also delete the existing stuck Job object directly
(`kubectl -n labs delete job labs-mctl-telegram-local-mode-flip-1`) so the
Application returns to Healthy immediately rather than waiting up to 24h for
the TTL controller, and so the next sync can re-create it under the new hook
semantics.

## Scope
Minimal. Only touches this one Job's metadata (adds annotations); no change
to its command, target account, or any other resource in the file.
