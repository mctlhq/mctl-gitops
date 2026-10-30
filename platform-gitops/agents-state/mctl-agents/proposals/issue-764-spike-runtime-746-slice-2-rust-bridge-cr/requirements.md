# Spike #746 slice 2: Rust stdio-to-Streamable-HTTP bridge, credentials, correlation, fake upstream (CI-verified)

## Context
Issue #764 is slice 2 of spike #746 (portable single-binary runtime). Slice 1 (#759 / PR #761) landed a crate skeleton at `experiments/portable-runtime-rs/` (`src/main.rs` only prints `mctl-runtime <version>`; `Cargo.toml` has no dependencies; toolchain pinned to `1.85.0`), the containment test `tests/test_portable_runtime_isolation.py`, and the optional CI workflow `.github/workflows/portable-runtime-spike.yml` (`cargo build/test/clippy --locked` and `cargo audit 0.22.1` on ubuntu-latest and macos-14). This slice implements parent tasks 3 to 7 and tests T2 to T10 of the #746 proposal verbatim: credential sources, a single scrubbing spawn helper, the `proxy` bridge with a local allowlist, per-call correlation on stderr, `init` and `doctor`, and an offline in-process fake upstream.

It matters because the #746 decision (slice 3) needs real evidence for J2 to J5 (bridge, credential handling, fail-closed preflight, correlation), and that evidence only counts if it is verified by cargo in CI. The implementer image has no `cargo` and no network, so the PR's `portable-runtime-spike.yml` run is the verifier, and CI failures are fixed by shepherd fix-up commits without widening scope.

## User stories
- AS a spike reviewer I WANT a working Rust proxy proven by offline cargo tests SO THAT the #746 report can cite measured behaviour instead of a prior.
- AS a static-token user I WANT the runtime to read my token from a `0600` file or `MCTL_TOKEN` and never from argv or generated config SO THAT the token does not leak into host config, process listings or child processes.
- AS a host (Claude Code or a fixture host) I WANT a stdio MCP server that exposes only allowlisted upstream tools and passes upstream refusals through unchanged SO THAT the local runtime narrows and never grants.
- AS an operator debugging a call I WANT one stderr JSON correlation line per call whose `invocation_id` matches the `X-Mctl-Invocation-Id` the upstream received SO THAT I can join host-side and MCTL-side evidence without the runtime storing payloads.
- AS a maintainer I WANT every change confined to `experiments/portable-runtime-rs/` SO THAT the spike stays deletable and the shipped image and Python test suite are unchanged.

## Acceptance criteria (EARS)

Credentials and spawning
- WHEN `MCTL_RUNTIME_TOKEN_FILE` names a file whose mode grants any group or other permission bit THE SYSTEM SHALL refuse it with a diagnostic naming the path and mode, and never read the token value.
- WHEN `MCTL_RUNTIME_TOKEN_FILE` names a `0600` file THE SYSTEM SHALL use its trimmed contents as the bearer token.
- IF `MCTL_RUNTIME_TOKEN_FILE` is unset and `MCTL_TOKEN` is set and non-empty THEN THE SYSTEM SHALL use `MCTL_TOKEN`.
- IF no credential source yields a token THEN THE SYSTEM SHALL report "credential absent" and make zero upstream requests.
- WHEN the `Keychain` or `Loopback` source is selected THE SYSTEM SHALL return `Unsupported`.
- THE SYSTEM SHALL offer no CLI flag that accepts a token value.
- WHEN the runtime spawns any child process THE SYSTEM SHALL do it only through `src/spawn.rs`, which removes `MCTL_TOKEN` and `MCTL_RUNTIME_TOKEN_FILE` from the child environment and never places a credential in argv.

Bridge (`proxy`)
- IF `fixtures/allowlist.toml` (or the configured allowlist path) is missing, empty, or invalid TOML THEN `proxy` SHALL exit non-zero before serving.
- WHEN the host sends `tools/list` THE SYSTEM SHALL return exactly the upstream tools whose name is in the allowlist, with `name` and `inputSchema` byte-equal to upstream.
- WHEN the host calls a tool whose name is not in the allowlist (including `secret_tool` and unknown names) THE SYSTEM SHALL return `isError: true` with reason `not-eligible` and perform no upstream I/O.
- WHEN an allowlisted call returns, THE SYSTEM SHALL pass the result (content and `isError`) through unchanged, including upstream DENY and REQUIRE_APPROVAL refusals.
- IF the upstream is unreachable THEN THE SYSTEM SHALL return `isError: true` with `provider-unavailable`.
- IF the upstream does not answer within the configured bound THEN THE SYSTEM SHALL return `isError: true` with `provider-timeout` no later than the bound plus a small slack.
- IF the upstream answers HTTP 401 or 403 THEN THE SYSTEM SHALL return `credential-rejected` after exactly one upstream attempt.
- WHILE a stdio session is open THE SYSTEM SHALL keep answering `ping` after any upstream failure.
- THE SYSTEM SHALL speak Streamable HTTP to the upstream `/mcp` endpoint only and SHALL NOT implement the legacy MCP SSE transport.

