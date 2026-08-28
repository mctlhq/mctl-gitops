# Design: issue-99-path-allowlist-for-gitops-writes-remote

## Current state

**Gitops write path (no path check).**
`internal/pipeline/pipeline.go:handleHighConfidenceFix` (lines 472-599+):
1. Calls `s.Fix(ctx, t, diag)` which returns `*skill.FixResult{Applied,
   NewContent, FilePath, Summary, NextSkills}` (`internal/skill/skill.go`).
2. Line 509-512: `filePath := fixResult.FilePath; if filePath == "" {
   filePath = fixer.DetectFilePath(t.Tenant, t.Service) }` — the skill's
   own `FilePath` wins whenever it is non-empty, with no validation.
3. Line 515: `p.github.GetFileContent(ctx, filePath, "main")` reads that
   path from `mctl-gitops` directly.
4. Lines 528-554: various `fixer.Generate*` functions patch `content`
   based on `diag.FixType`; the `default` branch even accepts
   `fixResult.NewContent` verbatim from the skill with no patching at all.
5. Lines 570-577: `p.github.CreatePR(ctx, fixer.PRRequest{FilePath:
   filePath, NewContent: newContent, ...})`.

`internal/fixer/github.go:CreatePR` (lines 67-175) takes `req.FilePath`
and calls `f.client.Repositories.GetContents` (line 113) and
`f.client.Repositories.UpdateFile` (line 133) at that literal path. There is
no prefix check, no `..`/absolute-path rejection, and no symlink check
anywhere on this path. `GetFileContent` (lines 196-207) has the same gap.

Three producers can set `FixResult.FilePath` to attacker-influenced values:
- `internal/skill/remote/remote.go:203-231` (`Skill.Fix`) — `FilePath` comes
  straight from the remote HTTP endpoint's JSON response
  (`resp.FilePath`, line 227).
- `internal/skill/yaml/` — YAML-defined skills (hot-reloaded from
  `skills/custom/`); their fix templates could also set `file_path`, and
  those YAML files are not restricted to being authored only by trusted
  operators once remote registration exists as a parallel, unreviewed path.
- Built-in skills only ever set `FilePath` via `detectFilePath(t.Tenant,
  t.Service)` (`internal/skill/builtin/oomkilled.go:87-92` etc.) or a fixed
  literal (`workflow_fixer.go:110,118`), so today's actual exposure is
  entirely the remote/YAML path — but the pipeline treats all three
  identically.

**Remote skill registration (no URL/capability validation).**
`internal/skill/remote/remote.go:Manager.Register` (lines 279-299):
```go
func (m *Manager) Register(reg Registration) error {
    if reg.Name == "" { return fmt.Errorf("skill name is required") }
    if reg.Endpoint == "" { return fmt.Errorf("skill endpoint is required") }
    if reg.Version == "" { reg.Version = "1.0.0" }
    s := New(reg)
    ...
}
```
No scheme check, no host check, no capability check. `Skill.post`
(lines 233-262) then does a plain `http.Client{Timeout: 10*time.Second}.Do`
to `s.reg.Endpoint + path` for `/match`, `/diagnose`, `/fix` — any endpoint,
including `http://169.254.169.254/latest/meta-data/` (cloud metadata) or a
10.x/192.168.x in-cluster service, is reachable. `RequiredCapabilities()`
(lines 137-143) blindly casts every string in `reg.Capabilities` to
`skill.CapabilityID` with no membership check against the enum defined in
`internal/skill/skill.go:23-37` (`CapReadLogs` ... `CapExecWorkflow`).
The registration handler (`internal/api/router.go:366-383`,
`remoteSkillRegisterHandler`) just JSON-decodes the body and calls
`mgr.Register(reg)` — it adds no validation of its own.

