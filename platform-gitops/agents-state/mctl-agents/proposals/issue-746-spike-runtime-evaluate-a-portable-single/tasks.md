# Tasks: issue-746-spike-runtime-evaluate-a-portable-single

- [ ] 1. Scaffold `experiments/portable-runtime-rs/`: a standalone crate (`Cargo.toml`, a committed `Cargo.lock` with exact pins, `rust-toolchain.toml`) and a `README.md` marked EXPERIMENTAL / default-off, with run and delete instructions. Add `experiments/**/target/` to `.gitignore` and `experiments/` to `.dockerignore`. — DoD: `cargo build` succeeds, and the docker smoke build and `uv run --locked pytest -q` are unchanged.
- [ ] 2. Write `tests/test_portable_runtime_isolation.py` (depends on 1). It asserts that:
  - no `experiments/` or `mctl-runtime` reference appears in `orchestrator/`, `config/`, `agents/`, `Dockerfile`, `entrypoint.sh`, `pyproject.toml` or `uv.lock`;
  - there is no `COPY experiments` in the Dockerfile;
  - `.dockerignore` excludes `experiments/`;
  - no `Cargo.toml` exists outside the experiment.

  The test skips when the directory is absent. Also extend the commit-lint `SHIPPING_PATHS` in `.github/workflows/pr-validation.yml` to `^(tests/|docs/|\.github/|experiments/)`. — DoD: the test passes under `ruff` and `pytest`, and fails if a `COPY experiments/` line is added.
- [ ] 3. Write `src/credential.rs` (depends on 1). The `CredentialSource` trait has two implementations, `TokenFile` (`MCTL_RUNTIME_TOKEN_FILE`; refuses group- or other-readable files) and `EnvVar` (`MCTL_TOKEN`), plus `Keychain` and `Loopback` stubs that return `Unsupported`. There is no CLI flag that accepts a token. Write `src/spawn.rs` as the single child-spawn helper: it calls `env_remove` on both variables, never puts the credential in args, and is exercised through a hidden `--spawn-probe`. — DoD: unit tests cover each source, the file-mode refusal, and the absent token.
- [ ] 4. Write `src/bridge.rs` and the `proxy` subcommand (depends on 3). It runs a stdio MCP server and a streamable-HTTP MCP client to one upstream. Use `rmcp` at an exact pin; fall back to a hand-rolled `initialize`/`tools/list`/`tools/call`/`ping` subset if needed, and record the choice. It must:
  - load the allowlist from `fixtures/allowlist.toml` and refuse to start if that file is missing, empty or invalid;
  - return `tools/list` as the intersection of upstream tools and the allowlist, with name and schema verbatim;
  - refuse non-allowlisted calls with `not-eligible` and no upstream I/O;
  - pass results through unchanged, including `isError`;
  - map upstream failures to `provider-unavailable`, `provider-timeout` and `credential-rejected` (401/403), within a bounded timeout and without crashing the session.

  — DoD: integration tests T2 to T7 pass. Do not add legacy MCP SSE transport support: the target upstream contract is Streamable HTTP `/mcp`.
- [ ] 5. Write `src/correlation.rs` (depends on 4). For each call it creates an `invocation_id` (UUIDv4), sends the `X-Mctl-Invocation-Id` header upstream, and writes one stderr JSON line with these fields: `invocation_id`, `host_request_id`, `tool`, `args_sha256`, `upstream_session_id`, `upstream_request_id`, `outcome`, `is_error`, `latency_ms`. It writes no file or DB. — DoD: T8 passes.
- [ ] 6. Write the `init --host fixture|claude-code` subcommand (depends on 3). It is dry-run by default and prints config to stdout, referencing the credential only by env var name or file path. `--write` requires an explicit `--config-dir` and refuses known real host config locations under `$HOME`. Also write `doctor`: version, credential source name, file mode, upstream round trip, allowlist count, and allowlisted tools missing upstream; it exits non-zero on failure. — DoD: T9 and T10 pass.
- [ ] 7. Build the in-process fake upstream for the cargo integration tests, plus a fixture-host driver that spawns the binary over stdio (supports 4 to 6). The fake upstream scripts these tools: `mctl_whoami` (ok), `deny_tool`, `approval_tool`, `slow_tool`, and `secret_tool` (upstream only). It also has knobs for 401, connection reset, and header echo. — DoD: `cargo test` is fully offline and deterministic, and passes 3 consecutive runs.
- [ ] 8. Write `baseline/thin_adapter.py` (depends on 7). It is a minimal Python stdio-to-streamable-HTTP passthrough with the same allowlist, using the `mcp==1.29.0` SDK already in `uv.lock` and no new Python dependency. It is not imported by anything, and it lives outside ruff and pytest scope. — DoD: it answers the same `tools/list` and `tools/call` as the Rust proxy against the fake upstream.
- [ ] 9. Write `bench/measure.sh` (depends on 4, 7, 8) to record:
  - release size;
  - `ldd`/`file` dependency count;
  - build time;
  - cold start to ready (N=20, median and p95);
  - idle RSS, and RSS during a call;
  - first-call and steady-state latency overhead (N=100) against a direct HTTP client call.

  Run it for the Rust proxy and the Python baseline. Attempt cross-builds for `x86_64-unknown-linux-musl`, `aarch64-unknown-linux-musl`, macOS `aarch64-apple-darwin` (runner permitting) and Windows (compile-only). An optional live run against `api.mctl.ai` is gated by `MCTL_RUNTIME_LIVE=1`. — DoD: raw results are committed under `docs/spikes/746/measurements/`, and every failure or unmeasured target is recorded as such.
