# Make Trivy dependency scan fail-closed in security.yml

## Context
`.github/workflows/security.yml` runs a Trivy filesystem scan (`aquasecurity/trivy-action`,
scan-type `fs`, `severity: CRITICAL`, `ignore-unfixed: true`) on every PR into `main` and on a
weekly cron. The job is currently configured with `exit-code: "0"`, meaning the workflow always
succeeds regardless of findings — it is report-only. The step carries an inline comment
explaining this was deliberate because `package-lock.json` had CRITICAL findings in Nuxt
DevTools and `seroval` with no upstream fix at the time, and the workflow existed mainly to
satisfy SOC control F16 (scan must run).

Per the issue, a local Trivy run on 2026-08-27 (including dev dependencies) found the repo
clean: 0 HIGH/CRITICAL findings. The vulnerable Nuxt DevTools / `seroval` versions referenced by
the stale comment are no longer present (or no longer vulnerable) in `package-lock.json`. With
the scan now clean, keeping the job soft (`exit-code: "0"`) means a newly introduced CRITICAL
vulnerability would no longer block the PR or fail the weekly cron — the control is silently
toothless. This is flagged as part of the 2026-08 platform audit (P2, dependency/SCA finding).

## User stories
- AS a maintainer of mctl-web I WANT the Trivy scan to fail the workflow when it finds an
  unfixed CRITICAL vulnerability SO THAT new dependency vulnerabilities block merge instead of
  being silently reported and ignored.
- AS a reviewer reading `security.yml` I WANT the inline comment to reflect the current, true
  state of the scan SO THAT I do not make decisions based on stale, inaccurate context.

## Acceptance criteria (EARS)
- WHEN the Trivy filesystem scan step in `.github/workflows/security.yml` runs and finds one or
  more CRITICAL severity vulnerabilities with an available fix (`ignore-unfixed: true` still
  applies), THE SYSTEM SHALL fail the `trivy` job (non-zero exit code).
- WHEN the Trivy filesystem scan step finds no CRITICAL vulnerabilities with an available fix,
  THE SYSTEM SHALL succeed the `trivy` job, exactly as it does today.
- WHILE `.github/workflows/security.yml` exists, THE SYSTEM SHALL NOT contain the stale
  inline comment referencing Nuxt DevTools / seroval findings as a reason the scan is
  report-only, since that condition no longer holds.
- IF a future PR reintroduces a CRITICAL, fixable vulnerability THEN THE SYSTEM SHALL fail the
  `security` workflow's `trivy` job on that PR and on the next weekly cron run, so it is visible
  in the PR checks / Actions history rather than silently passing.

## Out of scope
- Changing `severity` (currently `CRITICAL` only) to also include `HIGH`. The issue's context
  mentions the local scan was run for HIGH/CRITICAL, but the "Expected fix" section only asks
  to flip `exit-code` and remove the stale comment; broadening severity is a separate policy
  decision left for a follow-up.
- Changing `ignore-unfixed: true`, the Trivy version pin, `scan-type`, or `scan-ref`.
- Adding branch protection / required-status-check enforcement for the `trivy` job in GitHub
  repo settings (making the check "required" is an org/admin setting outside this workflow
  file and outside this proposal's scope).
- Triaging or remediating any vulnerability that a fail-closed run might newly surface after
  this change lands (e.g. via a fresh Dependabot bump) — handled by Dependabot PRs per the
  existing comment's stated remediation path.

## Open questions
- None. The issue is fully specified: set `exit-code: "1"` and remove the stale comment. The
  HIGH-severity scope question is recorded above as an explicit out-of-scope item rather than
  a blocker.
