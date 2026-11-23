# PA outbound egress and redirect policy (Phase 1, threat model T9)

## Context

Issue #1316 is the Phase 1 egress item of the Personal Assistant epic (#1312). ADR 0011
(`docs/adr/0011-personal-assistant.md`, "Egress") and threat model T9
(`docs/agent-runtime/personal-assistant-threat-model.md`, "T9 Egress, SSRF and redirects")
require one policy for every outbound request the PA makes to a catalog server: OAuth
authorization-server metadata discovery, DCR, the token and revocation endpoints, and the
MCP transport. The rules: HTTPS only; a per-server host allowlist; addresses resolved and
checked at connect time and the checked address dialled (no DNS rebinding); private,
loopback, link-local, CGNAT, `0.0.0.0/8`, multicast, cluster pod/service, IPv6 unique-local
and link-local ranges denied, including their IPv4-mapped and NAT64 forms; proxy environment
variables ignored; no redirects except re-checked discovery hops (at most two); per-request
body size and time caps. CIMD documents are fetched by the authorization server from MCTL
and are not MCTL egress (T9 "Scope").

The repository already has `internal/netsafe`, a public-address-only client used for CIMD
fetches. It covers address filtering, dial pinning, proxy disabling and redirect refusal,
but not scheme enforcement, host allowlists, discovery-hop redirects, configurable cluster
ranges, or body caps enforced on the transport. This proposal adds a PA egress layer on top
of it and the S1-E1..E7 tests that gate Phase 1. **The issue is on HOLD**: this proposal is
a design only; implementation needs the owner's Phase 1 GO.

## User stories

- AS the PA security owner I WANT every PA outbound request to pass one egress policy SO THAT a catalog entry, a metadata document or a redirect cannot make MCTL reach an internal address or a foreign host (SSRF).
- AS a PA connector author I WANT a per-server, per-request-type HTTP client SO THAT I cannot accidentally use `http.DefaultClient` or skip a cap.
- AS the Phase 1 gate reviewer I WANT S1-E1..E7 mapped to named tests with recorded mutation runs SO THAT "S1 green" is checkable evidence.

## Acceptance criteria (EARS)

- IF a PA outbound request URL has a scheme other than `https` THEN THE SYSTEM SHALL refuse it before any DNS lookup or dial and return `ErrScheme` (S1-E1).
- IF a PA outbound request URL host is not in the allowlist of the catalog server the request is made for THEN THE SYSTEM SHALL refuse it before any DNS lookup or dial and return `ErrHostNotAllowed` (S1-E2).
- IF a URL carries userinfo, a non-443 port, or an IP-literal host THEN THE SYSTEM SHALL refuse it.
- WHEN a host is resolved THE SYSTEM SHALL check every candidate address with `netsafe.PublicAddr` plus the configured cluster deny prefixes and SHALL dial only an IP literal that passed the check, so that a second resolution cannot change the dialled address (S1-E3).
- IF the resolved address is in a private, loopback, link-local, CGNAT, `0.0.0.0/8`, multicast, cluster pod/service, IPv6 unique-local (`fc00::/7`) or link-local range, or is an IPv4-mapped or NAT64 form of a denied IPv4 address, THEN THE SYSTEM SHALL refuse the dial with `netsafe.ErrNonPublic` (S1-E3).
- IF a resolver returns a public address on the check and a denied address on a later lookup (rebind) THEN THE SYSTEM SHALL still never connect to the denied address (S1-E3).
- WHEN a response to a token, revocation, DCR or MCP transport request has a 3xx status THE SYSTEM SHALL fail the request with `netsafe.ErrRedirect` and SHALL NOT follow it.
- WHEN a metadata-discovery response is a 3xx THE SYSTEM SHALL follow it only if the `Location` target passes the scheme, allowlist and address checks again, and SHALL fail on the third hop (at most two redirect hops) (S1-E4).
- IF a discovery redirect targets a private address or a host outside the server's allowlist THEN THE SYSTEM SHALL refuse it (S1-E4).
- IF a response body exceeds the cap for its request type THEN THE SYSTEM SHALL stop reading at cap+1 bytes and fail the call with `ErrTooLarge`; an oversized body is never truncated into a success (S1-E5).
- IF a request exceeds the time cap for its request type THEN THE SYSTEM SHALL cancel it and fail the call (S1-E6).
- WHILE `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` or `NO_PROXY` are set THE SYSTEM SHALL ignore them for PA egress and dial the destination directly (S1-E7).
- WHILE the PA package makes any outbound HTTP request THE SYSTEM SHALL use a client obtained from the PA egress layer; a static check SHALL fail CI if the PA package references `http.DefaultClient`, `http.Get`, `http.Post` or constructs `http.Client`/`http.Transport` outside the egress package.
- IF the cluster deny-prefix configuration is malformed THEN THE SYSTEM SHALL fail startup of the PA (fail closed), never run with an empty list silently.
- WHEN any S1-E test ID lacks a test in the S1 manifest THE SYSTEM SHALL fail CI, and each S1-E ID SHALL have a recorded mutation run.

## Out of scope

- The PA bot loop, OAuth linking flow, DCR/CIMD client registration logic, token storage and MCP tool dispatch (sibling Phase 1 issues of #1312). This proposal provides the client they must use.
- Inbound CIMD document serving, and the existing CIMD fetcher in `internal/oauth/cimd` (it keeps using `netsafe.Client` unchanged).
- Kubernetes NetworkPolicy changes; tenant `labs` keeps `allowClusterEgress: true` (defence in depth at the cluster layer is a possible follow-up, not part of T9).
- Custom MCP servers by URL (#1048).
- Any deployment, feature flag flip or `agents:intake` (issue is on HOLD).

## Open questions

- Cluster pod and service CIDRs are not visible in the clone or in the gitops tenant/service values read. The design makes them configuration (`PA_EGRESS_DENY_CIDRS`) and denies all RFC 1918 and CGNAT ranges anyway; the owner must supply the actual values before preview.
- `tg` is reached through its public host `tg.mctl.ai` (T9). That hairpins through the public ingress; if the ingress IP resolves to a non-public address inside the cluster DNS (split horizon), the policy will refuse it. Not observed; needs a preview check.
- Exact per-request-type caps are not specified by T9. Proposed defaults: discovery 64 KiB / 5 s, DCR 64 KiB / 10 s, token and revocation 16 KiB / 10 s, MCP transport 1 MiB per response / 30 s (the 64 KiB tool-output limit of ADR 0011 is applied later, above the transport). Owner to confirm.
- Whether the S1 test manifest file is created by this issue or by a sibling issue of #1312. This proposal creates it if absent, with only the S1-E entries.
- How `mark3labs/mcp-go` v1.4.0 accepts a custom `*http.Client` for the streamable HTTP client transport could not be verified (module cache unavailable in this run); the design wraps the transport at the `http.RoundTripper` level so it works with any option that accepts a client.
