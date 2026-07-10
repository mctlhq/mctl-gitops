---
name: argocd-health-remediation
description: Diagnose and fix ArgoCD application incidents in mctl clusters. Use when an app is Degraded, OutOfSync, Progressing too long, blocked on sync errors, stuck on rollout, or showing misleading orphan/sync warnings. This skill is for tracing the concrete failing resource, applying the smallest safe GitOps or live-state fix, and verifying the app returns to Synced Healthy.
---

# ArgoCD Health Remediation

Inspect the live Argo app before editing anything.

1. Read app health, sync status, conditions, operation state, and per-resource status.
2. Identify the exact failing resource or controller condition.
3. Prefer the smallest fix that removes the real blocker.
4. Verify the affected app and any parent app return to `Synced Healthy`.

## Core Workflow

Use this sequence:

1. Inspect the app:
   - `kubectl -n argocd get app <name> -o yaml`
   - `kubectl -n argocd get app <name> -o jsonpath=...`
2. Check the concrete resource, not just Argo summary:
   - `kubectl -n <ns> get <kind> <name> -o yaml`
   - `kubectl -n <ns> describe <kind> <name>`
   - `kubectl get events -A --sort-by=.lastTimestamp | tail -n ...`
3. Decide whether the fix belongs in:
   - GitOps desired state
   - live drift cleanup
   - both
4. Apply the smallest safe fix.
5. Force a refresh or sync only after desired state is correct.
6. Re-check:
   - affected app
   - parent app such as `root-app`

## High-Value Patterns

### Deployment stuck on `ProgressDeadlineExceeded`

Do not assume a generic resource shortage. Inspect the workload shape.

- For single-instance workloads with one `ReadWriteOnce` PVC, `RollingUpdate` can deadlock rollout.
- If the new pod waits for the same PVC while the old pod is still running, switch the workload to `Recreate`.
- Re-check pod events after the strategy change; attach/detach lag can resolve a few seconds later without more changes.

### `ExternalSecret` or CR stuck on SSA / `metadata.managedFields must be nil`

Treat this as a broken live object, not a reason to weaken desired state.

1. Compare live object with rendered desired manifest.
2. If desired is already correct and the live object is stuck in bad server-side-apply state, delete only the broken resource and its generated dependent secret if needed.
3. Let Argo self-heal recreate it cleanly.

### App healthy but showing false orphan warnings

Check whether the app intentionally manages only namespace bootstrap resources while service workloads live in the same namespace.

- For tenant namespace apps in the `platform` project, service workloads can look orphaned even though they are expected.
- Fix the project-level orphan warning behavior instead of deleting live service resources.

### `OutOfSync` caused by stale live leftovers

If GitOps is already correct and only stale cluster objects remain:

1. Confirm the objects are no longer in desired state.
2. Delete only the stale live resources.
3. Re-check sync and health.

## Editing Rules

- Prefer GitOps fixes for durable configuration problems.
- Use live deletes only for stale or corrupted resources that GitOps should recreate or prune.
- Do not hide real drift with broad ignore rules when a concrete fix exists.
- If you add ignore rules, scope them narrowly to the specific CRD and fields.

## Verification

Always verify at the end:

1. target app is `Synced Healthy`
2. parent app is not degraded by the same issue
3. live resource state matches rendered intent

Read [references/checklist.md](references/checklist.md) when you need the exact incident patterns and commands used in this repo.
