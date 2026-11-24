# Design: issue-1177-spike-architecture-architecture-fitness

All facts are pinned to mctl-api `1fd4ed5e9308c482bd946399df89a57804eb1807`
(committed 2026-11-24), using toolchain `go1.26.11 linux/amd64`. "Observed"
means the result came from a command or file read listed here. "Hypothesis"
means it is not yet measured.

## Current state

### Stack and composition roots (observed)

- This is a Go module `github.com/mctlhq/mctl-api` with `go 1.26.11` and the
  dependencies chi/v5, mcp-go v1.0.0, pgx/v5 v5.9.2, Temporal SDK v1.50.0 and
  client-go v0.37.1 (`go.mod`). There is no Python in the production code
  path.
- The module has two binaries, and each is a composition root:
  - `cmd/api/main.go` is 3537 lines and imports 58 internal packages.
  - `cmd/mcp/main.go` is a thin stdio MCP server that talks to the API over
    HTTP (`MCTL_API_URL`, `MCTL_API_TOKEN`, lines 12-16) and imports only
    `internal/mcp`.
- `internal/api` is the HTTP composition layer:
  - 43,173 non-test lines in one package, including 76 `handlers_*.go` files.
  - It imports 52 internal packages and is imported only by `cmd/api`.
  - Dependency injection goes through interfaces in `internal/api/interfaces.go`
    (211 lines). Routes are defined in `internal/api/router.go` (1689 lines).
- `internal/mcp` (9,341 lines) defines 123 tools in `internal/mcp/server.go`.

### Import graph (observed)

Reproduce with:
`go list -e -f '{{.ImportPath}} {{join .Imports " "}}' ./...`
(78 packages, about 1 s locally).

- **Cycles:** 0 at package level. The Go compiler rejects import cycles, so
  this is guaranteed by construction. "Logical" cycles through interfaces
  injected in `internal/api/interfaces.go` and through callbacks wired in
  `cmd/api/main.go` (for example the `SetTenantOwnerChecker` wiring referenced
  in `cmd/mcp/main.go:22`) cannot be seen by any import-graph tool. This is a
  static-analysis blind spot.
- **Highest fan-in:**

  | Package | Fan-in |
  |---|---|
  | `internal/pgshared` | 23 |
  | `internal/glovo` | 14 |
  | `internal/workitems` | 14 |
  | `internal/auth` | 11 |
  | `internal/glovo/dbq` | 9 |
  | `internal/bridge` | 7 |

- **Highest fan-out:**

  | Package | Fan-out |
  |---|---|
  | `cmd/api` | 58 |
  | `internal/api` | 52 |
  | `internal/glovojoin` | 11 |
  | `internal/mcp` | 8 |
  | `internal/workitems` | 8 |

- **The canonical WorkItem package depends on a product domain:**
  `internal/workitems` imports `internal/glovo`, `internal/glovo/dbq` and
  `internal/glovo/orders`. This happens in `apply_glovo.go`,
  `apply_schema.go`, `glovo_approvals.go`, `glovo_basket_approvals.go`,
  `glovo_decisions.go`, `glovo_execution.go` and `glovo_verify.go`. A
  generic work-item layer that depends on one product domain points in the
  wrong direction (hypothesis about intent; the edge itself is observed).
- **Leakage into the thin MCP binary (main finding):**
  `go list -deps ./cmd/mcp` returns 675 packages. They include `jackc/pgx/v5`,
  `internal/glovo`, `internal/glovo/orders`, `internal/glovo/basket`,
  `internal/bridge`, `internal/workitems`, and 143 `go.temporal.io` or
  `k8s.io` packages. Yet `internal/mcp` uses these packages almost only for
  constants and helpers:
  - `workitems.ActionApprovalIDPrefix`, `MaxIntentPageLimit` and
    `CreateActionApproval` (`internal/mcp/workitems.go`)
  - `lifecycle.Status*` and `Diverge*` (`internal/mcp/lifecycle.go`)
  - `usage.MaxQueryLimit` and `GroupBy*` (`internal/mcp/usage.go`)
  - `temporalclient.WorkflowIDForIssueURL` (`lifecycle.go`, `server.go`)
  - `operations.NewRegistry` (`server.go`, `resources.go`)
  - `domains.StatusActive` (`server.go`)

  Which direct `internal/mcp` edge brings in which heavy dependency
  (`go list -deps ./internal/<p>`):

  | Edge | pgx | glovo | temporal | k8s |
  |---|---|---|---|---|
  | auth | yes | | | |
  | domains | yes | | | |
  | lifecycle | yes | | | |
  | usage | yes | | | |
  | workitems | yes | yes | | |
  | temporalclient | yes | yes | yes | |
  | operations | | | | yes |
  | telemetry | | | | |

  Hypothesis: these extra packages enlarge the binary, the attack surface
  and the context an agent must load when it edits `internal/mcp`. This is
  not measured in S0.

