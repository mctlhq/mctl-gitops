# Tasks: issue-777-spike-runtime-746-slice-3-thin-adapter-b

All paths are relative to the repo root. Allowed paths: `experiments/portable-runtime-rs/`,
`docs/spikes/` and `.github/workflows/portable-runtime-spike.yml`.

- [ ] 1. Add `experiments/portable-runtime-rs/examples/fake_upstream.rs`. It includes
  `tests/common/fake_upstream.rs` through `#[path]`, starts
  `FakeUpstream::start(Knobs::default())`, prints `url()` on one stdout line, and blocks
  until stdin reaches EOF or SIGTERM. — DoD: `cargo clippy --locked --all-targets -- -D warnings`
  is clean, `Cargo.lock` is unchanged, and T2 to T10 are untouched.
- [ ] 2. Write `experiments/portable-runtime-rs/baseline/thin_adapter.py` (depends on 1).
  - It takes the flags `--upstream`, `--allowlist` and `--timeout-ms`, reads the
    allowlist with `tomllib`, and exits 2 on a missing, empty or invalid allowlist.
  - It reads the token from `MCTL_RUNTIME_TOKEN_FILE` or `MCTL_TOKEN` and never logs it.
  - It connects through `streamablehttp_client` and `ClientSession` upstream, and serves
    a lowlevel `Server` over `stdio_server`.
  - `tools/list` is filtered to the allowlist. A non-allowlisted call returns `isError`
    with the `not-eligible` text copied from `src/bridge.rs`, and makes no upstream call.
  - Allowlisted results pass through unchanged. Check the SDK source in `.venv` to see
    how a handler returns a `CallToolResult` verbatim.
  - It has a `# ruff: noqa` header and no new dependency, and nothing imports it.

  — DoD: it starts against the example fake upstream and answers `tools/list` and
  `tools/call`, and `uv run --locked pytest -q`, including
  `tests/test_portable_runtime_isolation.py`, is unchanged.
- [ ] 3. Write `experiments/portable-runtime-rs/examples/bench_driver.rs`, std-only
  (depends on 1).
  - Modes: `ready` (N=20, median and p95 to the `initialize` response), `latency` (N=100,
    first call plus steady-state median and p95, against direct
    `upstream::Upstream::call_tool`), `rss` (idle, and peak during `slow_tool`, from
    `/proc/<pid>/status` on Linux and `ps -o rss=` on macOS) and `parity` (canonical JSON
    of each `result`).
  - The spawn uses a cleared environment plus `PATH`, `HOME` and
    `MCTL_TOKEN=bench-token-746`.
  - Output is JSON lines with the fields `subject`, `metric`, `value`, `unit`, `status`,
    `reason`, `os`, `head_sha` and `run_id`.

  — DoD: clippy is clean, and the parity mode prints one line per request for the Rust
  proxy.
- [ ] 4. Write `bench/parity.sh` (T11) (depends on 2, 3). It starts the example fake
  upstream and runs `bench_driver parity` against `target/debug/mctl-runtime proxy` and
  against `$VENV/bin/python -I baseline/thin_adapter.py`. Both use the same
  `fixtures/allowlist.toml`. The request sequence is `initialize`, `tools/list`, and
  `tools/call` for `mctl_whoami`, `deny_tool`, `approval_tool`, `secret_tool` and
  `no_such_tool`. The script compares the parsed JSON, exits non-zero on a semantic
  difference, and writes byte differences to `$OUT/parity-bytes.md`. — DoD: the script
  passes locally in CI on ubuntu-latest, and fails if a `secret_tool` entry is added to
  the baseline's output.
- [ ] 5. Write `bench/measure.sh` and `bench/render_table.py` (depends on 3, 4).
  - `measure.sh` records the environment block, then for each subject: build time
    (`cargo build --release --locked` and `uv sync --locked`), size, `file`/`ldd`
    (`otool -L` on macOS) dependency count, and the `ready`, `latency` and `rss` driver
    modes.
  - It runs `uv run` cold start as a second Python number.
  - It writes the live record as `unmeasured` ("not run in this slice") unless
    `MCTL_RUNTIME_LIVE=1`.
  - Every Rust size, build, dependency and startup record carries
    `note: http-only, TLS not included`.
  - A failed step writes a `failed` record and the script continues, and no metric is
    ever written as 0 in place of missing.
  - `render_table.py` (stdlib only, run with `python -I`) writes `<os>.md`.

  — DoD: the script has no hard dependency on network or credentials, and the output
  schema is documented in `docs/spikes/746/measurements/README.md`.
- [ ] 6. Write `bench/check_report.sh` (depends on 7). It extracts the `## Decision`
  section of `docs/spikes/746-portable-runtime.md` and fails unless exactly one of
  `NO_RUNTIME`, `THIN_ADAPTER`, `PORTABLE_RUNTIME_RUST` or `PORTABLE_RUNTIME_OTHER` occurs
  in it. It also fails if any line of the GO-criteria checklist lacks a `measurements/`
  path or a `T<n>` test id. — DoD: it passes on the report, and fails on a copy that has
  two tokens or an uncited GO line.