**Capability sandbox exists but is dead code.**
`internal/capability/capability.go` defines `Provider` (raw platform
integrations) and `Context` (per-skill sandbox that checks
`RequiredCapabilities()` before allowing `GetServiceStatus`,
`GetFileContent`, `CreatePR`, `SendNotification`, etc. — lines 126-195).
`cmd/agent/main.go:104` builds `capProvider := capability.NewProvider(...)`
and passes it into `pipeline.NewPipeline` (`cmd/agent/main.go:107`), which
stores it as `Pipeline.provider` (`internal/pipeline/pipeline.go:46,67,80`).
Grepping the pipeline package for `p.provider`, `NewContext`, or
`capability.Context` outside of `capability_test.go` returns nothing:
`Pipeline` never constructs a `capability.Context` for a skill and never
calls through `p.provider`. All gitops reads/writes and notifications in
`handleHighConfidenceFix` go straight through `p.github` / `p.telegram`,
so `RequiredCapabilities()` — which `remote.Skill` already reports
faithfully (lines 137-143) — is never consulted at runtime. A remote skill
that never declared `modify_gitops` still gets its fix written to
`mctl-gitops` today.

## Proposed solution

### 1. Path allowlist enforcement — new `internal/gitopspath` package

Add `internal/gitopspath/gitopspath.go`:
```go
package gitopspath

// Allowlist holds the set of path prefixes gitops writes may target.
type Allowlist struct{ prefixes []string }

func NewAllowlist(prefixes []string) Allowlist
func DefaultAllowlist() Allowlist // see config default below

// Validate cleans path and checks it resolves under one of the allowed
// prefixes with no traversal. Returns a descriptive error otherwise.
func (a Allowlist) Validate(path string) error
```
`Validate` logic:
- Reject empty string.
- Reject `filepath.IsAbs(path)` (and a leading `/` even on path.Clean'd
  GitHub-style forward-slash paths).
- Use `path.Clean` (posix semantics — GitHub paths are always `/`-separated,
  regardless of build OS) and reject if the cleaned result starts with `..`
  or is `.` or differs from the input in a way that indicates a `..`
  segment was present (`strings.Contains(path, "..")` pre-check, then
  re-verify post-clean containment — belt and suspenders).
- Check the cleaned path has one of the allowlisted prefixes as a proper
  path-segment prefix (`cleaned == p || strings.HasPrefix(cleaned, p +
  "/")`) for every configured prefix `p`; reject if none match.

This package has no dependency on `fixer`/`github`, so it is trivially unit
testable with plain strings (traversal strings, absolute paths, off-prefix
paths, legit paths) without any GitHub mock.

**Config**: extend `internal/config/config.go` with
`GitOpsPathAllowlist []string`, parsed from `GITOPS_PATH_ALLOWLIST`
(comma-separated), defaulting when unset to the three prefixes the codebase
already treats as legitimate write targets:
```
platform-gitops/services/
platform-gitops/apps/templates/
platform-gitops/argo-workflows/workflow-templates/
```
This keeps `fixer.DetectFilePath`'s `PlatformServices` branch and
`workflow_fixer.go`'s two literal paths working unchanged, while still
rejecting `bootstrap/...` and `../.github/...` per the issue's acceptance
criteria — neither matches any default prefix.

**Enforcement points (defense in depth, per the issue's two evidence
sites):**
- `internal/fixer/github.go`: `GitHubFixer` gains an `allowlist
  gitopspath.Allowlist` field (constructor param). `GetFileContent` and
  `CreatePR` each call `f.allowlist.Validate(path)` / `.Validate(req.FilePath)`
  first and return a wrapped error on rejection — this is the outermost
  boundary right before the GitHub API call, so it catches every caller
  (pipeline, capability.Context, any future caller) uniformly.
- `internal/pipeline/pipeline.go`: `handleHighConfidenceFix` validates
  `filePath` immediately after it is resolved (line ~512), before the
  `GetFileContent` call, so a rejection is logged and surfaced through the
  *existing* "patch generation failed" path (same `t.Status =
  ticket.StatusFixProposed`, Telegram message, `EventTicketFixFailed`
  emission already used for other fix-generation errors at lines 556-565) —
  no new failure-handling shape is introduced, and the ticket is not left
  silently stuck.
