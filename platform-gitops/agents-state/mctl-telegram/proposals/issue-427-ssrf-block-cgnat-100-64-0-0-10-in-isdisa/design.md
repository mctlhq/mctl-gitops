# Design: issue-427-ssrf-block-cgnat-100-64-0-0-10-in-isdisa

## Current state

The SSRF guard lives entirely in `internal/telegram/fetchmedia.go` and is
exercised by `internal/telegram/fetchmedia_test.go`.

- `isDisallowedIP(ip net.IP) bool` (fetchmedia.go:63-71) is the deny-list
  predicate. It currently ORs together `ip.IsLoopback()`,
  `ip.IsLinkLocalUnicast()`, `ip.IsLinkLocalMulticast()`, `ip.IsPrivate()`,
  `ip.IsUnspecified()`, `ip.IsMulticast()`. Go's `net.IP.IsPrivate()`
  (stdlib `net/ip.go`) only matches RFC 1918 (`10.0.0.0/8`,
  `172.16.0.0/12`, `192.168.0.0/16`) and IPv6 ULA (`fc00::/7`) — it does not
  and cannot match RFC 6598 CGNAT (`100.64.0.0/10`), which is a separate
  IANA special-purpose allocation. No existing check in the OR-chain covers
  it, confirmed by reading the full method list on `net.IP` used here and by
  the absence of any `100.64` reference anywhere in the repo (`grep -r
  "100\.64" .` returns nothing).
- `resolveAllowedIP(ctx, host, lookup)` (fetchmedia.go:76-94) is what
  actually enforces `isDisallowedIP` against real traffic: if `host` parses
  as a literal IP it is checked directly; otherwise `lookup` (DNS) resolves
  it and each returned address is checked in turn, returning the first
  address that is not disallowed, or `ErrFetchDisallowedIP` if none qualify.
  This already runs **post-DNS-resolution** — the issue's "ensure the check
  applies post-DNS-resolution... not only on the literal host string"
  criterion is already satisfied by this function's structure, not something
  this proposal needs to add.
- `resolveAllowedIP` is invoked from inside the `http.Transport`'s
  `DialContext` (fetchmedia.go:132-143), which fires for the initial
  connection and again for every redirect hop the `http.Client` follows
  (`CheckRedirect` at fetchmedia.go:148-159 only enforces scheme + redirect
  count; the address re-check happens naturally because each redirect
  triggers a fresh `DialContext` call). This is documented in the comment at
  fetchmedia.go:137-141 and is exercised by
  `TestFetchGuardedURL_RedirectToDisallowedIP` in the test file. So a CGNAT
  address reached via redirect is covered by the same fix as a CGNAT address
  reached directly — no separate redirect-specific code path exists to
  update.
- Existing tests (`fetchmedia_test.go`): `TestIsDisallowedIP` is a
  table-driven test directly exercising `isDisallowedIP` with loopback,
  `::1`, `169.254.169.254`, RFC 1918 addresses, `0.0.0.0`, multicast, and two
  allowed public IPs (`93.184.216.1`, `8.8.8.8`). This is exactly the table
  the issue asks to extend with `100.64.0.1`.
  `TestFetchGuardedURL_DisallowedIP_Direct` and
  `TestFetchGuardedURL_DisallowedIP_ViaHostname` exercise the guard through
  `fetchGuardedURL` for a literal-IP URL and a DNS-resolved hostname
  respectively, using the injectable `lookupIPFunc`/`dialFunc` seams already
  built for exactly this kind of test (see the fakeResolver/dialToAddr
  helpers at the top of the test file).

## Proposed solution

1. Add a package-level CIDR constant for the CGNAT range in
   `fetchmedia.go`, next to the existing sentinel/const declarations:

   ```go
   // cgnatBlock is the RFC 6598 carrier-grade-NAT range (100.64.0.0/10).
   // Not covered by net.IP.IsPrivate(), which only recognizes RFC 1918 and
   // IPv6 ULA — CGNAT is a distinct IANA special-purpose allocation. In
   // cluster/cloud environments this range can route to internal
   // infrastructure, so it must be treated the same as the private-use
   // ranges for the SSRF guard's purposes.
   var cgnatBlock = &net.IPNet{IP: net.IPv4(100, 64, 0, 0), Mask: net.CIDRMask(10, 32)}
   ```

   A package-level `var` (not a function-local `net.ParseCIDR` call) is used
   so the mask is computed once at init and `isDisallowedIP` stays a cheap,
   allocation-free predicate on the hot path (it runs on every dial,
   including every redirect hop).

2. Extend `isDisallowedIP` with one more OR term:

   ```go
   func isDisallowedIP(ip net.IP) bool {
       return ip.IsLoopback() ||
           ip.IsLinkLocalUnicast() ||
           ip.IsLinkLocalMulticast() ||
           ip.IsPrivate() ||
           ip.IsUnspecified() ||
           ip.IsMulticast() ||
           cgnatBlock.Contains(ip)
   }
   ```

   `net.IPNet.Contains` handles the 4-byte-vs-16-byte `net.IP` representation
   correctly for an IPv4-mapped address, so no separate `To4()` normalization
   is needed here (consistent with how the existing `net.IP` methods on this
   same value already behave).

3. Update the doc comment above `isDisallowedIP` (fetchmedia.go:59-62) to
   mention CGNAT alongside the ranges it already lists, so the comment stays
   an accurate inventory of what the function blocks.

