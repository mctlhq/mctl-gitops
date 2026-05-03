# Design: git-plugin-install-allowlist

## Current state

As of openclaw 2026.3.14 (the version running on all three tenants — `admins`, `labs`,
`ovk`) the only plugin installation paths are:
- npm packages (`openclaw plugins install <npm-package>`) — covered by
  `npm-supply-chain-audit`
- ClawHub marketplace entries (`openclaw plugins install clawhub:<id>`) — covered by
  `clawhub-skills-allowlist`

Neither path uses raw git URLs. The `git:` scheme does not exist in 2026.3.14; it is
introduced in 2026.5.2. None of the three tenants have `git:` plugin installs today, so
there is no installed-plugin inventory to migrate.

The platform uses a standard pattern for controlling openclaw behaviour per tenant: Helm
values in `mctl-gitops` under `helm/openclaw/<tenant>/values.yaml`, applied by ArgoCD.
Existing examples of this pattern include the `clawHubSkillSources` allowlist (see
`clawhub-skills-allowlist` proposal) and the egress whitelist entries consumed by
NetworkPolicy manifests (see `egress-network-policy` proposal). There is currently no
`gitPluginInstallAllowlist` key in any tenant's Helm values because the feature does not
yet exist.

## Proposed solution

### Helm values schema

A new optional key is added to the openclaw Helm chart values schema for each tenant:

```yaml
gitPluginInstall:
  enabled: false          # master switch; false = reject all git: installs
  allowlist:              # list of URL prefix patterns; empty = deny all
    - "https://github.com/mctlhq/"
    - "https://github.com/openclaw/"
```

The `enabled: false` default means the `git:` install feature is off until the key is
explicitly set to `true` via a gitops PR. This mirrors openclaw 2026.5.2's own feature-flag
mechanism for the `git:` scheme and adds a second, platform-level gate.

### Allowlist matching

Each entry in `allowlist` is treated as a URL prefix. An install URL matches if:
1. It begins with one of the listed prefixes (case-insensitive), AND
2. The scheme is `https://` (SSH `git@` URLs are not permitted unless explicitly listed
   with `git@github.com:mctlhq/` syntax and `git:` is normalized to the canonical URL
   before matching).

SSH `git:` URLs are normalised to their HTTPS canonical form before prefix matching so that
`git:git@github.com:mctlhq/foo` is compared against `https://github.com/mctlhq/`.

### Enforcement point

openclaw 2026.5.2 exposes a pre-install hook interface (`plugin:before-install` lifecycle
event) that the platform can implement as a local plugin or via openclaw's built-in policy
config key `pluginPolicy.gitInstallAllowlist` (confirmed in the 2026.5.2 upstream changelog).
The Helm chart translates the `gitPluginInstall.allowlist` values array directly into the
`pluginPolicy.gitInstallAllowlist` field in the generated openclaw `config.yaml` ConfigMap.

This means enforcement lives inside the openclaw process itself (not a sidecar or external
webhook), keeping the memory footprint unchanged. No new containers or init-containers are
added.

### Gitops placement

```
mctl-gitops/
  helm/
    openclaw/
      admins/values.yaml    # add gitPluginInstall block
      labs/values.yaml      # add gitPluginInstall block (enabled: false initially)
      ovk/values.yaml       # add gitPluginInstall block
  manifests/
    openclaw/
      base/configmap-openclaw.yaml   # Helm template renders pluginPolicy section
```

### CI enforcement

A new CI step `check-git-plugin-allowlist` is added to the gitops repository pipeline:
- Fails if any `values.yaml` sets `gitPluginInstall.enabled: true` but
  `gitPluginInstall.allowlist` is empty or missing.
- Fails if the rendered `config.yaml` ConfigMap contains `pluginPolicy.gitInstallAllowlist`
  entries that do not appear in the corresponding `values.yaml` allowlist (detects
  out-of-band edits to the ConfigMap template).
- Runs on every PR that touches `helm/openclaw/*/values.yaml` or the ConfigMap template.

### Rollout order

