# Tasks: channel-lib-updates

- [ ] 1. **Identify current pinned versions of discord.js and @slack/socket-mode** — Check `package.json` (workspace root and/or `extensions/discord/`, `extensions/slack/`) to record the exact versions currently in use. — DoD: current versions documented in the PR description; diff against target versions (discord.js 14.26.4, @slack/socket-mode 2.0.7) is clear.

- [ ] 2. **Bump discord.js to 14.26.4 in package.json** (depends on 1) — Update the `discord.js` version constraint to `^14.26.4` (or `~14.26.4`). Run `npm install` to update `package-lock.json`. — DoD: `package-lock.json` records discord.js 14.26.4; no unrelated dependency version changes.

- [ ] 3. **Bump @slack/socket-mode to 2.0.7 in package.json** (depends on 1) — Update `@slack/socket-mode` to `^2.0.7`. Run `npm install` to update `package-lock.json`. — DoD: `package-lock.json` records @slack/socket-mode 2.0.7; no unrelated dependency version changes.

- [ ] 4. **Run full TypeScript type-check and build** (depends on 2, 3) — Execute `npm run build` (or equivalent) across the workspace to confirm no type errors introduced by the new library versions. — DoD: build exits with code 0; zero new TypeScript errors.

- [ ] 5. **Build and push Docker image** (depends on 4) — Build the Docker image with the updated dependencies; push to the registry; record the new image digest. — DoD: image with new digest is available in registry; digest recorded in the PR.

- [ ] 6. **Deploy to `labs` and validate Discord DM delivery** (depends on 5) — Deploy the new image to `labs`. Send a DM from a Discord account that has not previously messaged the bot (to ensure DMChannel is not cached). — DoD: DM is received and handled by the bot within 10 seconds; no errors in openclaw logs.

- [ ] 7. **Validate Slack reconnect on `labs`** (depends on 6) — Temporarily revoke and restore the Slack app token for the `labs` instance to trigger a reconnect. — DoD: reconnect completes within 10 seconds; no zombie connections visible in `kubectl exec` / `ss` output; no "pong wasn't received" in logs.

- [ ] 8. **Measure memory baseline on `labs`** (depends on 6) — Run `kubectl top pod -n labs` before and after image deploy. — DoD: memory delta < 20 MB; value recorded in PR. If delta ≥ 20 MB, **stop and escalate**.

- [ ] 9. **Promote to `admins`** (depends on 7, 8) — Deploy the same image to `admins`; repeat Discord DM and Slack reconnect smoke tests. — DoD: both smoke tests pass on `admins`.

- [ ] 10. **Promote to `ovk`** (depends on 9) — Deploy to `ovk` in a low-traffic window. — DoD: Discord DM delivery confirmed; Slack reconnect clean; no production error spike in the 1 h post-deploy window.

## Tests

- [ ] T1. Discord DM test (all tenants): send a DM from an account with no cached DMChannel; confirm delivery.
- [ ] T2. Slack reconnect test (labs only): force WebSocket close; confirm reconnect < 10 s.
- [ ] T3. Memory check (labs): `kubectl top pod` delta < 20 MB.
- [ ] T4. Regression check: confirm existing group/channel messages on Discord and Slack continue to flow normally after the update (not just DMs).

## Rollback

1. In mctl-gitops, revert the `image.tag` (or Docker digest) to the previous build.
2. Open a PR, merge, let ArgoCD sync.
3. Alternatively, revert `package.json` and `package-lock.json` to the previous library versions, rebuild the image, and redeploy.
4. No S3 state changes; no schema migrations; rollback is safe at any point.