- Symlink check: after `GetFileContent`'s underlying
  `Repositories.GetContents` call, `GitHubFixer` inspects the returned
  `RepositoryContent.GetType()`; if it is `"symlink"`, `GetFileContent`
  returns an error instead of attempting to decode content. `CreatePR`
  performs the same check on the `fileContent` it fetches at line 113
  before calling `UpdateFile`.

### 2. Wire `internal/capability` into the pipeline

Replace the direct `p.github.GetFileContent` / `p.github.CreatePR` /
`p.telegram.*` calls inside `handleHighConfidenceFix` (and `rollbackImage`,
which also calls `p.github.LookupPreviousImageTag` — extend
`capability.Context` with a thin passthrough for that read, gated behind
the existing `CapModifyGitOps`) with calls through a
`capability.Context` built once per skill invocation:
```go
capCtx := capability.NewContext(p.provider, s, t, ev)
content, err := capCtx.GetFileContent(ctx, filePath, "main")   // requires CapModifyGitOps
...
prURL, prNumber, err := capCtx.CreatePR(ctx, fixer.PRRequest{...}) // requires CapCreatePR
```
`capability.Provider.CreatePR` / `GetFileContent` (lines 82-90) already
delegate to `p.github`, which now carries the allowlist — so the capability
layer gets path enforcement for free by construction, and additionally
enforces the pre-existing `RequiredCapabilities()` check
(`internal/capability/capability.go:126-131`) that today is computed by
`remote.Skill.RequiredCapabilities()` but never consulted. Built-in skills
must be audited (`internal/skill/builtin/*.go`) to confirm each one that
calls `Fix` and expects a PR declares `CapModifyGitOps` + `CapCreatePR` in
its `RequiredCapabilities()` — those that don't yet declare it get updated
as part of this change (currently no builtin skill implements
`RequiredCapabilities()` beyond the interface's zero value, so this is a
new but mechanical declaration for each of the 9 builtin skills).
`Pipeline.provider` stops being a write-only field.

### 3. Remote skill registration + connection-time validation

New file `internal/skill/remote/validate.go`:
```go
package remote

// ValidateRegistration checks scheme, host, and capabilities of reg.
// Performs a best-effort DNS resolution of the host to catch registration
// of a hostname that already resolves to a denied range.
func ValidateRegistration(reg Registration) error
```
- Parse `reg.Endpoint` with `net/url`; require `u.Scheme == "https"` and a
  non-empty `u.Host`.
