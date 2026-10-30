# Design: issue-777-spike-runtime-746-slice-3-thin-adapter-b

## Current state

What slices 1 and 2 left in the clone:

- `experiments/portable-runtime-rs/` is a standalone crate (`Cargo.toml` with an empty
  `[workspace]` table and no dependencies; `Cargo.lock` holds only `mctl-runtime`;
  `rust-toolchain.toml` pins `1.85.0`, profile `minimal`, with clippy and rustfmt). The
  library (`src/lib.rs`) exposes the modules `allowlist`, `bridge`, `correlation`,
  `credential`, `hostcfg`, `http`, `json`, `sha256`, `spawn`, `upstream` and `uuid`.
  `src/main.rs` dispatches `proxy`, `init`, `doctor` and `--version`.
- `proxy` (`src/main.rs::cmd_proxy`) loads `fixtures/allowlist.toml` (the tools
  `mctl_whoami`, `mctl_list_services` and `mctl_get_service_status`) and exits 2 if the
  allowlist is bad. It resolves the credential from `MCTL_RUNTIME_TOKEN_FILE` or
  `MCTL_TOKEN`. With no token, calls return `credential-absent` and no upstream request is
  made. `src/upstream.rs::Upstream` (`new`, `list_tools`, `call_tool`) is the plain-HTTP
  client. The README states that an `https://` upstream is refused ("https upstream
  requires TLS (deferred, see README)").
- The fake upstream is `tests/common/fake_upstream.rs`. `FakeUpstream::start(Knobs)` binds
  `127.0.0.1:0`, and `url()` returns `http://<addr>/mcp`. It scripts the tools
  `TOOL_WHOAMI`, `TOOL_DENY`, `TOOL_APPROVAL`, `TOOL_SLOW` and `TOOL_SECRET`, with
  deliberately non-alphabetical keys and number text such as `1.50`. It depends only on
  `mctl_runtime::json`. It exists only inside `cargo test`, so nothing outside cargo can
  start it today.
- `tests/common/host.rs` spawns the binary through `CARGO_BIN_EXE_*` with a cleared
  environment, which ties it to cargo integration tests.
- `.github/workflows/portable-runtime-spike.yml` has these jobs:
  - `changes` runs on every PR. Through `gh api`, it sets `spike=true` if a file under
    `experiments/portable-runtime-rs/` or the workflow itself changed.
  - `cargo` is a matrix over `ubuntu-latest` and `macos-14`. It runs `cargo build`,
    `cargo test`, `cargo clippy --all-targets -D warnings` and `cargo audit` (with
    `cargo-audit` 0.22.1).
  - `portable-runtime-spike` is the required aggregator, gated on `changes` and `cargo`.

  `permissions: contents: read` is set at workflow level. checkout is pinned to
  `3d3c42e5aac5ba805825da76410c181273ba90b1`.
- `.github/workflows/spike-707-bench.yml` and `docs/spikes/707-pyrefly-type-check.md` are
  the house pattern for a measurement spike. The workflow is measurement-only, uses
  `astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78` (uv 0.11.11, Python 3.12)
  and `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02` (v4.6.2), and
  prints the environment. The report cites one run id for every number and commits the
  artifact.
- Python scope:
  - `pyproject.toml` pins `mcp==1.29.0` as a direct dependency (`uv.lock` line 355).
  - pytest uses `testpaths = ["tests"]`.
  - mypy uses `files = ["orchestrator", "config", "tools"]`.
  - CI runs `ruff check orchestrator config tests tools` (`pr-validation.yml:299`), so
    `experiments/` is already outside ruff in CI. A bare local `ruff check .` would still
    reach it.
- Isolation:
  - `.dockerignore:31` excludes `experiments/`.
  - `tests/test_portable_runtime_isolation.py` forbids `experiments/` and `mctl-runtime`
    references in `orchestrator/`, `config/`, `agents/`, `Dockerfile`, `entrypoint.sh`,
    `pyproject.toml` and `uv.lock`. It also forbids `COPY experiments` and any
    `Cargo.toml` outside the experiment.
  - `.gitignore:18` ignores `experiments/**/target/`.
- `docs/spikes/746*` does not exist yet.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/`: the tenants are `admins`, `karabu` and `labs`. A grep for
  `portable-runtime` or `mctl-runtime` under `services/` found no match, so no deployed
  service references the experiment. The mctl-agents workers
  (`admins/mctl-agents-worker*`) run the container image, and the experiment is excluded
  from that image. Nothing deployed changes in this slice.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-746-spike-runtime-evaluate-a-portable-single/`:
  read `tasks.md` and `design.md`. Tasks 8, 9, 10 and 11 below are copied from there. The
  decision rule is the one in that design's "Report and decision" section.
- `gh issue view 746`: read the parent issue body for the 14 matrix dimensions, Q1 to Q10
  and the seven GO criteria. They are copied below so that the offline implementer has
  them.
- mctl MCP tools were not needed. This slice has no deployed component.

### Parent-issue text the report must use (copied from #746)

Matrix dimensions (14): install artifact count; cold start; steady RSS; binary/package
size; macOS arm64; Linux amd64/arm64; Windows feasibility; cross-compilation/release
complexity; TLS/OAuth/MCP ecosystem maturity; child-process credential exposure;
embedding/library reuse with current MCTL; sandbox/WASM potential; operator/debug UX;
implementation/maintenance complexity.

Questions:
- Q1. Which real MCTL flows need an agent-side process rather than direct remote MCP?
- Q2. Which of those flows are already solved by #242, host skills or MCP config?
- Q3. Is host bootstrap or config generation enough?
- Q4. Does local result shaping or caching give token or latency value without data-custody
  problems?
- Q5. Does a runtime improve credential isolation, or only move credentials into another
  process?
- Q6. Should runtime policy be preflight and UX only, with server policy authoritative?
- Q7. Is x402 a natural future adapter at this boundary?
- Q8. Would WASM help MCTL in a concrete scenario?
- Q9. If GO, what belongs in v1 and what stays server-side?
- Q10. If GO, which repository and owner?

GO criteria (all seven are required for `PORTABLE_RUNTIME_*`):
- (G1) at least two cross-host jobs that direct MCP, config or skills do not solve cleanly;
- (G2) one artifact materially reduces friction;
- (G3) no new local authorization or business-logic authority;
- (G4) credential handling is no worse than the direct path and has a credible storage or
  handoff model;
- (G5) proxy overhead is small enough for interactive use;
- (G6) the packaging and update story is simple enough to justify another component;
- (G7) at least two hosts or environments can reuse the boundary.

`_RUST` additionally needs a material packaging, runtime or sandbox advantage that
outweighs adding Rust to the maintenance surface. If only bootstrap has value, the token
is `THIN_ADAPTER`. If docs and skills fix the friction, it is `NO_RUNTIME`.

## Proposed solution

### Layout (all new files inside the allowed paths)

```text
experiments/portable-runtime-rs/
  baseline/thin_adapter.py        task 8 (Python baseline)
  examples/fake_upstream.rs       standalone fake upstream for bench and parity
  examples/bench_driver.rs        stdio driver: ready-time, latency, RSS, parity
  bench/measure.sh                task 9 orchestrator
  bench/parity.sh                 T11
  bench/check_report.sh           report Decision-token and GO-citation check
  bench/render_table.py           JSON -> Markdown table (stdlib only, run with -I)
docs/spikes/746-portable-runtime.md
docs/spikes/746/measurements/README.md      (code phase: method; shepherd: run id)
docs/spikes/746/measurements/*.json, *.md   (shepherd fix-up commit only)
.github/workflows/portable-runtime-spike.yml (parity, bench, cross-build jobs)
```

The isolation test needs no change. Every new file is under `experiments/` or `docs/`,
and nothing is added to a guarded path.

### Standalone fake upstream (`examples/fake_upstream.rs`)

The parity and bench steps need the same deterministic upstream outside `cargo test`. The
example reuses the existing module verbatim with
`#[path = "../tests/common/fake_upstream.rs"] mod fake_upstream;`, so the tool fixtures
are never forked. It starts `FakeUpstream::start(Knobs::default())`, prints `url()` as one
line on stdout, and blocks until stdin closes or it receives SIGTERM. `cargo clippy
--all-targets -D warnings` already covers examples. Any `dead_code` warning from unused
helpers is silenced with a module-level `#[allow(dead_code)]` on the `mod` item in the
example only.

### Python baseline (`baseline/thin_adapter.py`)

The baseline is a single file. It imports only `mcp`, plus `anyio` and `httpx`, which
`mcp` already depends on, and the standard library. It has a `# ruff: noqa` file header
for local `ruff check .` and is outside mypy `files` and pytest `testpaths`. It works as
follows:

- It parses the same flags as `proxy`: `--upstream`, `--allowlist` and `--timeout-ms`. It
  reads the allowlist with `tomllib` (`tools = [...]`) and exits 2 if the file is missing,
  empty or invalid.
- It reads the bearer token from `MCTL_RUNTIME_TOKEN_FILE` or, if that is unset, from
  `MCTL_TOKEN`. Neither the token nor any argument is logged.
- It opens one `mcp.client.streamable_http.streamablehttp_client` session with an
  `Authorization` header, and an `mcp.ClientSession` on top of it.
- It runs a `mcp.server.lowlevel.Server` over `mcp.server.stdio.stdio_server`:
  - `list_tools` returns the upstream tools filtered to the allowlist.
  - `call_tool` refuses names outside the allowlist without upstream I/O. It returns a
    `CallToolResult` with `isError=True` and the same text content the Rust bridge emits
    for `not-eligible`. The implementer copies that string from `src/bridge.rs`.
  - Allowlisted calls pass the upstream `CallToolResult` through unchanged. The
    implementer checks in the installed SDK source (`.venv/lib/python3.12/site-packages/mcp/server/lowlevel/server.py`)
    how 1.29.0 lets a handler return a `CallToolResult` verbatim, rather than assuming it.
- Error mapping stays minimal: an upstream exception becomes `isError` with
  `provider-unavailable`. Timeout and 401 parity are not claimed. T11 covers only the
  happy path and refusals, and the report says so in the matrix.

The bench runs it as `"$VENV/bin/python" -I baseline/thin_adapter.py ...`, not through
`uv run`, so cold start measures the adapter rather than uv. The report records the
`uv run` cold start as a second number, because that is how a user would launch it.

### Bench driver (`examples/bench_driver.rs`, std-only)

One driver measures both subjects the same way. It is invoked as
`bench_driver <mode> --upstream URL [--n N] -- <server command...>`. It spawns the server
with a cleared environment plus `PATH`, `HOME` and `MCTL_TOKEN=bench-token-746`. A token
is required: with none, the Rust proxy returns `credential-absent`. Modes:

- `ready`: the time from spawn to the `initialize` response, repeated N times (default
  20). It reports median and p95.
- `latency`: one handshake, then N (default 100) `tools/call mctl_whoami`. It reports the
  first call and the median and p95 of the steady state. The direct baseline is the same N
  calls through `mctl_runtime::upstream::Upstream::call_tool` against the same URL.
  Overhead is the subject's figure minus the direct figure.
- `rss`: idle RSS after the handshake, then peak RSS sampled during a `slow_tool` call.
  Linux reads `VmRSS` and `VmHWM` from `/proc/<pid>/status`. macOS uses
  `ps -o rss= -p <pid>`. The Python RSS is the interpreter's own process.
- `parity`: sends the T11 sequence to the command and prints the `result` of each reply
  as canonical JSON, one line per request, using `mctl_runtime::json`. `parity.sh` runs
  it once per subject and compares the two outputs. The comparison parses both outputs,
  so it is not a byte diff. Byte differences are written to
  `measurements/parity-bytes.md` as a finding.

Output is JSON lines. Each record has `subject`, `metric`, `value` (a number or null),
`unit`, `status` (`measured`, `unmeasured` or `failed`), `reason`, `os`, `head_sha` and
`run_id`.

### `bench/measure.sh`

The script runs with `bash -euo pipefail`. It writes to `$OUT`, which defaults to
`docs/spikes/746/measurements`, and records an environment block (CPU, cores, memory, OS,
rustc, Python and uv versions). It measures the following:

1. Build time: a clean `cargo build --release --locked` timed with `date +%s%N`, and the
   `uv sync --locked` time for the baseline's environment.
2. Size:
   - for the Rust proxy, `stat` of `target/release/mctl-runtime`;
   - for the Python baseline, the script size plus `du -sk` of the installed `mcp`
     package and its transitive dependencies (from `uv pip show`), plus the interpreter.
     Each part is reported separately.
3. Dependencies: `file` plus `ldd` on Linux and `otool -L` on macOS, as a count of lines.
   For Python, the count of installed distributions the adapter needs.
4. The `ready`, `latency` and `rss` modes of the driver for each subject.
5. The live run. When `MCTL_RUNTIME_LIVE` is unset, the script writes
   `{"metric":"live","status":"unmeasured","reason":"not run in this slice (MCTL_RUNTIME_LIVE unset; no credentials in CI)"}`.

Every Rust size, build and dependency record carries
`"note":"http-only, TLS not included"`. A step that fails writes a `failed` record and
the script continues. The script exits non-zero only if it could not write its output.
`render_table.py` then produces `measurements/<os>.md`.

### TLS: document the limit (no `rustls` feature)

The proposal picks "state the limit" for these reasons:

- Adding `rustls` needs registry entries with checksums in `Cargo.lock`. The offline
  implementer cannot produce them, so `cargo build --locked` would fail on the PR.
- Generating the lock in CI and committing it from the shepherd would mean code
  dependencies arrive in a fix-up commit that never went through the implementer and
  review loop.
- It would also end slice 2's std-only property (no advisory surface, a one-entry lock),
  which the `cargo audit` step relies on.

The report instead adds a "TLS limit" section and labels each affected number. It also
gives a non-measured, cited estimate of what a TLS client adds. The GO checklist line for
G6 says that a TLS-capable artifact is unmeasured. If the verdict leans GO, measuring a
TLS variant becomes the first follow-up.

### Workflow changes (`portable-runtime-spike.yml`)

The existing `changes`, `cargo` and aggregator logic is kept. Three jobs are added, each
with `needs: changes`, `if: needs.changes.outputs.spike == 'true'`, its own
`timeout-minutes`, checkout pinned as today, and `persist-credentials: false`:

- `parity` runs on ubuntu-latest and is **required**. It uses setup-uv, pinned as in
  `spike-707-bench.yml`, with uv 0.11.11 and Python 3.12. Its steps are `uv sync
  --locked`, `cargo build --locked --examples`, `bench/parity.sh` and
  `bench/check_report.sh docs/spikes/746-portable-runtime.md`.
  - The check script fails if the `## Decision` section contains anything other than
    exactly one of the four tokens.
  - It also fails if a GO-checklist line has no `measurements/` path or `T<n>` id.
  - These are deterministic, offline checks, so they belong in the required gate. The
    aggregator gains `PARITY: ${{ needs.parity.result }}` and the same "spike changed and
    did not succeed" rule.
- `bench` runs on a matrix of ubuntu-latest and macos-14 and is **informational**. Its
  steps:
  - print the environment;
  - run `bench/measure.sh` with `OUT=$RUNNER_TEMP/measurements`,
    `RUN_ID=${{ github.run_id }}` and `HEAD_SHA=${{ github.event.pull_request.head.sha || github.sha }}`;
  - upload the artifact `portable-runtime-measurements-${{ matrix.os }}` with
    `if: always()`;
  - `cat` the Markdown table into `$GITHUB_STEP_SUMMARY`.
- `cross-build` is a matrix with `fail-fast: false` and is **informational**. Each target
  step uses `continue-on-error: true` and writes a JSON record (`built`, `ran` and
  `size`, or `failed` with the last 20 lines of the log), which is uploaded as an
  artifact. Targets:
  - `x86_64-unknown-linux-musl` on ubuntu-latest: `rustup target add`, then build with
    `CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER=rust-lld`, then run `--version` and
    record `file` output.
  - `aarch64-unknown-linux-musl` on ubuntu-latest: the same, with the aarch64 linker
    variable. The binary is built only and recorded as `ran: unmeasured`. An optional
    second entry on `ubuntu-24.04-arm` runs `--version` if that runner is available. If
    it is not, the job is skipped or fails without affecting the required check.
  - `aarch64-apple-darwin` on macos-14: a native build, then `--version`.
  - `x86_64-pc-windows-msvc` on windows-latest: `cargo build --release --locked`,
    compile-only. A Unix-API compile failure is recorded as evidence.

  No `cross`, `cargo-zigbuild` or Zig download is used. rust-lld ships with the pinned
  toolchain, which keeps the job free of new supply-chain inputs. `rustup target add`
  runs against the pinned `1.85.0`.

Neither `bench` nor `cross-build` is in the aggregator's `needs`. The workflow keeps
`permissions: contents: read` and adds no secret. `concurrency` is unchanged.

### Measurement phase (shepherd fix-up)

After the implementer's head is green, the shepherd downloads both bench artifacts and
the cross-build artifact from a run on the final head. It commits them under
`docs/spikes/746/measurements/` (`ubuntu-latest.json`, `macos-14.json`, `cross-build.json`,
the rendered `.md` files and `parity-bytes.md`). It records the run id and head SHA in
`measurements/README.md`, fills the report's measurements table, and re-checks the
proposed token against G5 and G6. A commit that touches only `docs/` still sits in a PR
whose file list contains `experiments/`, so `changes` keeps `spike=true`, and the next run
produces a fresh artifact. The README states which run's artifact is committed. That run
must be on a head whose code matches the final head, because docs-only commits do not
change the measured binaries.

### Report (`docs/spikes/746-portable-runtime.md`)

The report follows the `707` report's structure: an environment table and the run id at
the top. Sections, in order:

1. The current-state map and the friction list.
2. The duplicate check (#242, #717, mctl-telegram#784, .github#34 / #652, .github#173 /
   mctl-api#616).
3. The measurements table (from `measurements/*.md`), with `unmeasured` shown literally.
4. The TLS limit.
5. The 14-row matrix (the dimensions above).
6. The answers to Q1 to Q10.
7. J3: the credential analysis, based on T6, T7 and T10. It states what is not isolated:
   - the runtime process's own environment and memory;
   - the host config, which names the env var or file;
   - a same-user reader of the token file;
   - `MCTL_TOKEN` inherited from the host.
8. The J6 x402 note: a Mermaid sequence diagram (host, runtime, upstream, 402 challenge,
   Refuse) and a Rust trait sketch `PaymentChallengeHandler` in a fenced code block that
   only returns a `Refuse` decision. No payment code is added to the crate.
9. The boundary benchmark against Cloudflare AI Gateway / `createAI`. Model routing,
   fallback, BYOK and provider abstraction stay outside `mctl-runtime`. Any product
   finding is routed to mctlhq/.github#184 G4.
10. The transport note: Cloudflare retired `/sse` for its product MCP servers, and #746
    targets local stdio plus upstream Streamable HTTP `/mcp`, with no SSE work.
11. The GO checklist G1 to G7 plus the Rust clause. Each line is marked met, not met or
    unproven, and cites a `measurements/` file or a test id.
12. The Decision: exactly one token.
13. If the decision is GO, recommendations and follow-up drafts. Otherwise the section
    says "not applicable (decision is not GO)", and the list of possible tokens appears
    only in the introduction, outside the Decision section.

The implementer proposes the token from the criteria it can decide without numbers (G1,
G2, G3, G4 and G7). Under the parent's decision rule, a G1 or G7 failure already excludes
`PORTABLE_RUNTIME_*`. The shepherd re-checks the token after it fills G5 and G6. The
owner's verdict is not written here.

## Alternatives

- **A rustls feature measured in both variants.** Rejected for this slice. The offline
  implementer cannot produce the lock entries, so the PR would be red on `--locked`, and
  the dependency would arrive in an unreviewed shepherd commit. A TLS variant is listed
  as the first GO follow-up instead.
- **Bench and cross-build as part of the required check.** Rejected. Runner availability
  (arm64, Windows) and timing noise must not block unrelated PRs, now that the aggregator
  runs on every PR. Only the deterministic parity and report checks are required.
- **Timing with `hyperfine` or an external tool, and parity in Python.** Rejected. It
  adds tool installs and makes the two subjects use different clients. One std-only Rust
  driver gives both subjects the same clock, the same JSON canonicalizer
  (`mctl_runtime::json`) and the same direct-HTTP reference (`upstream::Upstream`).
- **Cross-builds with `cross` or `cargo-zigbuild`.** Rejected for the first attempt
  because they download Docker images or Zig. rust-lld self-contained musl linking needs
  nothing new. If it fails, the failure is the recorded evidence.

## Platform impact

- No migration and no deployed change. Nothing shipped changes, and the isolation test
  and `.dockerignore` keep the image unchanged.
- CI cost on PRs that touch the spike: about two bench runners (around 10 minutes each),
  four cross-build runners and one parity runner. On other PRs, nothing beyond today's
  `changes` job.
- Risks and mitigations:
  - **A red required check from parity.** This happens only if the baseline diverges
    semantically. The fix stays inside the experiment.
  - **A flaky or noisy benchmark.** The bench job is informational, every number cites
    its run, and N=20 and N=100 with p95 are reported.
  - **Unix-only code fails on Windows.** That failure is recorded, which is the evidence
    the matrix needs.
  - **The shepherd cannot fetch artifacts.** The measurements table stays explicitly
    `unmeasured`, and `check_report.sh` fails on a GO line without a citation. A report
    without numbers cannot claim G5 or G6 as met.
  - **The baseline drifts into the import path.** The isolation test and the ruff, mypy
    and pytest scopes are unchanged, and the file sits under `experiments/`.
