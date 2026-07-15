# Design: incident-argo-mct

## Confidence: LOW

Diagnosis is based on the Argo workflow event record only. No Loki logs were
available and the workflow audit entry was absent, so the exact failure step
is unknown. The implementer should inspect the Argo UI link in the incident
summary before applying any change.

## Diagnosis

The Argo workflow `mctl-agents-implement-1784072700` (the "implement all accepted"
implementer run) failed after approximately 585 seconds (~9.75 minutes). The
workflow is triggered by `mctl_trigger_implementer` and is responsible for:
1. Scanning accepted proposals under platform-gitops/agents-state/
2. For each proposal: cloning the target service repo, applying the code change,
   pushing a feature branch, and opening a GitHub PR.

The failure after ~585 s is consistent with one of three root causes (in
descending likelihood given the available evidence):

1. **GitHub API / auth failure mid-run**: A step that calls the GitHub API
   (gh clone, branch push, or PR creation) returned a non-zero exit code
   (expired token, rate-limit, or repo permission error), causing the Argo
   step to fail and the overall DAG to be marked Failed.

2. **Argo workflow activeDeadlineSeconds / step timeout**: The workflow
   template may have a per-step or global deadline shorter than the actual
   runtime needed for the number of accepted proposals queued. 585 s is just
   under 10 minutes; if `activeDeadlineSeconds: 600` is set in the workflow
   spec, the workflow would be killed near that boundary.

3. **OOMKilled or CPU throttle on an agent container**: The implementer
   sub-agent container hit its memory limit while the LLM was generating the
   code change, causing the pod to be evicted and the step to fail.

The skill matcher did not auto-resolve this incident (the incident remained in
`analyzing` for over 3 hours), which indicates no existing AlertManager rule
or skill handles `workflow_failed` for the mctl-agents service.

## Proposed Fix

**Primary action — investigate before patching:**

Visit the Argo UI link from the incident summary:
  https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-1784072700

Identify which step failed and the error message, then apply the matching fix
below:

**Fix A — GitHub auth/API error:**
- File: `platform-gitops/apps/mctl-agents/values.yaml` (or the relevant
  Secret / ExternalSecret manifest for the GitHub token)
- Check that the `GITHUB_TOKEN` / `MCTL_GITHUB_TOKEN` secret is not expired.
- Rotate the token in Vault at `secret/data/teams/admins/mctl-agents/github-token`
  and trigger a re-sync of the ExternalSecret.

**Fix B — Argo workflow timeout:**
- File: the WorkflowTemplate manifest in mctl-gitops that defines the
  implement workflow (likely
  `platform-gitops/argo-workflows/mctl-agents-implement.yaml` or equivalent).
- Current: `activeDeadlineSeconds: 600` (if set)
- New: `activeDeadlineSeconds: 1800` (30 minutes — accommodates up to ~5
  proposals at ~6 min each)

**Fix C — OOMKilled:**
- File: the WorkflowTemplate container spec (same file as Fix B).
- Current: `resources.limits.memory: 512Mi` (assumed)
- New: `resources.limits.memory: 1Gi`

## Scope

Minimal. Only touch the single field that matches the observed failure mode
confirmed in the Argo UI. Do not change unrelated workflow templates.
