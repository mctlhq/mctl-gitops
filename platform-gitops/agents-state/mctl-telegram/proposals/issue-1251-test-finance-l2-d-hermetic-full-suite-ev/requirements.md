# Finance Assistant L2 slice D: hermetic full-suite evidence and a machine-checked blocking security gate

## Context

Issue mctlhq/mctl-telegram#1251 is dependent slice D of the Finance Assistant L2 fake-transport
research (#1244). Three earlier slices each added `//go:build l2finance` tests and a per-slice
report: slice A, the policy package (#1247, `docs/reports/finance-assistant-l2-results.md`); slice B,
listener and control (#1249, `docs/reports/finance-assistant-l2-slice-b.md`); and slice C, agentapi
and telegram (#1250 / #1255, `docs/reports/finance-assistant-l2-slice-c.md`). Each slice says outright
"no aggregation across slices". Nothing yet runs the whole matrix in one pinned run, checks it
against a manifest of required subcases, or derives `FINANCE_SECURITY_GATE` from the results by
machine. Today a green `go test` exit code is the only automated signal, and the reports are written
by hand.

The current tagged sources have gaps that stop a trustworthy aggregate:
- `internal/agent/policy/l2finance_result_test.go` hardcodes `rev=248db4f` and has no `TestMain`
  offline guard.
- The same IDs (`T8.kill`, `T9.finance_tier`, `OFFLINE.default_paths`, `OFFLINE.whole_process`)
  are emitted by more than one package.
- `M4` is emitted with the outcome token `PASS (detected)`, which contains a space and does not
  match the rubric.

Slice D adds test-only tooling and a consolidated report. With them, the full matrix gives
reproducible offline evidence and an independent `FINANCE_SECURITY_GATE` status. The tooling fixes
no security gap. Parent mctlhq/.github#325 stays `RESEARCH_ONLY_DEFER`.

## User stories

- AS the platform owner I WANT one pinned, offline run of every mandatory T1-T10 subcase and M1-M4
  control SO THAT I can see the real finance security posture without reading four reports.
- AS a reviewer I WANT a machine-checked aggregator that fails on missing, duplicate or unclassified
  rows SO THAT a green CI check can never be read as a security pass.
- AS a future security-fix author I WANT exact gap IDs with evidence SO THAT each follow-up fix
  issue has a bounded, testable target.

## Acceptance criteria (EARS)

- WHEN the slice-D runner executes THE SYSTEM SHALL run `go test -json -tags l2finance -race
  -count=1 -run L2Finance` over exactly `./internal/agent/policy/`, `./internal/agent/listener/`,
  `./internal/agent/control/`, `./internal/agentapi/` and `./internal/telegram/`, with
  `L2FINANCE_SOURCE_REV` set to the 40-hex `git rev-parse HEAD`.
- WHEN any tagged package starts THE SYSTEM SHALL abort before emitting a result unless
  `L2FINANCE_SOURCE_REV` is 40-hex. This includes the policy package, which today hardcodes
  `rev=248db4f`.
- WHEN any `L2RESULT` line is emitted THE SYSTEM SHALL format it as
  `L2RESULT id=<id> outcome=<PASS|FAIL/GAP|NOT-IMPLEMENTED|CANNOT-OBSERVE> rev=<40-hex> evidence=<text>`,
  with an outcome token that contains no spaces.
- WHEN the aggregator reads the run output THE SYSTEM SHALL key each row by its canonical ID
  `<package-short>:<id>`, for example `policy:T8.kill` and `control:T8.kill`, and compare the set
  against a committed manifest of mandatory canonical IDs.
- IF a manifest ID is missing, a canonical ID appears more than once, a row has an unknown outcome
  token, a row's `rev` differs from the pinned revision, or a row is not in the manifest THEN THE
  SYSTEM SHALL set `harness_status=INVALID` and exit non-zero.
- WHEN a mutation control M1, M2, M3 or M4 runs THE SYSTEM SHALL record PASS only if the same
  assertion helper used by the real case reports the injected mutation. The aggregator SHALL treat a
  missing or non-PASS M row as a harness failure, not as a security gap.
- WHILE any tagged test runs THE SYSTEM SHALL refuse non-loopback dials and external DNS through
  `net.DefaultResolver` and `http.DefaultTransport`, SHALL unset `TG_API_ID`, `TG_API_HASH` and
  `DATABASE_URL`, and SHALL use only fakes, `httptest` loopback and in-memory SQLite. The aggregator
  SHALL require every package's `OFFLINE.default_paths` row to be PASS.
- THE SYSTEM SHALL report `harness_status` (`COMPLETE` or `INVALID`) separately from
  `FINANCE_SECURITY_GATE` (`PASS` or `BLOCKED`).
- IF any mandatory row is `FAIL/GAP`, `NOT-IMPLEMENTED` or `CANNOT-OBSERVE`, or the harness is
  `INVALID` THEN THE SYSTEM SHALL output `FINANCE_SECURITY_GATE=BLOCKED`, even when `go test` exits 0.
  The output SHALL appear in the aggregator's stdout, in the generated Markdown, and in the manual CI
  job summary and artifact.
- WHEN the aggregator finishes THE SYSTEM SHALL map the overall result to exactly one issue outcome:
  - `COMPLETE_WITH_PASS`: harness complete, every row PASS.
  - `COMPLETE_WITH_GAPS_BLOCKED`: harness complete, at least one non-PASS row.
  - `INCOMPLETE_BLOCKED`: harness `INVALID` because rows are missing, duplicated or unclassified.
  - `CANNOT_OBSERVE_BLOCKED`: the run could not execute, for example a build failure, a missing
    revision or no JSON output.
- WHEN the consolidated report `docs/reports/finance-assistant-l2-results.md` is regenerated THE
  SYSTEM SHALL include:
  - the pinned SHA and Go version, and the exact commands;
  - the per-row table and counts by outcome;
  - the gap IDs with planned follow-up fix titles, which are not implemented here;
  - the results of `go vet -tags l2finance` and of untagged `go test -race ./...` for comparison;
  - an `L2RESULT` fixture-ID reproducibility check across two runs;
  - a statement that #325 `RESEARCH_ONLY_DEFER` is unchanged.
- WHILE this slice is in effect THE SYSTEM SHALL change no file outside these: `//go:build l2finance`
  test sources, the test-only aggregator package and runner script, an optional
  `workflow_dispatch`-only workflow with `permissions: contents: read` and no secrets, and the
  report.
- IF the manual workflow is added THEN THE SYSTEM SHALL trigger it only on `workflow_dispatch`, SHALL
  reference no `secrets.*`, and SHALL NOT be a required check or part of `build.yml`.

## Out of scope

- Any fix for the reproduced gaps (T7.2, T7.3.omit_job_id, T8.mode_off_after_queue,
  T8.mode_off_before_queue.delivery, T8.revoked_after_queue, T8.reply_kill, T10.denycode_persisted,
  T10.intent_channel) or for NOT-IMPLEMENTED finance tiers and consent.
- Finance Assistant runtime, bank/Plaid OAuth, CSV consent architecture, production rollout,
  managed runtime, live statements, live Telegram accounts.
- A whole-process egress firewall (for example a network namespace). It stays CANNOT-OBSERVE.
- New behavioural coverage beyond the existing matrix. The exception is ID or format normalisation
  that the aggregator needs.
- Creating the follow-up security-fix issues. The report lists them, and they are filed separately
  after human acceptance.

## Open questions

- Whether CANNOT-OBSERVE rows that are layer boundaries are mandatory or advisory. Examples:
  `T6.gap`, `T9.executor_peer_send`, `T10.traces`, `OFFLINE.whole_process`. Assumption: they are
  mandatory, so the gate stays BLOCKED. Re-classifying any of them needs a reviewed manifest change.
- Whether the slice-B and slice-C reports should be superseded or left in place. Assumption: they are
  left untouched. The consolidated `finance-assistant-l2-results.md` replaces only the partial slice-A
  content and cites the others.
- Whether golangci-lint is "available". It is not configured in `.github/workflows/build.yml` and
  there is no `.golangci*` file. Assumption: the report records lint as `not configured` rather than
  installing it.
- Whether the manual workflow is wanted at all. The issue says "optional". Assumption: add it,
  because a CI summary artifact is part of acceptance item 4.
- The approval reference for this slice must be a fresh grant. It is filled in after human approval
  and never reuses the #1244 grant (`aar_5dc0456105f442829583adaa101516c6`).

## AMEND: fail-closed aggregation and evidence integrity (normative)

This AMEND is part of the same **docs-only** #1251 proposal. Its criteria supersede conflicting
statements above; they are not an implementation approval. All new work stays in the test-only,
runner, optional manual-workflow and report scope already specified.

### A1 — Every failure must visibly block finance authorization (P1)

- BEFORE starting any test, the runner SHALL initialize a conservative machine-readable result:
  `harness_status=INVALID`, `FINANCE_SECURITY_GATE=BLOCKED`, and
  `issue_outcome=CANNOT_OBSERVE_BLOCKED`. This result SHALL be retained on preflight failure,
  interrupted or empty output, build failure, tagged test failure, vet failure, untagged comparison
  failure, manifest failure, or aggregator crash; no failing command may skip publishing it.
- The runner SHALL preserve exit codes from `go test`, `go vet`, comparison and the aggregator
  (including failures hidden by pipes) and use an EXIT trap/finalizer to write a failure summary
  and artifact. The workflow SHALL additionally run its summary/artifact publication with
  `if: always()`, publishing a minimal BLOCKED fallback when the runner produced none.
- `COMPLETE_WITH_GAPS_BLOCKED` is allowed to exit 0 **only** when the full test/vet/comparison
  pipeline succeeded, the manifest is valid, and the recorded non-PASS cases are intentional
  rubric observations. Infrastructure, test, or validation errors SHALL exit non-zero. A
  normal CI success or exit 0 SHALL never imply `FINANCE_SECURITY_GATE=PASS`.
- Distinguish a complete stream with failed assertions (`INCOMPLETE_BLOCKED`) from one that
  never produced trustworthy test evidence (`CANNOT_OBSERVE_BLOCKED`). Both SHALL set the
  security gate BLOCKED; an empty stream may never be classified COMPLETE.

### A2 — Test-time network scope must be explicit (P1)

- `go mod download` may run only as a named **preflight** before any L2 case; test execution,
  including the second run, vet and aggregator, SHALL use `GOPROXY=off`,
  `GOSUMDB=off`, `GOFLAGS=-mod=readonly` and cached dependencies. No runner step may
  silently re-enable module downloads. Missing dependencies SHALL fail closed with BLOCKED.
- Credential environment variables (`TG_API_ID`, `TG_API_HASH`, `DATABASE_URL` and
  other reachable integration credentials) SHALL be removed before executing tests.
  The five packages SHALL each have an `OFFLINE.default_paths` control validating refusal
  of non-loopback/default-resolution paths, while allowing loopback.
- Such default-path guards **do not prove a whole-process network firewall**. The runner and
  report SHALL preserve `OFFLINE.whole_process=CANNOT-OBSERVE` unless a separately verified
  sandbox actually denies all outbound network. Do not describe the suite as fully isolated
  or fully hermetic solely because those guards pass. No real credentials, customer data,
  live Telegram accounts or external finance endpoints may be introduced.

### A3 — Freeze the complete mandatory manifest before judging results (P2)

- Freeze a reviewed crosswalk from **each** mandatory #1244 T1–T10 subcase and M1–M4 to
  canonical `<package>:<case-id>` rows; distinguish different layers even when local IDs
  match. Record required cases without a current emitter as **MISSING**, not silently omit
  them or infer success. The crosswalk and list of missing emitters SHALL be independently
  reviewed before the manifest can yield COMPLETE.
- An unrecognized package, extra row, duplicate, malformed row, missing mandatory row,
  mismatched revision, non-PASS negative control or offline self-check SHALL make the
  harness INVALID, with BLOCKED gate. The three call sites of T1 wire must not emit
  duplicate canonical IDs in a run.
- Every one of the five packages (policy, listener, control, agentapi, telegram) SHALL
  emit its own passing `OFFLINE.default_paths`; this is **not** a substitution for
  `OFFLINE.whole_process`.

### A4 — Reproducibility and meaningful redaction evidence (P2)

- The two independent tagged runs SHALL compare the exact sorted canonical
  `(package,id,outcome,fixture_id)` tuples **and** pinned source revision. Required cases
  SHALL carry a stable, synthetic fixture identifier in structured evidence (or
  `fixture_id=none` where genuinely not applicable). The committed manifest SHALL define
  expected fixture-ID requirements; absence, unstable IDs or mismatch SHALL block COMPLETE.
  Test fixtures SHALL contain no actual personal/financial data.
- A redaction case cannot be called PASS merely because the log handler emitted **zero bytes**.
  Separate the existing durable-record check from the observable slog redaction check:
  require a non-empty synthetic log event that exercises the production redacting handler
  before a slog PASS; otherwise report `CANNOT-OBSERVE` with `slog_bytes=0`. Preserve the
  existing durable `agent_actions.intent` plaintext `FAIL/GAP`; do not hide it or silently
  change the slice-C report's historical outcome.
- The consolidated report SHALL expose the actual source/test revision, both statuses, every
  mandatory result, limitations, missing emitters and blocking gap IDs. Any change to the
  observed rubric (including a previously zero-byte redaction check) must be reviewed rather
  than promoting it silently.

### A5 — CI cadence and governance

- The optional `workflow_dispatch` is a manually triggered **evidence** job, not a
  production/security approval. If tagged vet/race checks remain absent from the normal
  `build.yml`, the report and issue SHALL explicitly record the residual regression
  exposure and a separately gated follow-up. Do not claim continuous CI coverage.
- Retain `status: proposed` until this AMEND merges, independent Claude/Agy review,
  canonical digest calculation, and a **separate** owner approval through the live
  Temporal DevLoop. No implementer, security fix, product enablement, deployment or pilot
  is authorized by this AMEND. `FINANCE_SECURITY_GATE=BLOCKED` and
  `RESEARCH_ONLY_DEFER` remain unchanged.
