# Tasks: issue-780-spike-runtime-746-slice-3b-https-upstrea

All paths are under `experiments/portable-runtime-rs/` unless stated. `Cargo.toml` and `Cargo.lock` must not change.

- [ ] 1. Refactor `src/http.rs`: add `Url.tls`, factor URL authority parsing, split `post` into connect + generic
  `exchange<S: Read + Write>` (timeouts set on the underlying `TcpStream` from the one deadline), add `Connector` and
  `post_with`; keep `parse_url`'s https refusal under `#[cfg(not(feature = "tls"))]`. — DoD: default build compiles with the
  same public behaviour; `url_parsing` keeps its name, its https assertion is cfg-gated, a tls block checks port 443 and
  `tls: true`; default `cargo test` test names identical to base.
- [ ] 2. (depends on 1) TLS path under `#[cfg(feature = "tls")]`: `tls::client_config_with_roots(RootCertStore)` with
  `client_config()` delegating to it; `tls_exchange` using `ServerName::try_from(host)`, `ClientConnection`,
  `rustls::StreamOwned`, explicit handshake under the deadline before writing, error mapping (rustls errors and unclean EOF ->
  `Unavailable`, timeouts -> `Timeout`). Update module comments in `src/http.rs` and `src/tls.rs`. — DoD: `cargo build/clippy
  --locked --all-targets --features tls -- -D warnings` clean in CI.
- [ ] 3. (depends on 2) `src/upstream.rs`: hold a `Connector`; `#[cfg(feature = "tls")] Upstream::with_tls_config`; mark
  `https_is_provider_unavailable_without_io` `#[cfg(not(feature = "tls"))]` with its body unchanged. — DoD: T1 passes in the
  default build; no default-build test added or removed.
- [ ] 4. Fixtures `fixtures/tls/`: `gen.sh` (openssl commands: ECDSA P-256 test CA `CA:TRUE`, leaf `CA:FALSE` with SAN
  `IP:127.0.0.1,DNS:localhost` and EKU serverAuth, PKCS#8 key, unrelated `other-ca.pem`, 100-year validity), the generated
  `ca.pem`, `server.pem`, `server.key.pem`, `other-ca.pem`, and `README.md` stating they are test-only. — DoD: files checked in;
  if `openssl` is unavailable to the implementer, `gen.sh` and README are committed and the shepherd runs `gen.sh` in a fix-up.
- [ ] 5. (depends on 2, 4) `tests/common/fake_upstream.rs`: make `read_request`/`write_response`/`handle` generic over the
  stream; add a request counter if missing; add `#[cfg(feature = "tls")] FakeUpstream::start_tls(knobs, Arc<ServerConfig>)`
  serving over `StreamOwned<ServerConnection, TcpStream>` with `close_notify`. `examples/fake_upstream.rs` unchanged in
  behaviour. — DoD: default tests and T11 parity unchanged.
- [ ] 6. (depends on 3, 5) `tests/tls.rs` with `#![cfg(feature = "tls")]`: T2, T3, T3b (see Tests). — DoD: passes on
  ubuntu-latest and macos-14 with `--features tls`, offline.
- [ ] 7. Bench variant: `examples/bench_driver.rs` `--variant` flag on every record; `bench/measure.sh` loops
  `default`/`tls` with per-variant `CARGO_TARGET_DIR`, writes `variant` on every record (python/live records once with
  `default`), note only on default rust-proxy records; `bench/render_table.py` Variant column plus a default-vs-tls pivot
  table; `bench/check_variant.py` schema check. — DoD: T4 passes; a local/CI run yields both variants per OS.
- [ ] 8. Workflow `.github/workflows/portable-runtime-spike.yml`: run `check_variant.py` on its fixture in the required
  `parity` job; cross-build step loops both variants, writes `$NAME-$VARIANT.json` with `variant` and `prerequisite`, note only
  on default; artifact path `cross/${{ matrix.name }}-*.json`. — DoD: every cross-build entry uploads two records; required
  check `portable-runtime-spike` unchanged in its needs.
- [ ] 9. Report `docs/spikes/746-portable-runtime.md` and `docs/spikes/746/measurements/README.md`: side-by-side variant table,
  TLS-limit section rewritten (caveat kept for default only, plain-http-fake limit stated), matrix rows 4 and 9, G6 re-checked
  against tls cross-builds, `Proposed:` line replaced by exactly one `Recommendation: \`<TOKEN>\``; `bench/check_report.sh`
  requires exactly one `^Recommendation: ` line with an added self-check. Numbers left as `pending CI run` for the shepherd.
  — DoD: T12 and the new check pass.
- [ ] 10. (shepherd, depends on 1-9 green) Download the bench and cross-build artifacts of the PR's CI run, commit refreshed
  `docs/spikes/746/measurements/{ubuntu-latest,macos-14}.{json,md}` and `cross-build.json`, and fill every report number with
  that run id. — DoD: every number in the report cites a run id; `portable-runtime-spike` green.

## Tests

- [ ] T1. Default build: `upstream::tests::https_is_provider_unavailable_without_io` unchanged and passing; default
  `cargo test --locked -- --list` output equals the base commit's.
- [ ] T2. `tests/tls.rs::t2_tls_initialize_and_tools_list`: tls build, `start_tls` fake on `127.0.0.1:0`, client trusting only
  `fixtures/tls/ca.pem`; `initialize` completes (session id set) and `tools/list` returns the fake's tools.
- [ ] T3. `tests/tls.rs::t3_rejects_untrusted_server_cert`: client trusting only `other-ca.pem` gets `provider-unavailable`
  and the fake counted zero HTTP requests; `t3b_bundled_roots_reject_test_cert`: production `client_config()` (webpki roots)
  also rejects.
- [ ] T4. `bench/check_variant.py`: every record has `variant` in `{default, tls}`; tls records have no http-only note;
  default rust-proxy records have it; the script fails on a fixture with a missing variant (self-check).
- [ ] T11/T12. Existing parity and report-shape checks still pass; `uv run --locked pytest -q` unchanged.
- [ ] Lock check: `git diff --exit-code experiments/portable-runtime-rs/Cargo.lock` against the base is empty.

## Rollback

The slice touches only the experiment, its docs and the spike workflow, and nothing ships. Revert the PR; the default build,
#777's measurements and report return as they were. If only the bench or cross-build changes misbehave, revert those files:
both jobs are `continue-on-error`, so they never block other PRs in the meantime.
