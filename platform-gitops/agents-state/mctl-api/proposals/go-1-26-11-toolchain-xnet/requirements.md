# Move build toolchain to Go 1.26.11+ and bump golang.org/x/net

## Context
mctl-api is built on Go 1.24, which is out of upstream support. Advisories GO-2026-6603/6605/6607/6608/6610-6613/6617/6809/6859 and CVE-2026-97054 affect net/http, crypto/tls, net/textproto and crypto/x509, and are fixed only in Go 1.26.9+ (1.26.11 current). The API at api.mctl.ai is publicly exposed.

## User stories
- AS a platform operator I WANT mctl-api built on a supported, patched Go release SO THAT known stdlib DoS and desync flaws are not reachable.

## Acceptance criteria (EARS)
- WHEN the image is built THE SYSTEM SHALL use Go >= 1.26.11 (go.mod `go` and `toolchain`, Dockerfile digest).
- WHEN dependencies are resolved THE SYSTEM SHALL use golang.org/x/net >= 0.63.0.
- WHEN govulncheck runs against the built module THE SYSTEM SHALL report no reachable stdlib vulnerabilities.
- WHILE running in tenant `labs` or `admins` THE SYSTEM SHALL keep memory within current limits.
- IF any of the 24 MCP tools or auth flows regress in staging THEN THE SYSTEM SHALL block promotion.

## Out of scope
- Moving to Go 1.27; framework or router changes (ADR/architecture constraints).
