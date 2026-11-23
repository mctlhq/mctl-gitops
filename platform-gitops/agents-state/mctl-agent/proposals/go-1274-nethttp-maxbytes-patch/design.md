# Design: go-1274-nethttp-maxbytes-patch

## Current state
`context/architecture.md` lists Go 1.24, but earlier proposals (`go-toolchain-1263-patch`, `go-upgrade-1-26`, `go-toolchain-bump`, `bump-go-toolchain`, `go-toolchain-security-upgrade`, `go-runtime-patch`) targeted 1.26.x, and it is unknown which landed. The real baseline must be read from `go.mod`, the Dockerfile and the CI image. Webhook endpoints are served by `net/http` through chi.

## Proposed solution
1. Read the baseline (`go` directive, `toolchain` directive, Dockerfile `FROM`, CI image).
2. Verify the fix: check GO-2026-6859 in the Go vuln DB and the 1.26.11 / 1.27.4 release notes. Choose the lowest release listed as fixed. If sources still conflict, pick 1.27.4 or later, provided the baseline is on or can move to the 1.27 line without code changes.
3. Update `go.mod` (`go` and `toolchain`), the Dockerfile and the CI image to the same version. Verify the image digest.
4. Add a CI step `govulncheck ./...` that fails on findings. Keep it required for merge.
5. Run the full test suite plus a manual oversized-body request against `/api/v1/alerts` in staging.
6. Roll out via ArgoCD to `admins`.

This is a toolchain-only change. It stays narrow so it can merge quickly, and it is not bundled with dependency sweeps.

## Alternatives
- Stay on the current patch: leaves CVE-2026-97054 open; rejected.
- Mitigate in code (wrap handlers, smaller `MaxBytesReader` limits): does not remove the stdlib race and adds code; rejected as the primary fix.
- Bundle with chi and sqlite upgrades: delays the security fix and mixes rollback units; rejected.

## Platform impact
- Migrations: none.
- Backward compatibility: patch releases within a line are compatible. A move across lines (for example 1.26 to 1.27) needs a build and test run; verify the module still compiles.
- Resource impact: build-time only, no runtime memory growth. No impact on `labs` (the agent runs in `admins`).
- Risks and mitigations: conflicting sources on the fix (verify against the vuln DB, use 1.27.4 if unsure); image not yet published (check registry, fall back to the toolchain directive); `govulncheck` false positives or unrelated findings blocking CI (triage, allow-list only with a documented reason).
