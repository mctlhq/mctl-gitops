# Design: issue-764-spike-runtime-746-slice-2-rust-bridge-cr

## Current state

What exists in the clone (commit `5eecff3`):

- `experiments/portable-runtime-rs/Cargo.toml`: package `mctl-runtime` `0.0.0`, edition 2021, `publish = false`, an empty `[dependencies]`, and an empty `[workspace]` table so it never joins a parent workspace.
- `experiments/portable-runtime-rs/Cargo.lock`: lockfile `version = 4` with a single entry, the package itself. No registry crate is locked.
- `experiments/portable-runtime-rs/rust-toolchain.toml`: channel `1.85.0`, components `clippy`, `rustfmt`, profile `minimal`.
- `experiments/portable-runtime-rs/src/main.rs`: `fn version()` returning `CARGO_PKG_VERSION`, `main` printing `mctl-runtime <version>`, and one unit test. No other module, no `tests/`, no `fixtures/`.
- `experiments/portable-runtime-rs/README.md`: EXPERIMENTAL / default-off note, run and delete instructions.
- `.github/workflows/portable-runtime-spike.yml`: triggers on `experiments/portable-runtime-rs/**` and the workflow file; matrix `ubuntu-latest`, `macos-14`; `rustup show`, `cargo build --locked`, `cargo test --locked`, `cargo clippy --locked --all-targets -- -D warnings`, `cargo install cargo-audit --version 0.22.1 --locked` then `cargo audit`. It runs `cargo test` once per job.
- `tests/test_portable_runtime_isolation.py`: asserts no `experiments/` or `mctl-runtime` string in `orchestrator/`, `config/`, `agents/`, `Dockerfile`, `entrypoint.sh`, `pyproject.toml`, `uv.lock`; no `COPY experiments` in the Dockerfile; `.dockerignore` excludes `experiments/`; no `Cargo.toml` outside the experiment (pruning `target`). Nothing this slice adds under the experiment can trip it.
- `.dockerignore` already excludes the experiment; `.github/workflows/pr-validation.yml` line 134 treats `experiments/` as non-shipping in commit-lint, so a `chore(experiments)`/`test` style commit type is acceptable.
- The implementer environment has no `~/.cargo` and no network (checked: `ls ~/.cargo` fails).

Vocabulary and rules to mirror (read, not changed):

- `orchestrator/capability_gateway.py`: reason codes `not-eligible` (line ~1090, refused before any provider call), `provider-unavailable` (`ProviderUnavailableError`, line ~119), `provider-timeout` (`ProviderTimeoutError`, line ~128), `provider-error` when the provider returns `isError` (line ~1194). The bridge uses the same strings; `credential-rejected` and `credential-absent` are local additions.
- `orchestrator/context_snapshot.py::_canonical_json` is `json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)` (default `ensure_ascii=True`), and `_hash_bytes` prefixes `sha256:`. `orchestrator/policy_checkpoint.py::args_digest_of` is `hash_bytes(canonical_json(args))`. `args_sha256` reproduces that exact rule so a host-side digest can be compared with MCTL-side evidence.
- Parent design `platform-gitops/agents-state/mctl-agents/proposals/issue-746-spike-runtime-evaluate-a-portable-single/design.md` (sections "Runtime behaviour" and "Fake upstream and tests") is the behavioural source; tasks 3 to 7 and T2 to T10 here are copied from its `tasks.md`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/`: the deployed mctl-agents services are `mctl-agents-worker`, `mctl-agents-worker-exec`, `mctl-agents-worker-implement`. No runtime, proxy or `mctl-runtime` service exists. This slice deploys nothing, so no further deployed config is relevant.
- mctl MCP tools: not called in this run. The behaviour of `https://api.mctl.ai/mcp` (whether it sends `X-Request-Id`, whether it accepts a static human bearer token) is therefore not observed here, as it was not in #746; neither is needed for offline cargo tests and both stay under Open questions.

## Proposed solution

### Dependency strategy: std-only crate

