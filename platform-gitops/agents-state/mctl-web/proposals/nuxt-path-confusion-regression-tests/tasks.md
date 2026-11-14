# Tasks: nuxt-path-confusion-regression-tests

- [ ] 1. Confirm Nuxt baseline version and verify the motivating CVEs against official advisories — DoD: findings noted in the PR.
- [ ] 2. Inspect `deploy.yml` and choose the insertion point between build and deploy — DoD: step location agreed in PR.
- [ ] 3. Write the path-variant test script with a table of variants and expected outcomes for pages (depends on 1) — DoD: runs locally against the built site.
- [ ] 4. Add `/api/*` variant checks with a local Worker and stubbed upstreams/secrets (depends on 3) — DoD: identical routing and shared rate-limit counting asserted, no external calls made.
- [ ] 5. Add the production-error-leak assertion (depends on 3) — DoD: check passes on a build with the fixed Nuxt, documented as expected-fail or skipped on older ones.
- [ ] 6. Wire into `deploy.yml` as a blocking step (depends on 3, 4, 5) — DoD: CI run shows the step green; a deliberately broken expectation turns it red.
- [ ] 7. Document how to update the expectation table (depends on 6) — DoD: short README section.

## Tests
- [ ] T1. Negative control: a deliberately wrong expected value fails the job.
- [ ] T2. Script exits 0 on the current build.
- [ ] T3. Raw unnormalized paths actually reach the server (verified by server log or echo).
- [ ] T4. No outbound calls to Telegram, Resend or Backstage during the run.

## Rollback
Remove or mark the CI step `continue-on-error` in `deploy.yml`; delete the script. No runtime impact.
