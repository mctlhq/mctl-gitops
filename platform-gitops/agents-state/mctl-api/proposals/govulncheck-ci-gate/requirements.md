# Add govulncheck to CI and image build as a release gate

## Context
Go stdlib and dependency CVEs repeatedly surface late, producing many reactive upgrade proposals. An automated reachability scan would flag them at PR time.

## User stories
- AS a maintainer I WANT CI to fail on reachable vulnerabilities SO THAT drift is caught early.

## Acceptance criteria (EARS)
- WHEN a pull request is opened THE SYSTEM SHALL run govulncheck ./... and report results.
- IF govulncheck finds a reachable vulnerability THEN THE SYSTEM SHALL fail the check.
- WHEN a scheduled nightly run executes THE SYSTEM SHALL run govulncheck on main and notify on findings.
- WHILE an advisory is explicitly waived THE SYSTEM SHALL permit it only with an expiry date.

## Out of scope
- Runtime scanning; container image scanning.
