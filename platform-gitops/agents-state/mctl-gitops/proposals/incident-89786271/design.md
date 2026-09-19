# Design: incident-89786271

## Confidence: LOW

## Diagnosis
mctl-agents-implement-0eaa9853 (implementer run for mctlhq/mctl-telegram
issue-438) was submitted at 2026-09-19T00:12:31Z. Its run-implementer step
did start and produced a substantial transcript (~795KB), but transcript
growth stopped around 02:12:32Z with no final result/completion message ever
recorded — the implementer session hung. The Argo Workflow itself was not
marked failed until 02:51:11Z, 9516.365s (~2h38m) after submission and ~39
minutes after the transcript had already gone silent. No auto-fix skill
matched because there is no application error to match against: this is a
hung process plus an overly generous outer timeout, not an exception.

The same ~2.3-2.6 hour delay-before-failure pattern shows up on five sibling
implement workflows submitted 00:29:38-00:31:33 (shortly after a burst of six
dev-loop approvals at 00:28:05-00:28:15), except those never logged a single
byte from run-implementer at all — the signature of a pod that stayed
Pending rather than one that ran and errored. The most likely mechanism: this
workflow's implementer pod held resources in the shared "admins" namespace
for over two hours while hung, leaving no ResourceQuota headroom for the
burst of newly-submitted implement pods to schedule, so they sat Pending
until the same long per-workflow timeout finally killed them too.

I could not read the mctl-agents-implement WorkflowTemplate/CronWorkflow
manifest in this gitops checkout (no read access from this run) to confirm
the exact timeout field and its current value, so the current ~9500s figure
below is inferred from observed failure timing, not read directly from
config. Treat the field path as a best-effort pointer for the implementer to
verify before editing.

## Proposed Fix
In the mctl-agents "implement" Argo WorkflowTemplate/CronWorkflow definition
(expected under something like
platform-gitops/services/admins/mctl-agents/*.yaml or a shared
WorkflowTemplate chart), reduce the step/workflow-level timeout that is
currently allowing an implement run to occupy a pod slot for roughly 9500s
(~2h38m) down to something in the 1200-1800s (20-30 minute) range — for
example an `activeDeadlineSeconds: 1800` on the run-implementer template, or
the equivalent `timeout:` field if the CronWorkflow sets it centrally.
Current value: ~9500s (inferred, not confirmed). New value: 1800s (30
minutes), or whatever the team's target implementer runtime SLA already is,
if lower.

This makes a hung or unschedulable implementer pod fail fast and free its
ResourceQuota slot for queued work, instead of blocking the "admins"
namespace for over two hours before the failure is even visible.

## Scope
Minimal. Only touch the single timeout field controlling how long a
mctl-agents-implement run-implementer step is allowed to run before Argo
kills it. Do not change ResourceQuota sizing or concurrency limits here —
verify need for that separately if timeout tightening alone does not resolve
recurring starvation.
