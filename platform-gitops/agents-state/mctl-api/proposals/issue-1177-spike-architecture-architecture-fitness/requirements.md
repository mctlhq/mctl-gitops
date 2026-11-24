# Spike S0: architecture fitness functions and domain boundaries for mctl-api (with a separately gated S1 offline pilot)

## Context

Issue mctlhq/mctl-api#1177 asks for a research-only investigation (S0) into
enforceable internal domain boundaries ("architecture fitness functions") for
mctl-api. The goal is to reduce the code an agent has to read and the review
churn per change. It is not a platform rewrite, and it changes no service
deployment boundaries. The issue cites Agoda's modular-monolith write-up as
inspiration only. Its reported improvements are treated as observational and
are not targets or causal evidence for MCTL.

All findings are pinned to mctl-api HEAD `1fd4ed5e9308c482bd946399df89a57804eb1807`
(2026-11-24). Several findings change how the issue's framing applies:

- mctl-api is a Go module (`go.mod`: `go 1.26.11`), not Python. The Python
  tools the issue names (Import Linter, pytest/AST) cannot run on this code.
  The comparison is therefore made against Go options.
- The Go compiler rejects import cycles between packages, so there are 0
  package-level cycles by construction. Coupling shows up instead as fan-out
  and as transitive dependency leakage.
- The repo already has five ad-hoc import-boundary tests. A new mechanism
  must reuse that pattern rather than add a parallel gate.

The deliverable is this proposal (S0 findings), plus a bounded S1 offline
pilot that runs only after an explicit owner GO on the reviewed revision.

## User stories

- AS the mctl-api owner I WANT a source-pinned, reproducible inventory of
  package coupling SO THAT boundary decisions rest on measured evidence, not
  on assumed domain names.
- AS a reviewer of agent-authored PRs I WANT a new forbidden dependency
  edge to be reported automatically SO THAT I do not have to spot it in the
  diff.
- AS the DevLoop implementer agent I WANT the boundary rules for a package
  written in one discoverable place inside that package SO THAT I can work
  within them without reading the whole module.
- AS the platform owner I WANT the boundary policy and its baseline to be
  changeable only through reviewed human-owned edits SO THAT an agent cannot
  loosen the gate it is judged by.

## Acceptance criteria (EARS)

S0 (this proposal):

- WHEN the S0 proposal is published THE SYSTEM SHALL include a dependency
  inventory pinned to commit `1fd4ed5e` together with the exact commands
  that reproduce it (`go list -deps`, `go list -f '{{.ImportPath}} {{join .Imports " "}}' ./...`).
- WHEN the proposal names a candidate boundary THE SYSTEM SHALL cite the
  file paths and symbols that support it, and SHALL label each statement as
  either an observed fact or a hypothesis.
- WHEN the proposal compares tools THE SYSTEM SHALL record an explicit
  decision (reuse, adopt or no-go) for each option, with its version or
  source.
- WHEN the proposal reviews existing mechanisms THE SYSTEM SHALL map the
  existing purity/import tests, CI workflows, CODEOWNERS and ADRs, and SHALL
  NOT propose a second gate that duplicates them.

S1 (offline pilot, only after a separate owner GO):

- WHEN `go test ./internal/mcp/` runs THE SYSTEM SHALL compute the transitive
  dependencies of `internal/mcp` (production files only) and compare them
  with the boundary policy declared in `internal/mcp/boundary_test.go`.
- WHILE the pilot is in report-only mode THE SYSTEM SHALL log every edge
  that violates the policy and is not in the baseline, and SHALL NOT fail the
  test because of such an edge.
- IF a baseline entry no longer matches any current edge THEN THE SYSTEM
  SHALL fail the test, so that a fixed violation must be removed from the
  baseline (the baseline can only shrink).
- IF the number of baseline entries exceeds the ceiling constant in the test
  file, or an entry has no owner, reason or expiry, THEN THE SYSTEM SHALL
  fail the test.
- IF a baseline entry's expiry date has passed THEN THE SYSTEM SHALL report
  it as expired (report-only in S1).
- WHEN the checker runs against the negative fixtures THE SYSTEM SHALL
  report every planted violation. If it does not, the test fails, so a
  checker that sees nothing can never pass.
- IF `go list` fails or returns fewer than 10 dependencies THEN THE SYSTEM
  SHALL fail the test (fail closed), never pass silently.
- WHILE any boundary check runs THE SYSTEM SHALL preserve the existing
  security invariants: tenant isolation, authorization, MFA-gated approval,
  auditability and fail-closed behaviour. It SHALL NOT be presented as
  evidence of those invariants. Static imports alone do not establish
  security.

## Out of scope

- Any implementation PR in S0, and any production or staging mutation,
  deployment, dependency installation or upgrade, schema migration,
  credential or secret read, or proposal acceptance.
- A new required CI check, branch-protection change, or Merge Queue change.
- A mass refactor, moving packages, splitting `internal/api`, or
  consolidating or splitting microservices.
- Actually removing the baselined `internal/mcp` edges. That would be a later
  slice (S2), with its own proposal and approval.
- Switching the pilot from report-only to failing on new violations. That
  needs a separate approval after S1 measurement.
- A new approval mechanism. Existing DevLoop approval and PR review remain
  the only gates.
- Python tooling (Import Linter, pytest). It does not apply to this Go
  repository.

## Open questions

- The issue names Python tools. This proposal assumes the intent is "the
  credible equivalent for the real stack" and evaluates Go options instead.
  If the owner meant a Python repository elsewhere (for example
  mctl-agents), that is a separate spike.
- Whether branch protection on `main` requires code-owner review could not be
  observed from the clone. `.github/CODEOWNERS` is `* @MashkovD`, but
  CODEOWNERS only enforces anything when branch protection requires it. The
  baseline anti-laundering design assumes owner review; confirm it.
- `validate.yml` triggers on `pull_request` only, with no `merge_group`
  trigger. Whether a Merge Queue is enabled for mctl-api is unknown. If it is,
  any future required check needs a `merge_group` trigger.
- Deployed state: `mctl_get_service_status(admins, mctl-api)` reported no
  Argo CD application named `admins-mctl-api`, and there is no
  `services/*/mctl-api/values.yaml` under `$MCTL_GITOPS_ROOT`. The pilot is
  CI/offline only, so this does not block it. The real deployed name of
  mctl-api was not determined.
- The token, prompt and review-iteration telemetry needed for the
  measurement plan may not be attributable per PR today (see design.md
  "Measurement protocol"). This is an evidence gap, not a reason to invent
  numbers.
