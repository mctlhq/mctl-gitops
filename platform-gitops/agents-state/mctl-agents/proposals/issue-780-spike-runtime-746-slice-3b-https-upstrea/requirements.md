# Spike #746 slice 3b: https upstream behind the `tls` feature, and a TLS bench variant

## Context

Spike #746 asks whether a portable, single-binary agent-side runtime is worth building, and whether to write it in Rust. Slice 3
(#777, merged as PR #782) delivered the Rust proxy at `experiments/portable-runtime-rs/`, the bench (`bench/measure.sh`,
`examples/bench_driver.rs`), the cross-build matrix in `.github/workflows/portable-runtime-spike.yml`, and the report
`docs/spikes/746-portable-runtime.md` with its measurements under `docs/spikes/746/measurements/`. Every Rust number in that
report is labelled `http-only, TLS not included`, because `src/http.rs::parse_url` refuses `https://` and `src/upstream.rs`
maps that refusal to `provider-unavailable`. #779 added an optional `tls` Cargo feature (`rustls =0.23.46` with the ring
provider, `webpki-roots =1.0.11`, `src/tls.rs::client_config()`) that nothing calls yet.

This slice wires `https://` upstreams through rustls when the `tls` feature is on, proves it with an offline TLS test, and runs
the bench and cross-build matrix for both builds so the report can compare a TLS-capable Rust artifact against the Python thin
adapter (which already carries TLS through `httpx`). The #746 owner records the spike verdict only after this evidence exists,
so the G6 check and the size comparison in the report must stop being lower bounds.

## User stories

- AS the #746 spike owner I WANT size, build-time, dependency and startup numbers for a TLS-capable Rust build SO THAT the
  verdict does not rest on an http-only lower bound.
- AS the #746 spike owner I WANT G6 (packaging story) checked against the `--features tls` cross-builds SO THAT the ring
  toolchain cost per target is known.
- AS a maintainer of the spike I WANT the default (std-only) build to behave exactly as before SO THAT #777's results and tests
  stay valid.
- AS a reviewer I WANT the TLS path tested offline against a local server with a test-only trust root SO THAT CI needs no
  network and the bundled roots are never trusted for test certificates.

## Acceptance criteria (EARS)

- WHILE the crate is built without the `tls` feature THE SYSTEM SHALL refuse an `https://` upstream URL with reason code
  `provider-unavailable`, without any network I/O, exactly as today (existing test
  `upstream::tests::https_is_provider_unavailable_without_io`, unchanged).
- WHILE the crate is built without the `tls` feature THE SYSTEM SHALL produce the same set of `cargo test` test names as on the
  base commit (no test added, removed or renamed in the default build).
- WHEN the crate is built with `--features tls` and the upstream URL starts with `https://` THE SYSTEM SHALL connect over TCP,
  wrap the stream in `rustls::StreamOwned<ClientConnection, TcpStream>` using the configured `ClientConfig`
  (`tls::client_config()` in production), and use the URL host as the server name (SNI for DNS names, IP SAN check for IP
  literals).
- WHEN an `https://` URL has no explicit port THE SYSTEM SHALL use port 443; an `http://` URL keeps the default port 80.
- WHILE an https request is in flight THE SYSTEM SHALL bound the TCP connect, TLS handshake, write and every read by the same
  single deadline that bounds the plain-http path today, and map an expired deadline to `provider-timeout`.
- IF the server certificate does not chain to the configured root store, or does not match the host name THEN THE SYSTEM SHALL
  fail the request with `provider-unavailable` and send no HTTP request bytes (no bearer token leaves the process).
- IF the TLS connection ends without `close_notify` before a complete response is framed THEN THE SYSTEM SHALL fail the request
  with `provider-unavailable`, never return a truncated body.
- WHEN `cargo test --locked --features tls` runs THE SYSTEM SHALL complete `initialize` and `tools/list` against an in-process
  rustls server on `127.0.0.1:0` whose certificate is trusted only through a test-only `RootCertStore` built from a checked-in
  fixture, with no network access.
- WHEN the bench runs THE SYSTEM SHALL measure the Rust proxy for both builds, `default` and `tls`, and every record it writes
  SHALL carry `"variant": "default"` or `"variant": "tls"`.
- WHEN the bench writes a `tls` record THE SYSTEM SHALL omit the `http-only, TLS not included` note; default rust-proxy records
  SHALL keep it.
- WHEN the cross-build job runs for a target THE SYSTEM SHALL build both variants and write one record per variant with
  `variant`, `status`, `size_bytes` and a `prerequisite` field naming the toolchain prerequisite a failed or extra-configured
  ring build needed (empty when none).
- WHEN the report is updated THE SYSTEM SHALL contain a side-by-side default/tls table, a G6 line checked against the tls build,
  no TLS-limit caveat for the tls build, exactly one `Recommendation:` line carrying exactly one of `NO_RUNTIME | THIN_ADAPTER |
  PORTABLE_RUNTIME_RUST | PORTABLE_RUNTIME_OTHER`, and a CI run id for every number.
- WHILE this slice is implemented THE SYSTEM SHALL leave `experiments/portable-runtime-rs/Cargo.lock` byte-identical and change
  no file outside `experiments/portable-runtime-rs/`, `docs/spikes/746/`, `docs/spikes/746-portable-runtime.md` and
  `.github/workflows/portable-runtime-spike.yml`.
- WHILE this slice is implemented THE SYSTEM SHALL keep `uv run --locked pytest -q` results unchanged.

## Out of scope

- Any change to `Cargo.toml` dependencies or `Cargo.lock` (no new crate such as `rcgen`, `rustls-pemfile` or `tokio-rustls`).
- Client certificates, ALPN, HTTP/2, proxies, OAuth, host trust-store loading (`rustls-native-certs`).
- Exercising the TLS handshake inside the latency/RSS bench against a TLS fake upstream (the tls variant runs the existing bench
  against the existing plain-http fake upstream; see design).
- Restarting the #746 DevLoop or editing `roadmap/spikes/portable-runtime.yaml`: the owner records the verdict.
- Starting this slice before #777's implementer PR merged (it has: PR #782 is the current `HEAD`).

## Open questions

- The issue says the report lives in `docs/spikes/746/`, but the #777 report is `docs/spikes/746-portable-runtime.md` (only the
  measurements are under `docs/spikes/746/`). The proposal treats that file as in scope; the workflow's change filter
  `^docs/spikes/746` already matches it.
- The report has no `Recommendation:` line today; its `## Decision` section says `Proposed: \`THIN_ADAPTER\``. The proposal
  replaces that line with a single `Recommendation: \`<TOKEN>\`` line so `bench/check_report.sh` (T12, exactly one token in
  `## Decision`) still passes. Which token is recorded is decided from the tls evidence when the shepherd fills in numbers; the
  implementer keeps `THIN_ADAPTER` until then unless G1/G7 change, which this slice does not touch.
- "Every record carries variant": python-baseline and `both`/`live` records are not build variants. The proposal writes them
  once, in the default pass, with `"variant": "default"`, so the schema test is total. Confirm this labelling is acceptable.
- The tls bench variant measures startup/latency/RSS of the tls binary against the plain-http fake upstream, so it does not
  include handshake cost. The report must state this. An https latency record is not requested by the issue.
- Fixture generation: the implementer has no cargo and no network; `openssl` was present in the investigation sandbox
  (`/usr/bin/openssl`) but its availability to the implementer is not guaranteed. If it is unavailable, the shepherd generates
  the fixtures with the checked-in `fixtures/tls/gen.sh` in a fix-up commit.
