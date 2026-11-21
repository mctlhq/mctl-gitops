# Tasks: issue-1316-feat-pa-outbound-egress-and-redirect-pol

Precondition: owner Phase 1 GO on #1312/#1316 (issue is on HOLD). No task starts before it.

- [ ] 1. Extend `internal/netsafe`: factor `unwrap(ip)` out of `PublicAddr`; add `Options.ExtraDeny []netip.Prefix` (checked in `DialContext` and in the Control hook with mapped/NAT64 unwrapping) and `Options.CheckRedirect` (nil keeps refuse-all). — DoD: all existing `internal/netsafe` and `internal/oauth/cimd` tests pass unchanged; new unit tests cover `ExtraDeny` for IPv4, IPv4-mapped and NAT64 forms.
- [ ] 2. Add `PA_EGRESS_DENY_CIDRS` parsing in `internal/config` (union with built-in RFC 1918 + CGNAT list; malformed value returns an error). (depends on 1) — DoD: config tests for empty, valid, malformed values.
- [ ] 3. Create `internal/pa/egress` with `Kind`, `ServerPolicy`, `Limits`, `Config`, `New`, `(*Egress).Client`; implement `guardRoundTripper` (scheme, userinfo, port, IP literal, host allowlist, per-kind timeout) and `capBody`; wire netsafe with `ExtraDeny` and per-kind `CheckRedirect` (discovery: max 2 hops; others: none). (depends on 1, 2) — DoD: package builds, `go vet` and `golangci-lint` clean, doc comment states T9.
- [ ] 4. Static guard test in `internal/pa` refusing `http.DefaultClient`, `http.Get/Post/Head/PostForm`, `http.DefaultTransport` and `http.Client`/`http.Transport` literals outside `internal/pa/egress`. (depends on 3) — DoD: test fails on a planted violation, passes on the clean tree.
- [ ] 5. S1 manifest `docs/agent-runtime/pa-s1-manifest.json` (create if absent) with S1-E1..E7, and `internal/pa/egress/manifest_test.go` enforcing ID-to-test both ways. (depends on 6) — DoD: removing a test or an ID fails CI.
- [ ] 6. Write the S1-E tests (see Tests). (depends on 3)
- [ ] 7. `scripts/pa-s1/mutations.sh` with one named mutation per S1-E ID; run it and attach the `caught` output to the PR. (depends on 5, 6) — DoD: every S1-E ID reports `caught`; script exits non-zero on any `SURVIVED`.
- [ ] 8. Fix the weak existing netsafe tests: `TestTimeoutFailsClosed` must exercise the netsafe transport (via an injected resolver and TLS root pool option, not by replacing `Transport`); `TestProxyEnvIgnored` must assert behaviour (no connection to the proxy listener). (depends on 1) — DoD: each fails when its guard is reverted.
- [ ] 9. Docs: add a "PA egress" paragraph to `docs/agent-runtime/personal-assistant-threat-model.md` T9 pointing at `internal/pa/egress` and the manifest; note default caps. (depends on 3) — DoD: doc tests in `docs/` pass.

## Tests

All tests use `httptest.NewTLSServer`, a stub `netsafe.Resolver` mapping synthetic hostnames (e.g. `tg.example.test`, `alice.example.test`) and an injected root pool; no real network.

- [ ] T1. `TestS1E1_HTTPRefused`: `http://tg.example.test/` returns `ErrScheme`; the stub resolver records zero lookups. Also `http://...:443`.
- [ ] T2. `TestS1E2_HostNotAllowed`: `https://evil.example.test/` and `https://tg.example.test.evil.test/`, uppercase/trailing-dot variants of allowed host succeed in matching, userinfo and IP-literal URLs refused; zero lookups for refused cases.
- [ ] T3. `TestS1E3_NonPublicRefused`: table of `10.0.0.1`, `127.0.0.1`, `169.254.169.254`, `100.64.0.1`, `0.1.2.3`, `224.0.0.1`, a configured cluster CIDR address, `fd00::1`, `fe80::1`, `::ffff:10.0.0.1`, `64:ff9b::a00:1`, `ff02::1` — all `ErrNonPublic`, no TCP accept on the listener.
- [ ] T4. `TestS1E3_RebindPinned`: resolver returns public address on first call and `127.0.0.1` on every later call; assert exactly one lookup per dial and the dial target equals the first answer (observed via a dialer hook).
- [ ] T5. `TestS1E4_DiscoveryRedirects`: discovery with 1 and 2 hops to allowed hosts succeeds; a 3rd hop fails; a hop to a foreign host fails with `ErrHostNotAllowed`; a hop to a host resolving private fails with `ErrNonPublic`; a hop to `http://` fails. Token, revocation, DCR and MCP kinds fail on any 3xx with `ErrRedirect`.
- [ ] T6. `TestS1E5_OversizedBody`: per kind, body of cap bytes succeeds, cap+1 fails with `ErrTooLarge`; streaming handler writing indefinitely is cut at cap+1 and the call fails.
- [ ] T7. `TestS1E6_SlowResponse`: per kind, a handler sleeping past the kind's timeout (test config with short limits) fails with a deadline error; slow headers and slow body both covered.
- [ ] T8. `TestS1E7_ProxyEnvIgnored`: set `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` to a listening proxy; request succeeds directly and the proxy listener sees zero connections.
- [ ] T9. Static guard test (task 4) and manifest test (task 5).
- [ ] T10. Regression: `go test ./internal/netsafe/... ./internal/oauth/...` unchanged and green.

## Rollback

Code-only, no migration. The PA is behind fail-closed `PA_ENABLED` (ADR 0011 "Switches"), so production behaviour is unaffected until the PA is enabled. If the netsafe extension misbehaves, revert the PR (merge commit revert); the new `Options` fields are additive and CIMD uses their zero values. If deployed, roll back by flags off (`PA_ENABLED=false`), then image rollback to the previous tag.
