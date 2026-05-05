# Design: discord-js-dm-fix

## Current state

Per `context/architecture.md`, the mctl-openclaw Discord channel is implemented as a workspace extension (`extensions/discord/`) that depends on `discord.js`. The version currently in use is v14.26.3 (or earlier). All three tenants (`labs`, `admins`, `ovk`) build from the same source tree and run the same Discord extension code.

The discord.js `MessageCreateAction` handler (the internal action that processes `MESSAGE_CREATE` gateway events) checks whether the target channel is present in the internal channel cache before emitting the `messageCreate` event to application code. In v14.26.3 and earlier, if the channel is not cached — which is expected during cold-start and after reconnection — the event is silently dropped. No error is thrown; no log is written; the DM is permanently lost.

Because every openclaw pod restart (which occurs on every image rollout, and also on node eviction or OOM kill) causes the discord.js internal cache to start empty, the cold-start window exists on every restart. The ADR-0002 `restore-state` readiness probe ensures the pod does not receive production traffic until session/auth is restored from S3, but the Discord gateway connection is established and begins receiving events before the cache is fully warm.

The prior proposal `discordjs-v14264-update` was written against the `upgrade-to-2026-4-29` context. That proposal is now superseded. This proposal re-targets the fix for the current context: all tenants on v2026.3.14, with `upgrade-to-2026-5-3` as the concurrent major upgrade proposal.

## Proposed solution

The solution has two branches, determined by a verification check against the openclaw v2026.5.3 upstream bundle.

### Branch A: discord.js >= v14.26.4 is bundled in openclaw v2026.5.3 (expected path)

Inspect the upstream openclaw v2026.5.3 `package.json` and `package-lock.json` to confirm that `discord.js >= 14.26.4` is present:

```bash
# From within the openclaw v2026.5.3 source tree or Docker image:
npm ls discord.js 2>/dev/null | grep discord.js
# Expected: discord.js@14.26.4 or higher
```

If confirmed, this proposal is satisfied as a side-effect of `upgrade-to-2026-5-3`. Close this proposal with a verification note. Add a single confirmation line to the `upgrade-to-2026-5-3` soak checklist (task T10, channel connectivity test) noting that Discord DM receipt in uncached DMChannels should be validated.

### Branch B: discord.js < v14.26.4 in openclaw v2026.5.3 (fallback path)

If the upstream v2026.5.3 bundle does not include the fix:

1. Open a targeted PR to the openclaw fork's Discord extension, bumping `discord.js` from its current version to `14.26.4` in `extensions/discord/package.json`.
2. Regenerate `package-lock.json` for the Discord extension workspace.
3. Build a patched Docker image.
4. Roll out to `labs` first, following the ADR-0001 and ADR-0002 procedure (stop canary → deploy → verify restore-state probe → restart canary → 24-hour soak).
5. Promote to `admins`, then to `ovk`, each with a soak period.

The Branch B rollout is independent of `upgrade-to-2026-5-3` and can proceed in parallel if the openclaw upgrade is delayed.

### Why this approach

The fix is a single patch-release version bump with no API surface change and no new dependencies. There is no benefit to cherry-picking the upstream discord.js commit into a custom fork or implementing an application-level workaround; either would add maintenance overhead for zero additional benefit. The verification-first approach (Branch A) avoids duplicating rollout effort if the upstream bundle already incorporates the fix.

## Alternatives

**A. Defer indefinitely and accept silent DM drops.**
Rejected. Silent message loss is a correctness regression that affects end users on every pod restart. The impact is bounded but real, and the fix cost is minimal.

**B. Implement an application-level DM retry mechanism in the Discord extension.**
Rejected. This would duplicate logic that discord.js v14.26.4 already provides natively (fetching the channel object on cache miss), add complexity to the extension, and require ongoing maintenance. The upstream fix is strictly simpler.

**C. Cherry-pick the `MessageCreateAction` fix from discord.js upstream into a local discord.js fork.**
Rejected. Maintaining a fork of a large library like discord.js for a single-line fix introduces permanent maintenance burden. A version bump via `package.json` is the standard and correct mechanism. A fork is only warranted if the upstream project refuses to accept the fix or if the fix carries breaking changes (neither applies here).

## Platform impact

### Migrations

None. discord.js v14.26.4 is a patch release with no breaking changes to the API surface consumed by the openclaw Discord extension.

### Backward compatibility

Fully compatible. The fix is additive: it adds a channel-fetch code path that was previously absent when the channel was not in cache. Behaviour for cached channels is unchanged. No extension code changes are needed beyond the version bump.

### Resource impact (especially for `labs`)

Negligible. discord.js v14.26.4 introduces no new npm dependencies. The additional channel-fetch call in the uncached DMChannel code path is a one-time Discord REST API call per DM during the cold-start window; it has no steady-state memory or CPU impact. The `labs` tenant is close to its memory limit per `context/architecture.md`; this change is assessed as **zero risk** for `labs`.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Branch B requires an additional rollout cycle separate from `upgrade-to-2026-5-3`, increasing operator load | Only pursue Branch B if the v2026.5.3 bundle inspection confirms the fix is absent; verification (task 1) gates the decision. Branch A avoids the additional rollout entirely. |
| The channel-fetch in the uncached DM handler could trigger Discord rate limits under high DM volume in cold-start | The fetch only occurs for uncached DMChannels (cold-start scenario). Steady-state DM handling is unchanged. Rate-limit risk is negligible; add a note to the `labs` soak checklist to check for `429` errors in Discord API logs. |
| The discord.js minor version in `extensions/discord/package.json` conflicts with the version bundled in openclaw core | Verify the version resolution during the Branch B npm install step; confirm no duplicate discord.js versions appear in `npm ls discord.js`. |
