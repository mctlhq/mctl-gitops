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
