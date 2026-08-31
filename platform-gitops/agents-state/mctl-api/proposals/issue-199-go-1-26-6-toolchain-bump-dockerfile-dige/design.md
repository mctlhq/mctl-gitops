# Design: issue-199-go-1-26-6-toolchain-bump-dockerfile-dige

## Current state
Read directly from the clone:

- `go.mod:3` declares `go 1.26.0`, with no `toolchain` directive present. Direct
  deps include `k8s.io/api v0.36.1`, `k8s.io/apimachinery v0.36.3`, and
  `k8s.io/client-go v0.36.1` — apimachinery is already a patch ahead of
  client-go/api.
- `Dockerfile:1` builds the app with `FROM golang:1.26-alpine AS builder`, a
  floating minor-version tag (resolves to whatever the latest 1.26.x Alpine
  image is at pull time). The final stage (`Dockerfile:12`,
  `FROM alpine:3.24`) is untouched by this issue. The builder stage runs
  `go mod download`, copies source, and does a static build
  (`CGO_ENABLED=0 ... go build -ldflags="-s -w" -o /mctl-api ./cmd/api`).
- `.github/workflows/security.yml` runs two jobs on PRs to `main` and weekly
  cron: `govulncheck` (lines 14-27) and `trivy` (lines 29-40). The
  govulncheck job resolves its Go version from `go-version-file: go.mod`
  (line 20), installs `govulncheck@latest`, and runs `govulncheck ./...`
  with `continue-on-error: true` (line 24) — the comment directly above it
  (lines 22-25) says this is a deliberate stopgap "until a toolchain bump,"
  i.e. this issue's fix is exactly what the comment anticipates. The `trivy`
  job is already fail-closed (`exit-code: "1"`, `severity: CRITICAL`,
  `ignore-unfixed: true`, `trivy-action` pinned by digest at line 34) and is
  not touched by this issue.
- `.github/workflows/validate.yml` also resolves Go via
  `go-version-file: go.mod` for its `lint` and `test` jobs, so bumping
  `go.mod`'s Go version transparently upgrades the toolchain used there too
  — no separate edit needed in `validate.yml`.
