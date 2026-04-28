# Track and cherry-pick upstream fix for Gateway/UI responsiveness regression (#73836)

## Context

On 2026-04-28, upstream openclaw filed bug #73836 reporting a Control UI/Gateway
responsiveness regression. Observed symptoms include UI reconnect stalls, Telegram
typing-indicator gaps, excessive heartbeat poll noise, and media mirror UX
degradation. Telegram is an active channel in all three mctl-openclaw tenants
(`ovk`, `labs`, `admins`), making this regression directly relevant to production.

The heartbeat poll noise introduced by #73836 poses a secondary risk that is
critical in the mctl-openclaw context: excessive poll events can cause the s3-sync
canary (ADR-0002) to skip cycles during normal operation, not just during rollouts.
ADR-0002 explicitly identifies "canary skips cycles during rollout" as a known
footgun and warns that false canary positives erode alert trust. If operators start
dismissing canary alerts as noise, a real S3-sync failure (which would cause silent
auth loss on pod restart) could be missed. This makes #73836 a platform-integrity
issue beyond a UX inconvenience.

Because the upstream fix has not yet been released as of 2026-04-28, this proposal
covers tracking the fix in our fork and cherry-picking it as soon as it is available
upstream, rather than waiting for the next full openclaw release.

## User stories

- AS a platform operator I WANT the upstream #73836 fix tracked in our fork SO THAT
  we can cherry-pick it as soon as it is available without waiting for a full
  upstream release cycle.
- AS an SRE I WANT the excessive heartbeat poll noise eliminated SO THAT s3-sync
  canary alerts remain meaningful and real S3-sync failures are not masked.
- AS a Telegram user on any tenant I WANT the typing-indicator gaps and reconnect
  stalls resolved SO THAT message delivery is perceived as reliable.

## Acceptance criteria (EARS)

- WHEN the upstream openclaw repository publishes a commit or PR that fixes bug
  #73836 THE SYSTEM SHALL record the commit SHA and the associated upstream
  PR/branch in the tracking issue within one business day.
- WHEN the upstream #73836 fix commit is available THEN THE SYSTEM SHALL cherry-pick
  it onto the mctl-openclaw fork branch and verify it applies cleanly.
- WHEN the cherry-picked fix is applied to the fork THE SYSTEM SHALL pass CI
  (unit tests, extension compatibility checks) before any tenant deployment.
- WHEN the cherry-picked fix is deployed to `labs` THE SYSTEM SHALL show a
  measurable reduction in heartbeat poll event frequency as observed in pod logs
  compared to the baseline taken before the fix.
- WHILE the cherry-picked fix is running in `labs` THE SYSTEM SHALL NOT trigger
  any s3-sync canary false-positive alerts attributable to heartbeat poll noise.
- IF the upstream #73836 fix is included in the next full openclaw release before
  we cherry-pick it THEN THE SYSTEM SHALL validate that the release-bundled fix
  covers the regression and close this proposal in favour of the standard upgrade
  path.
- IF the cherry-pick produces merge conflicts with our fork's local patches THEN
  THE SYSTEM SHALL resolve them and document the resolution in the PR before merging.

## Out of scope

- Changes to the s3-sync canary thresholds or alert rules (the fix must address the
  noise at the source; masking it via threshold changes is explicitly not acceptable
  per ADR-0002).
- Upgrading the full openclaw version (that is handled by `upgrade-to-2026-4-26`).
- Changes to Telegram channel configuration or YAML skills.
- UI redesign or feature additions to the Control UI beyond what the upstream
  #73836 fix covers.
- Memory or CPU tuning.
