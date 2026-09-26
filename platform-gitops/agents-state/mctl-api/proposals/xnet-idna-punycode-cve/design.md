# Design: xnet-idna-punycode-cve

## Current state
Per `context/architecture.md`, mctl-api is built with Go 1.24 and depends on `client-go 0.32`,
`go-oidc/v3`, `chi/v5 5.2.1`, and stdlib `net/http`. It performs OIDC JWT verification against
Dex's JWKS endpoint (`ops.mctl.me/api/dex/keys`), and makes outbound authenticated HTTPS calls
to GitHub, Vault (`secrets.mctl.ai`), ArgoCD, Backstage, and Argo Workflows
(`workflows.mctl.ai`). None of these dependencies declare `golang.org/x/net` as a *direct*
dependency in `architecture.md`'s tracked list, but `client-go`, `go-oidc/v3`, and `chi`'s
transitive dependency trees have historically vendored `x/net` for HTTP/2 and IDNA support.
Today's exposure is unconfirmed — the researcher flagged it "raw" this cycle.

## Proposed solution
Two-phase approach, gated on confirmation:

**Phase 1 — Confirm.** Run `go list -m all` (or `go mod graph | grep golang.org/x/net`)
against mctl-api's actual `go.mod`/`go.sum` to determine:
1. Whether `golang.org/x/net` is present in the resolved module graph at all.
2. If present, which version, and via which direct dependency (`client-go`, `go-oidc/v3`,
   `chi/v5`, or something else).
3. Whether that version falls inside CVE-2026-39821's affected range (fixed in v0.55.0+).

**Phase 2 — Patch (only if Phase 1 confirms exposure).** Two possible remediation paths,
chosen based on what Phase 1 finds:
- **Toolchain path:** if the Go stdlib itself vendors the vulnerable `x/net` snapshot, bump
  the Go toolchain to 1.26.6+ (this may already be covered by the in-flight go-upgrade
  consolidation — see `proposal-backlog-consolidation`). This is the lower-effort path if a
  toolchain bump is already planned.
- **Direct dependency bump:** if `golang.org/x/net` is a resolvable transitive dependency
  independent of the Go version, add or bump a direct `require golang.org/x/net v0.55.0+`
  entry via `go get golang.org/x/net@v0.55.0` (or later), forcing the resolved version up
  via Go's minimal version selection, without needing to wait on the toolchain bump.

Either path is a dependency-version change only — no application code should need to change,
since IDNA/hostname handling happens inside the library, not in mctl-api's own code.

## Alternatives
- **Do nothing until a future cycle re-confirms exposure.** Rejected: CVSS 9.6 is the highest
  severity score surfaced this cycle; waiting risks an exploit window against the OIDC/JWKS
  trust chain that gates every authenticated request.
- **Vendor a patched fork of `x/net/idna` directly.** Rejected: adds a maintenance burden and
  diverges from upstream; a version bump is strictly simpler and lower-risk once confirmed.
- **Roll this into the go-upgrade toolchain bump proposal only, with no standalone tracking.**
  Rejected: the toolchain bump (tracked under `proposal-backlog-consolidation` /
  `go-1.24-eol-unpatched-cve`) targets Go >=1.26.4, and 1.26.6 is required specifically for
  this CVE fix — the two efforts should stay cross-referenced but not silently merged, in
  case the toolchain proposal lands on a version below 1.26.6 or the direct-dependency path
  turns out to be faster.

## Platform impact
- **Migrations:** none — this is a dependency version bump, not a data or API migration.
- **Backward compatibility:** `golang.org/x/net` v0.55.0+ and Go 1.26.6+ are both
  backward-compatible minor/patch releases with respect to the APIs mctl-api uses (HTTP
  transport, IDNA). No expected breaking changes; verified by the existing test suite.
- **Resource impact (`labs`):** none — mctl-api runs only in tenant `admins` per
  `context/architecture.md` and `context/current-version.md`; `labs` is not affected by this
  change.
- **Risks and mitigations:**
  - Risk: Phase 1 finds no exposure, and the CVSS-9.6 framing turns out to be a
    false-alarm/non-applicable finding. Mitigation: the acceptance criteria explicitly allow
    closing as "not applicable" with recorded evidence rather than forcing an unnecessary
    dependency bump.
  - Risk: the direct-dependency bump conflicts with a version pinned by `client-go` or
    `go-oidc/v3`. Mitigation: acceptance criteria require documenting the blocking dependency
    and coordinating with its own upgrade track rather than forcing an unsafe replace.
  - Risk: duplicate effort with the go-upgrade toolchain proposals. Mitigation: explicit
    cross-reference to `proposal-backlog-consolidation` in Out of scope and Alternatives.
