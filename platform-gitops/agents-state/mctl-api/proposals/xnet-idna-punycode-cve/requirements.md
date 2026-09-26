# Confirm and patch golang.org/x/net IDNA punycode bypass (CVE-2026-39821, CVSS 9.6)

## Context
CVE-2026-39821 is a CVSS 9.6 vulnerability in `golang.org/x/net/idna`: a punycode-encoding
bypass that lets a crafted hostname be interpreted differently by the IDNA decoder than by
the caller's own hostname comparison logic, enabling domain-spoofing against consumers that
rely on IDNA normalization for hostname trust decisions. The fix ships in Go stdlib 1.26.6+
(which vendors a patched `x/net`) or in `golang.org/x/net` v0.55.0+ directly. It was surfaced
this cycle via a k8s 1.35.8 tracking issue, and the researcher explicitly flagged applicability
to mctl-api's own dependency graph as "not confirmed."

mctl-api makes numerous outbound, hostname-driven HTTPS calls that are security-relevant:
Dex JWKS fetch (`ops.mctl.me/api/dex/keys`, used for every Dex-issued JWT verification), the
GitHub API (PAT-based auth and org-membership checks), Vault (`secrets.mctl.ai`), ArgoCD,
Backstage, and Argo Workflows (`workflows.mctl.ai`). These calls run through `client-go 0.32`,
`go-oidc/v3`, `chi/v5`, and Go's own `net/http` — dependency chains that commonly vendor
`golang.org/x/net` transitively. Because this bug sits at IDNA/hostname-normalization layer,
it is a plausible vector to make one of these hostnames resolve or compare in a way that
defeats certificate/hostname validation, directly undermining the OIDC/JWKS trust chain that
`architecture.md`'s auth flow depends on. Given the severity (9.6) we open this proposal now
rather than waiting for a future cycle to re-confirm, but the first deliverable is confirming
exposure before committing to a specific patch path.

## User stories
- AS a platform security engineer I WANT confirmation of whether mctl-api's build actually
  vendors an affected `golang.org/x/net` version SO THAT I know whether CVE-2026-39821 is a
  real exposure or a false positive for this service.
- AS a security engineer I WANT the affected dependency patched (via Go stdlib 1.26.6+ or
  `x/net` v0.55.0+) if exposure is confirmed SO THAT hostname-driven outbound HTTPS calls
  (Dex JWKS, GitHub API, Vault, ArgoCD, Backstage, Argo Workflows) cannot be spoofed via a
  punycode-encoding bypass.
- AS an on-call engineer I WANT the confirmation and patch to be tracked in one place SO THAT
  this doesn't fragment into duplicate proposals across future research cycles, the way the
  go-upgrade/pgx/mcp-go/chi families have.

## Acceptance criteria (EARS)
- WHEN this proposal's investigation task runs `go list -m all` (or `go mod graph`) against
  mctl-api's `go.mod`/`go.sum` THE SYSTEM SHALL report the resolved version of
  `golang.org/x/net`, whether it is pulled directly or transitively (via `client-go`,
  `go-oidc/v3`, or `chi/v5`), and whether that version is inside the affected range for
  CVE-2026-39821.
- IF the resolved `golang.org/x/net` version is confirmed affected THEN THE SYSTEM SHALL be
  patched to a non-affected version, either by bumping the Go toolchain to 1.26.6+ (if that
  upgrade path is already in flight per the go-upgrade family) or by bumping
  `golang.org/x/net` directly to v0.55.0+ as a standalone dependency update.
- IF the resolved `golang.org/x/net` version is confirmed NOT affected (e.g., not vendored at
  all, or already >= v0.55.0) THEN THE SYSTEM SHALL close this proposal as "not applicable"
  with the confirmation evidence recorded, and no code change SHALL be made solely for this
  CVE.
- WHEN `govulncheck ./...` is run against the built binary after any patch applied under this
  proposal THE SYSTEM SHALL report zero findings for CVE-2026-39821.
- WHILE mctl-api performs OIDC JWT verification (Dex JWKS fetch) or any other outbound
  hostname-driven HTTPS call listed in Context, THE SYSTEM SHALL perform hostname/certificate
  validation using a patched IDNA implementation, with no observable change in which hostnames
  are accepted as valid for legitimate traffic.
- WHILE the patch (if any) is deployed, THE SYSTEM SHALL pass all existing unit and
  integration tests, including auth-flow tests (GitHub PAT, Dex JWT, OAuth JWT) covering
  every one of the three bearer types, without modification to test logic.
- IF the confirmation step finds `golang.org/x/net` is pulled in at a version pinned by a
  direct dependency (e.g. `client-go` or `go-oidc/v3`) that itself has no compatible release
  yet THEN THE SYSTEM SHALL document the blocking dependency and coordinate the fix with that
  dependency's own upgrade track (e.g. `client-go-version-drift`) rather than force a
  potentially-breaking `go mod edit -replace`.

## Out of scope
- General `client-go` version drift (0.32 → 0.37.1) — tracked separately in the existing
  `client-go-version-drift` proposal; this proposal only touches `x/net` exposure via that
  dependency, not the broader version bump.
- The related `golang.org/x/net/html` XSS CVEs (CVE-2026-42502, CVE-2026-42506) surfaced this
  cycle — `x/net/html` is not on mctl-api's tracked-dependency list per `architecture.md` and
  is not confirmed to be in use; a separate proposal should be opened if confirmed.
- The broader Go 1.24 EOL / toolchain upgrade — tracked by the `go-upgrade-*` family (see
  `proposal-backlog-consolidation`). If the toolchain bump lands first and already carries
  Go 1.26.6+, this proposal's patch step becomes a no-op confirmation only.
- Any change to certificate pinning or TLS configuration beyond what the IDNA fix itself
  requires.
