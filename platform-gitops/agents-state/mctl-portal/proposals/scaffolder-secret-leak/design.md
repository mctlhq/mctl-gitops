# Design: scaffolder-secret-leak

## Current state
According to `context/architecture.md`, mctl-portal uses Backstage with the
`plugin-scaffolder-backend` plugin. The current package version sits in the range
3.1.0–3.1.4 (before the fix), vulnerable per CVE-2026-32237. The scaffolder dry-run
endpoint is available to authenticated users via Dex JWT SSO. Vault secrets are mounted
in the backend pod as environment variables and files via ExternalSecret — meaning that
at runtime `process.env` carries the Vault token, the Postgres DSN, and the GitHub App
credentials.

The problem is that during dry-run response serialization nested JSON objects do not pass
through recursive redaction: only top-level keys are masked, while values inside nested
structures are returned in clear.

## Proposed solution

### Package upgrade (single PR with CVE-2026-24046)

CVE-2026-32237 and CVE-2026-24046 are closed by the same release:
`plugin-scaffolder-backend` >= 3.1.1. Both CVEs are therefore closed in a single PR that
also bumps `@backstage/backend-defaults` to ^0.12.2 (the CVE-2026-24046 requirement).

Packages updated in the same PR:
```
@backstage/backend-defaults  ^0.12.2   (closes CVE-2026-24046)
plugin-scaffolder-backend    ^3.1.1    (closes CVE-2026-24046 + CVE-2026-32237)
```

The upstream fix in 3.1.1 implements a recursive redactor for the dry-run response: the
function walks the entire JSON graph of the response and replaces values matching a list of
known sensitive keys (`token`, `password`, `dsn`, `credentials`, `secret`, etc.) with the
marker `[REDACTED]`. Additionally — value-based filtering against patterns of known token
formats.

### Why a single PR, not two
- The same package (`plugin-scaffolder-backend`) closes both CVEs.
- Two separate PRs would mean two production deploys, two playwright runs, two ArgoCD
  syncs — for an identical `yarn.lock` change.
- An atomic patch reduces the risk of an unclosed window between deploys.

### Additional measure: Vault secret rotation
After deploying the patch it is recommended to rotate the secrets mounted in the backend
pod, in case the dry-run endpoint was exploited before the patch. This is outside the
scope of this PR but should be performed in parallel as an incident response action.

## Alternatives

**A. Add a custom middleware to filter dry-run responses**
Requires maintaining custom code that tracks the list of sensitive keys and patterns. The
upstream patch solves the task more reliably and without the maintenance burden. Rejected.

**B. Disable the dry-run endpoint entirely**
Dry-run is used by developers to debug templates. Disabling it degrades DX without need,
since the upstream patch is available. Rejected.

**C. Restrict access to dry-run via the Backstage permission framework**
Reduces the attack surface but does not eliminate the vulnerability for users with
legitimate access. May be applied as an additional control but not as the primary fix.
Rejected as the sole measure.

## Platform impact

### Migration
No schema or data migrations. Changes are limited to `yarn.lock` and `package.json`.

### Backward compatibility
`plugin-scaffolder-backend` 3.1.1 is a patch release; the public dry-run endpoint API
does not change. The response will contain `[REDACTED]` instead of secret-field values —
this is an intentional behaviour change, expected per spec.

### Resource impact
The recursive redactor adds negligible CPU overhead on dry-run calls (JSON graph walk).
Memory impact is negligible. The `labs` tenant is not affected.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Secrets have already leaked before the patch deploy | Unknown | Rotate every backend-pod secret after deploy; review Vault audit log |
| Peer-dependency conflict on simultaneous package updates | Medium | `yarn backstage-cli versions:check` before merge |
| Dry-run regression for legitimate templates | Low | Playwright test of dry-run with a reference template |
