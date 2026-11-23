# Design: worker-toolchain-bump-compat-date

## Current state
The Worker lives in `cloudflare-worker/` and is deployed by wrangler through `deploy.yml` in this repo, an exception to centralized builds (see `context/architecture.md`). Current wrangler version and `compatibility_date` are not known from context (verify, V2).

## Proposed solution
1. Determine the current wrangler and `compatibility_date`; verify the latest wrangler release (V1).
2. Bump wrangler to the verified latest and pin it exactly.
3. Treat the compat-date move as a separate, staged change: set the candidate date (up to 2026-11-13) in staging, run manual or scripted checks of OAuth login/callback, submit and contact flows, and rate limiting; compare behaviour with the old date.
4. Promote the new date to production only if staging is clean; otherwise keep the old date and document why. Do not turn on the MemoryCache autogate.
Toolchain bump and compat-date change land as two commits so each can be reverted independently.

## Alternatives
- Do nothing: dropped, drift accumulates and larger jumps are riskier later.
- Always track the default compat date automatically: dropped, silent runtime behaviour changes on a secrets-handling Worker.
- Bump toolchain and date in one step: dropped, harder to attribute regressions.

## Platform impact
- Migrations: none.
- Backward compatibility: a newer compat date can change runtime semantics; mitigated by staging validation and separate commits.
- Resource impact: Cloudflare Worker only, no Kubernetes memory change; `labs` unaffected.
- Risks and mitigations: unverified wrangler version (verify first); no staging environment available (create or use a preview deployment before production); secrets exposure during tests (use staging secrets only).
