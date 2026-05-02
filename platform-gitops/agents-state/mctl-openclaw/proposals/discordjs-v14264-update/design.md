# Design: discordjs-v14264-update

## Current state

OpenClaw's Discord channel extension depends on `discord.js`, tracked as a key dependency in `context/architecture.md`. The version in use is determined by the openclaw upstream `package.json`; the most recently confirmed version in our inbox tracking was `14.26.3` (as of 2026-05-01).

discord.js v14.26.4 introduces a targeted fix in `MessageCreateAction`: when a `MESSAGE_CREATE` gateway event arrives for a `DMChannel` that is not yet in the internal channel cache, the handler now fetches or constructs the channel object before emitting the `messageCreate` event, rather than silently discarding the event.

The affected scenario — DM arriving during the cold-start or post-reconnect window — occurs on every openclaw pod restart. Given ADR-0002's restore-state readiness probe, the pod begins accepting traffic (receives `Ready` status) only after session/auth is restored from S3. However, the Discord bot's internal cache is populated lazily after the gateway connection is established, which can leave a short window during which DMs sent immediately after the `READY` event would be dropped under discord.js < 14.26.4.

## Proposed solution

The solution has two branches depending on verification outcome:

### Branch A: Version included in openclaw 2026.4.29 (expected path)
Inspect the upstream openclaw 2026.4.29 `package.json` / lock file to confirm `discord.js >= 14.26.4` is declared. If confirmed:
- Close this proposal with a verification note.
- Add a single line to the 2026.4.29 upgrade verification checklist (in `upgrade-to-2026-4-29/tasks.md`) noting that discord.js v14.26.4 DM fix is included.
- No code change required.

### Branch B: Version not included in openclaw 2026.4.29 (fallback path)
If the upstream bundle pins discord.js to a version < 14.26.4:
1. Open a targeted patch PR to the openclaw fork's Discord extension, bumping the `discord.js` dependency from `14.26.3` to `14.26.4` in `extensions/discord/package.json`.
2. Regenerate `package-lock.json` in the Discord extension workspace.
3. Build and push a patched Docker image for `labs` first; validate Discord DM reception during the 24-hour soak.
4. Promote to `admins` and `ovk` per ADR-0001 rollout order.

### Verification method
```bash
# From within the openclaw 2026.4.29 Docker image or source tree:
npm ls discord.js 2>/dev/null | grep discord.js
# Expected: discord.js@14.26.4 or higher
```

## Alternatives

1. **Defer entirely to the 2026.4.29 upgrade**: Accept that DMs may be silently dropped in the post-restart window until the upgrade is complete. Viable if the upgrade timeline is short and the impact is low. Retained as Branch A above.

2. **Backport the `MessageCreateAction` fix directly**: Cherry-pick the specific commit from the discord.js upstream into a local fork. Rejected — maintaining a discord.js fork adds permanent maintenance burden; a version bump is strictly simpler.

3. **Implement an application-level DM retry**: Add a layer in the openclaw Discord extension that re-fetches missed DMs from the Discord REST API after the gateway `READY` event. Rejected — this duplicates logic that discord.js 14.26.4 already provides natively and adds complexity to the extension.

## Platform impact

- **Migrations**: None. discord.js v14.26.4 is a patch release with no breaking changes.
- **Backward compatibility**: Fully compatible. The fix is additive (fetches the channel object when missing); existing behavior for cached channels is unchanged.
- **Resource impact for `labs`**: Negligible. discord.js v14.26.4 introduces no new dependencies. The additional channel-fetch call in the cold-start window is a one-time REST API call per DM; it has no steady-state memory impact.
- **Risks and mitigations**:
  - *Risk*: Branch B requires a separate Docker image build and rollout outside the main 2026.4.29 upgrade track, adding rollout complexity. *Mitigation*: Only pursue Branch B if the upstream 2026.4.29 bundle inspection confirms the fix is missing; the verification task in this proposal gates the decision.
  - *Risk*: The additional channel-fetch in the DM handler adds a Discord API call that could hit rate limits under high DM volume. *Mitigation*: The fix only applies when the channel is uncached (cold-start scenario); steady-state DM handling is unchanged and rate-limit risk is negligible.
