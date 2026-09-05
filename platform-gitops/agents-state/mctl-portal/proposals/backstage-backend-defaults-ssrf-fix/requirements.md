# Patch Backstage backend-defaults SSRF (CVE-2026-24048)

## Context
`@backstage/backend-defaults` ships `FetchUrlReader`, the utility several Backstage
backend features use to fetch remote content (TechDocs, scaffolder templates fetched
from external hosts, the `proxy` plugin, and the catalog's URL-based readers). A
security researcher disclosed CVE-2026-24048: `FetchUrlReader` follows HTTP redirects
without re-validating the redirect target against the `backend.reading.allow`
allowlist configured in `app-config.yaml`. An attacker who controls (or compromises)
an already-allowlisted host can respond with a redirect to an internal or otherwise
sensitive URL (e.g. cloud metadata endpoints, internal-only services), and
`mctl-portal`'s backend will fetch it — a classic SSRF bypass of an allowlist control.

mctl-portal's backend performs authenticated fetches against both external and
internal hosts (TechDocs sources, scaffolder template repos, the `proxy` plugin, and
`mctl-api`), so this is directly exploitable in our deployment if any allowlisted
host is compromised or misconfigured to redirect. The fix is a patch-level bump of
`@backstage/backend-defaults` to 0.12.2 / 0.13.2 / 0.14.1 / 0.15.0 (whichever matches
our current major/minor line), reachable from the Backstage 1.54.6 train we already
track. No API or behavior change for legitimate use is expected.

## User stories
- AS a platform security engineer I WANT the `backend.reading.allow` allowlist to be
  enforced on every hop of a redirect chain SO THAT an allowed host cannot be used as
  a pivot to reach internal or sensitive URLs.
- AS a mctl-portal maintainer I WANT this fixed via a patch-level dependency bump
  SO THAT we close the SSRF window without taking on a major-version migration risk.
- AS an on-call engineer I WANT confirmation that TechDocs, scaffolder, and the proxy
  plugin still work after the bump SO THAT the fix does not introduce a regression.

## Acceptance criteria (EARS)
- WHEN `@backstage/backend-defaults`'s `FetchUrlReader` receives an HTTP redirect
  response THE SYSTEM SHALL re-validate the redirect target URL against
  `backend.reading.allow` before following it.
- IF the redirect target is not present in `backend.reading.allow` THEN THE SYSTEM
  SHALL refuse to follow the redirect and SHALL return an error to the caller instead
  of fetching the redirected URL.
- WHEN the dependency bump is deployed THE SYSTEM SHALL continue to serve TechDocs
  pages, scaffolder template fetches, and `proxy` plugin requests for all currently
  allowlisted hosts without any configuration change required.
- WHILE the patched version is running THE SYSTEM SHALL report the upgraded
  `@backstage/backend-defaults` version in `yarn.lock` / `package.json` so the fix is
  auditable.
- IF the currently pinned Backstage backend packages are on a line that only receives
  the fix at 0.15.0 (i.e. requires moving within the same Backstage minor train)
  THEN THE SYSTEM SHALL be bumped to the minimum patched version for that line, not
  skipped.

## Out of scope
- Any Backstage major-version upgrade (per ADR 0001, "no major bump on release day" /
  community-plugins compat lag).
- Fixing CVE-2026-29185 (Backstage SCM URL parsing) — our tracked release train
  (1.54.x) is already past the affected versions (pre-1.20.1); no action needed.
- Rewriting or replacing the `proxy` plugin or TechDocs reader architecture.
- Changes to `backend.reading.allow` allowlist contents themselves (a config review
  of what hosts are allowlisted is a separate, follow-up concern).