- [ ] 7. Write `docs/spikes/746-portable-runtime.md` and
  `docs/spikes/746/measurements/README.md` (depends on 5).
  - The report includes every section listed in design.md "Report", including the 14-row
    matrix, Q1 to Q10, J3, J6 (a Mermaid sequence diagram and a Refuse-only
    `PaymentChallengeHandler` trait sketch, with no crate code), the AI Gateway /
    `createAI` boundary (findings routed to mctlhq/.github#184 G4), the `/sse` transport
    note, the TLS limit, the GO checklist G1 to G7 plus the Rust clause, and the Decision
    with one token proposed from G1, G2, G3, G4 and G7.
  - The recommendations and follow-up drafts appear only if the decision is GO.
  - The measurements table has every cell `unmeasured (pending bench run)` until the
    shepherd phase.

  — DoD: `check_report.sh` passes, and the four tokens appear together only outside the
  Decision section.
- [ ] 8. Extend `.github/workflows/portable-runtime-spike.yml` (depends on 4, 5, 6).
  - Add a `parity` job on ubuntu-latest, which is required. It runs setup-uv pinned to
    `37802adc94f370d6bfd71619e3f0bf239e1f3b78` (uv 0.11.11, Python 3.12), then
    `uv sync --locked`, `cargo build --locked --examples`, `parity.sh` and
    `check_report.sh`.
  - Add a `bench` matrix job on ubuntu-latest and macos-14, which is informational. It
    runs `measure.sh` with `OUT=$RUNNER_TEMP/measurements`, `RUN_ID` and `HEAD_SHA`, then
    `upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02` with the name
    `portable-runtime-measurements-<os>` and `if: always()`, and appends the table to
    `$GITHUB_STEP_SUMMARY`.
  - Add a `cross-build` matrix job with `fail-fast: false` and `continue-on-error` per
    target, which is informational. Targets:
    - `x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl` on ubuntu-latest, with
      `rust-lld` as the linker. x86_64 runs `--version`; aarch64 is built only.
    - an optional `ubuntu-24.04-arm` entry that runs `--version`.
    - `aarch64-apple-darwin` on macos-14.
    - `x86_64-pc-windows-msvc` on windows-latest, compile-only.

    Each writes a JSON record, which is uploaded as an artifact.
  - All three jobs are gated on `needs.changes.outputs.spike == 'true'`.
  - In the aggregator, `needs` becomes `[changes, cargo, parity]`, with the same failure
    rule for `parity`. `permissions: contents: read` and full-SHA pins stay.

  — DoD: the workflow is green on the PR on ubuntu-latest and macos-14. Any failing
  cross-build target is shown as `failed` in its artifact and does not affect
  `portable-runtime-spike`.
- [ ] 9. Measurement phase, done by the shepherd (depends on 8 being green on the final
  code head).
  - Download `portable-runtime-measurements-ubuntu-latest`,
    `portable-runtime-measurements-macos-14` and the cross-build artifact, and commit them
    under `docs/spikes/746/measurements/`.
  - Record the run id and head SHA in `measurements/README.md` and at the top of the
    report.
  - Fill the measurements table, with every `unmeasured` or `failed` cell kept literal,
    and fill G5 and G6 with citations.
  - Re-check the proposed token.

  — DoD: the committed files cite a run on the final code head, and `check_report.sh`
  passes.

## Tests

- [ ] T11. Baseline parity (`bench/parity.sh`, in the required `parity` job): the Python
  baseline and the Rust proxy return semantically identical `result` objects for
  `tools/list` and for calls to `mctl_whoami`, `deny_tool`, `approval_tool`, `secret_tool`
  and an unknown tool against the example fake upstream. Byte differences are reported,
  not failed.
- [ ] T12. Report shape (`bench/check_report.sh`, in the `parity` job): the Decision
  section has exactly one token, every GO line has a citation, and the self-check fails
  on a two-token copy.
- [ ] T2 to T10 keep passing unchanged (`cargo test --locked`, on the existing `cargo`
  matrix).
- [ ] `uv run --locked pytest -q` is unchanged, including
  `tests/test_portable_runtime_isolation.py`.
- [ ] Containment: `git diff --name-only origin/main...HEAD` lists only paths under
  `experiments/portable-runtime-rs/`, `docs/spikes/` or
  `.github/workflows/portable-runtime-spike.yml`.

## Rollback

All changes are additive, and nothing shipped or deployed is touched. To roll back,
revert the PR's merge commit. That removes `baseline/`, `bench/`, `examples/`, the report
and the measurements, and restores the workflow to its slice-2 shape (aggregator `needs:
[changes, cargo]`). For a partial rollback, drop the `bench` and `cross-build` jobs. They
are informational, and removing them does not change the required check. No service
redeploys, and no gitops change is needed. The whole spike can still be deleted with
`git rm -r experiments/portable-runtime-rs .github/workflows/portable-runtime-spike.yml`,
plus the `docs/spikes/746*` files if they are not kept as a record.
