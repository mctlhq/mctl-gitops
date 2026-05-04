# Design: channel-lib-updates

## Current state

The mctl-openclaw workspace uses `discord.js` and `@slack/socket-mode` (part of `node-slack-sdk`) as channel client libraries, imported by the Discord and Slack extensions respectively. Current pinned versions are not specified in `context/` but are prior to the releases described below. The libraries are declared in the relevant `extensions/discord/package.json` and `extensions/slack/package.json` (or workspace root), and bundled into the Docker image at build time.

Both libraries have received point releases that fix silent regressions:
- `discord.js` 14.26.4 (2026-05-01): restores DM delivery in uncached DMChannels.
- `@slack/socket-mode` 2.0.7 (2025-04-30 on the npm registry): force-terminates stale WebSocket connections.

## Proposed solution

### Dependency bump procedure

1. Update `package.json` (workspace root or per-extension) to pin:
   - `"discord.js": "^14.26.4"` (or `"~14.26.4"` for maximum conservatism)
   - `"@slack/socket-mode": "^2.0.7"`
2. Run `npm install` (or `npm ci` in the build pipeline) to update `package-lock.json`.
3. Build the Docker image and push to the registry.
4. Deploy to `labs` first; validate Discord DM delivery and Slack reconnect behaviour under normal load.
5. Promote to `admins`, then `ovk` via the standard pipeline.

### Validation checklist (labs)

- Send a DM to the Discord bot from an account that has not recently messaged it (to ensure the DMChannel is not cached). Confirm message is received.
- Disconnect the Slack socket-mode WebSocket on the server side (e.g., temporarily revoke and restore the Slack app token). Confirm reconnect completes within 10 seconds and no zombie connections appear in `kubectl exec` network stats.
- Monitor `kubectl top pod` before and after to confirm no memory regression.

### No shared-skill changes

Neither fix touches Layer 2 (YAML skills) or Layer 3 (remote skills). The change is entirely in the Node.js dependency tree and the compiled extension code. No cross-tenant skill synchronisation is required.

## Alternatives

### A. Upgrade discord.js to v15+
v15 introduces breaking changes to the interaction handler API. **Rejected for this proposal** — requires extension code updates and cross-tenant regression testing; separate proposal when upstream extension support is confirmed.

### B. Replace @slack/socket-mode with direct WebSocket library
More control, less abstraction. **Rejected** — increases maintenance burden with no functional gain over a patch release.

### C. Do nothing and wait for openclaw upstream to bump these deps
openclaw 2026.5.2 may already bundle updated libs. **Rejected** — 2026.5.2 has known regressions and its dependency tree is not confirmed to include these specific versions; meanwhile `ovk` silently drops Discord DMs.

## Platform impact

| Dimension | Impact |
|---|---|
| **Migrations** | None — no API surface changes in either library |
| **Backward compatibility** | Full — same event names, same handler signatures |
| **Resource impact (labs)** | Expected zero memory delta (point releases with no new feature deps) |
| **Channel routing** | Unchanged — allowlists, pairing, onboarding flows unaffected |
| **Rollback** | Re-pin previous versions in `package.json`, rebuild image, re-deploy |
| **Risk** | LOW — point releases with a single fix each; no major version change |
