# Design: wrangler-4-88-upgrade

## Current state
The `cloudflare-worker/` directory contains a self-contained `package.json` that pins a specific
wrangler version used by both local development (`wrangler dev`) and the GitHub Actions `deploy.yml`
workflow. Per `context/architecture.md`, this is the only mctl service that ships its own CI
pipeline rather than delegating to mctl-gitops. The architecture document lists `cloudflare/workers-sdk`
as a tracked dependency. Based on the preceding proposal (`wrangler-4-87-upgrade`), the most recently
proposed pinned version is 4.87.0.

The `secrets` configuration block in `wrangler.toml` has until now been treated as experimental by
the wrangler toolchain. This means misconfigured entries (wrong key name, extra whitespace, invalid
binding type) could fail silently or produce non-deterministic binding behaviour at deploy time,
leaving a Worker that runs without the expected secret available to the handler — a potential data
exposure risk for endpoints such as `/api/submit` (uses `BACKSTAGE_LANDING_TOKEN`) and `/api/contact`
(uses `RESEND_API_KEY` and `TELEGRAM_BOT_TOKEN`).

## Proposed solution
Update the `wrangler` version specifier in `cloudflare-worker/package.json` to exactly `4.88.0`
(exact pin, consistent with the pinning strategy adopted by all previous wrangler proposals). Run
`npm install` inside `cloudflare-worker/` and commit both `package.json` and `package-lock.json`.

**Why this change matters beyond a routine version bump:**
The stabilization of the `secrets` config property means wrangler 4.88.0 now validates `secrets`
block entries during `wrangler deploy` and surfaces misconfiguration as a hard error rather than
silently proceeding. For mctl-web, with seven production secrets bound to four API endpoints, this
deterministic validation at deploy time is a meaningful security improvement: a misconfigured secret
binding will never reach production undetected.

No changes to `wrangler.toml` are required unless a validation error is surfaced during the first
deployment attempt with 4.88.0 — if that happens, it indicates a latent misconfiguration that must
be fixed before promotion to production.

**Why exact pin rather than `^` range:**
A supply-chain compromise in any wrangler release would have direct write access to production
Cloudflare Pages via the CI runner. Exact pins ensure the version deployed in CI is the version
audited, consistent with the policy established by `wrangler-upgrade-security` and reinforced by
all subsequent wrangler proposals.

## Alternatives

### A — Stay at wrangler 4.87.0 and skip 4.88.0
Rejected. The stabilization of the `secrets` API is a security-relevant change. Skipping it leaves
the project on an older tool that treats the secrets block as experimental, meaning misconfigurations
may not be surfaced at deploy time. The effort to upgrade is low (pin bump + lock file regeneration)
and does not justify accumulating the version gap.

### B — Use a floating `^4.x` range to receive upgrades automatically
Rejected. Established project policy is exact pins for the Worker deploy tool. A floating range
would break the auditability guarantee and could introduce unreviewed changes into production
deployments.

### C — Refactor wrangler.toml to remove the secrets block and rely solely on the Cloudflare
Dashboard for secret management
Rejected for this proposal. Removing the `secrets` block from `wrangler.toml` is a separate
architectural decision and would require auditing how wrangler resolves secrets at deploy time. The
stabilized API makes the current approach safer without requiring a structural refactor. A dedicated
proposal can address secrets-management strategy independently.

## Platform impact

**Migrations:** No migration is required. wrangler 4.88.0 is backward-compatible with the existing
`wrangler.toml`, Worker source code, and Cloudflare account configuration. The stabilized `secrets`
API is backward-compatible with the existing secrets block syntax; if any misconfiguration existed
under the experimental API it will surface as an error on first deploy — which is the desired
behaviour and must be resolved before merging.

**Backward compatibility:** Full for correctly configured secrets. The Worker's `/api/*` routes,
rate-limit configuration, and secret binding names remain unchanged. A pre-deploy validation step
(Task 4) is included to catch any latent `wrangler.toml` issues before they surface in CI.

**Resource impact:** Zero runtime or Kubernetes impact. wrangler is a CI-only tool; it is not
installed in any pod, and the Cloudflare Worker runs on Cloudflare infrastructure, not on the
Kubernetes cluster. There is no memory pressure on the `labs` tenant.

**Risks and mitigations:**
- *Risk:* The stabilized `secrets` validator rejects an existing entry in `wrangler.toml` that the
  experimental parser previously accepted silently, causing the first CI deployment to fail.
  *Mitigation:* Task 4 mandates running `wrangler deploy --dry-run` (or equivalent validation flag)
  against a preview environment before targeting production; any validation error is fixed in the
  same PR before merging.
- *Risk:* wrangler 4.88.0 introduces a breaking change in CLI output format that breaks a CI step
  parsing deploy logs. *Mitigation:* Review CI log output in a test deployment; compare with
  expected log format from the 4.87.0 run.
- *Risk:* Local developer environments have a globally installed wrangler at a different version,
  causing discrepancies between local and CI behaviour. *Mitigation:* Developers must invoke
  `npx wrangler` from within `cloudflare-worker/` to use the locally pinned version; this is
  documented in the commit message and optionally enforced via an `.npmrc` `engine-strict` setting.
- *Risk:* The `wrangler-4-87-upgrade` proposal has not yet been merged, meaning the effective
  baseline may be older than 4.87.0. *Mitigation:* Task 1 confirms the actual installed version
  before applying the bump; if the baseline is below 4.87.0 the upgrade from baseline to 4.88.0
  still applies cleanly and the increment is still safe.