- [ ] 10. Add the optional `.github/workflows/portable-runtime-spike.yml` (depends on 7, 9). It triggers on `paths: experiments/portable-runtime-rs/**` and `workflow_dispatch`, with `permissions: contents: read` and pinned action SHAs as in `pr-validation.yml`. It runs `cargo test`, `cargo clippy -D warnings`, `cargo deny` or `cargo audit`, and the cross-build matrix (ubuntu plus macos-14). It is not a required check. — DoD: the workflow is green on the PR, or a failing target is documented.
- [ ] 11. Write the report `docs/spikes/746-portable-runtime.md` (depends on 9). It contains:
  - the current-state map and friction list;
  - the duplicate check (#242, #717, mctl-telegram#784, .github#34 / #652, .github#173 / mctl-api#616);
  - the measurements table;
  - the 14-row Rust-vs-thin-adapter/direct matrix;
  - answers to Q1 to Q10;
  - the J3 credential analysis, including what the runtime does not isolate;
  - the J6 x402 design note with a sequence diagram and a `PaymentChallengeHandler` sketch (Refuse-only, with no payment code);
  - a boundary benchmark against Cloudflare AI Gateway / `createAI`: whether model-provider routing, fallback, BYOK and provider abstraction should remain outside `mctl-runtime`, with any model-routing product finding routed to `mctlhq/.github#184` G4 rather than implemented here;
  - a transport note recording that Cloudflare retired `/sse` for its product MCP servers and that #746 deliberately targets stdio locally + Streamable HTTP `/mcp` upstream, with no legacy SSE compatibility work;
  - a GO-criteria checklist with evidence per line;
  - exactly one decision token;
  - repository and ownership recommendations and follow-up issue drafts only if the decision is GO.

  — DoD: the report has exactly one of `NO_RUNTIME`, `THIN_ADAPTER`, `PORTABLE_RUNTIME_RUST` or `PORTABLE_RUNTIME_OTHER` in its Decision section, and every GO criterion cites a measurement or test.

## Tests

- [ ] T1. Isolation (pytest): `tests/test_portable_runtime_isolation.py` per task 2. A negative self-check (adding `COPY experiments/` in a temporary copy of the Dockerfile) is detected.
- [ ] T2. Allowlist (cargo): `tools/list` returns exactly the allowlisted tools present upstream, `secret_tool` is absent, and the `inputSchema` JSON is byte-equal to the upstream's.
- [ ] T3. Fail closed (cargo): calling `secret_tool` or an unknown name returns `isError: true` with `not-eligible`, and the fake upstream records zero `tools/call` requests. A missing or empty allowlist means `proxy` exits non-zero.
- [ ] T4. Remote refusal preserved (cargo): `deny_tool` and `approval_tool`, which are allowlisted locally, come back with `isError: true` and content identical to the upstream's. No path turns them into success.
- [ ] T5. Upstream unavailable or timeout (cargo): a closed port gives `provider-unavailable`, and `slow_tool` gives `provider-timeout` within the configured bound. The stdio session still answers `ping` afterwards.
- [ ] T6. Token absent or expired (cargo): with no token, `doctor` exits non-zero with "credential absent", and `proxy` call results are errors with zero upstream requests made. An upstream 401 gives `credential-rejected`, and exactly one upstream attempt is made.
- [ ] T7. No credential in argv, env or config (cargo): run with the sentinel token `mctl-runtime-sentinel-746`.
  - `--spawn-probe` child: its argv and env do not contain the sentinel, and neither `MCTL_TOKEN` nor `MCTL_RUNTIME_TOKEN_FILE` is set in it.
  - The runtime's own `/proc/<pid>/cmdline` does not contain the sentinel.
  - `init` stdout for both hosts does not contain the sentinel.
  - Captured stderr correlation lines do not contain the sentinel.
  - The upstream receives `Authorization: Bearer <sentinel>`, which proves the token was used.
- [ ] T8. Correlation (cargo): one call produces one stderr JSON line with all fields. `invocation_id` equals the `X-Mctl-Invocation-Id` the upstream received, and `args_sha256` matches the canonical-JSON digest. The line contains no argument or result values, and no new file appears in the working directory or the temp dir.
- [ ] T9. Init dry-run (cargo): the default writes nothing (the fixture dir's mtime and listing are unchanged). `--write` without `--config-dir` is refused. `--write --config-dir <tmp copy of fixtures/host-fixture>` writes only there.
- [ ] T10. Token file mode (cargo): a `0644` token file is refused with a diagnostic, and a `0600` file is accepted.
- [ ] T11. Baseline parity (script in `bench/`): the Python baseline and the Rust proxy return identical `tools/list` and call results against the fake upstream.

## Rollback

All changes are additive and isolated, and no production path, image or manifest is
touched. To roll back:

1. Delete `experiments/portable-runtime-rs/`, `.github/workflows/portable-runtime-spike.yml`
   and `tests/test_portable_runtime_isolation.py`.
2. Optionally revert the `.gitignore`, `.dockerignore` and commit-lint regex lines.
   They are harmless when left in place.
3. The report `docs/spikes/746-portable-runtime.md` and `docs/spikes/746/` may stay as a
   historical record, or be removed.

Reverting the merge commit achieves all of the above in one step. No deployed service
needs a redeploy.
