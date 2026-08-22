# Reconcile context/current-version.md with the live deployed image tag

## Context
`context/current-version.md` records Version 4.6.2, last updated 2026-04-25. The mctl
platform tooling (`mctl_get_service_status` and `mctl_get_service_config` for
admins/mctl-web) reports the live deployed image tag as 7.3.0 — a four-month-old,
significantly stale record. Every downstream agent in this repo (researcher, analyst,
spec-writer) treats `context/` as the source of truth for reasoning about version gaps
and upgrade effort; an unreconciled drift here risks compounding into bad decisions in
future passes (e.g., a future analyst mis-judging the size of an upgrade because it is
comparing against a wrong baseline).

This is a documentation/process proposal, not an application code change: the
deliverable is a corrected process for keeping `context/current-version.md` in sync
with reality, plus a one-time correction task. Note that `context/` is read-only for
the agents that produce this spec — the actual edit to `context/current-version.md` is
a task to be executed by whoever runs the deploy/update step, not by spec-writer.

## User stories
- AS a researcher/analyst agent I WANT `context/current-version.md` to reflect the true
  live deployed version SO THAT my version-gap and upgrade-effort reasoning is based on
  accurate data.
- AS a service owner I WANT a lightweight, repeatable process for keeping this file
  current SO THAT it does not silently drift out of sync again.

## Acceptance criteria (EARS)
- WHEN the true live version is verified via mctl MCP tooling (service status/config
  for tenant `admins`) THE SYSTEM SHALL record that verified version and the
  verification date in `context/current-version.md`.
- WHEN a deploy of mctl-web to the `admins` tenant completes THE SYSTEM SHALL update
  `context/current-version.md` as part of that deploy's completion steps.
- IF the recorded version in `context/current-version.md` and the live deployed image
  tag differ THEN THE SYSTEM SHALL flag the discrepancy the next time this
  reconciliation check is run.
- WHILE `context/current-version.md` is out of sync with the live deployment THE
  SYSTEM SHALL NOT be relied upon by researcher/analyst agents as an authoritative
  version baseline without a fresh mctl status check.
- IF a discrepancy between "Version" (application/Nuxt version) and "imageTag" (build
  artifact tag) semantics is discovered during verification THEN THE SYSTEM SHALL
  document what "7.3.0" actually corresponds to (e.g., internal build/release
  numbering vs. the Nuxt framework version) so the file's meaning is unambiguous going
  forward.

## Out of scope
- Actually editing `context/current-version.md` — that edit is a task for whoever
  executes the deploy/update process, not for the spec-writer agent, since `context/`
  is read-only for agents in this repo.
- Any application code, dependency, or infrastructure change — this proposal is
  process/documentation only.
- Automating the version-sync check into CI/CD tooling beyond a documented manual step,
  unless a future proposal specifically scopes that automation.
