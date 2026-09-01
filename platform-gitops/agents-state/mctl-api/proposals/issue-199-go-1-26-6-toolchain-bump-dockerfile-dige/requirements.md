# Go 1.26.6 toolchain bump, Dockerfile digest pin, fail-closed govulncheck

## Context
`go.mod` currently pins `go 1.26.0` and the Dockerfile builds from the floating
tag `golang:1.26-alpine` (`Dockerfile:1`). govulncheck (v1.7.0, DB 2026-08-27)
reports 25 stdlib vulnerabilities reachable from mctl-api code — including
html/template XSS (GO-2026-4982/4980/4865), an HTTP/2 infinite-loop DoS
(GO-2026-4918), and a TLS KeyUpdate DoS (GO-2026-4870), with call traces
through `http.Server.ListenAndServe` and `http.Client.Do` — all fixed in the
Go 1.26.6 stdlib. Because the toolchain is unpatched, `.github/workflows/security.yml`
carries an explicit `continue-on-error: true` on the govulncheck job (lines
23-25), with a code comment stating this is a stopgap until the toolchain is
bumped. mctl-api is the platform's control-plane API and MCP server; both its
CI vulnerability scanning and its production container image currently sit on
this unpatched base, and the floating `golang:1.26-alpine` tag also means the
image is not reproducible — a rebuild today can silently pull a different
patch layer than a rebuild tomorrow.

This proposal bumps the Go toolchain to 1.26.6 everywhere it is declared,
digest-pins the Dockerfile builder image for reproducible builds (matching
the pattern already used by mctl-telegram), flips the govulncheck CI job to
fail-closed now that the scan is expected to be clean, and pins the
govulncheck binary so that gate is reproducible.

The `k8s.io/client-go` ↔ `k8s.io/apimachinery` alignment the issue mentions
in passing is **deliberately excluded** (operator decision at approval).
It is the only part of the change that can break compilation, and it is not
a security fix — bundling it would mean that reverting a dependency-alignment
mistake also reverts the CVE patch. It gets its own issue and its own PR.

## User stories
- AS a platform operator I WANT mctl-api's container image built from a
  patched, digest-pinned Go toolchain SO THAT known-reachable stdlib CVEs
  (XSS, HTTP/2 DoS, TLS DoS) are closed in production and every build is
  byte-for-byte reproducible from the same base layer.
- AS a maintainer reviewing CI I WANT the govulncheck job to fail the build
  when a reachable vulnerability is found SO THAT new stdlib/dependency CVEs
  are caught before merge instead of silently ignored.
- AS a maintainer of this repository I WANT the govulncheck gate to be
  reproducible SO THAT an upstream release of the scanner cannot turn every
  PR red without a change on our side — the tool binary is pinned while its
  vulnerability database keeps floating.
- AS a reviewer I WANT to know whether "fail-closed" means the job fails or
  the merge is blocked SO THAT I do not assume a gate that is not configured.

## Acceptance criteria (EARS)
- WHEN `go.mod` is inspected THE SYSTEM SHALL declare `go 1.26.6` (or higher
  patch within 1.26) as the module's Go version.
- WHEN `go mod tidy` is run against the updated `go.mod` THE SYSTEM SHALL
  produce a `go.sum` with no unresolved or stale entries, and the module
  SHALL still build (`go build ./...`) and test (`go test ./...`) cleanly.
- WHEN the Dockerfile builder stage is inspected THE SYSTEM SHALL reference
  the builder image as `golang:1.26.6-alpine@sha256:<digest>` (a resolved,
  pinned digest) rather than the floating tag `golang:1.26-alpine`.
- WHEN the Docker image is built from the pinned digest on two different
  occasions with unchanged source THE SYSTEM SHALL produce a builder base
  layer that is bit-identical (same digest resolves to the same manifest).
- WHEN `govulncheck ./...` is run against the updated toolchain and
  dependencies THE SYSTEM SHALL report 0 reachable vulnerabilities.
