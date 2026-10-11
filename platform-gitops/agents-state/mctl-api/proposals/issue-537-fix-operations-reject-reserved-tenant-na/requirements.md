# Reject reserved tenant names in create-tenant validation

## Context
The `create-tenant` operation in `internal/operations/registry.go` validates `tenant_name` only against the format pattern `^[a-z0-9][a-z0-9-]{1,62}$`. A name that collides with a platform namespace, such as `kube-system`, `argocd` or `vault`, passes API validation. The request is accepted and audited, and a workflow is submitted. The request only fails later, inside the Argo `validate` step. That step is `tenant_name_reserved` in `platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml`, added by mctl-gitops#1770. The caller gets a late, opaque failure, and the reserved-name defence rests on one layer.

This proposal adds the same reserved-name rule to the API. It is defined once, in `internal/operations`, and enforced on every path that creates a tenant: the REST generic execute handler, the MCP `mctl_create_tenant` tool (which goes through REST), and any direct caller of `operations.Executor.Submit`. Invalid requests are rejected with a clear validation error before anything is submitted.

## User stories
- AS a workspace creator I WANT a reserved name to be refused immediately with a clear reason SO THAT I can pick another name without waiting for a workflow failure.
- AS a platform operator I WANT the API and the WorkflowTemplate to enforce the same reserved-name rule SO THAT the protection of platform namespaces does not depend on a single layer.
- AS a maintainer I WANT the reserved list in one place with a pointer to its gitops source SO THAT the two copies can be kept in sync.

## Acceptance criteria (EARS)
- WHEN a `create-tenant` request has a `tenant_name` that exactly matches a reserved name (`argocd`, `argo-workflows`, `argo-events`, `kube-system`, `kube-public`, `kube-node-lease`, `default`, `cert-manager`, `traefik`, `vault`, `external-secrets`, `monitoring`, `temporal`, `backstage`, `minio`, `database`, `forgejo`, `zitadel`, `local-path-storage`, `system-upgrade`, `observability-eval`), THE SYSTEM SHALL reject it with HTTP 400 and a `validationErrors` entry stating that the name is reserved.
- WHEN a `create-tenant` request has a `tenant_name` that matches a reserved glob from the gitops rule (`kube-*`, `argo*`, `*-system`, `platform-*`, `mctl-*`, `grafana-*`, `vault*`), THE SYSTEM SHALL reject it in the same way. For example, `kube-system-team`, `argonaut`, `billing-system`, `platform-x`, `mctl-foo`, `grafana-bar` and `vaultwarden` are all rejected.
- WHEN a `create-tenant` request has a format-valid `tenant_name` that matches no reserved entry (e.g. `billing`, `team-kube`, `my-argo`, `system-team`), THE SYSTEM SHALL accept it as far as name validation is concerned.
- IF a reserved name is submitted, THEN THE SYSTEM SHALL reject it before `Executor.Submit` creates any Argo Workflow, and before the Backstage catalog notification.
- IF any code calls `operations.Executor.Submit` for the `create-tenant` WorkflowTemplate with a reserved `tenant_name`, THEN THE SYSTEM SHALL return an error and SHALL NOT create a workflow.
- WHILE the caller is a platform admin THE SYSTEM SHALL still reject reserved names. The gitops template rejects them regardless of `reprovision`, so an admin bypass would only move the failure back into Argo.
- WHILE an operation other than `create-tenant` runs (e.g. `delete-tenant`, `deploy-service`), THE SYSTEM SHALL NOT apply the reserved-name check.
- WHEN the reserved-name check is removed from the code, THE SYSTEM's unit tests SHALL fail.

## Out of scope
- Adding a reserved-name check to `delete-tenant`, `delete-tenant-safe` or any other operation. Existing tenants are unaffected.
- A live Kubernetes namespace collision check in the API. The WorkflowTemplate's `check-namespace-collision` step stays the authority for that.
- Automatically syncing the list from mctl-gitops, or a CI check that compares the two lists.
- Changes to the gitops WorkflowTemplate.
- Changing the `tenant_name` regex pattern itself.

## Open questions
- The gitops rule is broader than exact names: it includes globs such as `argo*` and `vault*`, which also reject harmless-looking names like `argonaut`. This proposal mirrors the gitops rule exactly. A looser API rule would be pointless, because the workflow would still fail. Reviewers should confirm that this strictness is intended.
- Should the MCP `mctl_create_tenant` tool description mention that reserved names are refused? This proposal adds a short note. It is cosmetic and does not affect behaviour.
