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
  unfixed HIGH or CRITICAL vulnerability SO THAT new dependency vulnerabilities block merge instead of
  being silently reported and ignored.
- AS a reviewer reading `security.yml` I WANT the inline comment to reflect the current, true
  state of the scan SO THAT I do not make decisions based on stale, inaccurate context.

## Acceptance criteria (EARS)
- WHILE `.github/workflows/security.yml` exists, THE SYSTEM SHALL configure the Trivy
  filesystem scan step with `severity: "HIGH,CRITICAL"` and `exit-code: "1"`.
- WHEN the Trivy filesystem scan step in `.github/workflows/security.yml` runs and finds one or
  more HIGH or CRITICAL severity vulnerabilities with an available fix (`ignore-unfixed: true` still
  applies), THE SYSTEM SHALL fail the `trivy` job (non-zero exit code).
- WHEN the Trivy filesystem scan step finds no HIGH or CRITICAL vulnerabilities with an available fix,
  THE SYSTEM SHALL succeed the `trivy` job, exactly as it does today.
- WHILE `.github/workflows/security.yml` exists, THE SYSTEM SHALL NOT contain the stale
  inline comment referencing Nuxt DevTools / seroval findings as a reason the scan is
  report-only, since that condition no longer holds.
- IF a future PR reintroduces a HIGH or CRITICAL, fixable vulnerability THEN THE SYSTEM SHALL fail the
  `security` workflow's `trivy` job on that PR and on the next weekly cron run, so it is visible
  in the PR checks / Actions history rather than silently passing.

## Out of scope
- Severity levels below `HIGH` (MEDIUM, LOW, UNKNOWN). Widening past HIGH is a separate policy
  decision left for a follow-up.
- Changing `ignore-unfixed: true`, the Trivy version pin, `scan-type`, or `scan-ref`.
- Adding branch protection / required-status-check enforcement for the `trivy` job in GitHub
  repo settings (making the check "required" is an org/admin setting outside this workflow
  file and outside this proposal's scope).
- Triaging or remediating any vulnerability that a fail-closed run might newly surface after
  this change lands (e.g. via a fresh Dependabot bump) — handled by Dependabot PRs per the
  existing comment's stated remediation path.

## Open questions
- Resolved at approval (2026-08-30): the operator widened `severity` to `HIGH,CRITICAL`.
  The audit's own evidence is a local scan clean at HIGH *and* CRITICAL, so gating only on
  CRITICAL spends that clean baseline for less than it is worth — HIGH findings with an
  upstream fix would still merge silently. `ignore-unfixed: true` is unchanged, so the gate
  still only fires on findings that have somewhere to go.
