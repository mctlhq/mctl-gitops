# Go 1.25.13 toolchain bump for cli/mctl (25 reachable stdlib vulnerabilities)

## Context
`govulncheck` (vulnerability DB snapshot 2026-08-27) reports 25 reachable
standard-library vulnerabilities against `cli/mctl`, whose `go.mod`
(`cli/mctl/go.mod`) currently declares `go 1.25.0`. All 25 are fixed in the
Go 1.25.13 patch release. `cli/mctl` is the operator-facing CLI for the
mctl.ai platform (deploy, config, delete, status, logs, auth — see
`cli/mctl/cmd/*.go`); it talks to the mctl-api over HTTPS and shells out to
`gh`, so it exercises `crypto/tls`, `net/http`, and `os/exec` — exactly the
kind of stdlib surface these advisories tend to land in. This is part of
the platform's 2026-08 dependency audit (P1).

## User stories
- AS a platform operator running `mctl` from my workstation or CI, I WANT
  the CLI built with a patched Go toolchain SO THAT known stdlib
  vulnerabilities reachable from the CLI's code paths are closed.
- AS a maintainer of `mctl-gitops`, I WANT `govulncheck ./...` to run clean
  against `cli/mctl` SO THAT the platform audit finding is verifiably
  resolved and future regressions are easy to notice.

## Acceptance criteria (EARS)
- WHEN `cli/mctl/go.mod` is inspected THE SYSTEM SHALL show `go 1.25.13` as
  the `go` directive.
- WHEN `go mod tidy` is run inside `cli/mctl` after the bump THE SYSTEM
  SHALL produce a `go.sum` with no unresolved or stale entries (clean git
  diff after a second `go mod tidy` run).
- WHEN `govulncheck ./...` is run inside `cli/mctl` THE SYSTEM SHALL report
  zero reachable vulnerabilities.
- WHEN `make build` is run inside `cli/mctl` THE SYSTEM SHALL produce a
  working `mctl` binary.
- WHEN the built binary is invoked as `./mctl --help` THE SYSTEM SHALL
  print usage output and exit 0.
- IF a CI workflow pins a Go `setup-go` version for building `cli/mctl`
  THEN THE SYSTEM SHALL bump that pinned version to 1.25.13 (or a
  toolchain constraint compatible with it) so CI and local builds match.
- WHILE no such CI workflow exists for `cli/mctl` (see Open questions) THE
  SYSTEM SHALL NOT invent unrelated CI infrastructure as part of this
  change — the fix is scoped to the toolchain version and its immediate
  consequences.

## Out of scope
- Adding a new CI workflow to build/test/lint `cli/mctl` on every push
  (none exists today; see Open questions). Proposing that is a separate,
  larger change with its own review surface.
- Adding a `govulncheck` CI gate for `cli/mctl`.
- Any application-level code change to `cli/mctl/cmd/*.go` — this is a
  pure toolchain-version bump per Go's 1.x source-compatibility guarantee.
- Bumping direct dependencies (`cobra`, `pflag`, `mousetrap`) beyond what
  `go mod tidy` naturally does under the new `go` directive.
- Vulnerabilities in other services/modules in this repo (e.g. Terraform,
  Helm charts) — out of scope for this stdlib-in-cli/mctl issue.

## Open questions
- The issue says "if a CI job builds the CLI with a pinned Go setup-go
  version, bump it to match." A repo-wide search of
  `.github/workflows/*.yml(aml)` found no `setup-go` action and no
  workflow that builds or references `cli/mctl` at all — the CLI is
  currently built only via `make build`/`make install` (see
  `cli/mctl/Makefile`), not through CI. Resolution: treat this acceptance
  criterion as vacuously satisfied (nothing to bump) and note the gap in
  `design.md`/`tasks.md` rather than block on it. **Confirmed at approval**,
  with one requirement added: adding CI for `cli/mctl` stays out of scope,
  but a follow-up **issue** must be filed and cited in the PR (tasks.md
  approval decision 2). The gap is not cosmetic — with no CI, this bump is
  verified once by hand and nothing will catch the next batch of
  advisories, which is how the module reached 25 reachable findings in the
  first place.
- `cli/mctl/README.md` states "Go 1.21+ (for building from source)" as the
  documented prerequisite. Bumping to `go 1.25.13` raises the effective
  minimum (Go's toolchain directive semantics mean a `go 1.25.13` module
  requires a `go` command >= 1.25.13, or will auto-download a matching
  toolchain if `GOTOOLCHAIN=auto`, the Go default). This proposal updates
  the README prerequisite line to stay accurate. **Confirmed at approval** —
  keep the README edit; a documented prerequisite that understates the real
  floor by four minor versions is worse than no prerequisite line at all.