### Data access and ownership (observed, partial)

- pgx is used in 30 packages. `internal/api` itself contains pgx-touching
  code in `handlers_customer_deletion.go` (lines 26, 196, 281, 451) and
  `handlers_signup.go` (lines 18, 603), so the HTTP layer is not purely
  transport. Shared connection and migration primitives live in
  `internal/pgshared`, which has the highest fan-in (23). Treat it as a
  legitimate shared primitive.
- Table names referenced by more than one package:
  - `work_items`: `decisions`, `delegation`, `evidence`, `glovo/orders`,
    `workitems`
  - `work_item_executions`: `evidence`, `glovo/orders`, `workitems`
  - `agent_versions`: `agentregistry`, `mcp`, `operations`. In `mcp` and
    `operations` this is probably descriptive text rather than SQL (not
    verified).
- `lifecycle_ownership` is referenced only by `internal/lifecycle`, which
  makes it a clean single-owner store.
- This grep matches strings, so it is a heuristic, not proof of write
  ownership. Transaction boundaries across packages were not traced in S0.

### Candidate domains, by evidence

| Candidate | Packages | Evidence | Coupling |
|---|---|---|---|
| Identity/OAuth | `internal/auth` (+ `cimd`, `clientstore`, `flowstore`, `refreshstore`, `teamgrant`), `principals`, `zitadelhook`, `surfaceid` | `auth` fan-in 11, fan-out 6 (own subpackages + `surfaceid`) | Security-critical; wide blast radius |
| Agent registry | `internal/agentregistry` | imports only `pgshared` | Already a leaf; low value as a pilot |
| Lifecycle ownership | `internal/lifecycle` | imports only `pgshared`; single-owner table | Already clean |
| Usage | `internal/usage` | imports only `pgshared` | Already clean |
| Governance/approval | `internal/governance` (1 file), `decisions`, `reviewreceipts`, `reviewstore` | `governance` -> `auth`, `operations`, `workitems` | `reviewreceipts` already has a purity test |
| WorkItems / DevLoop | `internal/workitems`, `executionprovenance`, `evidence`, `temporalclient` | `workitems` fan-in 14, fan-out 8, depends on glovo | Highest coupling; schema-heavy; high risk |
| Glovo product | `internal/glovo*` (10 packages) | an existing `TestNoControlImport` boundary already applies | Already partly guarded |

### Existing architecture fitness tests (observed; reuse these)

| Test | What it guards |
|---|---|
| `internal/reviewreceipts/purity_test.go` | Forbids `database/sql`, pgx, `net/http`, `/internal/{api,auth,mcp,lifecycle,evidence}` through `go list -deps` |
| `internal/executionprovenance/purity_test.go:22` | Same `go list -deps` pattern |
| `internal/glovojoin/schema_test.go:571-588` (`TestNoControlImport`) | Forbids `internal/glovo/control`; fails closed if `go list` returns fewer than 10 dependencies |
| `internal/api/page_shell_test.go:93` | AST `parser.ImportsOnly` scan forbidding `html/template` and `text/template` outside `page_shell.go` |
| `internal/mcp/arg_validation_test.go:216`, `internal/workitems/attach_path_test.go:156` | AST-based structural tests |
| `internal/glovo/control/seam_release_test.go`, `internal/glovojoin/seam_release_test.go` | Build-tag seam tests |

These tests do not share a helper, have no baseline, and have no
owner/expiry metadata. Each one hard-codes its own matching rule.

### CI, governance and ADRs (observed)

- `.github/workflows/validate.yml` runs on `pull_request` to `main`. It runs
  `golangci-lint` v2.11.4 and `go test -p 1 ./...` with a Postgres 16
  service. Because the existing purity tests are ordinary `go test` tests,
  they already run inside this workflow, so they add no new CI job. There is
  no `merge_group` trigger.
