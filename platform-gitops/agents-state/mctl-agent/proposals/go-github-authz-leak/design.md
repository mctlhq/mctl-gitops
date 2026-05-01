# Design: go-github-authz-leak

## Current state
mctl-agent (see `context/architecture.md`) is pinned to **google/go-github v68**. The library is used in the fix-PR pipeline: after a skill produces a remediation patch, mctl-agent calls the GitHub API to create a branch, commit the patch, and open a pull request in `mctlhq/mctl-gitops`.

Authentication uses a GitHub App installation token fetched from Vault (`secret/platform/github-app`) and rotated every 30 minutes by the `cwft-rotate-github-token` CronWorkflow. The token is injected into the go-github HTTP client as a `Bearer` token in the `Authorization` header.

In go-github versions prior to v85.0.0, the HTTP client does not strip the `Authorization` header on cross-host redirects. If the GitHub API (or a network intermediary) were to issue a redirect to a different hostname, the installation token would be forwarded verbatim to the redirect target. This is the vulnerability addressed by the v85.0.0 cross-host redirect rejection feature.

## Proposed solution

**Upgrade `google/go-github` from v68 to v85.0.0 in a single PR that includes all necessary breaking-change migrations.**

The upgrade is done in one atomic commit set (not incrementally through each minor version) because:
- Intermediate versions do not contain the security fix.
- The breaking API changes are well-defined and limited to three function signatures and one type change; they can all be addressed in a single migration pass.

**Breaking changes to migrate (v68 → v85):**

| Symbol | v68 signature / type | v85 signature / type | Migration action |
|---|---|---|---|
| `GetOrgRole` | returns `*Role, *Response, error` | updated parameter or return set | Adjust call sites to match new signature; check for new required arguments |
| `CreateCustomOrgRole` | takes `CreateOrUpdateCustomRoleOptions` | signature updated | Update struct literal and call site |
| `UpdateCustomOrgRole` | takes `CreateOrUpdateCustomRoleOptions` | signature updated | Update struct literal and call site |
| `MarkThreadDone` | takes `int64` thread ID | takes `string` thread ID | Convert all `int64` thread ID values to `string` at the call site |

If mctl-agent does not currently call `GetOrgRole`, `CreateCustomOrgRole`, or `UpdateCustomOrgRole` (these are org-role management APIs, not PR-creation APIs), those symbols will be caught by a compile-time error during `go build` and confirmed as unused. Only `MarkThreadDone` (Notifications API) is likely to be an active call site if the Telegram notification path uses thread-based notification dismissal.

**Steps:**
1. Update `go.mod` import path from `github.com/google/go-github/v68` to `github.com/google/go-github/v85` and run `go get github.com/google/go-github/v85@v85.0.0`.
2. Run `go build ./...` to surface every broken call site as a compile error.
3. Fix each broken call site per the migration table above.
4. Run `go mod tidy` to clean up `go.sum`.
5. Update all test files that mock or import go-github v68 types.
6. Run the full test suite.

**Why this approach:**
- A compile-error-driven migration is safer than a runtime-driven one; all regressions surface before any binary is produced.
- Bundling all breaking-change fixes into one PR keeps the git history coherent and avoids a period where the code is partially migrated.
- The import-path major-version scheme (`/v85`) means the compiler enforces that all imports are updated.

## Alternatives

**A. Stay on go-github v68 and patch the cross-host redirect vulnerability manually.**
Patching this at the application layer (e.g., a custom `http.RoundTripper` that strips `Authorization` on cross-host redirects) is technically possible but duplicates logic that v85 provides and introduces a maintenance burden. Any future go-github upgrade would need to ensure the custom patch is still necessary. Dropped.

**B. Upgrade incrementally through each minor version (v68 → v70 → ... → v85).**
Each intermediate version bump would require a separate PR and CI run without closing the security gap until v85 is reached. The breaking changes are concentrated in the v68-to-v85 delta and are well-enumerated; incremental upgrades add churn without benefit. Dropped.

**C. Replace go-github with direct GitHub REST API calls using `net/http`.**
This would eliminate the dependency entirely but would require reimplementing pagination, retry, and auth-header management that go-github provides. The effort is disproportionate to the security benefit. Dropped.

## Platform impact

**Migrations:**
- `go.mod` import path changes from `/v68` to `/v85`; all files with `import "github.com/google/go-github/v68/..."` must be updated to `/v85/...`.
- `MarkThreadDone` call sites: any `int64` thread ID must be converted to `string` (e.g., `fmt.Sprintf("%d", id)` or storing the ID as a string from the point of receipt).
- `GetOrgRole` / `CreateCustomOrgRole` / `UpdateCustomOrgRole`: if used, signatures must be updated per the v85 release notes.

**Backward compatibility:**
- The go-github major-version bump is not backward compatible at the source level — this is intentional and enforced by the Go module import path convention. All call sites must be updated before the code compiles.
- The GitHub API wire format does not change; the PR-creation, commit, and branch APIs used by mctl-agent are unaffected at the REST level.

**Resource impact (labs tenant):**
- go-github is a thin REST client. The version bump does not introduce new background goroutines, caches, or connection pools. Memory and CPU impact are negligible. No risk to the labs tenant memory limit.

**Risks and mitigations:**
- Risk: A call site that passes an `int64` thread ID is missed during the migration and only fails at runtime. Mitigation: the import-path change forces a full recompile; `go build ./...` will catch all type mismatches at compile time, not runtime.
- Risk: New go-github v85 types cause mock objects in tests to drift from the real API. Mitigation: the test task (T2) requires updating all mocks before merging; CI enforces this.
- Risk: The GitHub App token is briefly exposed during a redirect in the window between PR merge and deploy. Mitigation: the token is rotated every 30 minutes; the exposure window is bounded. Deploy promptly after merge.
- Risk: go-github v85 has transitive dependency changes that conflict with another dependency. Mitigation: `go mod tidy` and `go mod verify` in CI will surface conflicts before the image is pushed.
