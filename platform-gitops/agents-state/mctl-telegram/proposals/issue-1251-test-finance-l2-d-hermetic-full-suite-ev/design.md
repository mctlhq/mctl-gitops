# Design: issue-1251-test-finance-l2-d-hermetic-full-suite-ev

## Current state

Repository HEAD at investigation: `d5b3a7d` (merge of #1256, slice-C recovery).

Tagged L2 sources, all `//go:build l2finance`:

| Package | Files | Harness |
| --- | --- | --- |
| `internal/agent/policy` | `l2finance_test.go`, `l2finance_result_test.go` | `l2Record` hardcodes `rev=248db4f`. There is no `TestMain`, no revision check and no offline guard. |
| `internal/agent/listener` | `l2finance_harness_test.go`, `l2finance_listener_test.go` | `TestMain` requires 40-hex `L2FINANCE_SOURCE_REV`, unsets `TG_API_ID`/`TG_API_HASH`/`DATABASE_URL`, and swaps `net.DefaultResolver` and `http.DefaultTransport.DialContext` for `l2GuardDial` (loopback only). |
| `internal/agent/control` | `l2finance_harness_test.go`, `l2finance_notifier_test.go` | Same `TestMain` and guard. M2 and M3 are emitted as `l2Record(t, "M2", l2Pass, "detected")`. |
| `internal/agentapi` | `l2finance_harness_test.go`, `l2finance_api_test.go` | Same guard. M4 is emitted as `l2Pass+" (detected)"`, an outcome token with a space. |
| `internal/telegram` | `l2finance_sendself_test.go` | Same guard. `T1.wire_input_peer_self` is reached from three call sites. |

Every package repeats the helpers `l2Record`/`expectGap`, the four outcome constants, and
`errL2ExternalDial`. `expectGap` calls `t.Fatalf` once a gap stops reproducing, so a gap cannot be
renamed to PASS silently.

IDs emitted by more than one package (from a grep of `l2Record`/`expectGap` call sites):

| ID | Packages |
| --- | --- |
| `T8.kill` | policy and control |
| `T9.finance_tier` | policy and agentapi |
| `OFFLINE.default_paths` | at least two |
| `OFFLINE.whole_process` | at least two |

Because of these collisions, a flat-ID aggregator would report false duplicates.

Reports:

| File | Content |
| --- | --- |
| `docs/reports/finance-assistant-l2-results.md` | Slice A partial: policy only, gate BLOCKED. |
| `docs/reports/finance-assistant-l2-slice-b.md` | 26 rows, gate BLOCKED. |
| `docs/reports/finance-assistant-l2-slice-c.md` | 24 rows, gate BLOCKED. |

All three are hand-written and each says "no aggregation across slices".

The mandatory matrix is defined in mctl-gitops
`agents-state/mctl-telegram/proposals/issue-1244-spike-test-finance-assistant-l2-owner-pr/`:
`requirements.md` T1-T10, and `design.md` lines 95-98 and 152-167 for M1-M4. That source requires
three things:
- a machine-validated per-case manifest;
- an error on any missing, duplicate or unclassified row;
- `FINANCE_SECURITY_GATE=BLOCKED` even when `go test` exits zero.

CI: `.github/workflows/build.yml` runs `go vet ./...` and `go test -race ./...` without the
`l2finance` tag, so tagged files are excluded. No golangci-lint step or config exists. The precedent
for manual workflows is `.github/workflows/live-telegram.yml`: `workflow_dispatch`,
`permissions: contents: read`. The precedent for test-only tooling is `scripts/gate-889/`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/` exists, so the service is deployed in tenant
  `labs`. A preview, `mctl-telegram-preview`, also exists. This slice changes no deployed config and
  produces no image change, because tagged test files are excluded from the default build and the
  aggregator lives only in `_test.go` files. I read no runtime config, because none is relevant.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-telegram/proposals/` holds the #1244, #1249, #1250 and #1255
  proposals. The #1244 `.status.yaml` reads `status: merged`.
- The mctl MCP tools were not called. No deployed-state question bears on a test-only change.

## Proposed solution

### 1. Harness alignment (tagged test sources only)

- `internal/agent/policy/l2finance_result_test.go`: add the same `TestMain` as the other packages,
  with the 40-hex `L2FINANCE_SOURCE_REV` check, the env unsets and the resolver/transport guard.
  Replace the hardcoded `rev=248db4f` with `l2SourceRev`. Add an `OFFLINE.default_paths` self-test
  row so that every package proves its guard.
- `internal/agentapi/l2finance_api_test.go`: emit M4 as outcome `PASS`, with `detected` moved into
  evidence, matching M1-M3.
- If the three `T1.wire_input_peer_self` call sites can all fire in one run, give them distinct
  suffixes, or make them exclusive branches. This is verified by running, and the aggregator's
  duplicate check enforces it.
- Expected outcomes do not change. `expectGap` rows stay `expectGap`.

### 2. Test-only aggregator: `internal/l2finance/gate/` (only `_test.go` plus `testdata/`)

- `testdata/manifest.txt` is the committed list of mandatory canonical IDs, one per line, written as
  `<pkg>:<id>`, where `<pkg>` is the last path element (`policy`, `listener`, `control`, `agentapi`,
  `telegram`). The list is built from the current call sites and checked against the #1244 T1-T10
  and M1-M4 definitions. Each line carries a `kind` column, `case`, `control` or `offline`, so that
  M rows and OFFLINE rows are validated as harness integrity.
- `gate_test.go` (`//go:build l2finance`), with test `TestL2FinanceGate`:
  - reads the `go test -json` stream from the path in `L2FINANCE_RESULTS_JSON`, plus `L2FINANCE_SOURCE_REV`;
  - takes the package from each event's `Package` field and parses `Output` lines with the strict
    regex `^\s*\S+:\d+: L2RESULT id=(\S+) outcome=(PASS|FAIL/GAP|NOT-IMPLEMENTED|CANNOT-OBSERVE) rev=([0-9a-f]{40}) evidence=(.*)$`;
  - treats any line that contains `L2RESULT` but does not match the regex as unclassified;
  - sets `harness_status=INVALID` on a missing manifest ID, a duplicate canonical ID, an
    unclassified row, an unknown outcome, a rev mismatch, an ID not in the manifest, a `control` or
    `offline` row that is not PASS, or any package with `Action=fail` in the stream;
  - sets `FINANCE_SECURITY_GATE=PASS` only if the harness is COMPLETE and every `case` row is PASS.
    Otherwise it sets BLOCKED;
  - maps the overall result to the issue outcomes. No stream, a build failure or a bad revision is
    `CANNOT_OBSERVE_BLOCKED`;
  - writes a Markdown fragment to `L2FINANCE_SUMMARY_MD` (default `$TMPDIR`). The fragment has a
    status block, counts, a row table sorted by canonical ID, and a gap list. stdout always ends with
    the literal lines `harness_status=...` and `FINANCE_SECURITY_GATE=...`;
  - exits non-zero only for `harness_status=INVALID`. A COMPLETE but BLOCKED result exits 0, because
    the gate is reported, not encoded in the exit code. The runner surfaces BLOCKED explicitly.
- Unit tests in the same package feed synthetic streams to the parser. They cover a missing row, a
  duplicate, a space in the outcome token, a wrong rev, an unknown ID, an M row FAIL, and all-PASS.
  The all-PASS case is the only one that yields gate PASS. This tests the aggregator itself and
  makes sure it is not tautological.

An empty Go package directory with only `_test.go` files compiles under `go test` and adds nothing to
`go build ./...`. The default `go test ./...` excludes it because of the build tag.

### 3. Runner: `scripts/l2finance/run.sh` (test-only)

The script performs these steps:
1. Pins the revision: `REV=$(git rev-parse HEAD)`. It fails unless the work tree is clean, so that
   there is no runtime code drift.
2. Runs `go test -json -tags l2finance -race -count=1 -run L2Finance` over the five packages, writing
   to `$OUT/results.json`.
3. Runs `go vet -tags l2finance` on the five packages plus `internal/l2finance/gate`.
4. Runs the untagged `go test -race -count=1 ./...` for comparison.
5. Runs golangci-lint only if it is on PATH, and otherwise records `not configured`.
6. Runs `go test -tags l2finance -count=1 ./internal/l2finance/gate/` with the env pointing at the
   stream.
7. Runs a second tagged run and diffs the sorted `(canonical id, outcome)` pairs. A difference means
   the fixtures are not reproducible, and the runner sets `harness_status=INVALID`.
8. Prints the status lines and exits non-zero on INVALID.

The runner sets `GOFLAGS=-mod=mod`, so modules come from the pre-populated cache. Dependencies are
downloaded before any test execution, and test-time egress stays guarded.

### 4. Optional manual workflow: `.github/workflows/l2finance-gate.yml`

The workflow has these properties:
- trigger: `on: workflow_dispatch` only;
- `permissions: contents: read`;
- no `secrets.*` and no environment;
- `actions/setup-go` pinned to SHA as in `build.yml`;
- `go mod download` runs as a separate step before the runner;
- the generated Markdown is written to `$GITHUB_STEP_SUMMARY`, and `results.json` plus the summary
  are uploaded as an artifact;
- the job succeeds on COMPLETE plus BLOCKED, but the summary's first line is
  `FINANCE_SECURITY_GATE=BLOCKED`.

The workflow is not added to required checks.

### 5. Consolidated report: `docs/reports/finance-assistant-l2-results.md`

Regenerated from the aggregator fragment, with these sections:
- the pinned SHA, Go version and commands;
- `harness_status`, `FINANCE_SECURITY_GATE` and the issue outcome;
- the full table and counts;
- the gap list. Each gap ID maps to a planned follow-up fix title (not filed, not implemented). For
  example, T7.2 maps to "Policy: treat InstallRevision=0 as fence-required".
- the M1-M4 detection evidence;
- vet, untagged-suite, lint and reproducibility results;
- the offline-guard limitation: `OFFLINE.whole_process` stays CANNOT-OBSERVE;
- a statement that mctlhq/.github#325 `RESEARCH_ONLY_DEFER` is unchanged and no pilot is authorised.

The slice-B and slice-C reports are left in place and cited.

Expected result given current code: `COMPLETE_WITH_GAPS_BLOCKED`. There are at least 8 FAIL/GAP
rows, about 5 NOT-IMPLEMENTED rows and several CANNOT-OBSERVE rows.

## Alternatives

- Flat IDs with renaming in every package: rename the colliding IDs, for example to
  `T8.kill.policy`. Dropped because it edits merged slice-B and slice-C evidence IDs and invalidates
  their reports. Package-qualified canonical IDs reach uniqueness without rewriting history.
- A shell or awk aggregator over `-v` text output. Dropped because text parsing cannot reliably
  attribute a line to a package, and a shell aggregator is harder to unit-test against tautology.
  Go plus `test2json` gives the `Package` field and runs under the same toolchain.
- A network-namespace sandbox (`unshare -n`) for a true whole-process no-egress guarantee. Dropped
  for now because it needs privileges on CI runners and differs between local and CI runs. It is
  recorded as a follow-up, and `OFFLINE.whole_process` stays CANNOT-OBSERVE.
- Making the gate fail the CI job (a non-zero exit on BLOCKED). Dropped because the gate is expected
  to be BLOCKED for the foreseeable future. A permanently red manual job conflates the harness
  failing with the gate being blocked, which is the very distinction the issue asks for.

## Platform impact

- No migrations, no production Go, no config or deploy change, no image change. Tagged and
  `_test.go`-only files are excluded from `go build` and from the default `build.yml` run.
- Backward compatibility: the slice-B and slice-C commands keep working. The policy package now
  requires `L2FINANCE_SOURCE_REV`, so the old slice-A command without it aborts with exit 2. The
  report documents the new command.
- Resource use: one manual workflow run is about two `-race` passes of five packages plus the full
  untagged suite, a few minutes on a GitHub runner.
- Risks and mitigations:
  - Risk: the manifest is drawn from the code, so it could encode today's omissions. Mitigation: the
    manifest review cross-checks each #1244 T1-T10 subcase and lists uncovered ones explicitly as
    manifest IDs with no emitter. The resulting MISSING rows force `INCOMPLETE_BLOCKED` until a
    reviewed change resolves them.
  - Risk: the aggregator itself is tautological. Mitigation: synthetic-stream unit tests, of which
    only all-PASS yields gate PASS.
  - Risk: the workflow leaks secrets or egress. Mitigation: `contents: read`, no `secrets.*` and the
    existing default-path guard. Tests unset Telegram and database env.
  - Risk: a green job is read as approval. Mitigation: `FINANCE_SECURITY_GATE=BLOCKED` is the first
    line of the summary and the report.
