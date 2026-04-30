# Design: slack-socket-mode-update

## Current state
The mctl-openclaw platform (described in `context/architecture.md`) runs the Slack channel via `@slack/socket-mode` from the `slackapi/node-slack-sdk` project. The currently installed version (pre-2.0.7) does not terminate stale closing WebSocket connections promptly when a normal close handshake fails. This manifests as repeated warning log entries across all three tenants and elevated reconnection latency on the Slack channel. The issue is visible in live logs but does not cause data loss or auth state corruption. All three tenants run the same version because Slack is a built-in channel shipped with openclaw (not a per-tenant extension).

## Proposed solution
Bump `@slack/socket-mode` to `2.0.7` in `package.json`, regenerate `package-lock.json`, rebuild the Docker image, and roll out to each tenant in ADR-0001 order (`labs` → `admins` → `ovk`) with ADR-0002 canary and probe guards at each step.

This is deliberately the simplest possible change: a single patch-level dependency bump with no code changes in the mctl-openclaw fork. The change is isolated to the Slack channel adapter; no other channels, skills, or S3 state handling are affected.

**Rollout procedure (per tenant):**
1. Suspend s3-sync canary.
2. ArgoCD applies the new image.
3. Restore-state probe must pass.
4. Resume s3-sync canary.
5. Observe Slack channel logs for absence of stale-connection warnings and confirm reconnection behaviour.

Because this is a patch-level bump with no API changes, no migration steps and no skill or routing changes are needed.

## Alternatives

**A. Ignore the warning logs and defer the update.** The current behaviour is not causing functional failures — only log noise and latency spikes. However, deferring accumulates technical debt, the fix is low-effort, and the warning noise can mask genuinely important log entries. Dropped.

**B. Pin `@slack/socket-mode` to a specific older version and write a local patch for the stale-connection fix.** Introduces fork maintenance overhead for a fix that is already available upstream as a clean patch release. Higher effort, lower reliability than taking the upstream release. Dropped.

**C. Replace `@slack/socket-mode` with a direct WebSocket implementation.** Eliminates the library dependency entirely but requires significant custom implementation, testing, and maintenance. Massively disproportionate to the problem. Dropped.

## Platform impact

**Migrations.** None. This is a patch-level library bump. No database changes, no S3 schema changes, no Kubernetes manifest changes.

**Backward compatibility.** `@slack/socket-mode@2.0.7` is a patch release; the public API is unchanged. No call sites in mctl-openclaw's Slack channel extension require modification.

**Resource impact — `labs`.** No memory or CPU increase is expected from a patch-level WebSocket library bump. Risk for `labs`: NONE. Memory should be verified post-deploy on `labs` as a sanity check (standard post-rollout observation), but no pre-emptive flag is raised.

**Risks and mitigations.**
- Risk: The 2.0.7 patch introduces an unintended regression in reconnection logic that causes the Slack channel to disconnect more frequently. Mitigation: observe Slack channel health on `labs` for at least several hours before promoting to `admins`. ArgoCD rollback restores the previous image within minutes if needed.
- Risk: The `package-lock.json` update inadvertently pulls in a transitive dependency upgrade alongside `@slack/socket-mode`. Mitigation: review the `package-lock.json` diff in the PR to confirm no unexpected transitive changes.
- Risk: Canary false alert during the brief rollout window. Mitigation: canary is suspended before rollout per ADR-0002 procedure.
