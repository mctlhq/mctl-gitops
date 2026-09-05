# Design: backstage-backend-defaults-ssrf-fix

## Current state
mctl-portal is a Backstage app (see `context/architecture.md`) running in tenant
`admins`, built with `backstage-cli`, on the current Backstage release train (1.54.x
per the researcher's latest scan, up from whatever was pinned in `package.json` /
`yarn.lock` at the time `context/current-version.md` was last updated, 2026-04-27,
service version 1.0.1). The backend uses `@backstage/backend-defaults`'s
`FetchUrlReader` transitively through:
- **TechDocs** — fetching docs source content from external/internal repos,
- **scaffolder** — fetching software templates from external hosts,
- **proxy** plugin — forwarding to external APIs,
- catalog's URL-based location readers.

All of these fetches are gated by the `backend.reading.allow` allowlist in
`app-config.yaml`. `FetchUrlReader` currently validates the *initial* request URL
against this allowlist but does not re-validate URLs reached via HTTP redirect,
which is the SSRF gap described in CVE-2026-24048.

## Proposed solution
Bump `@backstage/backend-defaults` (and, if yarn's dependency resolution requires it,
the surrounding `@backstage/backend-*` packages it is peer-dependent on) to the
minimum patched version for our line: 0.12.2, 0.13.2, 0.14.1, or 0.15.0. This is a
dependency version bump only — no custom plugin code we own calls into
`FetchUrlReader` directly, so no code changes are expected in `packages/backend` or
`plugins/*`. The fix is entirely inside the upstream package: it adds a
redirect-target re-check against `backend.reading.allow` before following each hop.

Rollout: bump the dependency in the yarn workspace root, run `yarn install`, run the
full backend test suite plus a manual smoke test of TechDocs rendering, scaffolder
template fetch, and one `proxy` plugin route against a real allowlisted external
host, then deploy through the standard mctl-gitops → ArgoCD pipeline to tenant
`admins`.

## Alternatives
- **Do nothing / accept the risk** — rejected. This is an SSRF with a plausible
  exploitation path in our topology (proxy plugin + TechDocs + scaffolder all fetch
  external URLs); leaving it unpatched conflicts with the operator's mandate to
  action security findings.
- **Write a custom `UrlReader` wrapper to re-validate redirects ourselves** —
  rejected. Duplicates logic upstream already ships correctly in the patched
  version; higher maintenance burden for us, and diverges from upstream behavior on
  the next Backstage upgrade.
- **Bump straight to Backstage 1.54.6 core packages (the "railroad" bundling all
  robustness fixes from 1.54.4-1.54.6)** instead of pinning `backend-defaults` in
  isolation — considered as a bonus, but this proposal scopes strictly to the
  security-relevant `backend-defaults` bump to keep the change small and reviewable;
  a separate/future proposal can pick up the other 1.54.x robustness fixes if
  desired. This is consistent with ADR 0001's guidance to avoid rushing broad
  Backstage version changes.

## Platform impact
- **Migrations:** none. Patch-level dependency bump, no schema or config migration.
- **Backward compatibility:** fully backward compatible. No `app-config.yaml` changes
  required; existing allowlist entries continue to work identically for
  non-redirecting requests. Only redirects to non-allowlisted targets are newly
  (and correctly) rejected — this is the intended security tightening, not a
  breaking change for legitimate traffic.
- **Resource impact (especially for `labs`):** not applicable — mctl-portal runs
  only in tenant `admins` (`context/current-version.md`); tenant `labs` does not run
  this service and is unaffected. Within `admins`, a patch-level dependency bump is
  not expected to measurably change CPU/memory footprint.
- **Risks and mitigations:**
  - *Risk:* transitive dependency resolution pulls in other `@backstage/backend-*`
    minor bumps and breaks a custom plugin. *Mitigation:* run full backend test
    suite + manual smoke test (TechDocs, scaffolder, proxy) before merging; roll out
    behind the standard ArgoCD sync gate.
  - *Risk:* a legitimate integration relies on redirect-following to a host not
    itself allowlisted (e.g. a CDN redirect). *Mitigation:* smoke-test all
    currently-configured `backend.reading.allow` entries post-bump; if a legitimate
    redirect target is found missing, add it to the allowlist explicitly rather than
    reverting the fix.
