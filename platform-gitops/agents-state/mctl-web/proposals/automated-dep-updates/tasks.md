# Tasks: automated-dep-updates

- [ ] 1. Install Renovate GitHub App on the `mctlhq` organisation (or just on the mctl-web
  repository) — DoD: the Renovate Bot account appears in the repository's "Installed GitHub
  Apps" settings; a Renovate onboarding PR is opened automatically by the app.

- [ ] 2. Author `renovate.json` at the repository root (depends on 1) — DoD: file committed
  with the configuration specified in `design.md` (base preset, cloudflare-runtime group
  with no schedule gate, weekly patch/minor group, vulnerability alerts ungated); Renovate
  linter (`renovate-config-validator`) passes with no errors.

- [ ] 3. Close the Renovate onboarding PR and merge `renovate.json` (depends on 2) — DoD:
  onboarding PR closed; custom `renovate.json` merged to main; Renovate picks up the new
  config within one scheduling cycle (≤ 1 hour).

- [ ] 4. Review and close or batch stale dependency PRs opened by Renovate during catch-up
  (depends on 3) — DoD: no more than one "catch-up" group PR remains open (covering all
  patch/minor deps that were behind at enable time); all security-labelled PRs reviewed
  within 24 hours.

- [ ] 5. Validate the cloudflare-runtime group fires on a new wrangler/workerd release
  (depends on 3) — DoD: when the next wrangler or workerd release publishes, Renovate opens
  a PR within 24 hours; PR is labelled `cloudflare` and `security-sensitive`.

- [ ] 6. Update `CLAUDE.md` researcher guidance to note Renovate handles version enumeration
  (depends on 5) — DoD: a sentence added to the researcher section noting that GitHub release
  polling for tracked libraries is now secondary to Renovate PRs; researcher focuses on CVEs
  and mctl metrics.

## Tests
- [ ] T1. Dry-run validation: run `renovate --dry-run` (or use the Renovate playground at
  app.renovatebot.com) against the repository config to confirm the grouping rules produce
  the expected PR buckets.
- [ ] T2. Vulnerability alert path: create a test branch with a known-vulnerable dep version
  (e.g. wrangler below 4.59.1) and confirm Renovate raises a PR labelled `security` within
  the ungated schedule window.
- [ ] T3. Major-bump label: confirm that a simulated major bump (e.g. hypothetical wrangler
  v5.0.0) generates a PR labelled `major-upgrade` and is NOT included in the weekly
  patch/minor group.

## Rollback
1. Disable the Renovate GitHub App on the repository via GitHub Settings → Installed Apps.
2. Close all open Renovate PRs (they make no code changes; closing them is safe).
3. Remove `renovate.json` from the repository root via a follow-up commit.
4. The researcher agent continues to operate as before; no other changes are needed.