Follows the standard promotion sequence (ADR-0001):
1. `admins` (lowest blast radius — internal team)
2. `labs` (experimental — confirm no memory regression)
3. `ovk` (production — only after `labs` is stable)

The feature remains `enabled: false` on all three tenants until after the 2026.5.2 upgrade
is confirmed stable. Enabling requires a separate gitops PR per tenant.

## Alternatives

### Alternative 1: Block `git:` installs at the network layer only (egress NetworkPolicy)

The `egress-network-policy` proposal already restricts which hosts openclaw pods can reach.
One could rely on that policy to block arbitrary git fetches by not listing `github.com` in
the egress whitelist. This was rejected because: (a) openclaw legitimately needs to reach
`github.com` for upstream plugin updates from approved repositories, so a blanket block is
not viable; (b) NetworkPolicy operates at the IP level and cannot distinguish between
`github.com/mctlhq/approved-plugin` and `github.com/attacker/malicious-plugin`; (c) IP-
level controls and URL-level allowlists are complementary, not substitutes. Both should be
in place.

### Alternative 2: Disable the `git:` feature flag at the openclaw binary level (build-time patch)

The fork could patch openclaw to remove the `git:` scheme entirely from the 2026.5.2 build.
This was rejected because: (a) it creates a long-term fork divergence that is expensive to
maintain across future upgrades; (b) the allowlist approach gives us the same protection
while retaining the ability to use the feature for approved repositories; (c) upstream
already provides a `pluginPolicy.gitInstallAllowlist` config key as the intended control
mechanism.

### Alternative 3: Require a manual security review for each git: install (process-only control)

A documented policy requiring operators to request security-team sign-off before any `git:`
install, enforced by documentation and culture rather than code. This was rejected because:
(a) process-only controls are not auditable and do not produce a log event; (b) a
compromised credential bypasses human-process controls by definition; (c) the config-based
allowlist costs the same operator effort as a process but is enforced automatically and
logged.

## Platform impact

### Migrations

No data migration is required. The `git:` plugin install feature does not exist in the
currently deployed version (2026.3.14), so there are no existing `git:`-sourced plugins to
inventory or grandfather. The Helm values change is additive (new optional key with a
safe default of `enabled: false`).

### Backward compatibility

- The Helm chart change is backward compatible: tenants that do not include the new key
  receive the `enabled: false` default, which matches the current behaviour (the `git:`
  scheme does not work at all before 2026.5.2).
- The openclaw `config.yaml` ConfigMap gains a new `pluginPolicy` section that 2026.3.14
  ignores (it does not parse that key). No impact on the currently deployed version.
- When `upgrade-to-2026-5-2` lands, the ConfigMap is already present and the allowlist
  policy takes effect immediately on the first pod start with the new image.

### Resource impact (labs)

The allowlist check is a string prefix match against a list that will have at most a handful
of entries. It runs on the hot path of `plugins install` only, which is an infrequent
operator action, not a request-per-second hot loop. The policy is stored in-memory as part
of the existing openclaw config object — no additional allocations beyond the config parse
at startup. Memory overhead is estimated at less than 1 KB per tenant. This is safe for the
`labs` tenant which is close to its memory limit. No flag as risky.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| A legitimate plugin repo is not on the allowlist and blocks operator work | Medium | Allowlist PR process is lightweight; operators can request an addition and the CI check makes the current allowlist visible in code review |
| The `enabled: false` default is accidentally flipped to `true` with an empty allowlist | Low | CI step `check-git-plugin-allowlist` blocks this combination |
| An allowlisted organisation account is itself compromised (supply-chain) | Low | This is the residual risk accepted by trusting `github.com/mctlhq/*`; mitigated by pinning to specific commit SHAs in a follow-on proposal if the risk is re-evaluated |
| ArgoCD sync delay means a policy change is not reflected immediately | Low | ArgoCD sync is typically sub-minute; the window is acceptable for a config change |
| A `plugins update` for a plugin whose origin was removed from the allowlist silently fails | Low | The EARS criterion requires a structured log event; operators will see the warning in the log pipeline |
