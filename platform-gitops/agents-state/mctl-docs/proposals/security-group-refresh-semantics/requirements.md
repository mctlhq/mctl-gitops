# Requirements: tenant membership refresh semantics
version-status: unverified, see commit SHA

Source: mctl-api 51c2533 "fix(auth): re-resolve tenant groups on OAuth refresh and validate" (plus 58d4d32, 724d24d, 6df9748, 32a1ad1 hardening).

## User stories
- As a tenant member I want to know when joining or leaving a tenant takes effect so I do not sign out unnecessarily.
- As an operator I want to know the knobs and failure fallback.

## Acceptance criteria (EARS)
- WHEN a user's tenant membership changes THE docs SHALL state that it applies to live sessions without re-login (bounded by the 30s per-login memo, `OAUTH_GROUPS_CACHE_TTL`).
- WHEN group resolution fails THE docs SHALL state the fallback: stored groups for one access-token TTL, then admins-only.
- WHERE the gitops checkout is stale THE docs SHALL describe `OAUTH_GROUPS_MAX_STALENESS` strict mode and the `mctl_api_gitops_last_sync_age_seconds` gauge.
- THE admin flag SHALL be documented as recomputed on every refresh.
