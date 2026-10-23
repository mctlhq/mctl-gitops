# Design: issue-780-spike-runtime-746-slice-3b-https-upstrea

## Current state

All paths are relative to the repo root; the crate is `experiments/portable-runtime-rs/` (`mctl-runtime`, standalone
`[workspace]`, `rust-version = "1.85"`). `HEAD` is `2c56358`, the merge of PR #782 (the #777 implementer PR), so the slice's
blocker is cleared.

- `Cargo.toml`: feature `tls = ["dep:rustls", "dep:webpki-roots"]`, default off. `rustls =0.23.46` with
  `default-features = false, features = ["ring", "std", "tls12"]`; `webpki-roots =1.0.11`. `Cargo.lock` holds rustls,
  rustls-pki-types 1.15.1, rustls-webpki 0.103.16, ring 0.17.14, cc, webpki-roots, untrusted, zeroize, subtle. No test crate
  (no `rcgen`, no `rustls-pemfile`), so test certificates must be fixtures and PEM parsing must use
  `rustls::pki_types::pem::PemObject` (pki-types `alloc` feature, enabled through rustls `std`) or DER fixtures.
- `src/tls.rs` (compiled only with `tls`, declared in `src/lib.rs` under `#[cfg(feature = "tls")]`): `client_config()` returns
  `Arc<ClientConfig>` built with `builder_with_provider(ring::default_provider())`, safe default versions, the
  `webpki_roots::TLS_SERVER_ROOTS` store, no client auth. One test, `builds_with_bundled_roots_offline`. The module comment says
  the https path "is not wired yet (slice 3b)".
- `src/http.rs`: `Url { host, port, path }`; `parse_url` returns `HttpError::Unsupported("https upstream requires TLS ...")`
  for `https://`, defaults http to port 80. `post(url, headers, body, deadline)` resolves, `TcpStream::connect_timeout` with
  the remaining budget, sets nodelay, writes `POST ... Host: host:port ... Connection: close`, then loops
  `parse_response(buf, eof)` with `set_read_timeout(remaining(deadline))`. `map_io` maps timeouts to `HttpError::Timeout`.
  Test `url_parsing` asserts the https refusal in the same test as the http cases.
- `src/upstream.rs`: `Upstream::new(url, token, timeout)`; `Upstream::post` calls `http::parse_url(&self.url)?` before the
  token check, so https fails before any I/O. `From<HttpError>`: `Timeout` -> `provider-timeout`, everything else ->
  `provider-unavailable`. Test `https_is_provider_unavailable_without_io` (T1).
- `tests/common/fake_upstream.rs`: in-process Streamable HTTP server on `127.0.0.1:0`; `handle(mut stream: TcpStream, ...)`,
  `read_request(stream: &TcpStream)` uses `stream.try_clone()` for a `BufReader`, `write_response(stream: &mut TcpStream, ...)`.
  It is reused verbatim by `examples/fake_upstream.rs` via `#[path]`.
- `bench/measure.sh`: one `NOTE="http-only, TLS not included"`; `rec()` prints records without a variant field; builds
  `target/release/mctl-runtime` once (`build_time`, `binary_size`, `dependency_lines`), then `bench_driver` modes
  `ready latency rss` for `rust-proxy` (passing `--note "$NOTE"`) and the Python baseline; `render_table.py` turns the JSONL
  into `<os>.json` / `<os>.md` (columns Subject, Metric, Value, Unit, Status, Reason, Note).
- `examples/bench_driver.rs`: flags `--upstream --n --subject --note --raw`; emits one JSON object per measurement and adds
  `note` only for the matching subject (line ~108).
- `.github/workflows/portable-runtime-spike.yml`: jobs `changes`, `cargo` (default and `--features tls` build/test/clippy,
  `cargo audit`), `parity` (T11, T12 `bench/check_report.sh docs/spikes/746-portable-runtime.md`), `bench` (informational,
  `continue-on-error`), `cross-build` (informational; 5 matrix entries; one `cargo build --release --locked --target` and one
  JSON record with a hard-coded `"note":"http-only, TLS not included"`; artifact path `cross/${{ matrix.name }}.json`), and the
  required aggregator `portable-runtime-spike`.
- `docs/spikes/746-portable-runtime.md` (208 lines): run `40002256127`; section `## 4. TLS limit`; matrix row 4 and 9 mention
  http-only; GO line G6 "unproven ... slice 3b (#780) measures the `--features tls` build"; `## Decision` contains
  `Proposed: \`THIN_ADAPTER\`` (no `Recommendation:` line). `docs/spikes/746/measurements/` holds `cross-build.json`,
  `ubuntu-latest.{json,md}`, `macos-14.{json,md}`, `parity-bytes.md`, `README.md`.