- WHEN the `security.yml` govulncheck job runs in CI after this change
  THE SYSTEM SHALL NOT carry `continue-on-error: true`; a reachable
  vulnerability finding SHALL fail the workflow.
- WHEN `go.mod` is inspected after this change THE SYSTEM SHALL show the
  `k8s.io/api`, `k8s.io/apimachinery` and `k8s.io/client-go` require lines
  **unchanged** at `v0.36.1` / `v0.36.3` / `v0.36.1`. The alignment is out of
  scope here and must not arrive as a side effect of `go mod tidy`.
- WHEN the `govulncheck` job installs the scanner THE SYSTEM SHALL pin it to
  a specific release rather than `@latest`, while continuing to let the
  vulnerability database resolve at run time.
- WHEN the PR description describes the fail-closed change THE SYSTEM SHALL
  distinguish a failing job from a blocked merge, and SHALL NOT claim the
  latter unless `govulncheck` is a required status check in the ruleset.
- WHILE the `security.yml` workflow's `trivy` job is unrelated to this change
  THE SYSTEM SHALL leave it untouched (already fail-closed on unfixed
  CRITICAL findings per `security.yml:33-40`).
- IF `go mod tidy` after the version bumps does not fully resolve the
  25 reported vulnerabilities on its own (e.g. a transitive dependency needs
  an explicit bump) THEN THE SYSTEM SHALL add the minimal explicit
  `require`/`replace` entries needed so `govulncheck ./...` reports 0
  reachable findings, before flipping CI to fail-closed.

## Out of scope
- Rewriting or restructuring the `trivy` job in `security.yml` — it is
  already fail-closed and not implicated by this issue.
- **The `k8s.io/client-go` / `k8s.io/apimachinery` alignment** — excluded at
  approval, moved to its own issue and PR so the CVE fix stays independently
  revertible. Also any broader dependency upgrade beyond whatever
  `go mod tidy` must pull in to close the reported CVEs (e.g. no speculative
  bump of
  `mark3labs/mcp-go`, `go.temporal.io/*`, `github.com/jackc/pgx/v5`, etc.
  unless required to resolve a reachable vulnerability).
- Changing the final `alpine:3.24` runtime stage base image or its digest —
  the issue only asks for the *builder* stage to be digest-pinned, matching
  the mctl-telegram precedent cited in the issue.
- Automating digest refreshes (e.g. Renovate/Dependabot digest-pin update
  rules) — this proposal produces a one-time pin; keeping it current is a
  process concern outside this change.
- Any change to `agy-review.yml`, `claude-review.yml`, `validate.yml`, or
  `release-please.yml` — none of these reference the Go toolchain version or
  govulncheck.

## Open questions
- The exact sha256 digest for `golang:1.26.6-alpine` cannot be resolved from
  inside this read-only clone (no network/registry access here). The
  implementer will need to resolve
  `docker pull golang:1.26.6-alpine && docker inspect --format='{{index .RepoDigests 0}}'`
  (or `crane digest`) at implementation time and hardcode that resolved
  digest into the Dockerfile. Record the resolution date in a comment next
  to the `FROM` line, mirroring how `security.yml:34` already pins the
  `trivy-action` by digest with a version comment.
- ~~Which direction the `k8s.io/client-go` / `apimachinery` alignment should
  go.~~ **Moot: the alignment is out of scope here** (see Out of scope). The
  question is real and belongs on the follow-up issue, where getting the
  direction wrong costs a revert of a tidiness change rather than a revert of
  a security patch.
- Whether the 25 reported govulncheck findings are fully closed by the Go
  1.26.6 stdlib bump alone, or whether one or more also require a dependency
  bump (e.g. `golang.org/x/net`, `golang.org/x/crypto`) is not verifiable
  without running govulncheck against the updated toolchain, which requires
  network/build access not available in this read-only investigation.
  Captured as an acceptance criterion (fail-closed on remaining findings)
  rather than blocking the proposal.
