# Design: axios-supply-chain-pinning

## Current state

The mctl-openclaw repo is a Node.js + TypeScript workspace (see
`context/architecture.md`). Dependencies include `node-slack-sdk`, which has been
confirmed to resolve `axios@1.15.0` (safe). However, no systematic audit has been
run across all workspace packages. Other workspace packages — including those under
`extensions/*` for channels such as WhatsApp, Telegram, Discord, and others — may
have their own direct or transitive `axios` dependencies that could resolve to
`axios@1.14.1` or `axios@0.30.4`.

The WAVESHAPER.V2 backdoor is activated on `require`/`import` of the compromised
package. Because openclaw runs with access to S3 credentials, channel OAuth tokens,
and API keys in the process environment, a single resolved backdoored dependency is
sufficient for a full credential exfiltration.

The existing `npm-supply-chain-audit` proposal covers `lotusbail` and
`discord.js-user` but does NOT cover this Axios vector. That proposal and this one
are independent and complementary.

## Proposed solution

**Run a full dependency-tree audit and, if needed, add npm `overrides` to pin Axios
to a safe version.**

Steps:
1. From the monorepo root, run `npm ls axios --all` (or the workspace equivalent)
   to enumerate every path in the dependency tree that resolves an `axios` version.
2. Inspect the output for any occurrence of `1.14.1` or `0.30.4`.
3. If found: add an `overrides` block to the affected workspace's `package.json`
   (or to the root `package.json` for a global override) pinning `axios` to the
   nearest safe version in the same semver range (e.g., `>=1.15.0` for the 1.x
   line, any non-backdoored 0.x release for the 0.x line).
4. Regenerate the lockfile (`npm install`) and verify `npm ls axios` no longer
   reports the backdoored versions.
5. Commit the lockfile and `package.json` changes; CI must pass.
6. If no backdoored versions are found: record the audit date and result as a
   comment in the repo's security log (or a dated note in `context/`) and close
   the proposal as "clean — no change required."

Why npm `overrides` rather than bumping the direct dependency:
- In many cases `axios` is not a direct dependency of our code but is pulled in
  transitively. A direct-dependency bump would require forking the upstream package
  or patching its `package.json`, which is not maintainable. npm `overrides`
  (supported since npm 8) is the canonical mechanism for forcing a safe resolution
  across the entire tree without changing upstream packages.
- No new packages are introduced; only the resolved version of an already-present
  package is changed. Memory footprint is unaffected.

## Alternatives

**Option A — Upgrade every direct dependency that pulls in Axios to a version that
no longer uses the backdoored release.**
Rejected: requires identifying which version of each upstream package has moved off
`axios@1.14.1` or `0.30.4`, and may not be possible if no such version exists yet.
npm `overrides` achieves the same outcome immediately.

**Option B — Remove all packages that transitively depend on Axios.**
Rejected: `node-slack-sdk` and likely other channel integrations require Axios.
Removing them would break Slack and other channel support, which is out of scope
and disproportionate.

**Option C — Wait for upstream openclaw to upgrade its own dependencies.**
Rejected: the threat is active now. The time between a backdoored package existing
in the dependency tree and an exfiltration event is not bounded by upstream release
cycles. We must act within our own fork.

## Platform impact

**Migrations**
- None. The lockfile regeneration is a build-time change only. No runtime
  migrations are needed.

**Backward compatibility**
- npm `overrides` does not change the public API of any package; it changes only
  the resolved version. If the safe Axios version has an interface change, CI tests
  will catch it.
- All channel integrations using Axios remain functional; only the resolved version
  changes (and only if the current resolution points to the backdoored versions).

**Resource impact — `labs`**
- No new packages are added. If the pinned version is already in the lockfile
  (e.g., `1.15.0` is already resolved elsewhere in the tree), npm deduplicates it.
  Memory impact is zero. The `labs` memory constraint is not affected.

**Risks and mitigations**

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Backdoored version already present and credentials exfiltrated | Medium if found | Open a separate incident immediately; rotate all S3 credentials, channel OAuth tokens, and API keys |
| Safe Axios version has a breaking API change | Low | CI test suite catches breakage before deployment |
| npm `overrides` silently breaks a nested dependency | Very low | `npm ls` re-run after lockfile regeneration confirms consistent resolution |
| False-clean audit (tool reports safe but lockfile contains backdoored version) | Very low | Cross-check `grep` on the lockfile for the version strings `1.14.1` and `0.30.4` as a secondary check |