- `bench/check_report.sh` (T12): exactly one decision token in `## Decision`; G1..G7 plus Rust clause lines each cite
  `measurements/` or `T<n>`.
- `tests/test_portable_runtime_isolation.py`: keeps the experiment out of shipped paths; no `Cargo.toml` outside it.

Deployed state checked:
- Not a deployed service: the crate is an experiment excluded from the image (`tests/test_portable_runtime_isolation.py`,
  `test_dockerfile_does_not_copy_experiments`).
- `grep -rli "portable-runtime|mctl-runtime"` over `$MCTL_GITOPS_ROOT`-equivalent `/workdir/mctl-gitops/platform-gitops/services`
  and `/tenants`: no match (tenants present: admins, karabu, labs). No deployed config is relevant; no mctl MCP call was needed.
- CI run ids cited in the report (`40002256127`) were read from the repo files only; GitHub Actions was not queried.

## Proposed solution

### 1. Transport in `src/http.rs`

- Add `pub tls: bool` to `Url` (false for `http://`). `parse_url`:
  - `#[cfg(not(feature = "tls"))]`: unchanged refusal of `https://` with `HttpError::Unsupported`.
  - `#[cfg(feature = "tls")]`: accept `https://`, default port 443, same authority/path parsing (factor the shared parsing into a
    private `parse_authority(rest, default_port, tls)`).
- Split the current `post` body into a generic exchange:
  `fn exchange<S: Read + Write>(stream: &mut S, sock: &TcpStream, url, headers, body, deadline)` that writes the request and
  runs the existing read/parse loop, calling `sock.set_read_timeout` / `set_write_timeout` with `remaining(deadline)` before
  each I/O. The current `post` keeps its signature and becomes: connect (unchanged), then
  `if url.tls { tls_exchange(...) } else { exchange(&mut tcp, &tcp_clone_or_ref, ...) }`. For plain TCP, use
  `exchange` over `&TcpStream` (which implements `Read + Write`) so no clone is needed.
- Add `pub fn post_with(url, headers, body, deadline, connector: &Connector)` where, under `tls`,
  `pub struct Connector { tls: Arc<rustls::ClientConfig> }` with `Connector::default_tls()` -> `tls::client_config()` and
  `Connector::with_config(cfg)` (tests inject a test-root config). `post` calls `post_with` with the default connector. Under
  the default build `Connector` is an empty struct, so `upstream.rs` compiles identically.
