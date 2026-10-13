# Tasks: issue-375 — CIMD

One PR per numbered group is fine; 1 and 2 can land before any wiring.
Re-read line numbers on `main` before editing.

- [ ] 1. `internal/netsafe` (§1). — DoD: table tests for `PublicAddr` over
  every refused range including IPv4-mapped and NAT64 forms; a stub
  resolver returning a public then a loopback address proves the `Control`
  hook refuses the loopback connect (rebinding); a local TLS server
  answering 302 is refused; proxy env vars are ignored; body cap and
  timeout fail closed. Mutation: dropping the `Control` check fails the
  rebinding test.

- [ ] 2. `internal/auth/cimd` (§2). — DoD: tests for every R5 shape rule,
  R6 allowlist (exact and suffix, checked before any dial; an empty list
  admits nothing), R11 `RedirectAllowed` (exact match; `127.0.0.1` and
  `[::1]` entries accept another port and refuse another scheme, host, path
  or query; `localhost` gets no port exemption; userinfo, fragment and
  backslash refused; mutation: comparing the port fails the ephemeral-port
  test, dropping the path comparison fails the other-path test), R8 (status,
  media type, size, timeout), R10 (client_id mismatch, empty/invalid
  `redirect_uris`, wrong auth method, `client_secret` present), positive
  and negative cache, singleflight (one fetch for N concurrent resolves),
  per-host rate limit and semaphore refusals.

- [ ] 3. Wire into `OAuthServer` (§3), behind `CIMD != nil`. — DoD:
  - CIMD enabled: a document-listed `redirect_uri` is accepted, an unlisted
    one is refused even when it is on the global allowlist or is loopback;
    a fetch failure refuses with a direct 400 and no redirect.
  - CIMD disabled: an `https://` `client_id` behaves exactly as on `main`.
  - Compatibility suite: existing pre-registered, DCR and loopback tests
    pass unchanged with CIMD enabled.
  - Mutation pins (A5): removing the CIMD branch fails the CIMD tests;
    removing DCR registration fails the DCR tests.
  - Metadata advertises the flag only when enabled.
  - Pre-registered loopback entries stay port-exact with CIMD enabled.

- [ ] 4. Consent interstitial (§4). — DoD: handler tests for approve, deny,
  replayed token, expired token, a second authorization by the same human
  and client showing the page again, missing/mismatched cookie, and a non-CIMD
  client never seeing the page; the page HTML-escapes `client_name`.

- [ ] 5. `oauth.grant_issued` audit (§5) for every client kind. — DoD:
  tests assert one entry per issued code with the right `client_kind`, the
  principal in `PrincipalID`, and no client field in the principal column;
  A4: the same human through CIMD, DCR and pre-registered clients resolves
  to the same `prn_`.

- [ ] 6. Configuration and docs (§6): `cmd/api/main.go`, README env table,
  `.env.example`, `helm/templates/deployment.yaml` (startup refuses
  `OAUTH_CIMD_ENABLED=true` with an empty allowlist, with a test), `docs/federation.md`
  (client identity vs principal identity), OpenAPI for `/oauth/consent`.
  — DoD: `go vet ./...`, `gofmt`, `golangci-lint` clean; `go test ./...`
  green.

- [ ] 7. Rollout (owner-gated, mctl-gitops): release with CIMD disabled;
  confirm egress; enable with the owner-chosen allowlist; collect A6 live
  proofs; then close #375.
