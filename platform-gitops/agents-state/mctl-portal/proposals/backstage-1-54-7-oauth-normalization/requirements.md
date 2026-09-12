# Adopt Backstage v1.54.7 patch (OAuth profile normalization fix)

## Context
mctl-portal's entire SSO flow depends on Dex JWT/OAuth (`ops.mctl.me/api/dex`), with
Backstage's core auth backend handling profile normalization for every login. Backstage
v1.54.7 (11 Sep 2026) is a patch release that fixes OAuth profile normalization when
processing email-verification information — directly on our authentication code path.
Because this is a patch-level release within the currently-tracked 1.x line, it does not
trigger the "no major upgrade on release day" guardrail from ADR 0001, and no prior
proposal (`backstage-1-50-4-patch`, `backstage-v1-50-4-security-patch`,
`backstage-v1504-security-upgrade`, `backstage-catalog-security-patch`) has covered this
specific 1.54.x fix.

Leaving this unpatched risks incorrect handling of unverified/mismatched emails during
Dex login, which could affect identity resolution (catalog user entity mapping, RBAC
group mapping) for real users.

## User stories
- AS a platform operator I WANT mctl-portal to run a Backstage version with correct
  OAuth profile normalization SO THAT user identities from Dex are resolved consistently
  and RBAC/group mapping is not affected by stale or malformed profile data.
- AS an end user logging into the portal I WANT my email-verification state to be
  interpreted correctly by the SSO flow SO THAT I am not mismatched to another
  identity or blocked from access.

## Acceptance criteria (EARS)
- WHEN the Backstage dependency set is bumped to v1.54.7 or later THE SYSTEM SHALL
  continue to authenticate users via Dex JWT/OAuth without regression in login success
  rate.
- WHEN a user completes the Dex OAuth flow with an email-verification claim THE SYSTEM
  SHALL normalize the profile using the patched v1.54.7 logic before creating or
  matching the catalog user entity.
- WHILE the upgrade is being validated in a lower environment THE SYSTEM SHALL keep the
  currently-deployed 2.6.3 revision serving production traffic in `admins` until the
  patch is confirmed safe.
- IF any custom plugin (kubernetes, observability, scaffolder, techdocs) fails to build
  or fails smoke tests against v1.54.7 THEN THE SYSTEM SHALL block promotion to
  production and the failure SHALL be reported before rollout continues.
- IF the patch upgrade requires a Backstage major version bump as a side effect THEN
  THE SYSTEM SHALL be rejected and re-scoped as a separate, out-of-band proposal per
  ADR 0001.

## Out of scope
- Any Backstage major version upgrade (tracked separately, subject to the "wait ~a
  week for community-plugins compat" guardrail).
- Changes to the Dex identity provider configuration itself (ops.mctl.me/api/dex).
- Broader auth architecture changes (e.g., replacing Dex, changing session storage).
