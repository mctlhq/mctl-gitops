# Design: go-toolchain-1263-patch

## Current state

`go.mod` declares `go 1.24` and `toolchain go1.24.x`. The binary is compiled by the CI
pipeline using the pinned toolchain image. Go 1.24 is end-of-life; the last 1.24.x patch
was go1.24.13 on 2026-02-04. Per Go release policy only the two most recent major releases
receive security fixes; 1.24 is outside that window. The existing `go-upgrade-1-26`
proposal targeted 1.26.2 but has not yet landed as of the 2026-05-16 inbox cycle.

See `context/architecture.md` for the full tech stack.

## Proposed solution

Update `go.mod` to:

```
go 1.26.3
toolchain go1.26.3
```

Pin the CI base image to `golang:1.26.3-alpine` (or equivalent). No application code
changes are expected: Go 1.26.x contains no breaking language changes relative to 1.24,
and the standard library APIs used by mctl-agent (net/http, context, crypto/tls, slog,
database/sql) are backward-compatible.

The Green Tea GC (default in 1.26) was already accounted for in the earlier `go-upgrade-1-26`
proposal; this patch continues that benefit.

### Why patch-to-1.26.3 rather than waiting for a coordinated upgrade PR

1.26.3 patches CVE-2026-33814 (HTTP/2 infinite loop), which is exploitable against the
mctl-agent webhook server by any caller that can control SETTINGS frames. The risk of
leaving it open while waiting for a full dependency sweep is unacceptable. This proposal
is intentionally narrow: toolchain only, merge fast.

## Alternatives

| Option | Reason rejected |
|---|---|
| Stay on Go 1.26.2 | Does not fix CVE-2026-33814, CVE-2026-39826/23, CVE-2026-42499/42501 |
| Upgrade to Go 1.25.10 | 1.25.x will reach EOL in ~6 months; Go 1.26.x is the current LTS track |
| Bundle with full dep sweep | Delays security patch; violates "security fix ships fast" principle |

## Platform impact

### Migrations
None. `go.mod` directive and CI image tag are the only changes.

### Backward compatibility
Go patch releases (x.y.Z → x.y.Z+1) carry a compatibility guarantee: no breaking changes.
All existing code compiles unmodified.

### Resource impact
- Green Tea GC (already in 1.26.0) reduces GC overhead 10–40% with no memory increase.
- No new goroutines, no new heap allocations from toolchain change.
- **`labs` tenant**: no impact — toolchain bump does not change the service's runtime
  memory profile.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Subtle stdlib behavior change in net/http | Run full integration test suite before merge |
| CI image not yet updated to 1.26.3 | Pin `FROM golang:1.26.3` in Dockerfile; verify digest |
| go1.26.3 not yet in the base image registry | Check registry; fall back to `golang:1.26` with toolchain directive |
