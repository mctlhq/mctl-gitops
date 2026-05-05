# Design: automated-dep-updates

## Current state
Dependency tracking for mctl-web is performed manually by the researcher agent, which runs
once per day and fetches GitHub release pages for the nine tracked libraries. This approach
has two structural gaps:

1. **Frequency**: workerd released v1.20260505.1 within 24 hours of v1.20260504.1; between
   cycles, any crash fix or security patch in a dependency is invisible.
2. **Coverage**: the researcher only tracks nine pre-listed libraries. Transitive dependencies
   (e.g. miniflare, esbuild bundled with wrangler) and devDependencies outside the list are
   not monitored.

mctl-web is the only service that owns its deployment pipeline in-repo (`deploy.yml` in this
repo, not in mctl-gitops — see `context/architecture.md`). This independence makes it feasible
to adopt Renovate without cross-service coordination.

## Proposed solution
**Install Renovate Bot via the GitHub App on the mctl-web repository (or equivalent
organisation-level installation for `mctlhq`) and add a `renovate.json` configuration.**

### Configuration strategy (`renovate.json`)
```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:base"],
  "packageRules": [
    {
      "matchUpdateTypes": ["patch", "minor"],
      "groupName": "weekly-dep-refresh",
      "schedule": ["every weekend"],
      "automerge": false
    },
    {
      "matchUpdateTypes": ["major"],
      "labels": ["major-upgrade"],
      "automerge": false
    },
    {
      "matchPackageNames": ["wrangler", "workerd"],
      "groupName": "cloudflare-runtime",
      "schedule": ["at any time"],
      "labels": ["cloudflare", "security-sensitive"],
      "automerge": false
    }
  ],
  "vulnerabilityAlerts": {
    "labels": ["security"],
    "schedule": ["at any time"]
  }
}
```

Key decisions:
- **Cloudflare runtime group (wrangler + workerd)** updates immediately (no schedule gate)
  because of their rapid, security-sensitive release cadence.
- **Security alerts** (vulnerability advisories) are also ungated — PRs open within hours.
- **All other updates** are batched into a weekly weekend PR to reduce review noise.
- **No automerge** — every PR requires human approval before merging into main.

### Interaction with `deploy.yml`
Renovate PRs target the main branch. The existing `deploy.yml` triggers on push to main;
Renovate PRs will go through normal PR review + merge, which triggers the deploy workflow
as expected.

### Interaction with the researcher agent
The researcher continues to run daily and monitors CVEs + mctl MCP metrics — signals that
Renovate cannot surface. Renovate complements the researcher by covering version enumeration
automatically, freeing the researcher to focus on CVE severity analysis, runtime metrics,
and architectural signals.

## Alternatives

**A. Dependabot**
GitHub's native Dependabot is simpler to set up (no App installation, just a YAML file in
`.github/dependabot.yml`). However, it does not support custom grouping of patch/minor bumps
into a single weekly PR, lacks the Cloudflare-specific scheduling rule, and its vulnerability
alerts are less configurable. Renovate is preferred for its grouping and scheduling power.

**B. Continue manual researcher tracking**
Proven insufficient: workerd's daily release cadence and the 48-hour lag on CVE-2026-0933
demonstrate the structural limits of once-per-day manual tracking. Rejected.

**C. GitHub Actions cron job**
A custom Actions workflow could check npm for new versions and open PRs via the GitHub API.
This is undifferentiated infrastructure work that would need to be maintained. Renovate is
a battle-tested open-source tool that solves this problem at a fraction of the engineering
cost. Rejected.

## Platform impact
- **Migrations:** Add `renovate.json` to the repo root; install Renovate GitHub App on
  `mctlhq` organisation (or just on this repository).
- **Backward compatibility:** Fully additive — no existing code changes. Renovate only opens
  PRs; it does not merge autonomously.
- **Resource impact:** Renovate runs on Renovate's own infrastructure (free tier covers
  public and private repos). Zero CPU/memory impact on the Kubernetes cluster. No risk for
  the `labs` tenant.
- **Risks:** PR volume may increase initially as Renovate catches up on all stale deps.
  Mitigate by scheduling a one-time "catch-up" group PR manually before enabling Renovate.
- **Rollback:** Disable the Renovate GitHub App on the repository. All open Renovate PRs
  can be closed; no changes are deployed unless explicitly merged.
