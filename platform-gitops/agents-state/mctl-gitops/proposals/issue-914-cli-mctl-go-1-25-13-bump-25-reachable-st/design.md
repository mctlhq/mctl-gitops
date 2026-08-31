# Design: issue-914-cli-mctl-go-1-25-13-bump-25-reachable-st

## Current state
`cli/mctl` is a small Cobra-based CLI (module
`github.com/mctlhq/mctl-gitops/cli/mctl`, see `cli/mctl/go.mod`) with three
direct/indirect dependencies: `github.com/spf13/cobra v1.10.2`,
`github.com/spf13/pflag v1.0.9`, and `github.com/inconshreveable/mousetrap
v1.1.0` (all currently marked `// indirect` in `go.mod`, which is itself a
minor tidiness gap `go mod tidy` will likely fix as part of this change).
Commands live in `cli/mctl/cmd/*.go` (`root.go`, `deploy.go`, `config.go`,
`delete.go`, `status.go`, `logs.go`, `repo.go`, `auth.go`) and call the
mctl-api over HTTPS (`GetAPIURL()` in `cmd/root.go` defaults to
`https://api.mctl.ai`), so `crypto/tls` and `net/http` are on the hot path.
`cmd/auth.go` also shells out to `gh` per `README.md`, touching `os/exec`.

The `go` directive in `cli/mctl/go.mod` is `go 1.25.0`. There is no
`toolchain` directive, so the effective build toolchain is whatever `go`
binary is invoked, subject to Go's `GOTOOLCHAIN` auto-download behavior
(default `auto`) once the module requires a newer version than what's
installed.

Build tooling: `cli/mctl/Makefile` defines `build` (`go build ... -o mctl
.`) and `install` (`go install ...`). `cli/mctl/README.md` documents "Go
1.21+ (for building from source)" as the prerequisite and describes
`make build && ./mctl --help` as the smoke test.

CI: I searched every workflow in `.github/workflows/` (`agy-review.yml`,
`auto-merge.yml`, `build-image.yaml`, `claude-review.yml`,
`gitops-bump.yaml`, `no-root-yaml.yml`, `release-deploy.yaml`,
`security.yml`, `terraform.yml`, `validate-manifests.yml`, `yamllint.yml`)
for `setup-go`, `go-version`, or `cli/mctl` references. None exist.
`build-image.yaml` is a generic reusable Docker-build workflow parameterized
by `team_name`/`component_name`/`image_tag`, invoked by
`mctl_deploy_service`-style operations for platform *services* that ship a
`Dockerfile` — `cli/mctl` has no `Dockerfile` (confirmed: no file matches
`cli/**/Dockerfile*`) and is not built through it. `security.yml` runs a
Trivy filesystem scan (dependency/CVE scanning at the OS/package level, not
`govulncheck`) on PRs and a weekly cron; it scans the whole repo tree
including `cli/mctl/go.sum`, so a stdlib-level Go vulnerability wouldn't
necessarily surface there today the way `govulncheck` catches it. In short:
`cli/mctl` today has **no CI build/test coverage at all** — it is built
ad hoc via `make build`/`make install` by whoever runs it.

## Proposed solution
A minimal, mechanical toolchain-version bump, mirroring the pattern already
used for the analogous Go-runtime CVE proposals in
`platform-gitops/agents-state/mctl-api/proposals/go-upgrade-1262/` and
`platform-gitops/agents-state/mctl-agent/proposals/go-runtime-upgrade-v2/`:

1. **`cli/mctl/go.mod`**: change the `go` directive from `go 1.25.0` to
   `go 1.25.13`. Per Go's module semantics this both raises the minimum
   required toolchain and pins reproducible builds to a version that
   contains the stdlib security fixes covering all 25 advisories cited in
   the issue.
2. **`go mod tidy`**: run inside `cli/mctl` to normalize `go.sum` and the
   `require` block against the new `go` directive (this will likely also
   clean up the currently-misleading `// indirect` markers on `cobra` and
   `pflag`, which `root.go` and the `cmd/*.go` files import directly).
3. **Rebuild and smoke-test**: `make build` inside `cli/mctl`, then run
   `./mctl --help` and confirm it prints usage and exits 0, per the issue's
   acceptance criteria.