- README.md:332 documents the `security.yml` job pairing ("govulncheck and a
  Trivy filesystem scan (CRITICAL, fail closed)") — this line becomes
  literally true again once `continue-on-error` is removed, and does not
  itself need editing.
- No `toolchain` directive, no existing digest pin anywhere in the repo's own
  Dockerfile (checked via grep across `*.yml`/`Dockerfile*`/`go.mod`); the
  only existing digest-pin precedent in this repo is the `trivy-action`
  action pin in `security.yml:34` (`# v0.36.0` comment alongside a SHA).
  There is no local copy of `mctlhq/mctl-telegram` in this clone to diff
  against directly; the issue's description of its Dockerfile pattern
  (`FROM golang:1.26.6-alpine@sha256:<digest>`) is taken as the reference
  and mirrored here, consistent with the digest-plus-version-comment style
  already used for `trivy-action`.

## Proposed solution
Four independent, additive edits, done in this order so that build/test
gates the CI-strictness flip:

1. **`go.mod` toolchain bump.** Change line 3 from `go 1.26.0` to
   `go 1.26.6`. Run `go mod tidy` so `go.sum` picks up any stdlib-adjacent
   metadata changes and the module graph is clean. This is the same
   mechanism `validate.yml`'s `lint`/`test` jobs and `security.yml`'s
   `govulncheck` job already use to resolve their Go version
   (`go-version-file: go.mod`), so no CI workflow YAML needs to change to
   pick up the newer toolchain for those jobs.

2. **`k8s.io/client-go` / `k8s.io/apimachinery` alignment.** While `go.mod`
   is open for the toolchain bump, update the `k8s.io/client-go` require
   line to the client-go release that is built/tested against
   `k8s.io/apimachinery v0.36.3` (or bump both to whatever mutually
   compatible pair `go mod tidy` resolves to, if a newer aligned pair exists
   at implementation time), and let `go mod tidy` reconcile `k8s.io/api` and
   the indirect `k8s.io/*` / `sigs.k8s.io/*` lines accordingly. Follow with
   `go build ./...` and `go test -p 1 ./...` (matching the exact test
   invocation `validate.yml`'s `test` job uses, including the `-p 1` flag
   documented at that job's comment) to catch any breaking API change in
   code under `internal/` before it reaches CI.

3. **Dockerfile digest pin.** Change `Dockerfile:1` from
   `FROM golang:1.26-alpine AS builder` to
   `FROM golang:1.26.6-alpine@sha256:<resolved-digest> AS builder`, with a
   trailing comment recording the resolution date/source (mirroring the
   `# v0.36.0` style comment already next to the digest-pinned
   `trivy-action` reference in `security.yml:34`). The digest must be
   resolved against the real `golang:1.26.6-alpine` manifest at
   implementation time (this read-only investigation has no registry
   access) — see Open Questions in requirements.md. The runtime stage
   (`FROM alpine:3.24`) is left as-is; only the builder stage is in scope
   per the issue.

4. **CI fail-closed flip.** In `.github/workflows/security.yml`, remove the
   `continue-on-error: true` line (24) and its preceding stopgap comment
   (22-23) from the `govulncheck` job, but only after step 1+2 are verified
   locally to produce `govulncheck ./...` with 0 reachable findings — doing
   this last avoids a red required check landing before the fix that makes
   it pass. If `govulncheck ./...` still reports reachable findings after
   the toolchain/dependency bump (per the fail-closed acceptance criterion
   in requirements.md), the minimal additional dependency bump needed to
   close them is applied before this step, not deferred.

This is a dependency/infra-only change: no application code paths, HTTP
handlers, MCP tool definitions, or database schema are touched. The four
edits are independent of each other (different files) and can be applied and
committed together in one PR, but are listed above in a dependency order for
verification purposes (toolchain+deps must be proven clean via local build
before the Dockerfile pin and before flipping the CI gate).

## Alternatives
- **Bump `go.mod` to `go 1.26.6` but leave the Dockerfile on the floating
  `golang:1.26-alpine` tag.** Rejected: this would still close the stdlib
  CVEs in Go's own reachability analysis (govulncheck uses `go.mod`/module
  source, not the container), but the *shipped* production image would
  continue floating on whatever patch Docker Hub resolves `1.26-alpine` to
  at build time — not necessarily 1.26.6, and not reproducible build-to-build.
  The issue explicitly calls out the Dockerfile as part of the fix and cites
  reproducibility ("Image builds reproducibly from the pinned digest") as an
  acceptance criterion, so this half-measure does not satisfy the issue.

- **Flip `security.yml`'s govulncheck job to fail-closed immediately,
  before confirming the scan is clean.** Rejected: the existing code
  comment on that job explicitly conditions fail-closed on "once the scan is
  clean" (this issue's own text repeats that framing). Flipping first would
  likely turn a currently-informational, always-green CI signal into a
  blocking, possibly-red one on the very PR that's supposed to fix it,
  creating a chicken-and-egg failure if any of the 25 findings survive the
  toolchain bump alone.

- **Use `docker.io/library/golang@sha256:<digest>` (digest-only, no tag) in
  the Dockerfile instead of `golang:1.26.6-alpine@sha256:<digest>`.**
  Rejected in favor of keeping the human-readable tag alongside the digest
  (`golang:1.26.6-alpine@sha256:...`), which is both valid Docker syntax and
  matches the issue's own example and the `trivy-action` precedent in this
  repo (`aquasecurity/trivy-action@ed142fd...` `# v0.36.0`) of pairing a
  digest with a readable version comment/tag for future maintainers.

- **Defer the `k8s.io/client-go`/`apimachinery` alignment to a separate,
  later change.** Considered, since it's a distinct concern from the CVE
  fix. Rejected because the issue explicitly bundles it in ("While here:
  align...") as a low-risk, low-cost addition to the same `go.mod` edit, and
  splitting it into a second proposal would mean touching `go.mod` twice for
  no added safety, given both edits are verified by the same
  `go build && go test` gate.

## Platform impact
- **Migrations / backward compatibility:** None. No database schema, HTTP
  API surface, or MCP tool surface changes. `internal/api/interfaces.go`-style
  interfaces are unaffected; this is purely a toolchain/base-image/dependency
  version change plus a CI workflow flag removal.
- **Resource impact:** None expected. Go 1.26.0 -> 1.26.6 is a patch-level
  stdlib update; binary size/behavior should be unaffected beyond the CVE
  fixes themselves. The Alpine builder image size is unchanged (same
  `golang:1.26.6-alpine` family, just pinned by digest instead of floating
  tag).
- **Risks:**
  - The `k8s.io/client-go` version bump could pull in an API change that
    breaks compilation somewhere under `internal/` (the module imports
    `k8s.io/client-go`, `k8s.io/api`, `k8s.io/apimachinery` directly per
    `go.mod`, implying real usage, e.g. for GitOps/cluster operations).
    Mitigation: `go build ./...` and `go test -p 1 ./...` must pass locally
    before opening the PR; if client-go's API shifted, fix the call sites in
    the same PR (per the requirements.md acceptance criterion) rather than
    deferring.
  - The digest resolved for `golang:1.26.6-alpine` could go stale if
    `golang:1.26.6-alpine` is later republished (rare, but Alpine base
    layers do get rebuilt for base-OS CVEs). Mitigation: this is an accepted
    tradeoff of digest pinning (reproducibility over auto-patching); the
    existing `trivy` job in `security.yml` continues to scan the built
    filesystem for CRITICAL unfixed CVEs regardless of which Alpine layer
    the digest resolves to, providing a safety net.
  - If govulncheck still reports reachable findings after the toolchain
    bump (e.g. a finding traces through a dependency rather than stdlib
    directly), flipping `continue-on-error` off first would immediately
    make PR checks fail-closed on unrelated future PRs. Mitigation: order of
    operations above — verify 0 findings locally before removing
    `continue-on-error`.
  - Weekly cron run of `security.yml` (Monday 04:17 UTC) will also pick up
    the fail-closed gate; if a *future* CVE appears after this change lands,
    the workflow will now fail on `main`'s scheduled run instead of silently
    passing. This is the intended outcome of the issue (fail-closed
    govulncheck) and not a regression to guard against, but worth flagging
    to reviewers as a behavior change in ongoing CI posture.
