# Design: discord-js-dm-fix-v2

## Current state

Per `context/architecture.md`, the mctl-openclaw Discord channel is implemented
as a workspace extension (`extensions/discord/`) that depends on `discord.js`.
The exact version currently pinned in the workspace `package.json` and lockfile
must be verified by inspection (run `npm ls discord.js` in the repository or
inside a running pod); it is expected to be v14.26.3 or earlier. All three
tenants (`labs`, `admins`, `ovk`) build from the same source tree and ship the
same Discord extension image.

The discord.js `MessageCreateAction` internal handler processes `MESSAGE_CREATE`
gateway events received from Discord. In versions prior to v14.26.4, when the
handler resolves the target channel it consults the internal channel cache
exclusively. If the channel is absent — which is the expected state during the
cold-start window after every pod restart, and after any gateway reconnection —
the handler exits without emitting the `messageCreate` event to application
code. No error is thrown; no log is written; the DM is permanently lost. There
is no retry path at the application level.

Because mctl-openclaw pods restart on every image rollout (and on node eviction
or OOM kill), the cold-start exposure window is present on every deployment
cycle across every tenant.

## Proposed solution

Bump `discord.js` from its current version to `14.26.4` in the Discord
extension workspace manifest, regenerate the lockfile, build a new image, and
roll it out tenant by tenant in the standard `labs` → `admins` → `ovk` order
(ADR-0001).

Concrete steps:

1. In `extensions/discord/package.json`, change the `discord.js` version
   constraint to `"14.26.4"` (exact pin).
2. From within `extensions/discord/`, run `npm install` in a clean environment
   to regenerate `package-lock.json` with the new resolution. Confirm
   `npm ls discord.js` shows only `discord.js@14.26.4` (no duplicate entries).
3. Build the Docker image from the updated source tree and tag it with the
   patch-level version identifier.
4. Roll out to `labs` following the ADR-0001 / ADR-0002 procedure. Validate
   with the DM-in-uncached-channel test (test T1) before promoting.
5. Promote to `admins` after a successful `labs` soak.
6. Promote to `ovk` after `admins` verification passes.

No changes to the three-layer skills YAML, no changes to the S3 state schema,
and no changes to the Kubernetes manifests beyond the image tag.

### Why this approach

The fix is a single patch-release version bump with no API surface changes and
no new runtime dependencies. Bumping the version in `package.json` and
regenerating the lockfile is the standard, lowest-risk mechanism to take a
dependency patch. No fork, no cherry-pick, and no application-level workaround
are necessary.

## Alternatives

**A. Cherry-pick upstream discord.js PR #11495 into a local discord.js fork.**
Rejected. Maintaining a fork of a large library for a single fix introduces
permanent maintenance overhead — the fork must be kept in sync with future
discord.js patch and security releases. The patch has already been cut as a
stable release (v14.26.4), so there is no basis for a fork.

**B. Implement an application-level channel-fetch workaround in the Discord
extension.**
Rejected. This approach would intercept every `messageCreate` event, check
whether the channel was uncached, and issue an explicit `client.channels.fetch`
call before re-emitting. It duplicates the logic that v14.26.4 provides
natively, adds complexity to the extension code, and becomes dead weight the
moment discord.js is upgraded. The upstream fix is strictly simpler and safer.

**C. Stay on the current version and accept the silent DM-drop behaviour.**
Rejected. Silent message loss is a correctness regression that affects real
users on every pod restart. The `ovk` SLA is materially impacted. The cost of
the fix (a version bump) is minimal relative to the user-experience impact of
inaction.

## Platform impact

### Migrations

None. discord.js v14.26.4 is a patch release. There are no changes to the
API surface consumed by the openclaw Discord extension, no new configuration
keys, and no schema changes.

### Backward compatibility

Fully compatible. The fix is additive: it adds a channel-fetch code path for
the previously unhandled cache-miss case. All existing behaviour for cached
channels remains unchanged. No extension code beyond `package.json` and
`package-lock.json` requires modification.

### Resource impact (especially for `labs`)

Negligible. discord.js v14.26.4 introduces no new npm dependencies. The
additional Discord REST API call that the uncached-channel fix introduces is a
one-time per-DM call that only fires during the cold-start window; it has no
steady-state memory or CPU impact. The `labs` tenant is close to its memory
limit; this change is assessed as **zero risk** for `labs` — it is a bug fix
with no new allocations in the steady-state path.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Unexpected discord.js v14.26.4 regression in gateway event handling | Roll out to `labs` first with a 24-hour soak; gating tests T1, T2, and T3 must all pass before promoting to `admins`. |
| Duplicate discord.js version resolution in the workspace | Verify `npm ls discord.js` output during the lockfile regeneration step (task 3); confirm a single version is resolved. |
| Discord API rate limits triggered by channel-fetch calls during high-volume cold-start | The fetch is bounded by the number of unique uncached DM senders during the cold-start window; monitor for HTTP 429 responses in `labs` logs during the soak period. |
| `labs` memory regression | T4 (memory baseline test) records pod RSS before and after the bump; a delta above 5 MB triggers a halt and investigation. |
