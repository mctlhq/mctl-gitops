# Design: npm-supply-chain-audit

## Current state
According to `context/architecture.md`, openclaw uses a Node.js + TypeScript workspace. The WhatsApp channel is built on `@whiskeysockets/baileys`, Discord on `discordjs/discord.js`. Dependencies are managed via `package.json` / `package-lock.json`. Deploy: Docker → mctl-gitops → ArgoCD. The current CI pipeline contains no explicit check for resolved package URLs or for forbidden names. The fact that correct packages are in use is not currently verified automatically.

Identified threats (inbox/2026-04-27.md):
- Poisoned Baileys fork (2025-12): intercepts WhatsApp auth, messages, contacts, media via a WebSocket wrapper
- `discord.js-user` (GHSA-69r6-7h4f-9p7q, CVSS 9.8): leaks Discord tokens

## Proposed solution

**Part 1: One-off audit (immediate)**

Run a `grep` audit of `package-lock.json` and `package.json` for:
1. Forbidden names: `baileys` (without namespace), `discord.js-user`, and any other known poisoned forks
2. Resolved URLs for `@whiskeysockets/baileys` and `discord.js` — must point to `https://registry.npmjs.org/`
3. Run `npm audit --audit-level=high` and capture the result

The audit result is documented: either "clean and confirmed" or a list of issues for immediate fix.

**Part 2: CI step (permanent)**

Add the script `scripts/check-npm-supply-chain.sh` (or a Python/Node equivalent) to the CI pipeline:

```bash
# Forbidden package name check
FORBIDDEN="baileys discord.js-user"
for pkg in $FORBIDDEN; do
  if grep -q "\"$pkg\"" package-lock.json; then
    echo "BLOCKED: forbidden package '$pkg' found in package-lock.json"
    exit 1
  fi
done

# Resolved URL check for monitored packages
MONITORED="@whiskeysockets/baileys discord.js"
for pkg in $MONITORED; do
  urls=$(jq -r ".. | objects | select(.name? == \"$pkg\") | .resolved" package-lock.json 2>/dev/null)
  for url in $urls; do
    if [[ "$url" != "https://registry.npmjs.org/"* ]]; then
      echo "BLOCKED: package '$pkg' resolved from non-official registry: $url"
      exit 1
    fi
  done
done
```

The script runs on every PR change to `package.json` or `package-lock.json`. Additionally: `npm audit --audit-level=high` for the monitored package list.

**Why this approach:**
A minimal, targeted approach — we check only specific known-bad packages and their resolved URLs. No external SCA tooling is required, it works with what is in CI. The one-off audit closes the question of current state; the persistent CI step prevents regressions.

## Alternatives

**Alternative 1: A full SCA tool (e.g. Snyk, Socket Security)**
Socket Security specialises specifically in supply-chain attacks via npm and can detect poisoned forks via behavioural analysis. Dropped for this proposal: requires an external integration, licensing, configuration — significantly higher effort while the known threats are concrete and covered by a simple script. It can be added later as an additional layer.

**Alternative 2: npm `overrides` / `resolutions` for pinning packages**
You can use `overrides` (npm 8+) in `package.json` to force specific versions and exclude forks:
```json
"overrides": { "baileys": "npm:@whiskeysockets/baileys@latest" }
```
Dropped as the primary mechanism: this protects against transitive dependency substitution but does not detect a case where someone explicitly added a forbidden package to `dependencies`. The CI check is more explicit and auditable. `overrides` can be added in addition.

**Alternative 3: Lockfile integrity check via `npm ci` in Docker build**
`npm ci` uses `package-lock.json` and refuses if the lock does not match `package.json`. Dropped as a sufficient measure: `npm ci` does not check package names against a forbidden list — if `package-lock.json` already contains a poisoned package, `npm ci` will install it without complaint. The CI script is required on top.

## Platform impact

**Migration**
No migrations. A one-off audit + adding the CI script and config to the repository.

**Backward compatibility**
The CI step does not affect the runtime. If the current packages are correct (as expected), CI will simply pass. If a problem is found — it requires an immediate fix in `package.json`/`package-lock.json`.

**Resource impact**
- labs: NO IMPACT. Changes are CI-only, not in the deploy.
- admins: NO IMPACT.
- ovk: NO IMPACT.

**Risks and mitigations**
- The audit detects a poisoned package in the current `package-lock.json` → immediately replace the package, rebuild the lock, run an emergency redeploy across all tenants; treat WhatsApp/Discord credentials as compromised (token rotation)
- The script reports a false positive due to mirror registries (e.g. a corporate Verdaccio) → add corporate registry prefixes to the allowlist as needed
- The script does not cover new poisoned packages that appear after it was written → periodically (quarterly) revisit the `FORBIDDEN` and `MONITORED` package lists
- A developer uses `--ignore-scripts` or another bypass → the CI step is mandatory (branch protection), it cannot be skipped without an explicit security-engineer approval
