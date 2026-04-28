# Design: gateway-ui-responsiveness-fix

## Current state

All three tenants run openclaw 2026.3.14 (being upgraded to 2026.4.26 in parallel
via `upgrade-to-2026-4-26`). Upstream bug #73836 was filed on 2026-04-28; the fix
has not yet been released. The regression causes:
- Control UI reconnect stalls and media mirror UX degradation
- Telegram typing-indicator gaps (Telegram is active on all three tenants)
- Excessive heartbeat poll events in pod logs

The excessive heartbeat poll noise is the most operationally dangerous symptom. The
s3-sync canary (ADR-0002) runs as an Argo CronWorkflow that checks for fresh S3
timestamps at a fixed interval. If openclaw's heartbeat polling generates enough
I/O or scheduling pressure to cause missed canary cycles, the canary fires a false
alert. ADR-0002 records that false canary positives erode alert trust, and that
"canary skips cycles during rollout" is a recurring footgun. A steady-state version
of the same failure mode — heartbeat noise causing skipped cycles outside of
rollouts — is equally harmful because operators may begin treating canary alerts
as unreliable noise, masking real S3-sync failures.

The mctl-openclaw repository is a fork of `github.com/openclaw/openclaw`
(see `context/architecture.md`). Fork-tracking is an explicit responsibility of
this service.

## Proposed solution

**Monitor the upstream #73836 issue/PR; cherry-pick the fix commit onto the
mctl-openclaw fork as soon as it lands; deploy through the standard
`labs` → `admins` → `ovk` rollout order (ADR-0001).**

Workflow:
1. Open a tracking issue in the mctl-openclaw issue tracker that links to
   upstream #73836. Assign it to the engineer responsible for fork-tracking.
2. Subscribe to upstream #73836 for notifications. Check daily until the fix
   is merged upstream.
3. Once the upstream fix commit SHA is known, fetch it into the fork:
   ```
   git fetch upstream
   git cherry-pick <fix-sha>
   ```
4. If the cherry-pick applies cleanly, push to a feature branch and open a PR.
   If there are conflicts (likely near Gateway or heartbeat-related code), resolve
   them and document the resolution in the PR body.
5. CI runs the full test suite and extension compatibility checks against the
   cherry-picked branch.
6. On CI green: deploy to `labs` with standard canary/probe procedure (ADR-0002).
   Record heartbeat poll frequency from pod logs before and after.
7. Observe `labs` for heartbeat noise reduction and absence of false canary alerts
   (minimum 24 h observation window).
8. Promote to `admins`, then `ovk`, following ADR-0001 order.

Why cherry-pick rather than waiting for the next full release:
- The s3-sync canary integrity risk is active now. Waiting for a full release could
  mean weeks of degraded alert reliability, during which a real S3-sync failure
  could be dismissed as heartbeat noise.
- The `upgrade-to-2026-4-26` proposal is already in flight; cherry-picking a
  targeted fix onto the 2026.4.26 base minimises the diff while addressing the
  specific regression.
- Cherry-picking a single focused fix is lower risk than a full upgrade increment
  and can be performed independently of the broader upgrade timeline.

Why not raise the canary threshold instead:
- ADR-0002 explicitly says "Disabling the canary 'because it's noisy' — the cause
  of the noise must be fixed." Raising the threshold is the threshold-equivalent
  of disabling: it masks the symptom instead of fixing the source.

## Alternatives

**Option A — Wait for the fix to appear in the next full openclaw release and
include it in the next upgrade cycle.**
Rejected as primary path: the canary integrity risk is active; we cannot guarantee
the next release arrives before a real S3-sync incident. The cherry-pick approach
resolves the risk sooner while the full upgrade proceeds in parallel.

**Option B — Increase the s3-sync canary alert threshold to tolerate missed cycles.**
Rejected: explicitly forbidden by ADR-0002 ("Disabling the canary 'because it's
noisy' — the cause of the noise must be fixed"). This approach would permanently
lower the sensitivity of our primary S3-sync alarm.

**Option C — Disable the Telegram channel on affected tenants until the fix
lands.**
Rejected: Telegram is a production channel on all three tenants, including `ovk`
with a high SLA. Disabling it causes customer-facing downtime, which is a worse
outcome than the UX regression.

## Platform impact

**Migrations**
- None. A regression fix for heartbeat/UI responsiveness does not change state
  formats, S3 schemas, or skill definitions.

**Backward compatibility**
- The cherry-picked commit is expected to be a targeted fix touching Gateway/UI
  and heartbeat polling code only. No API surface changes are anticipated.
- If the upstream fix changes any extension API, the CI extension compatibility
  check will catch it.

**Resource impact — `labs`**
- Fixing a poll frequency regression is expected to reduce CPU/memory pressure
  slightly, not increase it. No risk to the `labs` memory limit.
- CPU usage in `labs` may marginally decrease once excessive heartbeat poll events
  are eliminated.

**Risks and mitigations**

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Cherry-pick conflicts with local fork patches | Medium | Resolve and document in PR; CI must pass before merge |
| Upstream fix introduces a secondary regression | Low | `labs` observation window with canary monitoring catches it |
| Upstream never publishes the fix (issue stalls) | Low | Re-evaluate after 2 weeks; escalate or implement a local workaround patch if upstream is unresponsive |
| Fix lands as part of a larger upstream release before we cherry-pick | Low | Validate that the release-bundled fix covers #73836 and fold into the standard upgrade; close this proposal |
| Heartbeat noise continues after cherry-pick (fix incomplete) | Low | Compare pod-log poll frequency before/after; if unchanged, report back to upstream with metrics |