4. Extend `TestIsDisallowedIP`'s table in `fetchmedia_test.go` with:
   - `100.64.0.1` -> disallowed (inside the range, matches the issue's
     acceptance criterion literally).
   - `100.127.255.254` -> disallowed (top of the /10, boundary case).
   - `100.63.255.255` -> allowed (just below the range, guards against an
     off-by-one mask).
   - `100.128.0.0` -> allowed (just above the range, guards against an
     off-by-one mask).
   `169.254.169.254` is already present in the table (cloud metadata,
   covered by link-local) — the issue asks to "verify" it, which this
   existing case already does; no change needed there beyond confirming it
   stays in place.

5. Add one new test, `TestFetchGuardedURL_DisallowedIP_CGNATViaHostname`,
   mirroring `TestFetchGuardedURL_DisallowedIP_ViaHostname` exactly but with
   the fake `lookup` returning `net.ParseIP("100.64.0.1")` instead of
   `127.0.0.1`, and the same "dial must never be called" assertion. This
   directly proves the issue's acceptance criterion ("fetching a URL
   resolving to 100.64.0.1 is rejected with a test proving it") through the
   actual resolve-then-check path (`resolveAllowedIP` via `fetchGuardedURL`),
   not just the unit-level `isDisallowedIP` table.

6. No change to `TestFetchGuardedURL_Success` or any other passing test is
   required — they already use `93.184.216.1` as the allowed test IP, which
   is unaffected by the new CGNAT check, directly demonstrating "public
   media fetch unaffected."

No other files reference `isDisallowedIP` or duplicate its range list
(confirmed by `grep -rn "isDisallowedIP\|IsPrivate\|100\.64" --include=*.go
.` limited to `fetchmedia.go` and `fetchmedia_test.go`), so this is a
self-contained, two-function change plus tests.

## Alternatives

- **Use `net.ParseCIDR("100.64.0.0/10")` inside `isDisallowedIP` on every
  call instead of a package-level `var`.** Dropped: `isDisallowedIP` runs on
  every TCP dial the guarded client makes, including every redirect hop
  (fetchmedia.go:137), so re-parsing and re-erroring-checking a constant
  CIDR string on every call is wasted work and an unnecessary (if unlikely)
  panic/error-handling surface for a value that never changes. A
  package-level `net.IPNet` literal avoids both.
- **Adopt `net/netip` (`netip.Prefix`/`netip.Addr`) for the whole guard
  instead of extending the existing `net.IP`-based checks.** Dropped for
  this proposal: it would mean converting `isDisallowedIP`'s signature and
  every call site (`resolveAllowedIP`, both test files) from `net.IP` to
  `netip.Addr`, which is a larger refactor than what issue #427 asks for and
  touches code (the `DialContext` closure, `net.ParseIP` calls) that has
  nothing to do with the CGNAT gap. `net.IPNet.Contains(net.IP)` is
  sufficient and keeps the diff minimal and reviewable. Worth revisiting
  separately if the guard's IP-handling is ever generally modernized.
- **Block CGNAT by hostname/string pattern instead of by parsed IP.**
  Dropped: the whole point of `resolveAllowedIP` is to check the
  *resolved* address, not the literal host string, specifically to defend
  against DNS pointing an innocuous-looking hostname at an internal address
  (and against DNS-rebinding, per the dial-time re-check). Adding a
  string-based special case would bypass that design and reintroduce the
  literal-host-only gap the issue explicitly asks to avoid.

## Platform impact

- **Migrations:** none — this is a pure code change to a stdlib-only
  predicate function, no schema, config, or data changes.
- **Backward compatibility:** any `file_url` that currently resolves into
  `100.64.0.0/10` will start failing with `ErrFetchDisallowedIP` instead of
  succeeding. This is the intended security fix. `100.64.0.0/10` is not
  used for public internet hosting in practice (it is reserved for
  carrier/cluster-internal NAT), so no legitimate public media fetch is
  expected to resolve there; the "public media fetch unaffected" acceptance
  criterion is about the change not touching the public-address path at
  all, which the diff in `isDisallowedIP` (pure addition, no removal)
  guarantees.
- **Resource impact:** negligible — one extra `net.IPNet.Contains` check
  (a fixed-size byte comparison) per dial attempt. No new allocations on the
  steady-state path since `cgnatBlock` is computed once at package init.
- **Risks + mitigations:**
  - *Risk:* an off-by-one in the CIDR mask under- or over-blocks addresses
    near the range boundary. *Mitigation:* boundary-value tests at
    `100.63.255.255` / `100.64.0.0` / `100.127.255.254` / `100.128.0.0` (see
    tasks.md T1-T4) pin the exact edges.
  - *Risk:* someone later "simplifies" `isDisallowedIP` back down and drops
    the CGNAT term. *Mitigation:* the extended `TestIsDisallowedIP` table
    and the new `TestFetchGuardedURL_DisallowedIP_CGNATViaHostname` both
    fail immediately if that term is removed, and the updated doc comment
    calls CGNAT out explicitly as a deliberate, named entry rather than an
    incidental side effect of another check.
  - *Risk:* this proposal's scope creeps into the boot-guard work tracked in
    issue #426. *Mitigation:* explicitly out of scope (see requirements.md
    and issue body), no files under that guard's area are touched.
