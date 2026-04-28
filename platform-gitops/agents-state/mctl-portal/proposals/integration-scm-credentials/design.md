# Design: integration-scm-credentials

## Current state
According to `context/architecture.md`, mctl-portal runs on the Backstage version pinned in
the root `package.json` as `1.0.1`. The `@backstage/integration` package in this version
contains CVE-2026-29185: when constructing requests to SCM APIs, the URL is forwarded
without decoding and normalising path-traversal sequences. This allows an authenticated
user, via the catalog-import form, a scaffolder git action, or the github-actions plugin,
to supply a URL such as
`https://api.github.com/repos/org/repo%2F..%2F..%2F../evil-org/evil-repo`, which resolves
to an arbitrary GitHub API endpoint with the server-side GitHub App token.

Affected entry points:
- `catalog-import` — the new-service registration form accepts a repository URL.
- Scaffolder git actions (`fetch:plain`, `publish:github`, etc.) — accept user-supplied `repoUrl`.
- The `github-actions` plugin — substitutes `repoUrl` from the catalog.

## Proposed solution

### Upgrade Backstage to v1.50.3
The CVE-2026-29185 fix is in `@backstage/integration` v1.20.1, which is part of Backstage
v1.50.3. The approach is a major Backstage upgrade through the standard backstage-cli
upgrade process:

```bash
yarn backstage-cli versions:bump --release 1.50.3
```

The command updates every `@backstage/*` package to the versions declared in the 1.50.3
release manifest, including `@backstage/integration` v1.20.1.

After the upgrade:
1. Run `yarn backstage-cli versions:check` — confirm there are no peer conflicts.
2. Run `yarn backstage-cli repo build` — verify TypeScript compatibility.
3. Run playwright smoke tests: catalog-import, scaffolder onboarding, github-actions panel.
4. Build the Docker image; ArgoCD sync in the `admins` tenant.

The upstream fix in `@backstage/integration` v1.20.1 adds URL normalisation before
attaching auth headers: `decodeURIComponent` + `URL` constructor with hostname checks
against the configured SCM-integration list. Requests to hosts outside the list do not
receive credentials.

### Relation to other proposals
`scaffolder-path-traversal` and `scaffolder-secret-leak` upgrade `plugin-scaffolder-backend`
to 3.1.1+. Backstage v1.50.3 is compatible with that version (3.1.1 lives in the v1.50.x
line). All three proposals can be carried in a single large PR or in two sequential ones:
- PR 1: `backend-defaults` 0.12.2 + `plugin-scaffolder-backend` 3.1.1 (fast, Effort:2).
- PR 2: Backstage 1.50.3 (a wider upgrade requiring extra testing).

This order is recommended: close the two scaffolder CVEs first (lower regression risk),
then bring up Backstage as a whole.

## Alternatives

**A. Update only `@backstage/integration` to 1.20.1 without upgrading all of Backstage**
Theoretically possible via `yarn up @backstage/integration@^1.20.1`. However, Backstage
packages are tightly coupled by peer versions; mismatched package versions create a risk
of hidden incompatibilities. Backstage recommends upgrading every package consistently
through `versions:bump`. Rejected.

**B. Add a custom URL validation middleware before passing into `@backstage/integration`**
Requires maintaining custom code to handle every entry point (catalog-import API,
scaffolder actions, github-actions plugin). High risk of missing one path. The upstream
patch is more reliable. Rejected.

**C. Restrict access to catalog-import and scaffolder for all users until the patch lands**
Breaks core portal functionality. Acceptable as a short-term mitigation but not as the
main solution. Rejected as the sole measure.

## Platform impact

### Migration
Backstage 1.50.3 is a minor/patch update within Backstage's semver policy. No breaking
changes in the public API are expected. The Backstage CHANGELOG must be reviewed for
deprecated APIs used by the custom observability plugin.

### Backward compatibility
All standard plugins (`catalog`, `scaffolder`, `kubernetes`, `techdocs`, `search`,
`github-actions`) are compatible with v1.50.3 per the Backstage release notes. The custom
observability plugin requires a TypeScript-compatibility check (task 2).

### Resource impact
Upgrading Backstage adds no new services or significant dependencies. Backend pod memory
consumption should not change materially. The `labs` tenant is not affected (Backstage is
deployed only in `admins`).

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| The GitHub App token is already compromised before the patch | Unknown | Rotate GitHub App credentials after the deploy; review the GitHub audit log for suspicious API calls |
| Regression in the custom observability plugin | Medium | TypeScript build + playwright smoke test before merge |
| Backstage 1.50.3 incompatible with community-plugins (kubernetes, techdocs) | Low | Check the backstage/community-plugins compatibility matrix before deploy |
| ArgoCD sync race with parallel changes | Low | Deploy in a maintenance window |
