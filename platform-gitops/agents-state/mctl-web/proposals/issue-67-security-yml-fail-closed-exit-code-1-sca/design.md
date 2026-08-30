# Design: issue-67-security-yml-fail-closed-exit-code-1-sca

## Current state
`.github/workflows/security.yml` (7 steps, single `trivy` job, `runs-on: ubuntu-latest`,
`timeout-minutes: 15`) triggers on `pull_request` into `main` and on a weekly cron
(`57 4 * * 1`). It has `permissions: contents: read` and a single step:

```yaml
- name: Trivy filesystem scan
  uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0
  with:
    scan-type: fs
    scan-ref: .
    severity: CRITICAL
    exit-code: "0"
    ignore-unfixed: true
    version: v0.69.3
    # Report-only: package-lock.json already has CRITICAL findings with
    # upstream fixes (Nuxt DevTools, seroval). Dependabot PRs are the
    # remediation path; this workflow exists so the scan runs (SOC F16).
```

`exit-code: "0"` tells `trivy-action` to always return success, so the `trivy` job is green
even when Trivy detects CRITICAL, fixable vulnerabilities — it is purely observational today.
`package.json` currently pins `"nuxt": "^4.3.1"`, and `package-lock.json` resolves `seroval` at
`1.6.2` (line ~9112-9114) — versions that per the issue's local 2026-08-27 Trivy run
(`--include-dev-deps`) no longer trigger any HIGH/CRITICAL finding. The inline comment
explaining the soft exit code is therefore stale: it describes a vulnerability state
(`package-lock.json already has CRITICAL findings`) that no longer holds.

`security.yml` is not referenced by `CLAUDE.md`'s PR Review Flow section explicitly, but per
`CLAUDE.md`'s own classification, "Config/values YAML" changes are trivial and can merge
immediately without the Claude Opus review gate — this is a single-workflow YAML edit with no
application code impact.

## Proposed solution
Three edits to the same file, `.github/workflows/security.yml`, keeping every other setting
(`scan-type`, `scan-ref`, `ignore-unfixed`, `version`, the action's pinned SHA) unchanged:

1. Flip `exit-code: "0"` to `exit-code: "1"` on the Trivy filesystem scan step. Per
   `trivy-action`'s documented behavior, this makes the underlying `trivy` CLI exit non-zero
   when it finds a vulnerability at or above `severity` that is not filtered out by
   `ignore-unfixed: true` — which in turn fails the GitHub Actions step, and therefore the
   `trivy` job and the `security` workflow run.

1a. Widen `severity` from `CRITICAL` to `HIGH,CRITICAL` (operator decision, 2026-08-30). The
   audit's evidence for this issue is a local scan clean at HIGH *and* CRITICAL, including
   `--include-dev-deps`. Gating only on CRITICAL leaves fixable HIGH findings merging silently
   while claiming a fail-closed gate. `ignore-unfixed: true` still applies, so the gate can only
   fire on findings with an upstream fix available.
2. Delete the three-line inline comment (`# Report-only: ... SOC F16.`) since it documents a
   rationale (soft-fail because of known unfixed findings) that is no longer accurate now the
   scan is clean. No replacement comment is required — a fail-closed SCA gate with
   `ignore-unfixed: true` is self-explanatory; if a short comment is wanted, keep it factual and
   forward-looking, e.g. `# Fails on fixable HIGH/CRITICAL findings; ignore-unfixed skips CVEs with
  no upstream fix.` This proposal treats adding a replacement comment as optional polish, not a
  requirement, since the acceptance criteria only require the stale comment's removal.

No new steps, no change to `on:` triggers, `permissions:`, or the pinned action version/SHA.

## Alternatives
- **Leave `severity` at `CRITICAL` only.** This was the original proposal, rejected by the
  operator at approval: it declines the free coverage the clean HIGH baseline already pays for.
  Retained note on the original reasoning — widening severity changes what fails the build
  being tied to what the *workflow* itself scans today. Recorded as a follow-up candidate in
  `requirements.md`'s Out of scope.
- **Leave the comment in place but edit it to say "now clean, fail-closed."** Rejected because
  the issue explicitly asks to "remove the stale comment," not rewrite it, and a shrinking
  changeset is easier to review; a short factual replacement is offered as optional in this
  design but not mandated.
- **Introduce `continue-on-error` / a separate soft-fail path (e.g. warn-only for HIGH,
  fail for CRITICAL) via `trivy-action`'s newer table-based `exit-code` filters.** Rejected as
  over-engineering relative to a P2 audit item whose fix is a one-line flip; adds complexity
  (multiple severity/exit-code combinations) with no requirement driving it.

## Platform impact
- **Migrations / backward compatibility:** none. This is a CI-only YAML change; no application
  code, Nuxt build, nginx config, or Cloudflare Worker is touched.
- **Resource impact:** none — same job, same runner, same timeout; only the exit-code semantics
  change.
- **Risk:** the `trivy` job can now fail PRs and the weekly cron run when a HIGH or CRITICAL, fixable
  vulnerability is found (this is the intended effect). Since Trivy currently reports the repo
  clean, the immediate risk of breaking in-flight PRs is low, but:
  - Mitigation: verify the exact same Trivy version/config (`version: v0.69.3`,
    `severity: HIGH,CRITICAL`, `ignore-unfixed: true`) still reports 0 findings against `main` at PR
    time (this proposal's Tests section) before merging, so the flip doesn't immediately red the
    workflow.
  - Mitigation: because `security.yml` is not currently listed as a required status check
    anywhere in this repo's tracked config, a future failure blocks visibility (red X on the PR)
    but does not silently block merge via branch protection unless that is separately configured
    — reducing the blast radius of an unexpected finding to "visible and actionable" rather than
    "merge-blocking surprise." If branch protection already requires this check, a future
    HIGH/CRITICAL finding will correctly block merge until Dependabot/manual remediation lands, which
    is the intended fail-closed behavior the issue asks for.
  - Mitigation: rollback is a one-line revert (`exit-code: "1"` back to `"0"`) if the fail-closed
    gate proves too noisy in practice.
