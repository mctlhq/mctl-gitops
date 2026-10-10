# Design: issue-1768-security-create-tenant-reject-tenant-nam

## Current state

- `platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml`
  - The DAG `create-tenant-pipeline` runs these steps in order: `validate` →
    `create-vault-policy` → `commit-to-git` → `refresh-tenants-appset` → `wait-for-tenant-ready`.
  - `validate-tenant-name` runs in `alpine/git:2.43.0`, which has no kubectl. Parameters
    are bound through `env` (`PARAM_TENANT_NAME`, `PARAM_REPROVISION`). The step checks
    the format regex `^[a-z0-9][a-z0-9-]{1,62}$`.
  - It then loops over a fixed list of 12 reserved names (`argocd argo-workflows
    argo-events kube-system kube-public kube-node-lease default cert-manager traefik
    vault external-secrets monitoring`).
  - Finally it clones mctl-gitops and checks `platform-gitops/tenants/<name>`, failing
    closed if the clone fails.
  - Other steps in the same template already use `alpine/k8s:1.33.12`
    (`refresh-tenants-appset`, `wait-for-tenant-ready`).
- `platform-gitops/bootstrap/templates/bootstrap/applicationset-tenants.yaml` sets the
  destination namespace to `{{ .path.basename }}` with `CreateNamespace=true` and
  `ServerSideApply=true`. A tenant directory named after an existing namespace
  therefore adopts it.
- `platform-gitops/helm-charts/tenant/templates/namespace.yaml` and `preview.yaml`
  render `Namespace/<tenant>` and `Namespace/<tenant>-preview`. Both carry the
  `tenant.labels` labels (`_helpers.tpl`), which include
  `mctl.me/tenant: "<tenant>"`. That label is therefore a reliable ownership marker
  for every namespace the tenant chart creates.
- `platform-gitops/argo-workflows/cluster-templates/wft-delete-tenant-safe.yaml`
  - `validate-tenant-exists` (`alpine:3.19`) checks only a different static list of
    15 names. That list includes `admins`, `backstage` and `platform-db`, so it has
    already drifted from the create list.
  - `delete-k8s-resources` runs `kubectl get ns "${TENANT}" >/dev/null 2>&1` and then
    `kubectl delete ns`, and does the same for `${TENANT}-preview`. It never checks
    the labels, and any lookup error is treated as "not found, skipping".
  - The wait loop also treats any non-zero rc as "gone".
  - Both templates interpolate `{{inputs.parameters.tenant_name}}` into the script text.
- The legacy `wft-delete-tenant.yaml:333` also runs `kubectl delete ns "${TENANT}"`.
- `platform-gitops/argo-workflows/config/sa-and-rbac.yaml` declares
  `argo-workflow-sa` and only namespaced Roles for it: `argo-workflow-runner`,
  `argo-workflow-argocd-sync`, `argo-workflow-rotate-github-token` and
  `argo-workflow-platform-db-read`. No grant on `namespaces` appears anywhere in gitops.
- CI: `.github/workflows/validate-manifests.yml` runs a set of
  `scripts/validate-*.py --selftest` checks, for example
  `validate-shell-param-interpolation.py` and `validate-tenant-workflow-shared-writes.py`.
  New checks follow that pattern.

## Proposed solution

### 1. Shared, testable shell logic (single source)

The denylist and the namespace-ownership decision are written once as POSIX `sh`
functions in each template's script, between the markers `# BEGIN tenant-ns-guard` and
`# END tenant-ns-guard`. The block is identical in create-tenant, delete-tenant-safe
and delete-tenant. CI checks that the copies are byte-identical, because Argo
ClusterWorkflowTemplates cannot share a script file.

```sh
# BEGIN tenant-ns-guard
tenant_name_reserved() {   # $1 = name; returns 0 if reserved
  case "$1" in
    argocd|argo-workflows|argo-events|kube-system|kube-public|kube-node-lease|\
    default|cert-manager|traefik|vault|external-secrets|monitoring|\
    temporal|backstage|minio|database|forgejo|zitadel|\
    local-path-storage|system-upgrade|\
    kube-*|argo*|*-system|platform-*|mctl-*|grafana-*|vault*) return 0 ;;
  esac
  return 1
}

# Prints "absent", "owned" or "foreign"; returns non-zero if the lookup itself failed.
tenant_ns_owner_state() {  # $1 = namespace, $2 = tenant
  out=$(kubectl get namespaces --field-selector "metadata.name=$1" \
        -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.mctl\.me/tenant}{"\n"}{end}') || return 2
  [ -z "$out" ] && { echo absent; return 0; }
  [ "$(printf '%s' "$out" | cut -f2)" = "$2" ] && { echo owned; return 0; }
  echo foreign
}
# END tenant-ns-guard
```

