# Design: issue-101-go-1-25-13-bump-dockerfile-go-mod-toolch

## Current state

- `go.mod:3` declares `go 1.25.0`, no `toolchain` directive. This is the
  minimum language version the module requires; `actions/setup-go@v7` in CI
  resolves the actual installed toolchain from this line via
  `go-version-file: go.mod` (used in `.github/workflows/security.yml:18-21`
  and `.github/workflows/validate.yml:16-19` and `:38-41`).
- `Dockerfile:1` builds the binary with `FROM golang:1.26-alpine AS
  builder` — a floating minor-version tag, not digest-pinned, and one minor
  version ahead of what go.mod declares. The runtime stage is `FROM
  alpine:3.24` (`Dockerfile:23`).
- `.github/workflows/security.yml` runs two jobs on PRs to `main` and a
  weekly cron: `govulncheck` (lines 13-34) and `trivy` (lines 36-49). The
  govulncheck job installs `golang.org/x/vuln/cmd/govulncheck@latest` with
  `GOTOOLCHAIN: auto` (needed because `setup-go@v7` otherwise pins
  `GOTOOLCHAIN=local`, per the comment at lines 22-25), then runs
  `govulncheck ./...` with `continue-on-error: true` (line 33) — so a
  reachable-vuln finding is reported but never fails the job or blocks a
  merge. The comment justifying this (lines 30-32) says the "current Go
  1.24 patch line still flags stdlib findings" — stale, since go.mod is
  already on 1.25.0, not 1.24.
