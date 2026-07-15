# Design: incident-17840745

## Confidence: LOW

## Diagnosis

The `mctl-agents-run incident-responder` Argo Workflow has been failing deterministically
every 30 minutes since at least 00:18 UTC on 2026-07-15. This is the earliest in a run
of at least 5 consecutive failures (also see proposals incident-17840817, incident-17840799,
incident-17840781, incident-17840763). Each run crashes after 170-220 seconds (~3 minutes).
This incident at 00:18 UTC is the likely start of the regression.

Loki returned zero log lines for `admins/mctl-agents` over a 24-hour window. The Argo
Workflow UI at https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784074500
is the primary source for the exact failure reason.

Most likely root causes in rank order:

1. Token budget exhaustion: The incident-responder agent enforces a per-run Claude API
   budget (typically $2). If there are many `analyzing` incidents queued, the budget may
   be exhausted mid-run, causing the Argo step to exit non-zero after ~3 minutes.

2. MCP connectivity error: The mctl MCP server may be returning an unretried error that
   causes the Python workflow to raise an unhandled exception and exit 1.

3. Python runtime exception: An unhandled exception in the incident-responder workflow
   step.

4. OOMKilled: Less likely given the consistent timing.

The `workflow_failed` alert type has no pattern-matched skill, causing incidents to stay
in `analyzing` indefinitely.

## Proposed Fix

See primary proposal incident-17840817 for the full fix decision tree.

Implementer must first retrieve the actual failure reason from the Argo UI:
https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784074500

This is the earliest failure in the batch and may have additional context in the Argo UI
about what changed just before 00:18 UTC on 2026-07-15 (a deployment, config change,
or dependency update that triggered the regression).

## Scope

Minimal. Fix only the single root cause identified from the Argo Workflow logs. This
incident shares the same root cause as incident-17840817.
