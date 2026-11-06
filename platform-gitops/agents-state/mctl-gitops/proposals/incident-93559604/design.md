# Design: incident-93559604

## Diagnosis
The implement workflow for the mctl-telegram proposal issue-1097 did not fail from an infrastructure fault. The implementer read the accepted proposal (12 tasks: a new nested Go module with whatsmeow, about eight internal packages, 14 offline tests, CI workflow, runbook, report, plus a live checklist needing a human to pair a WhatsApp account), judged it too large for a single run, and exited without commits. The workflow then reported "implementer produced no commits" and the status projection moved the proposal to needs-triage. No skill matched because this is a proposal-sizing problem, not a platform fault. The log also showed a lifecycle-claim rejection (epoch=0 acquire) that did not block the run.

## Proposed Fix
No platform configuration or code change is indicated by the evidence. The remedy is a human decision on the source proposal: split mctl-telegram/issue-1097-spike-reply-to-personal-whatsapp-dms-and into smaller proposals, as suggested by the implementer (tasks 1-5 scaffold/store/clients; tasks 6-9 bridge, CLI, fixtures; tasks 10-12 CI, runbook, report). That proposal lives under platform-gitops/agents-state/mctl-telegram/proposals/ and is owned by the issue author, so this responder does not rewrite it.

Do not retry the original proposal automatically; an unchanged retry would fail the same way.

## Confidence: LOW
The cause is clear from the implementer's own output, but the correct action is a product decision and not a verified platform fix. Verify the current state of the source proposal's .status.yaml before touching anything.

## Scope
Minimal. If the source proposal's .status.yaml is already needs-triage and no split exists, make no file changes and record that in the PR description or close the task as no-op.
