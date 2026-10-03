## When membership changes take effect

Tenant groups and the admin flag are re-evaluated whenever an OAuth access token is refreshed or validated; they are not frozen at first login.

- **Joining or creating a tenant:** takes effect in your live session without signing out again.
- **Being removed from a tenant:** access ends shortly after the change is visible to the platform, not at the end of the 30-day refresh-token lifetime. Lookups are memoised per login for 30 seconds.
- **Admin status** is recomputed on every refresh.

::: warning Degraded mode
If tenant membership cannot be resolved (for example the GitOps checkout has never synced), the platform keeps your previously stored groups for one access-token lifetime, then falls back to admins-only access (fail closed).
:::

Operators can tune this with `OAUTH_GROUPS_CACHE_TTL` and opt into strict staleness handling with `OAUTH_GROUPS_MAX_STALENESS`. The gauge `mctl_api_gitops_last_sync_age_seconds` reports how old the membership data is.
