# Path allowlist for gitops writes + remote-skill URL/capability validation

## Context
mctl-agent turns skill output into direct writes against `mctlhq/mctl-gitops`.
`internal/pipeline/pipeline.go` (`handleHighConfidenceFix`, lines ~509-572) takes
`fixResult.FilePath` from a skill's `Fix()` result — falling back to
`fixer.DetectFilePath` only when the skill leaves it empty — and passes it
unchecked to `p.github.GetFileContent` and then `p.github.CreatePR`.
`internal/fixer/github.go` (`CreatePR`, lines 113-133) then calls
`Repositories.GetContents` / `Repositories.UpdateFile` at that exact path with
no prefix check, no traversal check, and no symlink check. Because remote
skills (`internal/skill/remote/remote.go`) and YAML skills both produce
`FixResult.FilePath` / `FixResult.NewContent` from external input (an HTTP
response from a registered endpoint, or a YAML fix template), a malicious or
compromised remote skill can steer a write to any path in `mctl-gitops`, not
just the tenant/service values file it should own.

Compounding this, `internal/skill/remote/remote.go` (`Manager.Register`,
lines 279-299) accepts any `Registration.Endpoint` string with only an
empty-string check, and any `Registration.Capabilities` list with no
validation against the known `skill.CapabilityID` enum
(`internal/skill/skill.go`). A registered endpoint can be `http://`, a
loopback, link-local, RFC1918, or CGNAT address (cloud metadata endpoints
included), and can claim capabilities like `modify_gitops` or `merge_pr` that
the pipeline never checks, because `internal/capability.Provider` /
`capability.Context` exist (`internal/capability/capability.go`) but are
never invoked: `cmd/agent/main.go:104` constructs `capProvider`, and
`pipeline.NewPipeline` stores it on `Pipeline.provider`, but no code path in
`internal/pipeline/pipeline.go` ever calls `capability.NewContext` or reads
`p.provider` — confirmed by grep, the field is assigned once and never read.
The pipeline instead calls `p.github` (the raw `*fixer.GitHubFixer`) directly,
bypassing the capability sandbox entirely.

This matters because mctl-agent's whole trust model rests on "the agent only
ever touches its own tenant's values file." Today that boundary is not
enforced in code, only by convention — any skill (built-in, YAML, or remote)
that returns an off-prefix `FilePath`, and any remote endpoint that points
inside the cluster network, silently works.

## User stories
- AS a platform operator I WANT every gitops write from mctl-agent restricted
  to an explicit path allowlist SO THAT a buggy or compromised skill cannot
  modify files outside the tenant/service directory it was invoked for.
- AS a platform operator I WANT remote skill registration to reject unsafe
  endpoints and undeclared capabilities SO THAT a malicious or compromised
  external service cannot direct mctl-agent to write anywhere in
  `mctl-gitops` or call platform capabilities it was never granted.
- AS a maintainer I WANT the existing `internal/capability` sandbox actually
  wired into the pipeline SO THAT capability checks are enforced at runtime,
  not just available as unused code.

## Acceptance criteria (EARS)
- WHEN a skill's `FixResult.FilePath` (or the fallback from
  `fixer.DetectFilePath`) is resolved before a GitHub write, THE SYSTEM SHALL
  validate it against a configurable path-prefix allowlist and reject any
  path that does not resolve under an allowed prefix.
- WHEN a candidate gitops path contains `..` segments, is absolute, or
  resolves (after cleaning) outside every allowed prefix, THE SYSTEM SHALL
  reject the write, log the rejection (skill name, ticket ID, offending
  path), and surface the failure the same way a patch-generation error is
  surfaced today (`t.Status = ticket.StatusFixProposed`, Telegram
  notification, `webhook.EventTicketFixFailed`) rather than opening a PR.
- WHEN `GitHubFixer.CreatePR` or `GitHubFixer.GetFileContent` is called with
  a path outside the allowlist, THE SYSTEM SHALL reject it at that layer too
  (defense in depth), independent of whether the pipeline-level check ran.
