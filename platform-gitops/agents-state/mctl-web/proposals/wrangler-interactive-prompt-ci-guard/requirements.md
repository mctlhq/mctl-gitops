# Guard CI against wrangler 4.88 interactive prompt hangs

## Context
wrangler v4.88.0 (released 2026-05-05) introduces interactive prompts that fire
at deploy time whenever `name` or `compatibility_date` are absent from
`wrangler.toml`. In a non-interactive environment such as GitHub Actions, no TTY
is available to answer the prompt, so the wrangler process blocks indefinitely
until the job's timeout kills it. For mctl-web this means any Worker deployment
triggered by `deploy.yml` would hang and never reach production.

The fix has two layers: (1) ensure `wrangler.toml` explicitly declares both
required fields so no prompt is ever triggered, and (2) pass `CI=true` (or
`--no-interactive`) to the wrangler invocation in `deploy.yml` so that wrangler
exits with a clear error rather than hanging, should a required field ever go
missing again in the future. This is a low-effort, high-reliability guard that
must be applied alongside the wrangler 4.88 upgrade (`wrangler-4-88-upgrade`).

## User stories
- AS a platform engineer I WANT `deploy.yml` to complete or fail fast in CI
  SO THAT production deployments are never silently blocked by an unanswered prompt.
- AS a developer I WANT `wrangler.toml` to always contain `name` and
  `compatibility_date` SO THAT wrangler never enters interactive mode regardless
  of the CLI version in use.
- AS an on-call engineer I WANT a failing CI job to show an explicit error message
  SO THAT I can diagnose the root cause without inspecting a timed-out log.

## Acceptance criteria (EARS)
- WHEN the `deploy.yml` workflow runs wrangler deploy THE SYSTEM SHALL pass the
  environment variable `CI=true` (or the flag `--no-interactive`) to the wrangler
  process so that interactive prompts are suppressed.
- WHEN `wrangler.toml` is committed THE SYSTEM SHALL contain an explicit `name`
  field with the Worker name.
- WHEN `wrangler.toml` is committed THE SYSTEM SHALL contain an explicit
  `compatibility_date` field set to an ISO-8601 date string.
- IF `name` or `compatibility_date` is missing from `wrangler.toml` AND
  `CI=true` is set THEN THE SYSTEM SHALL exit wrangler with a non-zero exit code
  and a human-readable error rather than hanging.
- WHILE a pull request is open THE SYSTEM SHALL run a lint/validation step that
  confirms both `name` and `compatibility_date` are present in `wrangler.toml`
  before the merge is allowed.
- WHEN the `deploy.yml` job fails due to a missing wrangler configuration field
  THE SYSTEM SHALL surface an explicit error message in the GitHub Actions log
  within 60 seconds of the job start.

## Out of scope
- Upgrading wrangler to v4.88.0 (covered by the separate `wrangler-4-88-upgrade`
  proposal; this proposal only adds the CI guard that makes the upgrade safe).
- Changes to any Nuxt/frontend build steps in `deploy.yml`.
- Modifications to Cloudflare secrets or Worker runtime logic.
- Enforcing `compatibility_date` freshness or pinning to a specific date value.
- Adding new CI workflows beyond what is required for this guard.
