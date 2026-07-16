# Design: incident-17841555

## Confidence: LOW

## Diagnosis
The `mctl-agents-incidents` cron workflow — the incident-responder's own scheduled
run — failed 20 times on 2026-07-15 across two separate windows (06:49-13:18 UTC and
20:29-22:47 UTC), with failure durations spread irregularly between ~104s and ~211s.
That irregularity rules out a single fixed `activeDeadlineSeconds` kill (compare the
near-identical ~8250.6s duration pattern in the sibling `shepherd` incident,
incident-17841348, which is a clear deadline signature); this looks instead like a
real, variable-length run that hit an error at different points each time — consistent
with contention on a shared resource (e.g. a git-write lock) rather than a hang.

No direct evidence (stack trace, error log) is available: Loki returns zero log lines
for mctl-agents/admins across a 24h window that covers every failure, and the Argo
Workflow audit record for same-day runs is already unqueryable ("not found in audit
log"). Both of these are themselves a diagnosability gap independent of the underlying
bug.

The one piece of live corroborating evidence is that a different mctl-agents operation
(`mctl-agents-implement`) was observed, at the time of this report, blocked waiting on
the `mctl-gitops-main-writes` Argo mutex ("Lock status: 0/1"). The incident-responder
also writes proposal/status files into the same `platform-gitops/agents-state/` tree
under version control, and very plausibly needs the same or a related mutex to do so
safely. If it acquires that mutex and the acquisition or the subsequent git write
fails/times out under contention, that would produce exactly the observed pattern:
a failure at a variable point in the run, with no distinguishing in-process log (since
logs are not even being retained), self-resolving once contention eases — which lines
up with runs on 2026-07-16 (05:45 and 06:15 UTC) both proceeding without failure.

This is inferred from timing and a live analog, not a captured error, so confidence is
LOW. It is possible the 2026-07-15 failures were caused by something unrelated (e.g. a
transient LLM API error, a since-fixed code bug in a prior image) that has already been
resolved by an intervening change; the implementer should verify current behavior
before assuming the mutex theory is the full story.

## Proposed Fix
1. Observability (do this regardless of the mutex theory): locate the Loki log-shipping
   configuration for mctl-agents workflow pods in this repo (promtail/Loki scrape
   config, or pod annotations, for the namespace these Argo Workflows run in) and
   confirm stdout/stderr is actually scraped and labeled `team=admins`,
   `app=mctl-agents` — `mctl_get_service_logs` currently returns 0 lines even across a
   24h window containing 20 failures, which should not happen if logging is wired up
   correctly. Also check the Argo Workflows archive/retention setting and extend it if
   same-day runs are already aging out of the audit log.
2. Resilience: find the CronWorkflow/WorkflowTemplate manifest for the
   `mctl-agents-incidents` operation (alongside the templates for
   `mctl-agents-implement` / `mctl-agents-shepherd` / `mctl-agents-issue-poll`
   referenced in sibling incidents). If its `synchronization` block acquires
   `mctl-gitops-main-writes` (or an equivalent mutex) before writing to the gitops
   tree, add a `retryStrategy` (e.g. 2-3 retries with backoff) around that
   step/template so transient contention causes a retry rather than an outright run
   failure. Unlike the `issue-poll` case (which does not need to write to gitops and
   had the mutex removed in incident-17841222), the incident-responder genuinely
   writes to gitops main and must keep the mutex — only add retry/backoff around it,
   do not remove it.
3. If, once the manifest is inspected, it turns out the incidents workflow does not use
   this mutex at all, treat this as primarily a "restore observability and monitor"
   fix: apply item 1, and note that the app-level failure may already be resolved
   (recent runs are succeeding) — do not speculatively change application logic with
   no supporting evidence.

## Scope
Minimal: (1) restore log/audit observability for mctl-agents workflow pods, and (2)
add a bounded retry around the gitops-write step of the `mctl-agents-incidents`
template only if it is confirmed to share the contended mutex. Do not modify the
`issue-poll`, `shepherd`, or `implement` templates — those are already tracked by their
own incidents/proposals (incident-17841222, incident-17841348, incident-argo-mct).
