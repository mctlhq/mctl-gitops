# Design: go-toolchain-bump

## Current state
Go 1.24, per `context/architecture.md`. The service serves AlertManager and Telegram webhooks and `/mcp` over net/http (chi/v5), and uses crypto/x509 for outbound TLS (GitHub, Anthropic, Telegram).

## Proposed solution
1. Verification first: determine the latest stable patch from go.dev/dl (not from third-party release notes), check the Go vulnerability database for the affected ranges of CVE-2026-78661, CVE-2026-97045 and CVE-2026-111943, and run `govulncheck ./...` plus `govulncheck -mode=binary` on the deployed image's binary for a baseline.
2. Bump the `go` directive (and `toolchain` directive if used) in `go.mod`, the Dockerfile builder image tag, and CI setup to the verified version. Candidate: 1.26.10 (unconfirmed).
3. Run `go vet`, the full test suite, and `govulncheck` again; fix any compile or vet breakage from the 1.24 to 1.26 language/stdlib changes.
4. Deploy via the normal ArgoCD flow to `admins`; compare RSS/CPU against the baseline.

Rationale: a toolchain bump is the only remedy for stdlib fixes; verifying first avoids pinning to an unconfirmed version.

## Alternatives
- Stay on 1.24 with the latest 1.24.x patch: smallest change, but 1.24 may be out of support and may lack the fixes; viable only if verification shows fixes are backported.
- Vendor patched x/net only via `go get golang.org/x/net@fixed`: fixes the x/net CVE but not stdlib net/http or x509 issues.
- Wait for the next Go minor: leaves a High CVE open; rejected.

## Platform impact
- Migrations: none (no data/schema change).
- Backward compatibility: Go compatibility promise; watch for behavior changes in net/http, crypto/tls and x509 defaults that might affect outbound calls.
- Resource impact: none for `labs` (agent runs in `admins`). Check RSS and GC behavior after deploy; no `labs` memory risk.
- Risks and mitigations: unverified target version (verification tasks first); new vet/lint failures (fix in the same PR); trust-store change from x509 distrust (confirm outbound endpoints do not chain through the distrusted eMudhra intermediates, which is unlikely).
