# Design: go-1-26-11-toolchain-xnet

## Current state
Go 1.24 per context/architecture.md; earlier Go bump proposals target older patch levels.

## Proposed solution
Bump `go` directive and `toolchain` to 1.26.11, update the builder image digest, run `go get golang.org/x/net@latest` and `go mod tidy`, rebuild, and run govulncheck. Deploy via mctl-gitops/ArgoCD to admins first, then labs.

## Alternatives
- Go 1.27.4: newer, but more behavioural change; revisit later.
- Stay on 1.24 with backports: none exist upstream.

## Platform impact
- Migrations: none.
- Backward compatibility: Go 1.26 changes minor stdlib behaviour; client-go 0.32 and mcp-go must compile (check).
- Resource impact: `labs` is near its memory limit — compare RSS before/after in staging; abort if higher.
- Risks: HTTP/2 behaviour changes; mitigated by staging soak and rollback to previous image.
