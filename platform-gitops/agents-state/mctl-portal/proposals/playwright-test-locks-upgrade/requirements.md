# Adopt Playwright v1.63.0 Test Locks for e2e suite

## Context
Playwright is an explicit part of the mctl-portal stack, used for the e2e test
suite (`context/architecture.md`). Playwright v1.63.0 introduces "Test Locks" —
named locks that prevent concurrent test runs across files/workers — along with
cross-frame locators without explicit iframe lookup, `locator.visible()`, richer
step reporting, aria/screen snapshot tracing, and a new Perfetto reporter. Note per
the researcher: the release page's date looked stale/cached during fetch, so the
exact release date should be re-confirmed against the official changelog before
implementation, though the version and feature set (Test Locks) are the ones being
adopted here.

Test Locks directly address a known class of e2e flakiness: cross-file/cross-worker
resource contention (e.g. two parallel test files both manipulating the same
scaffolder-created test service, or both hitting a shared Dex test session) causing
intermittent failures. This is a dev-tooling-only upgrade with no runtime/production
footprint — it changes CI and local developer experience only.

## User stories
- AS a mctl-portal contributor I WANT flaky, contention-based e2e test failures
  reduced SO THAT CI is more trustworthy and I spend less time re-running builds.
- AS a QA/DX owner I WANT to use named Test Locks around e2e specs that share
  external state (scaffolder-created resources, shared auth sessions) SO THAT
  parallel workers do not corrupt each other's test data.
- AS a mctl-portal maintainer I WANT this to be a dependency bump plus optional
  annotations SO THAT the upgrade has minimal effort and no production risk.

## Acceptance criteria (EARS)
- WHEN the `playwright` dev dependency is bumped to v1.63.0 THE SYSTEM SHALL
  continue to run the full existing e2e suite successfully with no test rewrites
  required as a precondition of the bump.
- WHEN a test spec that manipulates a shared external resource (e.g. a
  scaffolder-created test service, a shared Dex test session) is identified THE
  SYSTEM SHALL be annotated with a named Test Lock so that no other worker/file runs
  a conflicting test concurrently.
- WHILE two or more e2e test files hold the same named Test Lock's target resource
  THE SYSTEM SHALL serialize their execution rather than run them concurrently.
- IF a test spec does not touch shared/contended external state THEN THE SYSTEM
  SHALL NOT be required to carry a Test Lock annotation (locks are opt-in, applied
  only where contention is known or suspected).
- IF the Playwright bump introduces a breaking change to the existing e2e config or
  reporter setup THEN THE SYSTEM SHALL have that break fixed (or the bump paused)
  before merging — no CI-red state ships to `main`.

## Out of scope
- Adopting the new Perfetto reporter, aria/screen snapshot tracing, or
  `locator.visible()` as required practices — these are available but not mandated
  by this proposal; teams may adopt them opportunistically.
- Any change to production runtime code — this proposal touches dev/CI tooling
  (`devDependencies`, e2e specs) only.
- A full audit/rewrite of the existing e2e suite — only specs with known or
  suspected cross-file/cross-worker contention get Test Lock annotations initially.
