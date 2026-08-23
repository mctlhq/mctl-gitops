# Design: incident-87504945

## Diagnosis
The mctl-agents service attempts to discover and reconcile proposal state in `/workdir/mctl-gitops/platform-gitops/agents-state`, but this directory does not exist. The reconciliation workflows (ReconcileWorkflow and IncidentLoopWorkflow) run on a 15-minute interval and consistently fail because they cannot find the required state directory. This prevents the incident responder, service agents, and shepherd from storing and managing proposal state, blocking the entire agent-driven development pipeline.

## Proposed Fix
Create the required directory structure in the mctl-gitops repository:

Directory path: `platform-gitops/agents-state/`

This directory must exist and be tracked in git so that all mctl-agents workflow pods can mount and access it as their shared state volume. The directory should be created with an initial .gitkeep file to ensure git tracks it.

## Scope
Minimal: only create the missing directory structure that mctl-agents expects. Do not add any proposal content yet—the directory just needs to exist and be committable to git.
