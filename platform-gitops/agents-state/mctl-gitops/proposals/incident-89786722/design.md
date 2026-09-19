# Design: incident-89786722

## Confidence: LOW

## Diagnosis
mctl-agents-implement-41ec04ae (implementer run for mctlhq/mctl-gitops
issue-1178) was submitted at 2026-09-19T00:31:01Z as part of a burst of six
implement workflows submitted within about two minutes of each other
(00:29:38-00:31:33), right after a burst of dev-loop approvals
(00:28:05-00:28:15). Its workflow log archive contains only the
notify-telegram exit step; no run-implementer log was ever produced — the
signature of a pod that stayed Pending (unschedulable) rather than one that
ran and failed with an application error, which is also why no auto-fix
skill matched.

At the same time, an earlier implement run — mctl-agents-implement-0eaa9853
(issue-438, see incident-89786271), submitted at 00:12:31Z — had already been
running for over an hour and went on to hang for a further hour without
completing, holding a pod/ResourceQuota slot in the shared "admins" namespace
for the entire window this workflow needed to schedule. The "admins"
namespace ResourceQuota is narrow (requests.cpu=2, requests.memory=3Gi,
pods=12, shared with always-on worker/worker-exec pods), so the burst of five
new implement pods most likely found no scheduling headroom and sat Pending
until the workflow-level timeout (8857.716750s, ~2h27m) finally failed this
one.

I could not read the mctl-agents-implement WorkflowTemplate/CronWorkflow
manifest in this gitops checkout (no read access from this run) to confirm
the exact timeout field and its current value, so the ~9500s figure
referenced across these sibling incidents is inferred from observed failure
timing, not read directly from config.

## Proposed Fix
Same root cause and fix as incident-89786271: in the mctl-agents "implement"
Argo WorkflowTemplate/CronWorkflow definition (expected under something like
platform-gitops/services/admins/mctl-agents/*.yaml or a shared
WorkflowTemplate chart), reduce the step/workflow-level timeout that
currently allows a run to occupy a pod slot for ~8800-9500s down to roughly
1200-1800s (20-30 minutes) — for example `activeDeadlineSeconds: 1800` on
the run-implementer template, or the equivalent `timeout:` field. Current
value: ~9500s (inferred, not confirmed). New value: 1800s.

A short timeout makes an unschedulable or hung implementer pod fail fast,
freeing its ResourceQuota slot instead of blocking the "admins" namespace for
over two hours before the failure is visible. Apply this once (via
incident-89786271 or whichever proposal lands first) — the other sibling
proposals in this batch describe the same fix and do not need a second edit.

## Scope
Minimal. Only touch the single timeout field controlling how long a
mctl-agents-implement run-implementer step is allowed to run before Argo
kills it. Do not change ResourceQuota sizing or concurrency limits here.
