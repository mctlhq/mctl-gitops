# Requirements: DevLoop start outcomes
version-status: unverified, see commit SHA

Source: mctl-api 7512b9e / b8be2ae (issue #287) — single-issue DevLoop start shares the describe→classify→start logic with the roadmap wave.

## Acceptance criteria (EARS)
- WHEN `mctl_trigger_issue` is called with `use_temporal=true` THE docs SHALL list the outcomes `started`, `already_running`, `already_exists`, `failed`.
- WHEN a DevLoop for the issue is closed THE docs SHALL state it is not restarted (`already_exists`).
- IF the existing execution cannot be read THEN the docs SHALL state nothing is started (`failed`).
- THE docs SHALL point to `mctl_get_dev_loop` for follow-up.
