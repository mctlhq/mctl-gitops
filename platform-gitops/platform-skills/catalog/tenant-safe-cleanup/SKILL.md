---
name: tenant-safe-cleanup
description: Safely retire services and delete tenants in mctl without leaving namespace, database, Vault, or ArgoCD fallout behind. Use when removing a tenant, debugging failed retire/delete workflows, cleaning post-delete drift, or preventing shared-pg and root-app degradation after tenant cleanup.
---

# Tenant Safe Cleanup

Treat tenant deletion as orchestration, not as a blind namespace delete.

Use this skill to make sure service retirement, shared resource cleanup, and tenant removal happen in the correct order and leave Argo healthy.

## Required Order

Follow this order unless you have a strong reason not to:

1. inventory tenant services
2. retire each service
3. wait for retire workflows to finish
4. clean shared resources that do not live in the tenant namespace
5. delete tenant GitOps and namespace
6. verify post-delete health

Do not delete the tenant namespace first.

## Core Workflow

### 1. Inspect current state

Check:

- tenant services under `platform-gitops/services/<tenant>/`
- Argo apps for the tenant and shared dependencies
- shared resources in namespaces like `platform-db`
- failed or partial workflows in `argo-workflows`

### 2. Prefer `delete-tenant-safe`

Use the orchestrated workflow path rather than direct tenant deletion.

- `retire-service` should remain visible in the tenant namespace for ordinary service removal.
- `delete-tenant-safe` should run from `argo-workflows`, retire all services, wait, clean shared fallout, then remove the tenant.
- In this repo the fast path also eager-prunes Argo app CRs and waits explicitly for service app, tenant app, and namespace disappearance.

### 3. Clean shared fallout explicitly

Assume some tenant-owned resources live outside the tenant namespace.

In this repo the critical shared path is:

- `platform-gitops/infra-components/data/cnpg/shared`

Look for tenant-owned leftovers such as:

- `Database` CRs
- `ExternalSecret` DB credentials
- managed roles
- `pg_hba` entries

### 4. Verify after deletion

At the end verify:

1. tenant namespace is gone if deletion was intended
2. no tenant-owned shared DB artifacts remain
3. `shared-pg` is not degraded by the cleanup
4. `root-app` is not degraded by the cleanup

## High-Value Rules

- Block unsafe tenant deletion if services still exist and orchestration is unavailable.
- Prefer fail-closed behavior over “wait and hope”.
- If stale live resources remain after Git cleanup, delete only the confirmed leftovers.
- Distinguish tenant-fallout from unrelated platform incidents before broad remediation.
- Verify deletion with all four markers, not just API `404`:
  - service app CR gone
  - tenant app CR gone
  - namespace gone
  - tenant API returns `404`
- Treat `kubectl get ...` failures as success only when they are real `NotFound` results. Do not let generic command failures masquerade as cleanup success.
- If delete speed matters, remember the two platform levers that materially affect it:
  - eager prune inside `delete-tenant-safe`
  - short ApplicationSet git poll interval (the repo now uses `requeueAfterSeconds: 30` for `apps` and `tenants`)

## When To Use Live Cleanup

Use live cleanup only for:

- stale DB artifacts already removed from GitOps
- broken workflows or pods left after an incident
- corrupted CRs that Argo should recreate cleanly

Keep the durable fix in GitOps or workflow logic whenever the issue can recur.

Read [references/cleanup.md](references/cleanup.md) for the exact patterns that were fixed in this repo.