- `.golangci.yml` enables errcheck, govet, staticcheck, unused, ineffassign,
  gocritic, gosec, bodyclose and nilerr. depguard is not enabled.
  `run.go: "1.24"` differs from `go.mod` (`1.26.11`). This is a finding only;
  it is out of scope here.
- Other workflows:
  - `security.yml` (PR, push and weekly cron)
  - `claude-review.yml` and `agy-review.yml` (AI review on PR)
  - `agent-trailer-check.yml` (labels PRs with the `Agent:` trailer;
    warning only; reusable workflow pinned at `mctlhq/.github@afb2328`)
- `.github/CODEOWNERS` contains `* @MashkovD`.
- `docs/adr/` holds one ADR (`0001-queue-execution-request-while-active.md`).
  No ADR covers module boundaries. Domain contracts are documented as prose
  in `docs/*.md` (for example `review-receipts.md`, `execution-provenance.md`
  and `principals.md`).
- Related proposals in `$MCTL_GITOPS_ROOT/agents-state`:
  - `mctl-api/proposals/issue-895-feat-review-tier-b-adapter-for-version-b`
    is the origin of the `reviewreceipts` purity rule ("Package and
    purity").
  - `mctl-agents/proposals/issue-1032-devloop-997-s1-deterministic-offline-imp`
    has a module-purity section (Python side).

  No proposal defines a cross-package boundary framework, so this proposal is
  not redundant with them.

### Deployed state checked

- `mctl_get_service_status(team=admins, service=mctl-api)` reported "ArgoCD
  application not found: admins-mctl-api". The deployed app name or tenant
  of mctl-api was not determined. This is recorded under Open questions,
  without assuming the service is absent.
- `ls $MCTL_GITOPS_ROOT/services/admins/` lists `mctl-agents-worker*`,
  `mctl-design`, `mctl-docs`, `mctl-support`, `mctl-web` and `umami`, with no
  `mctl-api` directory. No other tenant directory was found holding a
  `mctl-api` service.
- The proposal changes nothing deployed. S1 is test-only, so the deployed
  configuration does not affect it.

## Proposed solution

### Decision: reuse and generalise the existing `go list -deps` purity-test pattern

Make no new dependency and add no new CI job.

### Tool comparison

| Option | Source / version | Fit | Decision |
|---|---|---|---|
| Import Linter / pytest-AST (Python) | PyPI | Not applicable: the repo is Go | **No-go** |
| Existing `go list -deps` test pattern | Go toolchain in `go.mod`; 5 tests already in the repo | Transitive, compiler-accurate, runs in the existing `go test`. About 0.36 s for `go list -deps ./internal/mcp`. Blind to DI/interfaces | **Reuse (chosen)** |
| depguard (golangci-lint v2 built-in) | Shipped in pinned golangci-lint v2.11.4 (GPL-3.0 tool, not linked into the binary) | Direct imports only, no transitive check. Rules live in `.golangci.yml`, a single shared file | **Defer.** Possible S2 complement for direct-import rules; no baseline support |
| go-arch-lint (fe3dback) | Third-party, MIT | YAML layer model, transitive checks. Adds a CI tool dependency of uncertain maintenance; not in the lockfile | **No-go for S0/S1** (a new dependency) |
| Go `internal/` directory visibility | Compiler | Strongest (a compile error), but needs package moves, which is a refactor | **Later option** per domain; out of scope |
| `golang.org/x/tools/go/packages` custom analyzer | `x/tools` is not a direct dependency | Needs a `go.mod` change | **No-go** (dependency change) |

None of the static options can see interface-based DI or runtime
authorization. This is why S1 also pins behaviour contract tests (below).

### Pilot domain: `internal/mcp`

Why `internal/mcp`, by measured coupling, blast radius and risk:

- **Coupling:** it has the clearest measurable leak. The thin HTTP-client
  binary links pgx, glovo, Temporal and k8s, mostly for constants.
- **Blast radius:** low. It is imported only by `cmd/api`, `cmd/mcp` and
  `internal/api`. The S1 pilot adds a test file only.
- **Security:** `internal/mcp` is meant to reach state only through the
  authenticated API (`NewServer(apiURL, apiToken)`, `server.go:87`).
  `NewInProcessServer` (`server.go:104`) is the composition-root exception.
  A store dependency in this package is therefore a signal worth reviewing.
  It is not proof of a security bug.
- **Rejected pilots:**
  - `auth` and `workitems`: high blast radius, security- and schema-heavy.
  - `agentregistry`, `lifecycle` and `usage`: already leaves, so a pilot
    there would measure nothing.

### Pilot policy (S1, in `internal/mcp/boundary_test.go`)

- **Allowed direction:** `internal/mcp` may depend on the stdlib, mcp-go,
  `internal/auth` (token and scope types) and `internal/telemetry`. Nothing
  may depend on `internal/mcp` except `cmd/api`, `cmd/mcp` and
  `internal/api`, which are the composition roots.
- **Forbidden transitive dependencies (production files only):**
  - `github.com/jackc/pgx`
  - `database/sql`
  - `/internal/pgshared`
  - `/internal/glovo` (and subpackages)
  - `/internal/workitems`
  - `/internal/bridge`
  - `go.temporal.io/sdk`
  - `k8s.io/client-go`
- **Composition-root exception:** `NewInProcessServer` may stay in this
  package. The rule constrains imports, not who calls the package.
- **Test files:** checked through `go list -deps -test=false`, so `_test.go`
  imports are excluded.
- **Public interface:** the 123 tools registered in `server.go`. They are
  already pinned by the tool-count expectation in `server_test.go` (per
  CLAUDE.md).

### Baseline (S1)

The baseline is a Go literal in the same test file, not a separate YAML
file, so that only one file can change it. It lists the direct edges that
currently bring in a forbidden dependency:

`auth`, `domains`, `lifecycle`, `usage`, `workitems`, `temporalclient` and
`operations`, which is 7 entries.

Each entry carries `{edge, brings, owner, reason, expires}`. The owner is
the mctl-api owner, and the expiry is set by the owner at approval. Note the
tension: `auth` brings in pgx through `auth/refreshstore`. Whether `auth` is
an allowed edge with a recorded exception, or a violation, is an owner call
recorded in the baseline. It is not decided here.

### Checker

- A pure function `classify(deps, directEdges, policy, baseline)` returns
  `{newViolations, staleBaseline, expired}`.
- An integration wrapper runs `go list -deps -f '{{.ImportPath}}' .` and
  `go list -f '{{join .Imports " "}}' .`. It fails closed when `go list`
  errors or returns fewer than 10 dependencies, the same guard as
  `TestNoControlImport`.
- Attributing a transitive violation to a direct edge reuses `go list -deps`
  per direct edge (about 8 extra calls, each under 0.5 s).

### Ratchet semantics

1. **S1, report-only:** new violations go to `t.Log`, prefixed
   `ARCH-REPORT:` so they can be grepped from the CI log. The test fails only
   on:
   - checker integrity failures (`go list` failure, too few dependencies,
     negative fixtures not detected);
   - baseline hygiene failures (stale entry, missing metadata, count above
     the ceiling constant).

   Stale-entry failure means a fixed edge must be deleted from the baseline,
   so the baseline only shrinks.
2. **S2 (separate approval):** switch new violations to `t.Error`. This is a
   one-line change to a constant, reviewed as its own PR. It still runs
   inside the existing `validate.yml` `go test` job, so no new required check
   is added.

### Anti-laundering

- The baseline ceiling is a constant (7) in the same file. Raising it is a
  visible diff.
- The test rejects wildcard or prefix entries broader than a single package.
- The DevLoop implementer prompt and OpenSpec `tasks.md` treat
  `*boundary_test.go` as a protected path. The proposal-review step (an
  existing human review) must flag any agent diff touching it. This is
  advisory in S1; CODEOWNERS already maps it to the owner. Whether
  code-owner review is required is an open question.
- No environment variable or build tag disables the check. A skip by
  `testing.Short()` is not added.

### Negative fixtures

- Table-driven unit cases on `classify`:
  - a synthetic dependency list containing pgx gives 1 violation;
  - a `glovo/x` subpackage gives 1 violation (prefix rule);
  - `github.com/jackc/pgxfoo` gives no violation (boundary match: an exact
    match or a `/`-suffixed prefix only);
  - a stale baseline entry gives a stale result;
  - a missing expiry gives a hygiene failure;
  - an expired date gives an expiry report.
- An on-disk fixture `internal/mcp/testdata/violator/` with its own `go.mod`
  (module `example.test/violator`) importing `database/sql`. `testdata` keeps
  it out of `./...`. Running the wrapper against it must report the
  violation, which proves the `go list` integration path detects a real
  edge.

### Behaviour and authorization contract tests (not only the import graph)

Keep and reference the existing ones, and add one assertion:

- Every `internal/mcp` tool call built by `NewServer` sends
  `Authorization: Bearer <apiToken>` to `apiURL` and performs no other
  outbound I/O. This is tested with an `httptest` server.
- Refusals from the API (403 `decide_page_required`, 404 for a foreign
  tenant) are passed through unchanged, not turned into success. This
  preserves fail-closed behaviour.

Security invariants stay enforced where they live today, in `internal/api`
handlers, `internal/auth` and the MFA decide page. The boundary test is
explicitly not evidence for them.

### DevLoop integration (existing artifacts only)

- **Investigator:** cites the boundary test of a touched package in
  design.md.
- **OpenSpec tasks.md:** lists any edge change as an explicit task.
- **Implementer:** may not edit `*boundary_test.go`. This is an instruction
  in the existing implement-agent scope (`docs/implement-agent-scope.md`
  exists; the edit belongs to an mctl-agents follow-up).
- **CI:** `go test` emits `ARCH-REPORT` lines.
- **Independent review:** the existing `claude-review.yml` and
  `agy-review.yml` plus the owner.

No new approval mechanism is added. The rule file is under the gate it
enforces, so an agent editing it shows up as a protected-path diff in
review. It is never silently accepted.

### Measurement protocol

- **Checker metrics:**
  - CI runtime delta of `go test ./internal/mcp/`, measured locally and from
    `validate.yml` timings before and after (budget: under 5 s added to
    the test job);
  - false positives and false negatives on the fixtures and on a manual
    audit of `ARCH-REPORT` lines over 4 weeks;
  - baseline size over time.
- **PDLC metrics, stratified by task size (changed LOC buckets) and model:**
  - review iterations per PR;
  - P1/P2 findings per PR;
  - time-to-merge;
  - tokens or prompts per changed LOC, for PRs touching `internal/mcp` versus
    a matched set touching other packages.
- **Baseline window:** the 8 weeks before S1 merges.
- **Evidence gaps:**
  - per-PR token attribution may not be available. It depends on the usage
    ledger linking `pr` (`mctl_get_usage_summary` supports `repository`+`pr`
    filters; coverage is incomplete per mctl-agents#507);
  - the sample is small (few PRs touch `internal/mcp`);
  - confounders: model upgrades, reviewer changes, task mix.
- No improvement target is set and no causal claim is made. With fewer than
  about 20 PRs per stratum, report the results as descriptive only.

## Alternatives

1. **Enable depguard in `.golangci.yml` for all packages.** Dropped for S1.
   It sees direct imports only, so it would not catch the pgx leak through
   `lifecycle -> pgshared`. It has no owner, reason or expiry baseline, and
   one shared config file widens who can loosen every rule at once. It can be
   kept for S2 as a complementary direct-import rule.
2. **A repo-wide architecture test package (`internal/archfitness`) holding
   the policy for every domain.** Dropped for now. One central policy file
   becomes a single-point bypass and is a bigger first step. A shared helper
   can be extracted only after the S1 pilot shows value, and the 5 existing
   purity tests could then migrate to it.
3. **Restructure into `internal/<domain>/internal/...` for
   compiler-enforced boundaries.** Dropped. It is a refactor across many
   packages (`internal/api` alone is 43k lines), which the issue explicitly
   rules out.
4. **Adopt go-arch-lint.** Dropped. It adds a new third-party CI dependency,
   its maintenance would need review, and it gives no capability that the
   existing pattern cannot cover at this scale.

## Platform impact

- **Migrations:** none. **Runtime:** none. The pilot is a `_test.go` file
  plus a `testdata/` fixture, and the production binaries are unchanged.
- **Backward compatibility:** unaffected. No API, MCP tool or schema
  changes.
- **CI:** under 5 s added inside the existing `go test -p 1 ./...` step. No
  new job and no new required check.
- **Risks and mitigations:**
  - Hidden flakiness from `go list` needing the module cache: the existing
    tests already depend on it in CI, and the test fails closed with a clear
    message.
  - A report-only result being ignored: measure it, and decide in S2.
  - False confidence about security: stated explicitly; behaviour contract
    tests are kept.
  - An agent editing the policy: covered by the protected path, CODEOWNERS
    and owner review.
- **Governance:** S0 is research-only. S1 requires an explicit owner GO on
  the reviewed proposal digest, and an independent P1/P2/P3 review of this
  exact revision before any implementation decision.