`cargo build --locked` fails whenever Cargo would rewrite `Cargo.lock`. Adding any registry crate requires a lock entry with a `checksum`, which cannot be obtained without network access; the implementer and shepherd both lack network and `cargo`. A std-only crate keeps the committed lockfile valid as is (the single package entry), makes `cargo audit` trivially clean, and makes the tests trivially offline. This is the issue's sanctioned fallback ("hand-rolled `initialize`/`tools/list`/`tools/call`/`ping` subset"); the README records the choice and why `rmcp` was not used. Cost: the upstream client speaks `http://` only (the fake upstream on `127.0.0.1`); an `https://` URL is refused up front with `provider-unavailable` and a stderr diagnostic `https upstream requires TLS (deferred, see README)`. Adding TLS is a later slice (see Alternatives and Open questions).

### Layout (all under `experiments/portable-runtime-rs/`)

```text
src/main.rs         # hand-rolled argv parsing: proxy | init | doctor | --version; hidden --spawn-probe, __probe-dump
src/lib.rs          # pub mod declarations so integration tests can unit-check helpers
src/json.rs         # minimal JSON Value, parser, serializer; canonical form (sorted keys, ASCII-escaped)
src/sha256.rs       # FIPS 180-4 SHA-256 (tested against NIST vectors)
src/uuid.rs         # UUIDv4 from /dev/urandom (unix); version/variant bits set
src/allowlist.rs    # parse `tools = ["a", "b"]` TOML subset; error on missing/empty/invalid
src/credential.rs   # CredentialSource trait; TokenFile, EnvVar, Keychain/Loopback stubs; resolve()
src/spawn.rs        # the only Command builder: env_remove(MCTL_TOKEN, MCTL_RUNTIME_TOKEN_FILE)
src/http.rs         # HTTP/1.1 POST client over TcpStream: Content-Length + chunked, deadlines
src/upstream.rs     # Streamable HTTP MCP client: initialize, Mcp-Session-Id, tools/list, tools/call
src/bridge.rs       # stdio JSON-RPC server loop, allowlist filter, error mapping
src/correlation.rs  # invocation record -> one stderr JSON line
src/hostcfg.rs      # init rendering + guarded --write; doctor checks
fixtures/allowlist.toml            # tools = ["mctl_whoami", "mctl_list_services", "mctl_get_service_status"]
fixtures/host-fixture/README.md    # placeholder dir copied to a temp dir by T9
tests/common/mod.rs                # temp dirs, binary path (env!("CARGO_BIN_EXE_mctl-runtime")), sentinel
tests/common/fake_upstream.rs      # in-process Streamable HTTP /mcp server (std TcpListener)
tests/common/host.rs               # fixture-host driver: spawns binary, line-delimited JSON-RPC over stdio
tests/bridge.rs (T2-T6), tests/secrets.rs (T7), tests/correlation.rs (T8), tests/init_doctor.rs (T9, T10)
README.md                          # updated: subcommands, std-only decision, rmcp not used, delete instructions
```