4. **`govulncheck ./...`**: run inside `cli/mctl` and confirm 0 reachable
   vulnerabilities (the issue's primary acceptance gate).
5. **`cli/mctl/README.md`**: update "Go 1.21+ (for building from source)"
   to "Go 1.25.13+ (for building from source)" so the documented
   prerequisite doesn't silently understate what the module now requires.
6. **CI pinned Go version**: not applicable — no workflow currently builds
   `cli/mctl` or pins a `setup-go` version (verified above). This task is
   satisfied vacuously; nothing to change. If a future proposal adds CI
   coverage for `cli/mctl`, it should pin `1.25.13` (or newer) from the
   start.

No application code in `cmd/*.go` needs to change: this is a pure
toolchain/stdlib patch bump within the same Go 1.x line, which Go
guarantees to be source-compatible.

## Alternatives

**Alternative 1: Bump to the latest Go 1.x (e.g. 1.26.x) instead of 1.25.13.**
Rejected for this proposal. The issue is scoped explicitly to "Go 1.25.13"
as the fix version for the 25 stdlib advisories found by the 2026-08-27
`govulncheck` DB snapshot against a `go 1.25.0` module. Jumping a minor
version (1.25 -> 1.26) is a larger, separately-reviewable change (new
minor releases occasionally deprecate/change tooling behavior, e.g. GOFLAGS
defaults) and isn't what the issue asks for. If 1.26.x is desired, that
should be its own proposal, consistent with how the mctl-api go-upgrade
proposals in this repo were split by target version (`go-upgrade-1262` is
a distinct proposal from earlier `go-upgrade` ones).

**Alternative 2: Add a `toolchain go1.25.13` directive instead of changing `go`.**
Rejected. A `toolchain` directive would pin the toolchain without raising
the module's declared minimum Go version, which is weaker: someone building
with an older, still-vulnerable local `go` binary and `GOTOOLCHAIN=local`
would not get the safe version enforced. Changing the `go` directive itself
is the standard, minimal fix and matches every prior Go-CVE proposal found
in this repo's `agents-state` history.

**Alternative 3: Do nothing until a CI pipeline for `cli/mctl` exists, and bundle CI creation into this fix.**
Rejected. The issue's acceptance criteria are about the vulnerability count
and the CLI building/running, not about CI infrastructure. Bundling a new
CI workflow (with its own `validate-manifests.yml`/`claude-review.yml`
review surface, since it would be a `.github/workflows/*.yml` change) into
a P1 security-audit fix would slow down closing the vulnerabilities and
mixes two concerns. Recorded as an open question / follow-up instead.

## Platform impact
- **Migrations**: none. No Kubernetes manifests, ArgoCD Applications, or
  Helm values change — `cli/mctl` is not deployed as a platform service
  (it has no entry under `platform-gitops/services/`).
- **Backward compatibility**: Go guarantees source compatibility across
  the 1.x series, and 1.25.0 -> 1.25.13 is a patch release (bug/security
  fixes only, no language or stdlib API changes). Existing `cmd/*.go` code
  is expected to compile and behave identically.
- **Resource impact**: none. This changes only the build-time toolchain,
  not runtime resource usage of any deployed service.
- **Risks and mitigations**:

| Risk | Likelihood | Mitigation |
|---|---|---|
| A dependency (`cobra`, `pflag`, `mousetrap`) doesn't build cleanly under the new `go` directive | Very low — these are widely-used, actively maintained modules | `make build` + `go vet ./...` before considering the change done |
| Contributor/CI machine has an older `go` binary than 1.25.13 installed | Low | Go's default `GOTOOLCHAIN=auto` will download the matching toolchain automatically; documented in the updated README prerequisite |
| `go mod tidy` pulls in an unexpected transitive dependency bump with its own advisory | Very low, none expected for this dependency set | Review the `go.sum` diff in the PR; re-run `govulncheck ./...` after tidy |
| Issue's "bump pinned CI setup-go version" criterion is silently unmet because no such CI exists | N/A (informational) | Explicitly documented above and in `tasks.md`/`requirements.md` as vacuously satisfied, not skipped |
