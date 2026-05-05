# Automated Dependency Updates via Renovate

## Context
The mctl-web dependency graph includes libraries with high-frequency release cadences:
workerd ships daily (v1.20260504.1 → v1.20260505.1 within 24 hours), wrangler ships weekly,
and Nuxt / Vue ship every few weeks. The current manual researcher cycle (once per day, human
triggered) structurally cannot guarantee security patches are caught within 24 hours of
release. CVE-2026-0933 (wrangler CVSS 7.7) had a patched version available days before it
appeared in the researcher's inbox.

Introducing Renovate Bot to the mctl-web repository would raise automated pull requests for
every version bump, keep the lockfile current, and reduce mean-time-to-patch from days to
hours. mctl-web is already the only service that manages its own deployment pipeline
(`deploy.yml` lives in this repo, not mctl-gitops), making it self-contained enough to adopt
Renovate independently without cross-tenant coordination.

## User stories
- AS a platform engineer I WANT dependency upgrade PRs raised automatically SO THAT I spend
  zero time manually tracking version numbers.
- AS a security-conscious operator I WANT critical patches to appear as PRs within hours of
  release SO THAT the exposure window for known CVEs is minimised.
- AS a developer I WANT Renovate to group minor/patch bumps into a single weekly PR
  SO THAT the review burden stays manageable.

## Acceptance criteria (EARS)
- WHEN a new version of any dependency listed in `package.json` (or `cloudflare-worker/package.json`)
  is published to npm, THE SYSTEM SHALL open a pull request against the main branch within 24 hours.
- WHEN the new version is a major bump (e.g. vue-router v4 → v5), THE SYSTEM SHALL open a
  separate labelled PR and NOT auto-merge it.
- WHEN multiple patch or minor bumps are available simultaneously, THE SYSTEM SHALL group them
  into a single "dep-refresh" PR unless a security advisory is attached, in which case
  THE SYSTEM SHALL open an individual PR labelled `security`.
- WHILE a Renovate PR is open, THE SYSTEM SHALL run the existing CI pipeline (build + type-check)
  on the PR branch and surface the result in the PR status checks.
- IF Renovate cannot resolve a dependency update due to a peer-conflict, THE SYSTEM SHALL
  comment on the PR with the conflict details rather than failing silently.
- WHEN a Renovate PR is merged to main, THE SYSTEM SHALL trigger the existing `deploy.yml`
  workflow exactly as for any other merge.

## Out of scope
- Replacing the researcher agent entirely; the researcher continues to monitor CVEs and
  mctl metrics that Renovate cannot surface.
- Configuring Renovate for other services in the mctl platform (out of mctl-web scope).
- Auto-merging PRs without human review (merge policy is out of scope for this proposal).
