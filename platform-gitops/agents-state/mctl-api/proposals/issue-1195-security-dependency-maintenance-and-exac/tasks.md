# Tasks: issue-1195-security-dependency-maintenance-and-exac

- [ ] 1. Pin the target `main` SHA. Run govulncheck v1.7.0 (`-format json`, symbol level) and record the scanner version, Go version, DB URL and DB last-modified timestamp. — DoD: a private artifact holds the raw JSON, and a public summary lists each finding as module, package or symbol level, with no advisory IDs.
- [ ] 2. Get the owner baseline privately and classify each item as already fixed, duplicate (open Dependabot PRs, .github#222, mctl-agents#809/#813), fixable now or exception candidate (depends on 1). — DoD: every baseline item has a state and evidence, and anything that cannot be reconciled is marked unknown.
- [ ] 3. Check the upstream advisories and the patched versions that are compatible: x/net v0.62.0 is tagged; mcp-go has only a pseudo-version (depends on 2). — DoD: each fixable item names its lowest tagged fixed version and source.
- [ ] 4. Run `go get golang.org/x/net@v0.62.0` and `go mod tidy` (depends on 3). — DoD: only `go.mod` and `go.sum` change; `go mod tidy` produces no further diff; `go mod verify` passes; every transitive bump is listed, and any that touch auth-relevant modules are flagged.
- [ ] 5. Run the full CI on the candidate SHA (validate.yml and security.yml) (depends on 4). — DoD: lint, `go test` with Postgres, bridge PG tests, govulncheck and Trivy fs are all green.
- [ ] 6. Build the candidate image and record its digest. Scan the extracted binary with govulncheck `-mode=binary`, and scan the image with Trivy using a recorded version and DB timestamp (depends on 4). — DoD: there is image digest evidence; the go1.27.4 stdlib result is either produced or explicitly marked unknown.
- [ ] 7. Diff the before and after summaries (depends on 1, 5, 6). — DoD: the x/net findings are gone, there are no new findings, and anything new is blocked pending owner approval.
- [ ] 8. Record the SecurityFinding lifecycle entries: an observation for each remaining finding; an x/net remediation attempt with a verification record for the candidate SHA and digest; an mcp-go occurrence with a proposed exception (module-level only, review trigger: tagged upstream fix) (depends on 7). — DoD: the occurrences exist in the store, and the exception is still pending owner approval.
- [ ] 9. File the follow-up recommendations (toolchain alignment, a govulncheck version that supports go1.27, an image-scan CI job, an alpine digest pin) as separate issues (depends on 6). — DoD: issues are linked from #1195, and nothing is implemented without approval.
- [ ] 10. Get an independent review of the evidence pack (depends on 7, 8). — DoD: a reviewer other than the author signs off.

## Tests
- [ ] T1. `go test -count=1 ./internal/auth/...`: the OAuth, PKCE, preregistered-client, CIMD and federation tests pass unchanged.
- [ ] T2. `go test -count=1 ./internal/mcp/...`: the tool-count assertion in `server_test.go` still holds.
- [ ] T3. `go test -count=1 -run 'ClientIP|RateLimit|TrustedProxy|Loopback|KeyByTrustedIP' ./internal/api/`: the spoofed-XFF and trusted-proxy bucket tests pass.
- [ ] T4. `go test -p 1 ./...` with `TEST_DATABASE_URL` set, plus the `cd e2e && go test -v` suite where it is available.
- [ ] T5. `go mod tidy && git diff --exit-code go.mod go.sum` and `go mod verify`.
- [ ] T6. A govulncheck source scan at the candidate shows no x/net findings, and the binary-mode scan of the image binary shows no new findings.

## Rollback
The change is limited to `go.mod` and `go.sum`, so reverting the single dependency commit restores
x/net v0.60.0. Nothing changes in data, schema or config. If the change was already released, redeploy
the previous image digest through the normal release process. SecurityFinding records are append-only.
A failed remediation is recorded as a new attempt or verification and nothing is deleted.
