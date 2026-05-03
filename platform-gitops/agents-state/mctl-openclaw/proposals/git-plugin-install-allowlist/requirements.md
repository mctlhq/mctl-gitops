# Git Plugin Install Allowlist

## Context

openclaw 2026.5.2 introduces first-class `git:` plugin installs, allowing operators to run
`openclaw plugins install git:https://github.com/owner/repo` (or the SSH variant
`git:git@github.com:owner/repo`). Before 2026.5.2 all plugin installs went through npm or
ClawHub, both of which are covered by existing controls (`npm-supply-chain-audit`,
`clawhub-skills-allowlist`). The `git:` scheme bypasses those controls entirely: no
provenance record, no npm audit log, no ClawHub review gate.

Without an allowlist policy, any operator credential — or a compromised one — can point
openclaw at an arbitrary git repository URL. This creates a direct path from a single
compromised account to code execution inside the openclaw pod, because the repository
content is installed and run with no further inspection. The threat is compounded by the
fact that a repository that passes manual review today can have malicious code pushed to
it after the fact, and a subsequent `plugins update` would pull it in. Gating `git:` installs
on a version-controlled allowlist is a low-friction control that closes this attack class
before any tenant enables the feature.

## User stories

- AS a platform security engineer I WANT a version-controlled allowlist of permitted git
  hosts and organisations SO THAT operators can only install git-sourced plugins from
  explicitly approved sources
- AS an operator I WANT openclaw to reject `git:` install requests that target an
  unapproved repository with a clear error message SO THAT I know immediately whether
  a repository needs to go through the allowlist approval process
- AS a platform operator I WANT the allowlist to be stored in mctl-gitops and require a PR
  review to change SO THAT no single operator can unilaterally add a new git source at
  runtime
- AS a developer adding a new plugin source I WANT a documented approval process for
  expanding the allowlist SO THAT legitimate additions can be made without bypassing the
  control
- AS a labs tenant operator I WANT the allowlist enforcement to add no runtime memory
  overhead to the labs pod SO THAT the labs tenant does not breach its memory limit

## Acceptance criteria (EARS)

- WHEN an operator invokes `openclaw plugins install git:<url>` and `<url>` does not match
  any entry in the tenant's `gitPluginInstallAllowlist` THE SYSTEM SHALL reject the install
  with a non-zero exit code and a message stating which policy blocked it and where the
  allowlist is managed
- WHEN an operator invokes `openclaw plugins install git:<url>` and `<url>` matches an entry
  in the tenant's `gitPluginInstallAllowlist` THE SYSTEM SHALL proceed with the install as
  it would without the policy
- WHILE `gitPluginInstallAllowlist` is set to an empty list THE SYSTEM SHALL block all
  `git:` plugin installs (fail-closed semantics)
- IF a tenant's Helm values contain no explicit `gitPluginInstallAllowlist` key THE SYSTEM
  SHALL apply a default deny-all policy for `git:` plugin installs on that tenant
- WHEN a `git:` plugin install is blocked by the allowlist THE SYSTEM SHALL emit a
  structured log event (at WARN level or above) containing the attempted URL and the tenant
  identifier, accessible via the existing mctl-api metrics and log pipeline
- WHEN an operator invokes `openclaw plugins update` for a previously installed git-sourced
  plugin THE SYSTEM SHALL re-validate the plugin's origin URL against the current allowlist
  before fetching updates, and block the update if the origin is no longer in the allowlist
- WHEN the `gitPluginInstallAllowlist` Helm value is updated via a gitops PR and ArgoCD
  syncs the new manifest THE SYSTEM SHALL apply the updated policy without requiring a pod
  restart
- WHILE the feature flag `git:` plugin installs is disabled in tenant config THE SYSTEM
  SHALL reject any `git:` install attempt regardless of the allowlist contents
- IF a gitops PR removes an entry from `gitPluginInstallAllowlist` THEN THE SYSTEM SHALL
  not automatically uninstall already-installed plugins sourced from that entry, but SHALL
  block future installs and updates from that source (removal of installed plugins is a
  separate operational step)

## Out of scope

- Scanning or auditing the content of git repositories on the allowlist for malicious code
  (SAST/SCA is outside this proposal's scope)
- Blocking git traffic at the network layer — that is covered by `egress-network-policy`
- Controls over npm or ClawHub plugin sources — those are covered by `npm-supply-chain-audit`
  and `clawhub-skills-allowlist` respectively
- Automatic removal of plugins whose source has been removed from the allowlist
- Enforcement on the openclaw upstream CLI outside of the mctl platform deployment
- Changes to the 2026.5.2 upgrade timeline — this proposal is independent of
  `upgrade-to-2026-5-2`
