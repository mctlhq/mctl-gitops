# Spike #746 slice 3: thin-adapter baseline, benchmarks, cross-builds and decision report

## Context

Spike #746 asks whether MCTL needs a portable agent-side runtime and, if it does,
whether a Rust single binary is the right way to build it. Slices 1 (#759, PR #761) and 2
(#764, PRs #768 and #770) added the std-only Rust crate `experiments/portable-runtime-rs/`.
It provides `proxy`, `init` and `doctor`, an in-process fake upstream, and cargo tests T2
to T10. The `portable-runtime-spike` job in `.github/workflows/portable-runtime-spike.yml`
is a required check. Slice 3 is the last slice. It adds the comparison baseline
(`baseline/thin_adapter.py`, a Python stdio-to-Streamable-HTTP passthrough on the
`mcp==1.29.0` SDK), a measurement harness, a cross-build matrix, the parity test T11 and
the decision report `docs/spikes/746-portable-runtime.md`. The report ends with exactly
one decision token. The token is proposed from the measured numbers. The verdict stays
with the owner and is recorded on #746.

The implementer image has no cargo and no network, so the slice is split into two phases
inside one PR. In the code phase, the implementer writes everything except the numbers.
In the measurement phase, the CI `bench` job produces the numbers on the PR. The shepherd
then commits that artifact into `docs/spikes/746/measurements/`, citing the run id, and
fills the measurements table. Slice 2 is http-only. This proposal does not add TLS (the
reason is in design.md). It records the TLS limit next to every size, build-time,
dependency and startup number, and in the GO-criteria checklist.

## User stories

- AS the #746 owner I WANT measured size, startup, RSS, latency, build and cross-target numbers for the Rust proxy and a Python thin adapter SO THAT the verdict rests on evidence rather than language preference.
- AS the #746 owner I WANT one report with the matrix, the Q1 to Q10 answers, the GO checklist and exactly one proposed token SO THAT I can record a verdict without re-running the investigation.
- AS a reviewer I WANT a parity test that shows both implementations answer the same `tools/list` and `tools/call` SO THAT the comparison is like-for-like.
- AS a maintainer of mctl-agents I WANT the slice confined to the experiment, `docs/spikes/` and the spike workflow SO THAT nothing shipped changes and the required check cannot be turned red by an unrunnable target.

## Acceptance criteria (EARS)

Baseline (task 8)
- THE SYSTEM SHALL provide `experiments/portable-runtime-rs/baseline/thin_adapter.py`, a stdio MCP server that forwards `tools/list` and `tools/call` to one Streamable HTTP `/mcp` upstream using only `mcp==1.29.0` and its transitive dependencies already in `uv.lock`.
- WHEN the baseline receives `tools/list` THE SYSTEM SHALL return only upstream tools whose names appear in the same `fixtures/allowlist.toml` the Rust proxy reads.
- IF the baseline receives `tools/call` for a name outside the allowlist THEN THE SYSTEM SHALL return `isError: true` with the same `not-eligible` content shape as the Rust proxy and make no upstream request.
- IF the allowlist file is missing, empty or invalid THEN the baseline SHALL exit with status 2 before serving, as `proxy` does.
- WHILE the baseline exists THE SYSTEM SHALL keep it out of every import path, out of the `pytest`, `ruff` and `mypy` scopes, and out of the container image, so that `tests/test_portable_runtime_isolation.py` keeps passing unchanged.

Parity (T11)
- WHEN the parity script runs against the fake upstream THE SYSTEM SHALL send the same request sequence to the Rust proxy and to the baseline, and SHALL fail if the parsed JSON `result` of `tools/list` or of any `tools/call` differs. The sequence is `initialize`, `tools/list`, and `tools/call` for `mctl_whoami`, `deny_tool`, `approval_tool`, `secret_tool` and an unknown name.
- WHEN the two responses are semantically equal but not byte-equal THE SYSTEM SHALL record the byte-level difference in the measurements output as a finding, and SHALL NOT fail T11.

Measurement (task 9)
- WHEN `bench/measure.sh` runs THE SYSTEM SHALL record, for the Rust proxy and for the Python baseline: release or package size, dependency count from `ldd`/`file` (`otool -L` on macOS), build time, cold start to ready (N=20, median and p95), idle RSS, RSS during a call, and first-call and steady-state latency overhead (N=100) against a direct HTTP call to the same fake upstream.
- THE SYSTEM SHALL write raw results as JSON and a Markdown table under `docs/spikes/746/measurements/`. Each record SHALL carry its status (`measured`, `unmeasured` or `failed`), its reason, the runner OS, the head SHA and the run id.
- IF a metric or target cannot be measured THEN THE SYSTEM SHALL record it as `unmeasured` or `failed` with a reason, and SHALL NOT record zero.
- WHILE `MCTL_RUNTIME_LIVE` is not `1` THE SYSTEM SHALL skip the live `api.mctl.ai` run and record it as `not run`. No job in this slice SHALL set it.
- THE SYSTEM SHALL label every size, build-time, dependency and startup number for the Rust proxy `http-only, TLS not included`.

Workflow (task 10)
- WHEN `changes.outputs.spike == 'true'` THE SYSTEM SHALL run a `parity` job (T11 plus the report check), a `bench` matrix job (ubuntu-latest, macos-14) and a `cross-build` matrix job. The cross-build targets are `x86_64-unknown-linux-musl`, `aarch64-unknown-linux-musl`, `aarch64-apple-darwin` and Windows compile-only.
- THE `portable-runtime-spike` required job SHALL depend on `changes`, `cargo` and `parity` only. `bench` and `cross-build` SHALL be informational. A target that cannot build or run on a GitHub runner SHALL record `failed` or `unmeasured` without turning any job red.
- WHEN the `bench` job finishes THE SYSTEM SHALL upload the measurements directory as an artifact named `portable-runtime-measurements-<os>` and write the table to `$GITHUB_STEP_SUMMARY`.
- WHILE the workflow is changed THE SYSTEM SHALL keep `permissions: contents: read` at workflow level, and every action reference SHALL be pinned to a full commit SHA.

Report (task 11)
- THE SYSTEM SHALL provide `docs/spikes/746-portable-runtime.md` with every section the issue lists, including the TLS limit note.
- THE report's `## Decision` section SHALL contain exactly one of `NO_RUNTIME`, `THIN_ADAPTER`, `PORTABLE_RUNTIME_RUST` or `PORTABLE_RUNTIME_OTHER`, and every line of the GO-criteria checklist SHALL cite a measurement file or a test id.
- IF the proposed decision is not `PORTABLE_RUNTIME_*` THEN the report SHALL NOT contain repository recommendations or follow-up issue drafts.
- WHEN the shepherd commits the bench artifact THE SYSTEM SHALL cite the producing run id in `docs/spikes/746/measurements/README.md` and in the report, and the run SHALL be on the PR's final head.

Containment
- THE SYSTEM SHALL change files only under `experiments/portable-runtime-rs/`, `docs/spikes/`, or `.github/workflows/portable-runtime-spike.yml`.
- WHILE this slice is in progress THE SYSTEM SHALL keep `cargo test --locked` (T2 to T10) and `uv run --locked pytest -q` passing unchanged, and `Cargo.lock` SHALL keep only the package itself.

## Out of scope

- Adding TLS (`rustls` or any other registry crate) to the crate. The limit is documented instead (see design.md).
- The live `MCTL_RUNTIME_LIVE=1` run against `api.mctl.ai`.
- Recording the owner's verdict on #746 or in `roadmap/spikes/portable-runtime.yaml` (mctlhq/.github).
- Any GO follow-up: new repository, release pipeline, host integrations, #757.
- Restarting or re-approving the failed #746 DevLoop. Closing #746.
- Changes to `orchestrator/`, `config/`, `agents/`, `tests/`, the Dockerfile, `pyproject.toml`, `uv.lock` or any manifest.

## Open questions

- Runner availability. The aarch64 musl binary is linked with `rust-lld` on ubuntu-latest and run on `ubuntu-24.04-arm` if that runner is available to the repository. If it is not, the aarch64 runtime numbers are recorded `unmeasured` (built, not run). This proposal assumes the arm runner may be unavailable and does not depend on it.
- Windows. The crate uses Unix-only APIs (`credential.rs` file-mode checks, `/proc` in tests). A Windows compile-only build may fail. If it does, the failure is recorded as Windows evidence. The proposal does not port the crate.
- Python SDK serialization. `mcp==1.29.0` re-serializes tool schemas through pydantic, so key order and number text (for example `1.50`) may differ from the upstream bytes the Rust proxy preserves (T2). T11 compares parsed JSON, and records any byte difference as a matrix finding, not as a failure. If the owner wants byte parity to be a hard requirement, the baseline cannot meet it without bypassing the SDK.
- Measurement phase ownership. The issue assigns the fix-up commit to the shepherd. If the shepherd cannot fetch artifacts, a human has to commit the artifact. The report must not be merged with an empty measurements table.
