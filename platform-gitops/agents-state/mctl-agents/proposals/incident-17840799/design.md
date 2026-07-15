# Design: incident-17840799

## Confidence: LOW

## Diagnosis

The `mctl-agents-run incident-responder` Argo Workflow has been failing deterministically
every 30 minutes since at least 00:18 UTC on 2026-07-15. This incident is one of at least
5 consecutive failures (also see proposals incident-17840817, incident-17840781,
incident-17840763, incident-17840745). Each run crashes after 170-220 seconds (~3 minutes).
This consistent crash window indicates a deterministic code or configuration defect, not
a transient infrastructure issue.

Loki returned zero log lines for `admins/mctl-agents` over a 24-hour window. The Argo
Workflow UI at https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784079900
is the primary source for the exact failure reason.

Most likely root causes in rank order:

1. Token budget exhaustion: The incident-responder agent enforces a per-run Claude API
   budget (typically $2). If there are many `analyzing` incidents queued and the agent
   performs numerous tool calls (list, get, logs, write, resolve per incident), the budget
   may be exhausted mid-run, causing the Argo step to exit non-zero after ~3 minutes.

2. MCP connectivity error: The mctl MCP server may be returning an unretried error (auth
   failure, tool not found, rate limit) that causes the Python workflow to raise an
   unhandled exception and exit 1.

3. Python runtime exception: An unhandled exception in the incident-responder workflow
   step (e.g. KeyError, AttributeError, or network timeout without retry).

4. OOMKilled: Less likely given the consistent timing.

The `workflow_failed` alert type has no pattern-matched skill, causing incidents to stay
in `analyzing` indefinitely.

## Proposed Fix

See primary proposal incident-17840817 for the full fix decision tree.

Implementer must first retrieve the actual failure reason from the Argo UI:
https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784079900

Apply the appropriate fix (budget, MCP error handling, Python exception, or OOM limit)
as described in incident-17840817/design.md.

## Scope

Minimal. Fix only the single root cause identified from the Argo Workflow logs. This
incident and incident-17840817 share the same root cause — a single fix should resolve
both.
