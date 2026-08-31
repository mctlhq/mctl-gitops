# Go 1.25.13 stdlib bump, Dockerfile/go.mod toolchain alignment, README version sync

## Context

govulncheck (vuln DB 2026-08-27) reports 27 reachable stdlib vulnerabilities
against mctl-agent, all fixed in Go 1.25.13. Today `go.mod` declares `go
1.25.0` while `Dockerfile` builds with the floating `golang:1.26-alpine` tag
(`Dockerfile:1`) — the builder toolchain and the module's declared stdlib
floor disagree, and neither is pinned to a patched version, so the actual
stdlib shipped in the production image is not guaranteed to include the
1.25.13 fixes. `.github/workflows/security.yml` currently runs `govulncheck
./...` with `continue-on-error: true` (`security.yml:33`), with a comment
explicitly stating this is a stopgap "current Go 1.24 patch line still flags
stdlib findings that need a toolchain bump" (the comment is itself stale —
go.mod already reads 1.25.0, not 1.24). README.md separately advertises `Go
1.24` (`README.md:37`, `README.md:79`) and `go-chi/chi v5.2.1`
(`README.md:38`) as the stack, while go.mod already has `go 1.25.0` and
`github.com/go-chi/chi/v5 v5.3.1` — so the docs mislead anyone auditing the
dependency surface.

This matters because mctl-agent is the platform's self-healing GitOps agent
with GitHub write access and Telegram delivery; unpatched reachable stdlib
CVEs in a service with that blast radius are a real risk, and a
report-only vuln scan means regressions are silent. Fixing the version
drift and making the scan fail-closed closes both the immediate exposure
and the process gap that allowed it.

## User stories

- AS a platform operator I WANT the govulncheck CI job to fail on reachable
  vulnerabilities SO THAT a regression blocks the PR instead of merging
  silently.
- AS a security auditor I WANT go.mod, the Dockerfile builder image, and the
  README to state one consistent, patched Go version SO THAT a version scan
  of the repo reflects what actually ships in the image.
- AS a contributor reading README.md I WANT the documented Go and chi
  versions to match go.mod SO THAT I do not set up a toolchain that silently
  diverges from CI.

## Acceptance criteria (EARS)

- WHEN `govulncheck ./...` is run against the module after this change THE
  SYSTEM SHALL report 0 reachable vulnerabilities.
- WHEN the `security.yml` govulncheck job runs on a PR THE SYSTEM SHALL fail
  the job (non-zero exit, no `continue-on-error`) if govulncheck reports any
  reachable vulnerability.
- WHEN the Dockerfile builder stage is built THE SYSTEM SHALL use a
  `golang:<version>-alpine@sha256:<digest>` base image whose `<version>`
  matches the `go` directive in `go.mod` at the same patch level.
- WHILE go.mod declares `go 1.25.13` (the chosen line — see Open questions)
  THE SYSTEM SHALL use a Dockerfile builder image `golang:1.25.13-alpine`
  pinned by digest.
- WHEN a reader opens README.md THE SYSTEM SHALL find the Go version and
  go-chi/chi version listed there equal to the versions declared in
  `go.mod` (`go` directive and `github.com/go-chi/chi/v5` require line).
- IF the govulncheck job is green for a full CI run after the bump THEN THE
  SYSTEM SHALL have the `continue-on-error: true` line and its justifying
  comment removed from `.github/workflows/security.yml`.
- IF `go mod tidy` / `go build ./...` / `go vet ./...` / `go test ./...` are
  run after the go.mod bump THEN THE SYSTEM SHALL complete with no errors
  introduced by the version change alone.

## Out of scope

- Bumping any other dependency in go.mod (chi, go-github, sqlite, etc.)
  beyond what is already at the versions the issue asks README to match.
  Only go.mod's `go` directive and the Dockerfile base image move.
- Reworking the `security.yml` Trivy job, which is already fail-closed on
  CRITICAL unfixed findings and is not implicated by this issue.
- Fixing the README's CI/CD section, which still describes a
  `.github/workflows/build.yml` file (`README.md:157`) that does not exist
  in this clone — the actual release pipeline is
  `.github/workflows/release-please.yml` dispatching to mctl-gitops. This is
  a separate documentation drift, unrelated to the Go/chi version mismatch
  this issue reports, and is left for a follow-up proposal.
- Fixing README's "Container | Multi-stage Alpine 3.20" claim (`README.md:44`)
  against the Dockerfile's actual `alpine:3.24` runtime base — same class of
  drift as the Go/chi mismatch but not named in the issue's acceptance
  criteria; captured as an open question below rather than silently bundled
  in.
- Changing `GOTOOLCHAIN` behavior in CI beyond what's needed for the
  `govulncheck` install step already present in `security.yml`.

## Open questions

- The issue offers two options: pin go.mod to `1.25.13` or move the whole
  module to `1.26.6`. This proposal picks **1.25.13** (stay on the same
  minor line already declared in go.mod today) as the minimal-risk patch
  bump, and treats the Dockerfile's current `golang:1.26-alpine` as the
  stale side to correct rather than the target. Moving to 1.26.6 instead is
  a reasonable alternative (see design.md Alternatives) but pulls in a new
  Go minor version's toolchain/runtime behavior on a security-fix change,
  which is unnecessary risk for this proposal's goal. Reviewer should
  confirm this choice.
- README's stale "Alpine 3.20" claim and stale "build.yml" CI description
  (see Out of scope) are not part of this proposal; flagging in case the
  reviewer wants them folded in for a single documentation-consistency pass
  instead of a second issue.
- The `security.yml` comment block above the govulncheck install step
  references "Go 1.24 patch line," which is already inaccurate today (go.mod
  says 1.25.0). This proposal removes/rewrites that comment as part of
  dropping `continue-on-error` (task 4), rather than leaving stale prose
  behind.
