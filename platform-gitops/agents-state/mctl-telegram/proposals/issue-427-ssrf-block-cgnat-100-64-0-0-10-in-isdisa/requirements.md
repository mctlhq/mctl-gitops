# Block CGNAT range (100.64.0.0/10) in the media-fetch SSRF guard

## Context
`isDisallowedIP` in `internal/telegram/fetchmedia.go` is the deny-list check
backing `FetchGuardedURL`, the only outbound HTTP path in this server driven
by caller-supplied input (Telegram `file_url` media fetches). It currently
blocks loopback, link-local unicast/multicast, RFC 1918 / ULA private-use
ranges, the unspecified address, and multicast, via Go's `net.IP` helper
methods (`IsLoopback`, `IsLinkLocalUnicast`, `IsLinkLocalMulticast`,
`IsPrivate`, `IsUnspecified`, `IsMulticast`). None of those helpers cover the
CGNAT range `100.64.0.0/10` (RFC 6598): Go's `net.IP.IsPrivate()` only
recognizes RFC 1918 (`10/8`, `172.16/12`, `192.168/16`) and IPv6 ULA
(`fc00::/7`) — RFC 6598 is a distinct allocation and is not private-use in
Go's sense. In cluster/cloud environments this range is commonly used to
route to internal load balancers, service meshes, or node-to-node traffic,
so a crafted `file_url` that resolves to a `100.64.0.0/10` address can reach
internal infrastructure the SSRF guard is meant to keep off-limits. This
matters because it is a direct SSRF gap in the one guarded outbound-fetch
path this server exposes to untrusted input.

## User stories
- AS a server operator I WANT the media-fetch SSRF guard to reject CGNAT
  addresses SO THAT a crafted Telegram media URL cannot use the shared
  carrier-grade-NAT range to reach internal cluster/cloud infrastructure.
- AS a maintainer I WANT table-driven tests covering CGNAT and other
  sensitive ranges SO THAT a future refactor of `isDisallowedIP` cannot
  silently regress this protection.

## Acceptance criteria (EARS)
- WHEN `isDisallowedIP` is called with an IPv4 address in `100.64.0.0/10`
  (e.g. `100.64.0.1`, `100.127.255.254`) THE SYSTEM SHALL report it as
  disallowed.
- WHEN `isDisallowedIP` is called with an IPv4 address just outside
  `100.64.0.0/10` (e.g. `100.63.255.255`, `100.128.0.0`) THE SYSTEM SHALL
  report it as allowed (i.e. not treated as CGNAT), so the new check does
  not over-block adjacent public space.
- WHEN a `file_url` host (literal IP or DNS name) resolves to an address in
  `100.64.0.0/10` THE SYSTEM SHALL reject the fetch with
  `ErrFetchDisallowedIP`, proven by a test that resolves a hostname to
  `100.64.0.1` via the injectable `lookupIPFunc` and asserts the fetch never
  dials.
- WHEN a `file_url` fetch redirects to a URL whose host resolves to an
  address in `100.64.0.0/10` THE SYSTEM SHALL reject that redirect hop the
  same way it already rejects redirects to `127.0.0.1` (existing
  `TestFetchGuardedURL_RedirectToDisallowedIP` pattern), because the
  dial-time check in `fetchGuardedURL`'s `DialContext` re-validates every
  hop, not just the initial URL.
- WHEN a `file_url` resolves to a normal public IP (e.g. an
  `httptest.NewTLSServer`-style allowed address) THE SYSTEM SHALL continue
  to permit the fetch — the CGNAT check must not affect public media fetch.
- WHILE `isDisallowedIP` evaluates any candidate address THE SYSTEM SHALL
  continue to also reject loopback, link-local unicast (including
  `169.254.169.254`), link-local multicast, RFC 1918 / ULA private-use,
  unspecified, and multicast addresses exactly as it does today — this
  proposal adds a range, it does not change or narrow the existing ones.
- IF a hostname resolves to multiple addresses and at least one is public
  (not disallowed) THEN THE SYSTEM SHALL select that public address, per the
  existing `resolveAllowedIP` behavior of returning the first non-disallowed
  candidate — unchanged by this proposal.

## Out of scope
- The local-dev/`ENCRYPTION_KEY` boot guard (tracked separately in
  mctlhq/mctl-telegram#426).
- Any change to IPv6 handling beyond confirming existing coverage: `::1`
  (loopback), `fe80::/10` (link-local unicast), and `fd00::/8` /
  `fc00::/7` (ULA, covered by `IsPrivate`) are already covered by the
  existing `net.IP` method checks and require no code change — this
  proposal only verifies that via tests, per the issue's request to "verify
  metadata/link-local ranges ... are all covered."
- Any change to `resolveAllowedIP`'s selection strategy (first
  non-disallowed IP) or to redirect/timeout/oversize handling elsewhere in
  `fetchmedia.go`.
- Configurability of the deny-list (e.g. via env var or config file) — the
  list stays a compiled-in constant as it is today.

## Open questions
- None. The issue is fully specified: add `100.64.0.0/10` to the deny list,
  add table-driven tests including `100.64.0.1`, `169.254.169.254`, and an
  allowed public IP, and confirm the check runs post-DNS-resolution. The
  post-DNS-resolution requirement is already met by the existing
  `resolveAllowedIP` / `DialContext` design (see design.md "Current state");
  this proposal adds the missing range and the tests the issue asks for
  without restructuring that flow.