- WHEN the GitHub API reports the existing blob at a candidate path as a
  symlink (content type `symlink`), THE SYSTEM SHALL reject the write.
- WHEN a remote skill registration (`POST /api/v1/skills/register`) is
  processed, THE SYSTEM SHALL reject it unless `Endpoint` parses as an
  `https://` URL.
- WHEN a remote skill registration's endpoint host is a literal IP, or
  resolves via DNS to an IP, in a private (RFC 1918), loopback (127.0.0.0/8,
  ::1/128), link-local (169.254.0.0/16, fe80::/10), or CGNAT
  (100.64.0.0/10) range, THE SYSTEM SHALL reject the registration.
- WHEN a remote skill registration declares a capability string not present
  in the known `skill.CapabilityID` set, THE SYSTEM SHALL reject the
  registration.
- WHILE a remote skill is registered and its endpoint's DNS record can
  change after registration, THE SYSTEM SHALL also block outbound requests
  from `remote.Skill.post` whose resolved connection IP falls in a denied
  range, so registration-time validation cannot be bypassed by DNS
  rebinding.
- WHEN the pipeline performs any gitops read or write (`GetFileContent`,
  `CreatePR`) or notification on behalf of a skill, THE SYSTEM SHALL route
  the call through `capability.Context` for that skill so the existing
  `RequiredCapabilities()` / `CapModifyGitOps` / `CapCreatePR` checks in
  `internal/capability/capability.go` actually execute, instead of calling
  `p.github` / `p.telegram` directly.
- IF a skill's `RequiredCapabilities()` does not include `CapModifyGitOps`
  (or `CapCreatePR`) THEN THE SYSTEM SHALL refuse that skill's gitops write
  and surface the same fix-failed path as other rejections.
- WHEN a legitimate fix targets an allowed prefix (`platform-gitops/services/
  <tenant>/<service>/...`, plus the existing built-in prefixes used by
  `fixer.DetectFilePath` for platform services and by
  `workflow_fixer.go`), THE SYSTEM SHALL continue to create the PR exactly as
  before — this change must not regress today's working fix flows.

## Out of scope
- Fail-closed token auth (tracked separately in mctlhq/mctl-agent#98).
- Changing the `AUTO_MERGE_ENABLED` default (separate issue).
- Redesigning the remote-skill protocol or authenticating remote skill
  endpoints (e.g. mTLS, signed responses) — this proposal only adds
  URL/capability validation at registration and connection time.
- Rate-limiting or quarantining repeatedly-rejected skills (existing circuit
  breaker in `internal/skill/metrics.go` is untouched).

## Open questions
- The issue says "make the prefix configurable" (singular), but the repo
  already has legitimate built-in write targets outside
  `platform-gitops/services/...`: `fixer.DetectFilePath` writes
  `platform-gitops/apps/templates/<service>.yaml` for `PlatformServices`
  (`mctl-api`, `mctl-agent`), and `workflow_fixer.go` writes
  `platform-gitops/argo-workflows/workflow-templates/wft-deploy-service.yaml`
  and `platform-gitops/apps/templates/projects/project-apps.yaml`. Resolved
  by treating the allowlist as a configurable *list* of prefixes (env var,
  comma-separated), defaulting to exactly these known-safe roots, so
  existing fix flows keep working. Flagging for reviewer confirmation.
- Whether remote-skill capability validation should also apply an
  allow-by-default vs deny-by-default policy for high-risk capabilities
  (`CapMergePR`, `CapExecWorkflow`) beyond "must be a known enum value."
  Resolved by proceeding with enum-membership validation only for this
  proposal (matches the issue's literal ask: "validate declared
  capabilities"); tightening which capabilities remote skills may ever
  request is left as a follow-up.
- Whether DNS-rebinding protection for remote skill HTTP calls should block
  at dial time (custom `DialContext` deny-listing resolved IPs, chosen here)
  vs. re-resolving and re-checking the host before every call. Resolved by
  using a custom `DialContext`, since it also naturally covers redirects
  and is the standard Go idiom for SSRF hardening.
