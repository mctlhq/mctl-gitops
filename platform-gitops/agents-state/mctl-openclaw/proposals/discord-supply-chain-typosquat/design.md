# Design: discord-supply-chain-typosquat

## Current state

OpenClaw's Discord channel integration depends on the `discord.js` npm package (tracked in `context/architecture.md`). The workspace package structure uses `workspace:*` references for internal packages and direct npm references for external channel libraries. There is currently no deny-list or integrity-enforcement mechanism for Discord-related packages beyond what npm's lock-file provides.

The `baileys-registry-lockdown` proposal established the reference pattern for channel-library supply-chain hardening: explicit version pinning in `package.json`, lock-file integrity entries, an `.npmrc` deny-list for known-malicious package names, and a CI check that fails if the deny-listed name appears in `node_modules`.

GHSA-69r6-7h4f-9p7q (`discord.js-user`) is a fully malicious package — not a legitimate library with a flaw — so the appropriate response is a permanent deny-list entry rather than a version upgrade.

## Proposed solution

Apply the `baileys-registry-lockdown` pattern to the Discord library:

### 1. `.npmrc` deny-list entry
Add the following to the workspace-root `.npmrc` (or a per-tenant `.npmrc` overlay if workspaces differ):

```
# Supply-chain deny-list: known malicious typosquats
@discord.js-user:registry=null
discord.js-user:registry=null
```

Setting `:registry=null` causes npm to error immediately if resolution of the deny-listed name is attempted, regardless of which transitive dependency requests it.

### 2. Explicit version pin in `package.json`
Ensure the openclaw Discord extension's `package.json` specifies an exact version or range that excludes `discord.js-user`:

```json
"dependencies": {
  "discord.js": "^14.26.4"
}
```

Exact pinning (`14.26.4`) is preferred over a range during the lockdown period; can be relaxed to `^14.26.4` after the CI check is in place.

### 3. CI integrity check
Add a step to the CI pipeline that runs after `npm ci`:

```bash
if grep -r '"discord.js-user"' node_modules/.package-lock.json 2>/dev/null; then
  echo "SECURITY: discord.js-user detected in resolved dependencies" >&2
  exit 1
fi
```

This catches any case where the deny-list is bypassed (e.g., a new npm version changes deny-list behavior) or where the lock file was committed with the malicious package already resolved.

### 4. Lock-file integrity verification
After pinning, re-generate `package-lock.json` and commit the updated integrity hashes. On all subsequent `npm ci` runs, npm verifies the `integrity` field (SHA-512 shasum) for `discord.js` before installation, blocking substitution attacks at the install step.

## Alternatives

1. **Rely solely on the lock file**: The lock file's `integrity` field prevents hash substitution but does not block a fresh install on a new environment where the attacker controls the registry. Rejected as insufficient standalone protection.

2. **Rename the internal Discord package to remove ambiguity**: Changes internal package naming to make typosquat resolution impossible. Rejected — the malicious package is on the public npm registry, not in our workspace; renaming our internal package does not affect npm's resolution of external transitive deps.

3. **Move Discord integration to a private registry mirror**: All packages served from an internal mirror that pre-vets packages. This is the strongest long-term solution but is infrastructure-heavy and out of scope for this proposal. Worth tracking as a future platform-level initiative.

## Platform impact

- **Migrations**: No runtime changes; deny-list and CI check affect only the install and build pipeline.
- **Backward compatibility**: Fully backward-compatible. Existing Discord channel functionality is unchanged.
- **Resource impact for `labs`**: Zero. No new runtime dependencies; `.npmrc` changes affect install time only (negligible).
- **Risks and mitigations**:
  - *Risk*: The `.npmrc` deny-list syntax differs between npm v6, v7, v8, and v9. *Mitigation*: Test the deny-list syntax against the exact npm version used in CI and in the openclaw Docker build image; document the tested version in the PR description.
  - *Risk*: A future transitive dependency legitimately depends on a package with a similar name. *Mitigation*: The deny-list is narrow (`discord.js-user` exactly); a legitimate transitive dep would use `discord.js` and is unaffected.
  - *Risk*: The deny-list alone does not remediate a compromise that already occurred. *Mitigation*: No evidence of compromise exists today; the advisory recommends token rotation only if the package was previously installed. Confirm `discord.js-user` is absent from all three tenants' current `node_modules` as part of task 1.