`list` with a field selector returns an empty list for an absent namespace and a
non-zero exit for an API or RBAC error. That gives an unambiguous three-way answer,
with no parsing of a `NotFound` message. A lookup error is never "absent".

The current delete list contains `admins`, which is a real tenant. It stays only in
delete-tenant-safe's own extra list, as a "protected tenant" rule. It is not added to
the shared create denylist, because adding it there would break reprovisioning of `admins`.

### 2. create-tenant: new `check-namespace` step

- `validate-tenant-name` keeps its git-based checks. Its reserved loop is replaced with
  `tenant_name_reserved`.
- A new template `check-namespace-collision` runs in `alpine/k8s:1.33.12` (the image
  already used in this file). Its inputs are `tenant_name` and `reprovision`, bound
  through `env`. It does the following:
  - re-checks the name format, so the step is safe when run on its own via `--entrypoint`;
  - runs `tenant_name_reserved`;
  - for each of `N` and `N-preview`, calls `tenant_ns_owner_state`:
    - `foreign`: exit 1, naming the namespace and the label it lacks;
    - lookup error: exit 1 with "could not list namespaces";
    - `owned` with `reprovision=false`: allowed. The git check in `validate-tenant-name`
      already refuses an existing tenant, and an orphaned owned namespace from a
      half-deleted tenant is legitimately re-adoptable.
- The DAG becomes `validate` and `check-namespace` (in parallel), followed by
  `create-vault-policy`, which depends on both. Nothing is written before both pass.
- Keeping the live check in its own template lets it be proven in isolation without
  side effects:
  `argo submit --from clusterworkflowtemplate/create-tenant --entrypoint check-namespace-collision -p tenant_name=temporal`.
  The workflow arguments feed the entrypoint inputs by name.

### 3. delete-tenant-safe and delete-tenant: ownership guard

- `validate-tenant-exists` switches to `alpine/k8s:1.33.12`, binds `tenant_name` through
  `env` (`PARAM_TENANT_NAME`), and checks the format. It keeps its protected-tenant list
  and adds the following:
  - `tenant_name_reserved` refuses the name;
  - `tenant_ns_owner_state` must return `owned` or `absent` for `N` and `N-preview`;
  - `foreign` or a lookup error fails the step before retire-services, Vault or git
    deletion runs.
- `delete-k8s-resources` re-checks the state immediately before each `kubectl delete ns`.
  This is a time-of-check to time-of-use guard, because the namespace could change
  between `validate` and this step:
  - `owned`: delete;
  - `absent`: skip;
  - `foreign` or error: exit 1.
- The wait loop distinguishes `absent` from lookup errors. An error is no longer
  counted as "namespace gone". The step also gets `env` binding and moves to the
  `alpine/k8s` image, which removes the runtime `curl` download of kubectl v1.28.0.
- The legacy `wft-delete-tenant.yaml` gets the same guard before its
  `kubectl delete ns` (line 333).
- `scripts/validate-shell-param-interpolation.py` BASELINE entries for these
  templates/parameters are removed if present. The ratchet then prevents regressions.

### 4. RBAC

Append to `platform-gitops/argo-workflows/config/sa-and-rbac.yaml`:

```yaml
# Lets create-tenant / delete-tenant-safe tell a tenant-owned namespace
# (mctl.me/tenant=<name>) from a platform one before adopting or deleting it.
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: argo-workflow-namespace-read
rules:
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: argo-workflow-namespace-read
subjects:
  - kind: ServiceAccount
    name: argo-workflow-sa
    namespace: argo-workflows
roleRef:
  kind: ClusterRole
  name: argo-workflow-namespace-read
  apiGroup: rbac.authorization.k8s.io
```

Namespace objects hold labels and annotations only, never secret material, so
cluster-wide read access is low risk.

### 5. CI: `scripts/validate-tenant-ns-guard.py`

