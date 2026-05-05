# Design: workerd-json-crash-fix

## Current state
The mctl-web Cloudflare Worker is deployed via wrangler (version TBD in CI, pinned in
`cloudflare-worker/package.json`). workerd is a transitive runtime dependency brought in by
wrangler; its version is not directly pinnable in `wrangler.toml`. The existing proposal
`wrangler-cve-2026-0933` recommends upgrading wrangler to ≥ 4.59.1 (latest: 4.87.0) to
patch CVE-2026-0933. wrangler 4.87.0 was verified to include workerd v1.20260504.1 as a
transitive dependency. However, workerd v1.20260505.1 — released May 5, 2026 — contains a
crash fix for JSON module handling that is **not** included in v1.20260504.1.

See `context/architecture.md` for Worker structure and the `deploy.yml` deployment pipeline.

## Proposed solution
**Bump wrangler in `cloudflare-worker/package.json` to the latest version available at merge
time (≥ 4.87.0) and add a version verification step in `deploy.yml`.**

Since workerd tracks wrangler closely (Cloudflare releases both), the safest approach is:
1. Use `npm update wrangler` or pin `"wrangler": "^4.87.0"` in `cloudflare-worker/package.json`.
2. After `npm install`, emit the resolved workerd version from the lockfile and assert it is
   ≥ v1.20260505.1 using a small CI script.
3. Fail the pipeline if the assertion fails, preventing deployment of a runtime with the
   known crash path.

This is deliberate belt-and-suspenders on top of the CVE proposal: the CVE proposal upgrades
wrangler for security; this proposal adds explicit runtime-version verification to CI so
future crash fixes are also caught before deployment.

### CI assertion script (pseudo-code)
```bash
WORKERD_VERSION=$(node -e "require('./node_modules/workerd/package.json').version" | sed 's/workerd-//')
MIN_VERSION="20260505.1"
# compare YYYYMMDD.rev numerically; fail if WORKERD_VERSION < MIN_VERSION
```

## Alternatives

**A. Pin workerd directly in package.json**
workerd is not a direct dependency of mctl-web; attempting to pin it alongside wrangler could
create peer-dependency conflicts and is not a supported pattern by Cloudflare. Rejected.

**B. No verification step — trust wrangler to pull the right version**
Possible but brittle: if wrangler's own lockfile is pinned to an older workerd for some
reason, a bug could slip through silently. The CI assertion costs < 5 seconds and eliminates
ambiguity. Rejected in favour of explicit verification.

**C. Wait for `wrangler-cve-2026-0933` to be implemented and absorb this fix**
If wrangler 4.87.0 happens to pull in a workerd ≥ v1.20260505.1 transitively, this proposal
is automatically satisfied. However, this cannot be guaranteed without the CI assertion;
hence the two proposals are complementary, not redundant.

## Platform impact
- **Migrations:** None — no Worker logic changes.
- **Backward compatibility:** Full. The Worker API surface is unchanged.
- **Resource impact:** workerd runtime updates do not affect CPU or memory quotas. No impact
  on the `labs` tenant (this change is scoped to the `admins` tenant where mctl-web runs).
- **Risks:** Low. The change is a runtime version bump with a crash fix; no API behaviour
  changes are expected. The CI assertion catches any regression before deployment.
- **Rollback:** Revert `cloudflare-worker/package.json` to the previous wrangler pin and
  redeploy via `deploy.yml`. The previous version remains available in git history.