Correlation
- WHEN a `tools/call` is handled THE SYSTEM SHALL generate a UUIDv4 `invocation_id`, send it upstream as `X-Mctl-Invocation-Id` (when a request is made), and write exactly one stderr JSON line with `invocation_id`, `host_request_id`, `tool`, `args_sha256`, `upstream_session_id`, `upstream_request_id`, `outcome`, `is_error`, `latency_ms`.
- THE SYSTEM SHALL compute `args_sha256` over the same canonical JSON rule as `orchestrator/context_snapshot.py::_canonical_json` (sorted keys, `,`/`:` separators, ASCII-escaped) with the `sha256:` prefix of `_hash_bytes`.
- THE SYSTEM SHALL NOT write argument values, result values, or the token into the correlation line, and SHALL NOT write any file or database.

`init` and `doctor`
- WHEN `init --host fixture|claude-code` runs without `--write` THE SYSTEM SHALL print config to stdout only, referencing the credential by env var name or file path, never by value.
- IF `--write` is given without `--config-dir` THEN THE SYSTEM SHALL refuse with non-zero exit.
- IF `--config-dir` resolves to a known real host config location under `$HOME` THEN THE SYSTEM SHALL refuse to write.
- WHEN `doctor` runs THE SYSTEM SHALL report version, credential source name, token file mode, upstream round trip, allowlist count, and allowlisted tools missing upstream, and exit non-zero on any failure.

Verification and containment
- WHEN the PR is opened THE SYSTEM SHALL be green in `portable-runtime-spike.yml` on ubuntu-latest and macos-14 for `cargo build --locked`, `cargo test --locked` (three consecutive passes), `cargo clippy --locked --all-targets -- -D warnings`, and `cargo audit`.
- THE SYSTEM SHALL keep every changed file under `experiments/portable-runtime-rs/`, leaving `uv run --locked pytest -q` (including `tests/test_portable_runtime_isolation.py`) unchanged.
- THE SYSTEM SHALL make `cargo test` fully offline and deterministic (fake upstream bound to `127.0.0.1:0`, no live API).

## Out of scope
- Parent task 8 (`baseline/thin_adapter.py`), task 9 (`bench/measure.sh`, musl amd64/arm64, macOS arm64, Windows cross-builds), the cross-build matrix part of task 10, task 11 (the report and decision token), and parent tests T1 (isolation, already merged in slice 1) and T11 (baseline parity). T11 belongs to slice 3.
- Any change to the CI workflow file, `orchestrator/`, `config/`, `agents/`, the Dockerfile, `pyproject.toml`, `uv.lock`, or any manifest.
- Restarting or re-approving the #746 DevLoop; closing #746.
- Legacy MCP SSE transport, result caching or shaping, local policy evaluation, payment handling, a real Keychain or loopback implementation, a live call against `api.mctl.ai`.

## Open questions
- RESOLVED (request `hir-4ecbf111aa835878`, owner answer: "std-only, http-only upstream in slice 2"): the crate stays std-only with no registry dependency and an unchanged `Cargo.lock`. It uses a hand-rolled MCP subset (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`) instead of `rmcp`, and hand-rolled JSON, SHA-256, UUIDv4 and HTTP/1.1. The upstream client speaks plain `http://` only. An `https://` upstream (the real `api.mctl.ai/mcp`) is refused with `provider-unavailable` until a later slice adds TLS. The crate README records this choice, as the issue asks.
- Is TLS (and therefore a live `doctor` round trip against `api.mctl.ai`) a slice 3 prerequisite, or a separate follow-up? This proposal does not decide that. It only states the limitation in the README.
- `credential-absent` is a local reason code not in ADR 017's vocabulary; it is used only for the no-token case so T6 can tell it apart from `credential-rejected`.
- `upstream_session_id` / `upstream_request_id` source: assumed to be the `Mcp-Session-Id` response header and an `X-Request-Id` response header respectively; `null` when absent. Whether `api.mctl.ai/mcp` sends `X-Request-Id` is unobserved (carried over from #746).
- Exact timeout default and CLI/config knob name (proposed: `--timeout-ms`, default 10000; tests use ~300 ms). The issue only says "configured bound".
- T7's `/proc/<pid>/cmdline` check is Linux-only; on macos-14 the assertion falls back to `ps -o args=` or is skipped with a recorded reason.
- Which `$HOME` paths count as "known real host config locations" (proposed: `~/.claude`, `~/.claude.json`, `~/.config/claude`, `~/Library/Application Support/Claude`, `~/.cursor`).
