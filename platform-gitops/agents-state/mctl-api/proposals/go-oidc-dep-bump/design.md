# Design: go-oidc-dep-bump

## Current state
`go.mod` currently specifies `github.com/coreos/go-oidc/v3` at a version that pulls in `go-jose/go-jose/v4 4.1.3` and `golang.org/x/oauth2 0.28.0`. These libraries handle cryptographic verification of all inbound bearer tokens across the three auth paths in mctl-api (see `context/architecture.md`, Auth flow). No known CVEs are open against `go-jose 4.1.3` at the time of writing; this bump is proactive hygiene to close the gap before any are disclosed.

## Proposed solution
This is a pure dependency version bump with no architectural changes.

1. Update `go.mod`: change `github.com/coreos/go-oidc/v3` to `v3.18.0`.
2. Run `go mod tidy` to resolve the updated transitive graph (`go-jose/v4 4.1.4`, `golang.org/x/oauth2 0.36.0`) and regenerate `go.sum`.
3. Verify the build compiles cleanly: `go build ./...`.
4. Run the full test suite: `go test ./...`.
5. Commit both `go.mod` and `go.sum`.

No source files outside `go.mod` and `go.sum` should require modification — `coreos/go-oidc v3.18.0` is API-compatible with all prior v3 releases.

## Alternatives

### Option A: Pin at current version and monitor for disclosed CVEs
Wait until a CVE is disclosed against `go-jose 4.1.3` before bumping. Rejected: this is precisely the reactive posture the proposal aims to avoid; the cost of the bump is trivially low (minutes of developer time, zero API changes) compared to the risk of operating on a known-stale JWT library.

### Option B: Replace `coreos/go-oidc` with a different OIDC library
Switch to `zitadel/oidc` or `ory/fosite` for JWT verification. Rejected: would require non-trivial code changes across three auth paths, introduces new API surface to audit, and provides no additional security benefit for this specific concern.

## Platform impact

### Migrations
None. No database schema changes, no Kubernetes manifest changes, no Vault policy changes.

### Backward compatibility
`coreos/go-oidc v3.18.0` is API-compatible with all prior v3.x versions. No call sites in mctl-api change. Existing tokens issued under the previous library version remain valid.

### Resource impact
No measurable change in CPU, memory, or binary size. No impact on the `labs` tenant.

### Risks and mitigations
- **Risk:** `go mod tidy` pulls in an unexpected additional transitive dependency that introduces a build conflict. **Mitigation:** `go mod tidy` output is reviewed in the PR diff before merge; CI enforces `go mod tidy` idempotency (the build fails if `go.sum` is not up to date).
- **Risk:** A behavioral change in `go-jose 4.1.4` or `oauth2 0.36.0` causes a subtle test failure. **Mitigation:** All three auth paths have existing unit and integration tests; a failure here is caught before deployment.
