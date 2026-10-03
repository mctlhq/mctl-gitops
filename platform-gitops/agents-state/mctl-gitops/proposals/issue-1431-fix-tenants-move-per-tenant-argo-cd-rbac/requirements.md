# Move per-tenant Argo CD RBAC out of the shared argocd/values.yaml

## Context

Every tenant create and delete currently rewrites one shared file,
`platform-gitops/argocd/values.yaml`. `wft-create-tenant.yaml` builds a six-line
casbin block and inserts it with `awk` immediately before the `    secret:` key
(the "Append ArgoCD RBAC entries" step, ~line 560), while
`wft-delete-tenant.yaml` (lines 212-218) and `wft-delete-tenant-safe.yaml`
(lines 555-561) delete the same lines with four `sed -i` passes. Because the
insertion point is a fixed anchor, two concurrent `create-tenant` runs that
cloned the same `main` write different content at the same spot; the push retry
loop reacts to the rejected push with `git rebase origin/main`, the rebase hits
`CONFLICT (content)`, and the step runs under `set -e`, so it exits immediately
and the remaining four attempts never run. This is what happened on 2026-09-27:
`karabu` pushed first, `drawing` (workflow `create-tenant-4651065f`) died in
`commit-to-git`, and because `create-vault-policy` runs earlier in the DAG it
left orphaned Vault policies and Kubernetes auth roles behind that had to be
removed by hand.

The fix is structural, not a better retry: a tenant's Argo CD RBAC must live in
a file that belongs to that tenant alone, so that concurrent tenant operations
touch disjoint paths and git merges them without conflict. This proposal moves
each tenant's policy lines into `platform-gitops/argocd/rbac/tenants/<tenant>.csv`
and has the `argocd-config` chart assemble `argocd-rbac-cm` from those fragments
at render time, so create writes one new file, delete removes one file, and
neither ever edits a file another tenant shares.

## User stories

- AS a platform operator I WANT two `create-tenant` runs started seconds apart to
  both succeed SO THAT tenant provisioning is not serialized by luck and does not
  leave orphaned Vault policies behind.
- AS a platform operator I WANT a tenant's Argo CD RBAC to be created and removed
  with the tenant's own files SO THAT deleting a tenant leaves no dangling
  comment, blank line, or policy line in a shared file.
- AS a tenant member I WANT my Argo CD permissions to be byte-for-byte what they
  were before the migration SO THAT the change is invisible from the UI.
- AS a security reviewer (SOC F4) I WANT a machine-checked guarantee that no
  tenant role can ever gain `exec` SO THAT the "no tenant exec" control does not
  depend on whoever edits a CSV next.
- AS a reviewer I WANT CI to fail if a tenant workflow template writes to a file
  that is not parameterized by the tenant name SO THAT this class of conflict
  cannot be reintroduced.

## Acceptance criteria (EARS)

- WHEN `wft-create-tenant` provisions tenant `<t>` THE SYSTEM SHALL write the
  tenant's Argo CD RBAC to `platform-gitops/argocd/rbac/tenants/<t>.csv` and SHALL
  NOT modify `platform-gitops/argocd/values.yaml`.
- WHEN `wft-delete-tenant` or `wft-delete-tenant-safe` removes tenant `<t>` THE
  SYSTEM SHALL `git rm` `platform-gitops/argocd/rbac/tenants/<t>.csv` and SHALL
  NOT modify `platform-gitops/argocd/values.yaml`.
- WHEN two `create-tenant` runs for different tenants are pushed against the same
  base commit THE SYSTEM SHALL let the second run's push succeed after a fetch and
  rebase, because the two commits touch disjoint paths.
- WHEN the `argocd-config` chart is rendered THE SYSTEM SHALL emit a single
  `argocd-rbac-cm` ConfigMap whose `policy.csv` is the base policy from
  `argo-cd.configs.rbac["policy.csv"]` followed by every
  `rbac/tenants/*.csv` fragment in sorted filename order.
- WHILE the migration commit is in effect THE SYSTEM SHALL grant every existing
  tenant (`labs`, `ovk`, `karabu`) exactly the five `applications`/`logs` rules and
  the one group binding it had before, verified by a normalized diff of the
  rendered `policy.csv` and by `argocd admin settings rbac can <group> <action>
  <resource>` for each tenant.
- WHILE any tenant fragment exists THE SYSTEM SHALL keep its content restricted to
  the canonical six lines for that tenant (`applications get|list|sync|override`
  and `logs get` on `apps/<t>-*`, plus `g, <t>, role:team-<t>`), and CI SHALL fail
  on any fragment that adds a verb, widens the object glob, or grants `exec`.