- Split host/port, resolve via `net.DefaultResolver.LookupIPAddr` (best
  effort, registration-time only — see open questions on rebinding), and
  reject if the literal host (when it's already an IP) or every resolved IP
  is contained in a denied range: use `net.IP.IsLoopback()`,
  `IsPrivate()` (stdlib since Go 1.17, covers RFC 1918 + `fc00::/7`),
  `IsLinkLocalUnicast()`, plus an explicit CGNAT check
  (`100.64.0.0/10`, not covered by any stdlib helper) via
  `net.ParseCIDR("100.64.0.0/10")` + `Contains`.
- Validate `reg.Capabilities`: every string must equal one of the known
  `skill.CapabilityID` constants (a small `skill.AllCapabilityIDs()` helper
  is added to `internal/skill/skill.go` next to the const block so this
  list has one source of truth); reject unknown values by name so the
  operator sees exactly which capability string was rejected.
- `Manager.Register` (`internal/skill/remote/remote.go:280`) calls
  `ValidateRegistration(reg)` first and returns its error unchanged — the
  existing `remoteSkillRegisterHandler` (`internal/api/router.go:373-376`)
  already forwards `mgr.Register`'s error as a 400, so no API-layer change
  is needed.

**Connection-time (anti-rebinding) enforcement**: `remote.New` builds
`Skill.client` with a custom `http.Transport{DialContext: guardedDialer}`
where `guardedDialer` wraps the default dialer, resolves the address being
dialed, and refuses to connect (returns an error before any bytes go out)
if the resolved IP is in a denied range — this covers both the initial
`/match`/`/diagnose`/`/fix` calls and any redirect the endpoint issues,
independent of what `ValidateRegistration` saw at registration time. The
denied-range check function is shared between `validate.go` and the dialer
(one `isDeniedIP(net.IP) bool` helper) so the policy cannot drift between
the two call sites.

## Alternatives

1. **Validate paths only in `pipeline.go`, not in `fixer/github.go`.**
   Simpler (one call site), but the issue explicitly lists
   `internal/fixer/github.go:113-133` as a separate finding, and any future
   caller of `GitHubFixer.CreatePR` (there is already a second call site
   pattern via `capability.Provider.CreatePR`) would silently regain the
   vulnerability. Rejected in favor of defense-in-depth at the layer that
   actually calls GitHub.

2. **Delete `internal/capability` instead of wiring it in.** The issue
   explicitly prefers wiring it in, and it is the natural place to enforce
   "a skill can only do what it declared" — the exact shape of the remote
   skill vulnerability (declares nothing, gets everything). Deleting it
   would remove a working, tested sandbox (`capability_test.go` already
   covers the capability-check behavior) and would require inventing an
   equivalent mechanism elsewhere anyway. Rejected.

3. **Single hardcoded `platform-gitops/services/` prefix, no config, and
   move the three other legitimate targets into the same directory
   structure.** Would satisfy the issue's literal example most simply, but
   requires migrating `PlatformServices` values files and the two
   `workflow_fixer.go` targets into `platform-gitops/services/...` in
   `mctl-gitops`, which is a cross-repo change outside this proposal's
   blast radius and would break unrelated tooling that expects those paths
   today. Rejected in favor of a configurable, multi-prefix allowlist
   defaulting to the paths already in use.

4. **SSRF guard via a maintained third-party library (e.g. an "safe HTTP
   client" package) instead of a hand-rolled dialer.** No such dependency
   is currently in `go.mod`, and the check needed (deny loopback/private/
   link-local/CGNAT) is ~20 lines of stdlib `net` code covered by the
   existing Go 1.25 toolchain (`go.mod` already pins `go 1.25.0`). Adding a
   new dependency for this is unnecessary surface area. Rejected.

## Platform impact

- **Migrations**: none. No data model or schema change; `mctl-gitops` is
  untouched by this change (the fix only makes the agent picker of paths
  stricter).
- **Backward compatibility**: `GITOPS_PATH_ALLOWLIST` is optional with a
  default that mirrors current legitimate behavior exactly (see prefix list
  above), so existing deploys need no config change to keep working. Remote
  skills that were registered with `http://` endpoints or private-range
  hosts before this ships will need to be re-registered over `https://`
  with a public/allowed host — this is a deliberate breaking change for
  that (already out-of-policy) configuration and should be called out in
  the release notes / CHANGELOG per repo convention.
- **Resource impact**: negligible — one extra DNS lookup at registration
  time (rare, operator-driven) and one prefix-string comparison per gitops
  write (already on a path that does two GitHub API round trips).
- **Risks + mitigations**:
  - *Risk*: default allowlist misses a legitimate write target not
    discovered during this investigation, breaking a working fix flow in
    production. *Mitigation*: task list includes grepping all `FilePath:`
    assignments repo-wide (already done for this proposal — six builtin
    call sites plus `workflow_fixer.go`'s two literals, all covered by the
    three default prefixes) and a rollout with `DRY_RUN=true` first, plus
    tests asserting every `fixer.DetectFilePath` / builtin `FilePath` value
    passes the default allowlist.
  - *Risk*: DNS-based allowlist bypass (register with a hostname that
    resolves to a public IP at registration time, then repoint DNS to a
    private IP). *Mitigation*: the connection-time `DialContext` guard
    re-checks the resolved IP on every actual request, not just at
    registration.
  - *Risk*: enforcing `RequiredCapabilities()` on the six builtin skills
    that never declared `CapModifyGitOps`/`CapCreatePR` breaks their fix
    flow if any is missed. *Mitigation*: task list includes a table-driven
    test that runs every registered builtin skill's `Fix()` through
    `capability.Context` and asserts none are rejected for missing
    capabilities they actually need.
