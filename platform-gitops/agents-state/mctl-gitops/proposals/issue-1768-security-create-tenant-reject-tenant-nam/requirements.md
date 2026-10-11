# create-tenant: reject tenant names that collide with existing non-tenant namespaces

## Context

`create-tenant` (`platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml`,
template `validate-tenant-name`) checks a requested tenant name against a fixed
list of 12 reserved names. It then checks only whether
`platform-gitops/tenants/<name>` exists in git. Many live platform namespaces are
not on that list and are not tenants, for example `temporal`, `backstage`,
`mctl-api`, `minio`, `database`, `platform-db`, `platform-events`, `forgejo`,
`zitadel`, `cnpg-system`, `reflector-system`, `argo-rollouts`, `grafana-iac`,
`vault-human-auth-iac`, `local-path-storage` and `system-upgrade`. A request for
one of these names passes validation. The `tenants` ApplicationSet
(`CreateNamespace=true`) and the tenant chart then take over that namespace.
They apply the tenant labels, a ResourceQuota, a default-deny NetworkPolicy, and
Roles/RoleBindings for `argo-workflow-sa` and the team's SSO account.
`delete-tenant-safe` would later `kubectl delete ns` it. This is audit finding
SEC-N101.

The fix adds a live check of the cluster's namespaces, which is the
authoritative signal. The static denylist stays as defence in depth and is
widened to patterns. Both delete workflows must refuse to delete a namespace that
the tenant does not own. Ownership is the `mctl.me/tenant=<name>` label that the
tenant chart puts on every namespace it renders (`helm-charts/tenant/templates/_helpers.tpl`
`tenant.labels`, used by `namespace.yaml` and `preview.yaml`).

## User stories

- AS a platform operator I WANT create-tenant to refuse names that already exist as
  platform namespaces SO THAT a tenant request cannot take over or lock down a
  platform component's namespace.
- AS a platform operator I WANT delete-tenant to refuse to delete namespaces
  that the tenant does not own SO THAT a mistaken or malicious tenant record cannot
  remove `temporal`, `backstage` or a similar namespace.
- AS a tenant owner I WANT reprovisioning (`reprovision=true`) of my existing tenant
  to keep working SO THAT I can repair a half-provisioned tenant.
- AS a reviewer I WANT CI to prove the denylist and the live-check logic both ways
  SO THAT a change to them cannot silently weaken them.

## Acceptance criteria (EARS)

- WHEN create-tenant is submitted with a name `N` and a namespace `N` exists in the
  cluster without the label `mctl.me/tenant=N` THE SYSTEM SHALL fail the validation
  step before any Vault policy or git commit is created, and print the colliding namespace.
- WHEN create-tenant is submitted with a name `N` and namespace `N-preview` exists
  without the label `mctl.me/tenant=N` THE SYSTEM SHALL fail validation in the same way.
- WHEN create-tenant is submitted with `reprovision=true` for an existing tenant whose
  namespace carries `mctl.me/tenant=N` THE SYSTEM SHALL pass the namespace check.
- WHEN create-tenant is submitted with a fresh name for which no namespace `N` or
  `N-preview` exists, and which matches no denylist entry, THE SYSTEM SHALL pass the
  namespace check.
- IF the namespace lookup fails for any reason other than an empty result (API error,
  RBAC forbidden, timeout, missing kubectl) THEN THE SYSTEM SHALL fail the validation
  step and SHALL NOT treat the namespace as absent.
- WHEN a tenant name matches the static denylist THE SYSTEM SHALL reject it. The
  denylist is the 12 existing names plus the patterns `kube-*`, `argo*`, `*-system`,
  `platform-*`, `mctl-*`, `grafana-*`, `vault*` and the exact names `temporal`,
  `backstage`, `minio`, `database`, `forgejo`, `zitadel`. It also adds the exact names
  `local-path-storage` and `system-upgrade`, which are live platform namespaces that
  none of the issue's patterns match.
- WHILE any tenant exists under `platform-gitops/tenants/` THE SYSTEM SHALL keep that
  tenant's name accepted by the denylist, so that reprovisioning it still works. CI enforces this.
- WHEN delete-tenant-safe (or legacy delete-tenant) is about to delete namespace `N`
  or `N-preview` and that namespace exists without `mctl.me/tenant=N` THE SYSTEM
  SHALL refuse to delete it and fail the workflow.
- WHEN delete-tenant-safe runs its `validate` step for `N` and namespace `N` exists
  without `mctl.me/tenant=N` THE SYSTEM SHALL fail before retire-services, Vault or
  git deletion runs.
- IF the namespace lookup in a delete workflow fails for any reason other than
  "not found" THEN THE SYSTEM SHALL fail the step, and SHALL NOT report the namespace
  as "not found, skipping" or as "gone".
- THE SYSTEM SHALL grant `argo-workflow-sa` `get` and `list` on `namespaces` through a
  ClusterRole and ClusterRoleBinding declared in
  `platform-gitops/argo-workflows/config/sa-and-rbac.yaml`, and no further verbs.
- WHEN CI runs on a pull request THE SYSTEM SHALL run a selftest that proves the
  denylist and the live-check decision logic both ways:
  - names like `temporal` and `cnpg-system` are rejected;
  - existing tenants are accepted;
  - a lookup error fails closed.

## Out of scope

- Reserved-name validation in mctl-api (`internal/operations/registry.go`), which
  will be a separate mctl-api issue.
- Multi-team tenants (`tenant.teams`, namespaces `<tenant>-<team>`). create-tenant
  does not write `teams`, so it never renders those namespaces.
- An admission policy that blocks the `tenants` ApplicationSet from adopting
  non-tenant namespaces. It is recorded under Alternatives as possible follow-up
  hardening.
- Fixing the remaining `{{inputs.parameters.*}}` script interpolations tracked in
  gitops#992, except in the templates this change rewrites.

## Open questions

- gitops does not declare any RBAC that lets `argo-workflow-sa` `get` or `delete`
  namespaces, yet `delete-k8s-resources` already runs `kubectl get ns` and
  `kubectl delete ns`. Either a grant lives outside this repo, or these calls are
  failing today. They would fail silently: `kubectl get ns ... >/dev/null 2>&1`
  treats "forbidden" as "not found, skipping", and the wait loop treats it as
  "gone". This proposal assumes the delete right, wherever it comes from, is left
  unchanged and only adds `get`/`list`. The implementer should check
  `kubectl auth can-i delete namespaces --as=system:serviceaccount:argo-workflows:argo-workflow-sa`
  and record the result in the PR. If the right is missing, granting `delete` is a
  separate decision that is not made here.
- The issue's pattern `argo*` also rejects harmless names such as `argonaut`, and
  `vault*` rejects names such as `vaultwarden`. This proposal accepts that, because
  the issue asks for these patterns explicitly.