`Cargo.toml` gains no dependency. It may gain `[lib]`/`[[bin]]` paths only if needed for `src/lib.rs` plus `src/main.rs` (Cargo's default layout already supports both, so likely no change).

### Credentials (`src/credential.rs`, task 3)

```rust
pub enum CredentialError { Absent, Unsupported(&'static str), InsecureMode { path: PathBuf, mode: u32 }, Unreadable(PathBuf, io::Error), Empty(PathBuf) }
pub trait CredentialSource { fn name(&self) -> &'static str; fn load(&self) -> Result<Secret, CredentialError>; }
pub struct TokenFile(PathBuf); pub struct EnvVar; pub struct Keychain; pub struct Loopback;
pub fn resolve(env: &dyn Fn(&str) -> Option<String>) -> Box<dyn CredentialSource>;
```

- Precedence: `MCTL_RUNTIME_TOKEN_FILE` (if set) then `MCTL_TOKEN`; otherwise a source whose `load` returns `Absent`. Env access goes through an injected closure so unit tests never mutate process env (tests run in parallel threads).
- `TokenFile::load` checks `metadata.permissions().mode() & 0o077 == 0` before reading (unix, `std::os::unix::fs::PermissionsExt`); `#[cfg(not(unix))]` returns `Unsupported`. Contents are trimmed; empty is an error.
- `Secret` wraps the string with a `Debug` impl printing `Secret(<redacted>)` and no `Display`, so it cannot reach a log line by accident. The only consumer is `upstream.rs` building the `Authorization: Bearer` header.
- No argv flag takes a token; `main.rs` rejects unknown flags.

### Spawn helper (`src/spawn.rs`, task 3)

`pub fn command(program: &Path) -> Command` returns `Command::new(program)` with `env_remove("MCTL_TOKEN")` and `env_remove("MCTL_RUNTIME_TOKEN_FILE")`; callers add only non-secret args. Production paths spawn nothing. Hidden `mctl-runtime --spawn-probe` resolves a credential (to prove one was loaded in the parent), then spawns `current_exe() __probe-dump` through `spawn::command`; the child prints its argv and full environment as JSON on stdout, the parent relays it and exits with the child's status. Neither hidden entry is listed in help.

### Bridge (`src/bridge.rs`, `src/upstream.rs`, `src/http.rs`, task 4)

- `proxy [--upstream URL] [--allowlist PATH] [--timeout-ms N]`. Defaults: `https://api.mctl.ai/mcp`, `fixtures/allowlist.toml` (relative to cwd), 10000 ms. The allowlist is loaded before reading stdin; missing, unreadable, empty list or a parse error exits 2 with a stderr diagnostic.
- Stdio: newline-delimited JSON-RPC 2.0 (the MCP stdio framing). Handled: `initialize` (answered locally with `protocolVersion` echoed from the host request when it is one of the supported versions, else `2025-06-18`; `capabilities: {tools: {}}`; `serverInfo: {name: "mctl-runtime", version}`), `notifications/initialized` (ignored), `ping` (`{}`), `tools/list`, `tools/call`. Other methods return JSON-RPC `-32601`. Malformed JSON returns `-32700` and the loop continues. Stdout carries only JSON-RPC; all diagnostics go to stderr.
- Upstream session is lazy: the first `tools/list` or `tools/call` that needs upstream performs `initialize` + `notifications/initialized` and stores `Mcp-Session-Id`. A failed attempt leaves no session, so the next call retries the handshake (no retry within one call).
- HTTP: `POST <path>` with `Content-Type: application/json`, `Accept: application/json, text/event-stream`, `Authorization: Bearer <token>`, `Mcp-Session-Id` once known, `X-Mctl-Invocation-Id` on `tools/call`. Responses: `application/json` body, or `text/event-stream` where the first `data:` event carrying the matching JSON-RPC `id` is the result (this is the Streamable HTTP response form, not the legacy SSE transport; no GET stream, no `/sse` endpoint). Bodies via `Content-Length` or `Transfer-Encoding: chunked`. `TcpStream::connect_timeout` and per-read `set_read_timeout` are derived from one deadline (`Instant::now() + timeout`) so the whole call is bounded.
- `tools/list`: upstream list filtered to names in the allowlist; each tool object is re-serialized from the parsed `Value`, and that re-serialization must reproduce the upstream's compact form, preserving key order and number text. To make T2's byte-equality hold, `json.rs` stores objects as ordered `Vec<(String, Value)>` and numbers as their source text.
- `tools/call`: name not in the allowlist -> `{"content":[{"type":"text","text":"not-eligible: <name> is not allowlisted"}],"isError":true,"structuredContent":{"reason_code":"not-eligible"}}` with no upstream I/O at all (not even a lazy initialize). Otherwise forwarded; the upstream `result` object is returned verbatim (content and `isError`); an upstream JSON-RPC `error` is relayed as the JSON-RPC error.
- Error mapping (each returned as an `isError: true` result with `reason_code`, the session stays alive): connect refused / reset / EOF before response -> `provider-unavailable`; deadline exceeded -> `provider-timeout`; HTTP 401 or 403 -> `credential-rejected` (exactly one request, no retry); no token -> `credential-absent` with zero requests; `https://` URL -> `provider-unavailable`. `tools/list` failures return a JSON-RPC error (`-32000`) whose `data.reason_code` carries the same code.

### Correlation (`src/correlation.rs`, task 5)

One record per `tools/call` (including refused and failed ones), written by a single `eprintln!` of a compact JSON object: `invocation_id` (UUIDv4), `host_request_id` (the host's JSON-RPC `id`, as JSON), `tool`, `args_sha256` (`sha256:` + hex of canonical `arguments`, `{}` when absent; canonical = sorted keys by code point, `,`/`:`, non-ASCII as `\uXXXX` with surrogate pairs, number text as parsed, matching Python's `json.dumps(..., sort_keys=True, separators=(",", ":"))`), `upstream_session_id` (`Mcp-Session-Id` or null), `upstream_request_id` (`X-Request-Id` response header or null), `outcome` (`ok`, `provider-error`, `not-eligible`, `provider-unavailable`, `provider-timeout`, `credential-rejected`, `credential-absent`), `is_error`, `latency_ms`. No argument, result or token value is ever placed in the record type; the struct has no field that could hold one. No file or DB write.

### `init` and `doctor` (`src/hostcfg.rs`, task 6)

- `init --host fixture|claude-code [--token-file PATH] [--write --config-dir DIR] [--upstream URL]`. The rendered config uses `command` = canonicalized `current_exe()`, `args = ["proxy", ...]`, and `env = {"MCTL_RUNTIME_TOKEN_FILE": "<path>"}` when `--token-file` is given, else a `_comment` telling the user to export `MCTL_TOKEN`. `claude-code` renders the `{"mcpServers": {"mctl": {...}}}` shape; `fixture` renders `{"servers": [{"name":"mctl", ...}]}`. `init` never resolves a credential value.
- Dry run is the default (stdout only). `--write` without `--config-dir` exits 2. `--config-dir` is canonicalized and refused if it equals or is inside `$HOME/.claude`, `$HOME/.claude.json`'s directory entry, `$HOME/.config/claude`, `$HOME/Library/Application Support/Claude`, `$HOME/.cursor`. Writes only `<dir>/mcp.json` (fixture) or `<dir>/.mcp.json` (claude-code).
- `doctor [--upstream URL] [--allowlist PATH] [--timeout-ms N]` prints one `check: status detail` line per item: version; credential source name; token file mode (when `TokenFile`); upstream round trip (`initialize` + `tools/list`); allowlist count; allowlisted tools missing upstream. Absent credential prints `credential absent` and skips the round trip. Exit 1 if any check fails.

### Fake upstream and host driver (`tests/common/`, task 7)

- `FakeUpstream::start(Knobs) -> FakeUpstream` binds `127.0.0.1:0`, serves `POST /mcp` on a thread per connection, responds with `Content-Length` JSON (and one tool, `mctl_whoami`, optionally via `text/event-stream` to cover that path), sets `Mcp-Session-Id: fake-session-1` and `X-Request-Id: req-<n>`. It records each request (method, JSON-RPC method, headers) in `Arc<Mutex<Vec<Recorded>>>`, with helpers `count("tools/call")`, `headers_of(n)`.
- Tools: `mctl_whoami` (ok text), `deny_tool` (`isError: true`, text `DENY: policy ...`), `approval_tool` (`isError: true`, `REQUIRE_APPROVAL ...`), `slow_tool` (sleeps `knobs.slow_ms`, default 2000), `secret_tool` (present upstream, never allowlisted). Each has a distinctive `inputSchema` with nested keys and non-alphabetical key order so byte-equality is meaningful.
- Knobs: `status_401` (every request -> 401), `reset` (accept then drop the socket), `echo_headers` (whoami result includes received header names and `X-Mctl-Invocation-Id`, `Authorization`).
- Closed port: bind a listener on `127.0.0.1:0`, take its port, drop it.
- `Host::spawn(args, env)` uses `std::process::Command` on `env!("CARGO_BIN_EXE_mctl-runtime")` with `env_clear()` plus explicit `PATH`, `HOME`, `TMPDIR`, captures stderr on a reader thread, and offers `request(method, params) -> Value` with a per-request deadline. Temp dirs are created under `std::env::temp_dir()` with pid + atomic counter + nanos names and removed on drop.
- Determinism: no fixed ports, no sleeps used for synchronization (channels and joins instead), the slow tool's sleep is the only timing and the bound uses wide slack (timeout 300 ms, assert elapsed < 1500 ms; slow tool 2000 ms). Tests never mutate the test process env.
- Three consecutive passes: CI runs `cargo test` once and the workflow file is out of this slice's write scope; the triple run is covered by a test-local loop: a `tests/stability.rs` that, under `#[test]`, runs the T2-T8 scenario functions three times in sequence. This satisfies the DoD without touching `.github/`.

### Clippy and portability

All code must pass `clippy -D warnings` on 1.85.0 for `--all-targets`. Unix-only APIs (`PermissionsExt`, `/dev/urandom`, `/proc`) are behind `#[cfg(unix)]`/`#[cfg(target_os = "linux")]` with non-unix fallbacks returning `Unsupported`, so the slice-3 Windows compile-only attempt is not pre-broken. T7's `/proc/<pid>/cmdline` assertion is `#[cfg(target_os = "linux")]`; on macOS it uses `ps -o args= -p <pid>`.

## Alternatives

1. **`rmcp` (exact pin) plus `tokio`, `reqwest`/`ureq` with `rustls`, `serde_json`, `uuid`, `sha2`, `clap`.** Less hand-written code and real TLS, which is what the eventual binary-size measurement needs. Rejected as the default because the offline implementer cannot write correct `Cargo.lock` entries (registry checksums for 50+ crates), so `cargo build --locked` would fail on the first CI run and neither implementer nor shepherd could fix it; `rmcp`'s MSRV against `1.85.0` is also unverified. It becomes viable if a human with cargo pushes a `cargo generate-lockfile` fix-up commit; that choice is the clarification question.
2. **Minimal deps (`serde_json` only, plus hand-rolled HTTP).** Halves the hand-written code, but still needs checksummed lock entries (serde, serde_core, itoa, memchr, ryu), so it has the same `--locked` failure as option 1 for little gain.
3. **Skip byte-equal schema forwarding by re-serializing through a generic map.** Simpler JSON, but fails T2 (`inputSchema` byte-equal) whenever upstream key order is not sorted. Rejected; the ordered `Value` with number source text is kept.

## Platform impact

- **Migrations / backward compatibility:** none. No production module, image, manifest, schema or API changes. The Docker build context excludes `experiments/` already; `pytest` and the isolation test are unaffected.
- **Resource impact:** the existing optional workflow runs a little longer (more tests; the stability test adds roughly 3 x 2 s for `slow_tool`, mitigated by a shorter `slow_ms` in the stability loop). No new runner or secret.
- **Risks and mitigations:**
  - *Unverified Rust lands.* Expected per the issue; CI on the PR is the verifier and shepherd fix-up commits address failures within scope. The std-only choice removes the lockfile and audit failure classes entirely, leaving compile, clippy and test failures, which are fixable without network.
  - *Hand-rolled JSON/SHA-256/HTTP bugs.* Unit tests with known vectors (NIST SHA-256 "abc" and empty string; JSON round trip of escapes, surrogates, nested ordering; chunked decoding) sit beside each module.
  - *Token leakage.* `Secret` has no `Display`; correlation struct has no value fields; `spawn.rs` is the single spawn path; T7 greps every capture for the sentinel.
  - *Local runtime becomes a policy authority.* Only the allowlist narrows; T4 proves remote refusals pass through unchanged.
  - *Flaky timing on macOS runners.* Wide slack on bounds, no fixed ports, no sleep-based synchronization.
  - *No TLS means `doctor` cannot reach the real `api.mctl.ai`.* Accepted for this slice and stated in the README; the live run was already opt-in and out of CI.
