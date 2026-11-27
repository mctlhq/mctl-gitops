# Dependency maintenance and exact-revision vulnerability verification for mctl-api

## Context
Issue mctlhq/mctl-api#1195 (parent mctlhq/.github#417, R1, P1, tracking/proposed only) asks for
the owner-provided dependency maintenance baseline to be checked against current `main` and the Go
module graph. The work should find items that are already fixed or duplicated, confirm upstream
advisories and the patched versions that are compatible, and propose the smallest update that changes
only dependencies. Reachability must be shown with govulncheck. The work must keep three things apart:
the module being present, its code being linked, and actual exposure. It must also show that auth,
OAuth, MCP, proxy-aware client IP and rate limiting do not regress. Remaining findings go into the
canonical SecurityFinding lifecycle (mctl-api#774, `docs/security-findings.md`). Provenance is
required: exact revision, tool and database versions, and before/after evidence.

An investigation at `main` 0352f3af9e67c10bbc75f0ba12b368dd9434d848 with the CI-pinned govulncheck
v1.7.0 (symbol scan level, go1.26.11, vuln.go.dev last modified 2026-11-24T15:56Z) found no reachable
(symbol-level) advisories. It found three advisories at module level only: two in
`golang.org/x/net` v0.60.0, which is indirect and pulled in through `k8s.io/client-go`, and one in
`github.com/mark3labs/mcp-go` v1.0.0, which is direct. For `golang.org/x/net`, a tagged fix is
available (v0.62.0). For `mcp-go`, the only fixed version is an untagged pseudo-version. The gap that
matters is in the toolchain. `go.mod` declares `go 1.26.11` and CI's govulncheck runs on that
toolchain. The image is built with `golang:1.27.4-alpine` (`Dockerfile`), and govulncheck v1.7.0
cannot load the 1.27.4 stdlib in source mode. So the standard library that actually ships is never
checked for reachability today, and no CI job scans the built image. Advisory identifiers are
deliberately left out of this public proposal, as the issue requires.

## User stories
- AS a platform security owner I WANT every dependency finding to be classified as present, linked or reachable, at an exact revision and digest, SO THAT dispositions rest on evidence rather than scanner noise.
- AS a maintainer I WANT the smallest dependency-only update that clears the fixable findings SO THAT auth, OAuth and MCP behaviour does not change unexpectedly.
- AS a reviewer I WANT tool and database provenance and before/after evidence SO THAT I can reproduce the verdict on my own.
- AS an operator I WANT findings that are not fixed recorded as SecurityFinding occurrences with a justified disposition SO THAT none of them is silently dropped.

## Acceptance criteria (EARS)
- WHEN the baseline is validated THE SYSTEM SHALL record, for each baseline item, one of: already fixed on main, duplicate of an existing issue or PR (including .github#222, mctl-agents#809/#813), fixable now, or exception candidate. Each record SHALL include the exact `main` SHA it was checked against.
- WHEN govulncheck runs THE SYSTEM SHALL record scanner version, Go toolchain version, DB URL and DB last-modified timestamp. It SHALL classify each finding as module-level (present), package-level (linked) or symbol-level (reachable).
- WHEN the candidate update is prepared THE SYSTEM SHALL change only `go.mod` and `go.sum`, and SHALL bump `golang.org/x/net` to v0.62.0 or the lowest tagged version that fixes the scoped advisories.
- IF the only fixed version of a dependency is an untagged pseudo-version (currently `github.com/mark3labs/mcp-go`) THEN THE SYSTEM SHALL NOT adopt it without separate owner approval. It SHALL instead record a SecurityFinding occurrence marked as an exception candidate, with the module-level-only (not reachable) evidence.
- WHEN the candidate revision is built THE SYSTEM SHALL check that `go mod tidy` produces no diff, that `go mod verify` passes, and that `go build ./...`, `go vet ./...`, golangci-lint and `go test -p 1 ./...` (with Postgres) pass.
- WHEN the candidate revision is built THE SYSTEM SHALL pass the auth, OAuth and MCP regression tests (`internal/auth/...`, `internal/mcp/...`) and the proxy-aware client IP and rate-limit tests (`internal/api/clientmeta_test.go`, `internal/api/ratelimit_test.go`) unchanged.
- WHEN the candidate image is built THE SYSTEM SHALL run a fresh repository scan (govulncheck source mode and Trivy fs) at the exact commit SHA. It SHALL also run a built-image scan by image digest, covering govulncheck `-mode=binary` on `/usr/local/bin/mctl-api` (so the shipped go1.27.4 stdlib is covered) and a Trivy image scan of the alpine layer.
- WHILE the toolchain declared in `go.mod` differs from the builder image toolchain THE SYSTEM SHALL record the stdlib reachability for the shipped binary as unknown unless the binary-mode scan produced it.
- IF any new finding appears in the after-scan that was not in the before-scan THEN THE SYSTEM SHALL block the candidate until an owner approves a disposition.
- WHEN the work is complete THE SYSTEM SHALL publish only summarised evidence (counts, levels, module names, fixed versions) in public issues. Raw scanner output and advisory-level baseline details SHALL stay in the SecurityFinding store or in private artifacts.

## Out of scope
- Changes to auth or OAuth contracts, MCP tool shapes or release policy.
- Changing the `go.mod` `go` directive, the Dockerfile builder or base image, or CI workflow files. These are recorded as follow-up recommendations that need separate approval.
- Adopting the mcp-go pseudo-version or a major or minor jump of mcp-go.
- Agent runs, merge, deployment, live probing or production changes. Each of these needs a separate owner GO.

## Open questions
- The owner-provided baseline is not in the issue or in this clone, so it could not be reconciled item by item here. The implementer must get it privately. Until then, the govulncheck results above are the working baseline.
- The deployed mctl-api image digest was not observable (`mctl_get_service_config admins/mctl-api` returned not found, and there is no `services/*/mctl-api` path in gitops). "Before" image evidence must come from whichever digest the owner names.
- Should the toolchain mismatch (go.mod 1.26.11 vs builder 1.27.4, CI govulncheck on 1.26.11) be fixed under this issue or tracked separately? This proposal records it and treats it as separate, because it touches build and release policy.
- Is the mcp-go module-level advisory acceptable as a time-boxed exception until a tagged release exists, or does the owner want an upgrade evaluated? This proposal assumes an exception candidate.