- IF a tenant directory `platform-gitops/tenants/<t>/` exists without a matching
  `rbac/tenants/<t>.csv` (or the reverse) THEN THE SYSTEM SHALL fail CI with the
  offending tenant named. The one exception is `admins`: its directory exists but
  its Argo CD access is the base policy's `g, admins, role:admin`, not a
  `role:team-admins` block. The gate SHALL exempt `admins` through an explicit,
  commented allow-list, and SHALL fail if a `rbac/tenants/admins.csv` fragment
  appears. Adding one would change effective policy.
  (Reviewer amendment, 2026-09-27.)
- WHEN the chart renders `argocd-rbac-cm` THE SYSTEM SHALL carry over every key of
  `argo-cd.configs.rbac` except `create` and `annotations`, as the upstream
  subchart template does (`omit .Values.configs.rbac "create" "annotations"`).
  Only `policy.csv` is extended with the tenant fragments. A key added to
  `configs.rbac` later (e.g. `policy.matchMode`) SHALL reach the ConfigMap without
  a template change. (Reviewer amendment, 2026-09-27.)
- IF a tenant workflow template (`wft-create-tenant.yaml`,
  `wft-delete-tenant.yaml`, `wft-delete-tenant-safe.yaml`) writes, stages, or
  deletes a repository path that does not contain the tenant name and is not on an
  explicit, comment-justified waiver list THEN THE SYSTEM SHALL fail CI, and this
  check SHALL fail when the old `awk` insertion into
  `platform-gitops/argocd/values.yaml` is put back.
- IF `platform-gitops/argocd/rbac/tenants/` contains no fragments THEN THE SYSTEM
  SHALL still render a schema-valid `argocd-rbac-cm` containing the base policy.
- IF the migration removes the orphan blocks `role:team-yyy` and `role:team-xxxx`
  (present in `values.yaml` lines 213-226 with no `platform-gitops/tenants/`
  directory and no `platform-gitops/services/` directory) THEN THE SYSTEM SHALL
  record that removal explicitly in the PR description as the only intentional
  difference in effective policy.

## Out of scope

- The push retry loop's `git rebase` vs `reset --hard origin/main` + regenerate
  hardening (the issue lists it as separate). This proposal removes the *cause* of
  the conflict; it does not rewrite the retry loop.
- Rolling back `create-vault-policy` when the git commit later fails (separate
  item in the issue).
- The other shared files the delete templates still edit with `sed -i`:
  `platform-gitops/infra-components/data/cnpg/shared/{databases,secrets,cluster}.yaml`
  (wft-delete-tenant.yaml lines 255-278). They are a real instance of the same
  anti-pattern but they are delete-only, involve CNPG object lifecycles, and are
  not what issue 1431 is about. They are carried as named, commented waivers in the
  new CI guard so the guard does not silently pretend they are fine.
- Moving service Applications out of the shared `apps` AppProject.
- Argo Workflows SSO RBAC (`platform-gitops/argo-workflows/sso-team-<t>.yaml`) —
  already per-tenant, including the precedence derivation.
- mctl-api's operation registry (`internal/operations/registry.go`, the
  `create-tenant` and `delete-tenant` entries) lists
  `platform-gitops/argocd/values.yaml` in `ModifiesPaths`. That field is
  descriptive metadata only: it is shown by `list_operations`, and nothing parses
  tenant blocks from the file. It goes stale after this change and is fixed in a
  separate mctl-api PR, not here. (Reviewer note, 2026-09-27: the out-of-repo
  reader grep in task 11 was run; this is the only hit.)

## Open questions

- Are the orphan groups `yyy` and `xxxx` in `values.yaml` really dead? Nothing in
  this repo references them: no `platform-gitops/tenants/yyy|xxxx`, no
  `platform-gitops/services/yyy|xxxx`, so `apps/yyy-*` can match no Application.
  Proceeding on the reading that they are leftovers of deleted test tenants and
  dropping them; if a Backstage group by that name still exists, re-adding a
  fragment is a one-file commit.
- Does anything outside this repo parse the tenant blocks out of
  `platform-gitops/argocd/values.yaml` (e.g. mctl-api or mctl-portal rendering a
  team's Argo CD permissions)? Nothing in this repo does. Proceeding on the
  assumption that the workflow templates are the only writers and that no reader
  depends on the blocks' location; the implementer should grep mctl-api for
  `role:team-` before merge.
- `argo-cd.configs.rbac.create: false` hands ownership of `argocd-rbac-cm` to a
  template in this repo. That is exactly what the upstream chart documents the flag
  for ("it is expected the configmap will be created by something else",
  `argo-cd-9.5.9/values.yaml` line 447), so it is treated as supported rather than
  as an open question.
