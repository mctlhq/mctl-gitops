# Dependency maintenance and exact-revision vulnerability verification for mctl-api

## Revision 2026-11-27
This revision applies the review amendment register
(https://github.com/mctlhq/mctl-api/issues/1195#issuecomment-7229398131). Scope stays dependency-only
and status stays proposed; the revision needs independent re-review and a fresh approval bound to the
new content digest.
- Evidence is kept in three layers: source/module graph, shipped binary and container image. UNKNOWN at
  any mandatory layer is not PASS and blocks security sign-off.
- Before and after evidence must have exact commits and image digests, comparable scanner versions, a
  vulnerability DB snapshot and recorded build conditions. Not being detected by a scanner does not
  count as safe.
- The mcp-go exception candidate needs a private baseline, artifact evidence, a risk owner, an expiry or
  review date and re-review triggers. This proposal approves no exception.
- Toolchain alignment, image scanning and base-image digest work is checked against the existing
  follow-ups (mctlhq/mctl-api#1196, mctlhq/mctl-gitops#3036) first and needs separate approval.

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
v1.7.0 (symbol scan level, go1.26.11, vuln.go.dev last modified 2026-11-24T15:56Z) detected no reachable
(symbol-level) advisories. That is a statement about the source/module graph on go1.26.11 only, not
evidence that the shipped artifact is safe. It found three advisories at module level only: two in
`golang.org/x/net` v0.60.0, which is indirect and pulled in through `k8s.io/client-go`, and one in
`github.com/mark3labs/mcp-go` v1.0.0, which is direct. For `golang.org/x/net`, a tagged fix is
available (v0.62.0). For `mcp-go`, the only fixed version is an untagged pseudo-version. The gap that
matters is in the toolchain and the artifact. `go.mod` declares `go 1.26.11` and CI's govulncheck runs
on that toolchain. The image is built with `golang:1.27.4-alpine` (`Dockerfile`), and govulncheck
v1.7.0 cannot load the 1.27.4 stdlib in source mode. CI's Trivy scan is a filesystem scan only. So
neither the standard library that actually ships nor the built image is covered by any CI scan today.
Advisory identifiers are deliberately left out of this public proposal, as the issue requires.

## User stories
- AS a platform security owner I WANT every dependency finding to be classified as present, linked or reachable, at an exact revision and digest, SO THAT dispositions rest on evidence rather than scanner noise.
- AS a maintainer I WANT the smallest dependency-only update that clears the fixable findings SO THAT auth, OAuth and MCP behaviour does not change unexpectedly.
- AS a reviewer I WANT tool and database provenance and before/after evidence SO THAT I can reproduce the verdict on my own.
- AS an operator I WANT findings that are not fixed recorded as SecurityFinding occurrences with a justified disposition SO THAT none of them is silently dropped.

## Acceptance criteria (EARS)
- WHEN the baseline is validated THE SYSTEM SHALL record, for each baseline item, one of: already fixed on main, duplicate of an existing issue or PR (including .github#222, mctl-agents#809/#813), fixable now, or exception candidate. Each record SHALL include the exact `main` SHA it was checked against.
- THE SYSTEM SHALL keep evidence in three separate layers: source/module graph (exact commit), shipped binary (the binary extracted from the image) and container image (image digest). Evidence from one layer SHALL NOT be reported as coverage of another.
- WHEN any scan runs THE SYSTEM SHALL record scanner name and version, Go toolchain version, vulnerability DB URL and snapshot (last-modified timestamp or DB version), the exact commit and, for binary and image layers, the image digest and build conditions (builder image, build flags). It SHALL classify each finding as module-level (present), package-level (linked) or symbol-level (reachable).
- WHEN before and after evidence is compared THE SYSTEM SHALL use exact before and after commits and image digests scanned with comparable scanner versions and DB snapshots. IF the two sides are not comparable THEN THE SYSTEM SHALL report the comparison as UNKNOWN.
- THE SYSTEM SHALL NOT treat scanner non-detection as evidence of safety. A layer that was not scanned, or whose scan failed or could not load the target, SHALL be recorded as UNKNOWN, not as clean.
- IF any mandatory verification layer is UNKNOWN THEN THE SYSTEM SHALL NOT report PASS and SHALL NOT issue security sign-off until the gap is resolved or explicitly dispositioned through the separate owner risk process.
- WHEN the candidate update is prepared THE SYSTEM SHALL change only `go.mod` and `go.sum`, and SHALL bump `golang.org/x/net` to v0.62.0 or the lowest tagged version that fixes the scoped advisories.
- IF the only fixed version of a dependency is an untagged pseudo-version (currently `github.com/mark3labs/mcp-go`) THEN THE SYSTEM SHALL NOT adopt it without separate owner approval. It SHALL instead record a SecurityFinding occurrence marked as an exception candidate, carrying the private baseline reference, evidence from each relevant artifact layer, a named risk owner, an explicit expiry or review date, and re-review triggers (tagged upstream fix, change in reachability, change in exposure). This proposal SHALL NOT approve the exception.
- WHEN the candidate revision is built THE SYSTEM SHALL check that `go mod tidy` produces no diff, that `go mod verify` passes, and that `go build ./...`, `go vet ./...`, golangci-lint and `go test -p 1 ./...` (with Postgres) pass, with evidence that the Postgres-backed tests ran rather than skipped.
- WHEN the candidate revision is built THE SYSTEM SHALL pass the auth, OAuth and MCP regression tests (`internal/auth/...`, `internal/mcp/...`) and the proxy-aware client IP and rate-limit tests (`internal/api/clientmeta_test.go`, `internal/api/ratelimit_test.go`) unchanged.
- WHEN the candidate image is built THE SYSTEM SHALL run a fresh repository scan (govulncheck source mode and Trivy fs) at the exact commit SHA. It SHALL first verify that the binary scanner supports the shipped toolchain, then run govulncheck `-mode=binary` on `/usr/local/bin/mctl-api` (so the shipped go1.27.4 stdlib is covered) and a Trivy image scan by image digest. IF either scan is unavailable or fails THEN THE SYSTEM SHALL report that layer as UNKNOWN and block mandatory verification.
- WHILE the toolchain declared in `go.mod` differs from the builder image toolchain THE SYSTEM SHALL record the stdlib reachability for the shipped binary as UNKNOWN unless a compatible binary-mode scan produced it.
- IF any finding appears in the after-scan that was not in a comparable before-scan THEN THE SYSTEM SHALL block the candidate until an owner approves a disposition.
- WHEN the work is complete THE SYSTEM SHALL publish only summarised evidence (counts, levels, module names, fixed versions) in public issues. Raw scanner output, advisory-level details and the private baseline contents SHALL stay in the SecurityFinding store or in private artifacts.

## Out of scope
- Changes to auth or OAuth contracts, MCP tool shapes or release policy.
- Changing the `go.mod` `go` directive, the Dockerfile builder or base image, or CI workflow files. Toolchain alignment, image scanning and base-image digest work is first checked against the existing follow-ups (mctlhq/mctl-api#1196, mctlhq/mctl-gitops#3036); anything they do not cover is recorded as a recommendation that needs separate approval.
- Adopting the mcp-go pseudo-version or a major or minor jump of mcp-go.
- Approving any exception or risk disposition.
- Agent runs, implementation, merge, release, deployment, live probing or production changes. Each of these needs a separate owner GO.

## Open questions
- The owner-provided baseline is not in the issue or in this clone, so it could not be reconciled item by item here. The implementer must get it privately. Until then, the govulncheck results above are the working baseline, and items that cannot be reconciled are UNKNOWN.
- The deployed mctl-api image digest was not observable (`mctl_get_service_config admins/mctl-api` returned not found, and there is no `services/*/mctl-api` path in gitops). The "before" image digest must be obtained from the owner before any before/after comparison; without it the image-layer comparison is UNKNOWN.
- The toolchain mismatch (go.mod 1.26.11 vs builder 1.27.4, CI govulncheck on 1.26.11) is treated as separate from this issue because it touches build and release policy. Whether mctlhq/mctl-api#1196 or mctlhq/mctl-gitops#3036 already covers it must be checked before a new follow-up is proposed.
- Is the mcp-go module-level advisory acceptable as a time-boxed exception until a tagged release exists, or does the owner want an upgrade evaluated? This proposal assumes an exception candidate; the decision belongs to the separate owner risk process.