The script is wired into `validate-manifests.yml` as `--selftest` and as a plain run,
in the same way as its siblings. It does the following:

1. Extracts the `tenant-ns-guard` block from all three templates and asserts the
   copies are identical.
2. Runs it in `sh`:
   - must reject: `temporal backstage minio database forgejo zitadel kube-foo
     argo-rollouts cnpg-system reflector-system system-upgrade local-path-storage platform-db
     platform-events mctl-api grafana-iac vault-human-auth-iac argocd default`;
   - must accept: every directory name under `platform-gitops/tenants/` (today
     `admins erpact karabu labs mctl ovk`), plus `team1` and `dev-platform`.
3. Puts a fake `kubectl` on `PATH` and drives `tenant_ns_owner_state` through each case:
   - empty list → `absent`;
   - label equals the tenant → `owned`;
   - label missing → `foreign`;
   - label belongs to another tenant → `foreign`;
   - kubectl exits 1 → non-zero, and the caller fails.
4. As a best-effort freshness check, lists the literal `destination.namespace` /
   `namespace:` values in `platform-gitops/bootstrap/templates/**` that are not tenant
   namespaces, and warns or fails on any that the denylist does not cover. Exact policy
   (fail or warn) is decided at implementation time; it is "fail" if it produces no
   false positives on HEAD. This gives the static list an early signal when a new
   platform namespace is added in gitops.

`--selftest` mutates a copy of the block (drops a pattern, makes the lookup ignore
the kubectl exit code) and proves the checker then fails.

## Alternatives

1. **Only extend the static denylist.** This was dropped as the primary control
   because the list goes stale whenever a platform namespace is added, which is the
   root cause the issue names. The denylist is kept only as defence in depth.
2. **A ValidatingAdmissionPolicy that refuses label/ResourceQuota writes from the
   `tenant-*` Argo CD applications to namespaces lacking `mctl.me/tenant`.**
   `bootstrap/templates/system/admission-policies.yaml` already holds similar policies.
   This would also cover tenants created without the workflow, but:
   - Argo CD's `CreateNamespace` / SSA identity is the Argo CD controller for every
     app, so the policy has to key on managed-by/tracking metadata, which is fragile;
   - it does not protect the delete path;
   - it fails late, after Vault and git writes.
   It is left as follow-up hardening.
3. **A check inside mctl-api before the workflow is submitted.** That is out of scope
   per the issue. It also does not protect direct workflow or Backstage submissions,
   which go straight to the ClusterWorkflowTemplate.
4. **Folding the live check into `validate-tenant-name` by switching its image to
   `alpine/k8s`.** This was dropped because a separate template can be run alone via
   `--entrypoint` as a side-effect-free proof. It also keeps the git and kube concerns
   apart, and they can run in parallel.

## Platform impact

- **Migration**: none. There are no data changes. ArgoCD syncs the new ClusterRole and
  ClusterRoleBinding and the updated ClusterWorkflowTemplates. Per CLAUDE.md, wait
  about 3 minutes after merge before submitting.
- **Ordering risk**: if the templates sync before the RBAC, `check-namespace` fails
  closed (forbidden). That is safe, and the next sync fixes it. Both live in
  `argo-workflows/config`/`cluster-templates` under the same app, so in practice they
  land together.
- **Backward compatibility**: existing tenants (`admins erpact karabu labs mctl ovk`)
  do not match the denylist, and CI guards this. Their namespaces carry
  `mctl.me/tenant`, so `reprovision=true` and deletion keep working. If a live tenant
  namespace lacks the label (for example, one created before the label existed), its
  deletion will now be refused. That is the intended fail-closed behaviour. The fix is
  to sync the tenant app so the label is applied. The implementer verifies labels with
  `kubectl get ns -l mctl.me/tenant --show-labels` before merge.
- **Delete-path behaviour change**: lookup errors that were previously swallowed now
  fail `delete-k8s-resources`. If the open question about missing `delete`/`get`
  rights turns out to be true, deletions will now fail loudly where they used to
  falsely report success. That is a correct but visible change, and it must be
  called out in the PR.
- **Resource impact**: negligible. There is one extra short pod per create-tenant
  run, and the image is already pulled for other steps.
- **Security**: there is one new cluster-wide read grant (get/list namespaces) for
  `argo-workflow-sa`, and no write grant. The change also removes three
  parameter-interpolation sites.