- `tls_exchange` (`#[cfg(feature = "tls")]`): `ServerName::try_from(url.host.clone())` (DNS name -> SNI; IP literal ->
  `ServerName::IpAddress`, verified against an IP SAN, no SNI sent, which is rustls' behaviour); build
  `ClientConnection::new(cfg, name)`, wrap in `rustls::StreamOwned::new(conn, tcp)`, then drive the handshake explicitly with
  `while conn.is_handshaking() { conn.complete_io(&mut sock) }` under the deadline before any request bytes are written, so a
  certificate failure sends no Authorization header. Then call `exchange` on the `StreamOwned`, using `stream.get_ref()` for
  timeouts.
- Error mapping: `rustls::Error` (including `InvalidCertificate(UnknownIssuer)` and `NotValidForName`) ->
  `HttpError::Unavailable("tls: ...")`; I/O `WouldBlock`/`TimedOut` -> `HttpError::Timeout` (existing `map_io`);
  `UnexpectedEof` from rustls (no `close_notify`) -> retry `parse_response(buf, true)` only if the framing is self-delimiting
  (Content-Length or chunked complete); otherwise `Unavailable("connection closed before a complete response")`. This keeps the
  existing until-close framing safe against truncation.
- Host header stays `host:port`.

### 2. `src/upstream.rs`

- Add `#[cfg(feature = "tls")] pub fn with_tls_config(mut self, cfg: Arc<ClientConfig>) -> Self` storing a `Connector`; default
  `Upstream::new` uses `Connector::default_tls()` lazily (built on first https post, error -> `provider-unavailable`).
  `Upstream::post` calls `http::post_with(&url, ..., &self.connector)`.
- `https_is_provider_unavailable_without_io` gets `#[cfg(not(feature = "tls"))]` and is otherwise unchanged (T1).
- In `http::tests::url_parsing`, move the https assertion under `#[cfg(not(feature = "tls"))]` inside the test body and add a
  `#[cfg(feature = "tls")]` block asserting `parse_url("https://api.mctl.ai/mcp")` gives port 443, `tls: true`. Test names in
  the default build do not change.
- Update the module comments in `src/http.rs` and `src/tls.rs` (no longer "deferred"/"not wired").

### 3. Offline TLS test (T2, T3)

- Fixtures under `experiments/portable-runtime-rs/fixtures/tls/`: `ca.pem` (self-signed test CA, ECDSA P-256,
  `basicConstraints=critical,CA:TRUE`), `server.pem` (leaf signed by the CA, `CA:FALSE`, SAN `IP:127.0.0.1, DNS:localhost`,
  EKU serverAuth), `server.key.pem` (PKCS#8), `other-ca.pem` (a second, unrelated self-signed CA for the negative test), and
  `gen.sh` + `README.md` recording the exact `openssl` commands and a validity window of 100 years so the test never expires
  in practice. A CA plus leaf is used instead of one self-signed leaf because rustls-webpki rejects a certificate carrying
  `CA:TRUE` as an end-entity (`CaUsedAsEndEntity`), which `openssl req -x509` sets by default.
- `tests/common/fake_upstream.rs`: make `read_request` take `&mut impl BufRead` and `write_response` take `&mut impl Write`, and
  `handle` generic over `S: Read + Write` (the TcpStream path passes a `BufReader<&TcpStream>`/`&TcpStream`). Add, under
  `#[cfg(feature = "tls")]`, `FakeUpstream::start_tls(knobs, server_config)` that wraps each accepted stream in
  `rustls::StreamOwned<ServerConnection, TcpStream>` and sends `close_notify` after the response; `url()` returns `https://`.
  The example binary keeps using `start` unchanged.
- New `tests/tls.rs` gated with `#![cfg(feature = "tls")]` (so the default build's test list is unchanged):
  - helper `server_config()`: `ServerConfig::builder_with_provider(ring)` + `with_single_cert(server.pem chain, key)` parsed
    with `CertificateDer::pem_slice_iter` / `PrivateKeyDer::from_pem_slice` via `include_bytes!` of the fixtures.
  - helper `client_with(ca)`: `RootCertStore` containing only the given CA, built exactly like `tls::client_config()` but with
    that store (expose `tls::client_config_with_roots(RootCertStore)` and have `client_config()` call it, so the test exercises
    the production builder).
  - `t2_tls_initialize_and_tools_list`: `Upstream::new(fake.url(), token, 5 s).with_tls_config(client_with(ca.pem))`,
    `list_tools()` returns the fake's tool set; assert session id set (proves `initialize` completed).
  - `t3_rejects_untrusted_server_cert`: same with `other-ca.pem` -> `reason_code() == "provider-unavailable"` and the fake
    recorded zero HTTP requests (add a request counter knob if not present).
  - `t3b_bundled_roots_reject_test_cert`: `Upstream::new` without injection (production `client_config()`, webpki roots) ->
    `provider-unavailable`. Offline: the fake listens on `127.0.0.1`.
- Bridge-level coverage: one tls test that runs the proxy binary (`tests/common/host.rs` style) is not required; the unit
  path is the same code.

### 4. Bench variant (T4)

- `bench/measure.sh`: wrap the build/size/deps/startup sections in `for VARIANT in default tls`; features
  `FEATURES=()` / `FEATURES=(--features tls)`; build into separate target dirs (`CARGO_TARGET_DIR=target/bench-$VARIANT`) so
  both binaries exist and the clean build time is honest per variant (`cargo clean` per target dir). `NOTE` is
  `http-only, TLS not included` for default and empty for tls. `rec()` gains a `variant` field written on every record; the
  Python baseline, `python-uv-run` and `live` records are emitted once during the default pass with `"variant":"default"`.
  `examples` (driver and fake) are built once, default features.
- `examples/bench_driver.rs`: new `--variant NAME` flag (default `default`) added to every emitted record; `--note` behaviour
  unchanged. `measure.sh` passes `--variant "$VARIANT"`.
- `bench/render_table.py`: add a Variant column, plus a second "Rust proxy: default vs tls" table pivoted on
  (metric) with one column per variant.
- `bench/check_variant.py` (stdlib, `python -I`): schema check that every record in a measurements JSON has `variant` in
  `{"default","tls"}`, that every `tls` record lacks the http-only note and every default rust-proxy record has it; run on a
  synthetic sample generated by calling `rec()` through a small `measure.sh --self-test` path or, simpler, on the committed
  `docs/spikes/746/measurements/*.json` once refreshed plus a built-in fixture list. Wired into the `parity` job (required) on a
  fixture so it is deterministic, and run in the `bench` job on the real output.

### 5. Cross-builds

- In the `cross-build` step, loop `for VARIANT in default tls` inside the existing matrix entry (keeping the matrix as is avoids
  GitHub's `include` merge rules collapsing entries). Each iteration: `cargo build --release --locked --target "$TARGET"
  ${VARIANT:+...}` with `--features tls` for tls, own `CARGO_TARGET_DIR`, write `$out/$NAME-$VARIANT.json` with the existing
  fields plus `"variant"` and `"prerequisite"`. `note` is `http-only, TLS not included` only for default.
- `prerequisite`: empty when the build succeeded with the existing setup; on failure, a short classification grepped from the
  log (`ring` build script / `cc` "failed to find tool" -> `C cross-compiler for $TARGET (e.g. clang or aarch64-linux-musl-gcc)`;
  `link.exe`/MSVC -> `MSVC build tools`), otherwise the first ring error line. No toolchain is installed by this slice; the
  record says what would be needed. Artifact path becomes `cross/${{ matrix.name }}-*.json`.
- `docs/spikes/746/measurements/cross-build.json` is regenerated by the shepherd as one array of 10 records.

### 6. Report

- `docs/spikes/746-portable-runtime.md`: new run id in the header; section 3 adds a side-by-side table (metric x
  {default, tls} for ubuntu-latest and macos-14, plus cross-build size/status per target per variant), every cell citing the run
  id; `## 4. TLS limit` is rewritten to "TLS variant": the caveat is kept only for default numbers, and the remaining limit
  (bench startup/latency use the plain-http fake, handshake not timed) is stated; matrix rows 4 and 9 updated; G6 line re-checked
  against tls cross-builds citing `measurements/cross-build.json`; `## Decision` has exactly one `Recommendation: \`<TOKEN>\``
  line replacing `Proposed: ...`. The implementer writes the structure with `pending CI run` placeholders; the shepherd fills
  numbers from the CI artifact in a fix-up citing the run id (as in #777).
- `bench/check_report.sh` additionally requires exactly one line matching `^Recommendation: ` in the file, with the self-check
  extended (two `Recommendation:` lines must fail).

## Alternatives

- **Separate `HttpsUpstream` type / trait object for the transport.** Cleaner abstraction but duplicates `Upstream`'s session
  logic or adds dynamic dispatch to the default build. Rejected: a generic `exchange<S: Read + Write>` keeps the default code path
  identical and confines TLS to one `#[cfg]` function.
- **Test with a single self-signed leaf certificate.** What the issue literally names; rejected as the only form because
  rustls-webpki refuses a `CA:TRUE` end-entity and `openssl req -x509` sets it by default. The CA+leaf pair is still a
  self-signed test root, trusted only through a test store. A `CA:FALSE` self-signed leaf would also work and is acceptable if
  the implementer prefers fewer files.
- **Cross-build variants as a matrix dimension.** Doubles jobs and interacts badly with the `include`-only matrix (GitHub merges
  include entries into existing combinations). Rejected in favour of an in-step loop with per-variant records.
- **Generate the certificate at test time.** Needs `rcgen` (not in the lock) or a shell-out to `openssl` (not guaranteed on
  runners/Windows). Rejected: fixtures plus `gen.sh`.

## Platform impact

- No migration, no deployed component, no shipped path: the crate stays excluded from the image
  (`tests/test_portable_runtime_isolation.py`). `Cargo.lock` unchanged; `cargo build --locked` enforces it in CI.
- Default build: same code path for http, same refusal and same test names. Risk: refactoring `post` into `exchange` changes
  default behaviour subtly. Mitigation: existing `tests/bridge.rs`, `tests/stability.rs`, T11 parity and the unchanged default
  test list are the guard; the refactor keeps the timeout calls in the same order.
- CI time: bench and cross-build roughly double (two release builds per job); both jobs are informational
  (`continue-on-error`). The required `cargo` job already builds tls.
- Risk: ring fails to cross-compile for `aarch64-linux-musl-built-only` (no C cross-compiler with `rust-lld`). That is a
  finding for G6, recorded, never a red required check.
- Risk: checked-in private key fixture. It is a test-only key for `127.0.0.1`/`localhost`, documented as such in
  `fixtures/tls/README.md`; secret scanners may flag it, so the README states it and the path is test-only.
- Security: TLS failures happen before any request byte is written, so a bearer token is never sent to an unverified peer.
