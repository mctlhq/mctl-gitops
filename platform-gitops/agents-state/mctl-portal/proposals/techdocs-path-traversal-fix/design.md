# Design: techdocs-path-traversal-fix

## Current state
mctl-portal is a Backstage-based portal (yarn workspaces, `packages/app` +
`packages/backend`) served via nginx + Docker and deployed to the `admins`
namespace via ArgoCD (see `context/architecture.md`).

The TechDocs plugin is configured with `techdocs.generator.runIn: local`.
MkDocs runs as a child process inside the backend container. The currently
installed version of `@backstage/plugin-techdocs-node` is on a line prior to
1.13.11, which does not validate whether symlinks inside the source docs
directory resolve to paths outside the docs root. Because the MkDocs process
runs as the same OS user as the Node.js backend, any file readable by the
backend process can be embedded in generated HTML.

## Proposed solution
Upgrade Backstage to the v1.50.3 patch release. This release bundles:
- `@backstage/plugin-techdocs-node` >=1.13.11 / >=1.14.1 — adds symlink
  escape validation before invoking MkDocs (CVE-2026-23947 fix).
- A fix for the catalog facets performance regression that was introduced in
  an earlier 1.50.x build.

The upgrade procedure follows the standard Backstage bump process:
1. Run `yarn backstage-cli versions:bump --release 1.50.3` in the monorepo
   root to update all first-party `@backstage/*` packages consistently.
2. Run `yarn install` and resolve any peer-dependency conflicts.
3. Build and push a new Docker image tagged `mctl-portal:1.50.3-<gitsha>`.
4. Update the image tag in `mctl-gitops` (the ArgoCD source of truth) and
   open a PR for review.
5. ArgoCD syncs the new image to the `admins` namespace after PR merge.

No configuration changes are required: the symlink validation is enforced
unconditionally when `runIn: local` is active.

## Alternatives

### Option A: Pin only `@backstage/plugin-techdocs-node` to >=1.13.11
Cherry-pick the single vulnerable package rather than doing a full Backstage
bump. Dropped because Backstage packages are tightly coupled by version; a
partial upgrade frequently causes peer-dependency conflicts and mismatched
API assumptions across the monorepo. The official guidance is always to bump
via `backstage-cli versions:bump`.

### Option B: Switch to `techdocs.generator.runIn: docker`
Running MkDocs inside a separate Docker-in-Docker (or sidecar) container
would sandbox the filesystem. Dropped for this proposal because it is a
significant architectural change with its own operational risks (DinD
privileges, latency) and should be evaluated independently — not as a
quick security patch.

### Option C: Add a pre-generation symlink scanner in a custom wrapper
Write a pre-flight script that walks the docs directory and aborts if any
symlink escapes the root. Dropped because the upstream fix already does this
at the correct layer; a custom wrapper adds maintenance burden and may have
edge cases.

## Platform impact

### Migrations
None. No schema changes; no Postgres migrations required. The TechDocs
generator behavior change (symlink rejection) is transparent to
well-formed documentation repositories.

### Backward compatibility
Documentation repos that rely on out-of-tree symlinks will have their TechDocs
build fail (which is the intended security behavior). Platform team should
communicate this in the changelog.

### Resource impact
A Backstage patch upgrade does not add new workloads or increase memory
consumption. No impact on the `labs` tenant (the upgrade is scoped entirely
to the `admins` namespace). No flag required.

### Risks and mitigations
- **Risk:** `backstage-cli versions:bump` may pull in a minor version of a
  community plugin that introduces a regression.
  **Mitigation:** Run the full Playwright e2e suite against the staging
  environment before promoting to production.
- **Risk:** The MkDocs symlink check may produce false positives on repos that
  use valid relative symlinks within the docs tree.
  **Mitigation:** Test against the three highest-traffic TechDocs repos in the
  catalog before promoting.