- README.md's Tech Stack table (`README.md:35-44`) lists `Language | Go
  1.24` and `Router | go-chi/chi v5.2.1`; the Prerequisites section
  (`README.md:79`) repeats `Go 1.24+`. The actual go.mod requires
  `github.com/go-chi/chi/v5 v5.3.1` (`go.mod:5`) and `go 1.25.0` — both
  ahead of what the README states.
- `validate.yml` (build+lint+test) already reads the Go version from
  go.mod via `go-version-file`, so it needs no direct edit for the version
  bump — it will pick up whatever `go.mod` declares once changed.

## Proposed solution

1. **go.mod**: bump the `go` directive from `1.25.0` to `1.25.13` (the
   patched line per the govulncheck DB cited in the issue). No dependency
   version changes — chi is already at v5.3.1, which is what README needs
   to be corrected to match, not the reverse.
2. **Dockerfile**: replace the floating `FROM golang:1.26-alpine AS
   builder` with a digest-pinned `FROM
   golang:1.25.13-alpine@sha256:<digest> AS builder`, matching go.mod's new
   `go` directive at the same patch level. The digest is resolved once at
   authoring time (`docker pull golang:1.25.13-alpine && docker inspect
   --format='{{index .RepoDigests 0}}'`, or the equivalent `crane digest`)
   and hardcoded, following the same pattern the issue points to in
   mctl-telegram (pin builder images by digest, not floating tag, so a
   `docker build` today and in six months resolves to the identical bytes
   modulo explicit re-pin). The runtime `alpine:3.24` stage is untouched —
   out of scope per requirements.md.
3. **README.md**: update the Tech Stack table's `Language` row to `Go
   1.25.13` and `Router` row to `go-chi/chi v5.3.1`; update the
   Prerequisites bullet to `Go 1.25.13+` (or `Go 1.25+` — matching the
   table's precision is preferable so the two don't drift independently
   again; this proposal uses the exact patch version in the table and a
   `1.25+` floor in Prerequisites, since Prerequisites is describing a
   minimum for local dev, not a pin).
4. **security.yml**: remove `continue-on-error: true` from the govulncheck
   step (line 33) and replace the now-stale justifying comment (lines
   30-32) with a short note that the job is fail-closed following the
   1.25.13 bump. Leave the `GOTOOLCHAIN: auto` workaround for the
   `go install ...@latest` step untouched — that is an unrelated, still-valid
   constraint from `setup-go@v7` pinning `GOTOOLCHAIN=local`.
5. **Verification**: after the above, run `go mod tidy`, `go build ./...`,
   `go vet ./...`, `go test ./...`, and `govulncheck ./...` locally (or in
   CI) to confirm 0 reachable vulnerabilities and no build breakage from the
   patch bump. Go patch releases within a minor line (1.25.0 → 1.25.13) are
   contractually backward compatible per the Go 1 compatibility promise, so
   no source changes are expected beyond the version strings themselves.

This is a version/config-only change — no application code in
`internal/skill`, `internal/pipeline`, `internal/capability`, `internal/mcp`,
or `internal/api` is touched, and no new runtime behavior is introduced.

## Alternatives

- **Move go.mod to `1.26.6` and pin Dockerfile to `golang:1.26.6-alpine`
  instead.** This is the other option the issue explicitly offers, and it
  has the appeal of matching the Dockerfile's current (if unpinned) intent
  of using 1.26. Dropped in favor of staying on 1.25.x because: (a) it's a
  larger version jump for a change whose only stated goal is closing 27
  reachable CVEs, all of which are fixed by 1.25.13 alone; (b) a Go minor
  version bump (1.25 → 1.26) carries a nonzero chance of new vet/lint
  findings, deprecations, or runtime behavior changes that would need wider
  validation than a security-focused proposal should carry; (c) go.mod
  already declares 1.25.0 today, so treating the Dockerfile's 1.26 as the
  drift to fix (rather than the target to adopt) is the smaller diff.
  Recorded as an open question for the reviewer since it is a legitimate
  call either way.
- **Use a floating patch-pinned tag (`golang:1.25.13-alpine`) without a
  digest.** Rejected because the issue explicitly asks to "digest-pin the
  matching builder image ... following the mctl-telegram pattern," and a
  tag alone can be repointed upstream (Alpine base image rebuilds under the
  same tag), which defeats the reproducibility goal of pinning.
- **Add a `toolchain go1.25.13` directive to go.mod in addition to bumping
  `go`.** Considered to force an exact toolchain even under `GOTOOLCHAIN
  <different-value>`, but not adopted: `actions/setup-go@v7` already
  resolves the exact version from `go-version-file: go.mod`'s `go` line for
  the `validate.yml` build/test job, and the Dockerfile builder image is
  independently digest-pinned. Adding `toolchain` on top would mean
  changing two files (go.mod and Dockerfile) in lockstep on every future
  patch bump instead of one, with no additional guarantee this proposal
  needs. Left as a follow-up if a future incident shows local dev
  toolchains drifting.

## Platform impact

- **Migrations**: none — no data model, schema, or API surface changes.
- **Backward compatibility**: none expected. Go 1.25.0 → 1.25.13 is a patch
  bump under the Go 1 compatibility promise; `go build ./...` and `go test
  ./...` are expected to pass unchanged. The image's runtime behavior
  (binary entrypoint, exposed ports, `skills/custom` path handling) is
  unaffected since only the builder stage's base image changes.
- **Resource impact**: negligible. Digest-pinning the builder image does
  not change the final Alpine 3.24 runtime image size or contents; the
  builder stage is discarded after `go build`.
- **Risks**:
  - Digest pin goes stale relative to upstream Alpine/Go security patches
    within the `golang:1.25.13-alpine` tag family (Alpine package updates
    inside the same Go patch image). Mitigation: this is the same tradeoff
    mctl-telegram already accepted per the issue's own reference; the
    existing weekly Trivy `schedule: cron "27 4 * * 1"` scan in
    `security.yml` continues to catch drift in the filesystem/image, and a
    future proposal can add Renovate/Dependabot digest-update automation if
    desired (not in scope here).
  - Removing `continue-on-error` could turn a previously-silent govulncheck
    finding into a hard CI failure for any PR opened before this bump lands
    if a new vuln surfaces between authoring and merge. Mitigation: task
    ordering in tasks.md runs the version bump first and confirms 0
    reachable vulnerabilities locally before flipping the CI job to
    fail-closed, so the flip only lands once verified green.
  - If the reviewer prefers the 1.26.6 alternative, the Dockerfile digest
    and go.mod `go` line in tasks.md below would both need to target 1.26.6
    instead — flagged in Open questions in requirements.md so this is a
    one-line swap, not a redesign.
