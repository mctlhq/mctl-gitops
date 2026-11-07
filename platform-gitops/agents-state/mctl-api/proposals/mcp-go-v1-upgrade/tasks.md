# Tasks: mcp-go-v1-upgrade

- [ ] 1. Read 0.31 to 1.5.0 changelogs and list breaking changes — DoD: migration notes in PR description.
- [ ] 2. Bump dependency and fix compile errors (depends on 1) — DoD: build and unit tests green.
- [ ] 3. Configure body limits and redirect policy for any client use (depends on 2) — DoD: tests cover oversized body and redirect.
- [ ] 4. Run MCP Inspector over all 24 tools and the Claude.ai OAuth flow (depends on 2) — DoD: results recorded, no regressions.
- [ ] 5. Canary rollout (depends on 3, 4) — DoD: 24h clean.

## Tests
- [ ] T1. Per-tool contract tests (schema + auth).
- [ ] T2. Oversized SSE message body returns an error.
- [ ] T3. OAuth PKCE end-to-end with localhost redirect variants.

## Rollback
Revert go.mod/go.sum and redeploy the previous image.
