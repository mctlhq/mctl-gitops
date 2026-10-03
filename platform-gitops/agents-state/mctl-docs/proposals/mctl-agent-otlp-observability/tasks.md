# Tasks: mctl-agent-otlp-observability

- [ ] 1. Update `docs/platform/components.md` — add the tracing/metrics
        bullet from `proposed-content.md` (Block 1) to the mctl-agent
        capability list. — DoD: `vitepress build docs` is green.
- [ ] 2. Update `docs/reference/troubleshooting.md` — insert the new
        `## Observability` section from `proposed-content.md` (Block 2)
        after `## Self-Healing Agent` and before `## Getting Help`.
        — DoD: section renders, table formatting matches the rest of the
        page.
- [ ] 3. Update `docs/reference/telemetry-attributes.md` — apply the
        `reserved` → `shipped` promotion diff from `proposed-content.md`
        (Block 3). — DoD: the specific rows are updated; the rest of the
        page (all other `reserved` rows) is untouched.
- [ ] 4. Run `npm run dev` locally and open the three updated pages.
        — DoD: all render, internal links work, no console errors.
- [ ] 5. Cross-link: check whether `docs/platform/architecture.md` or
        `docs/mcp/overview.md` should mention observability at all.
        — DoD: judged unnecessary for this narrow, single-producer scope;
        note left in the PR rather than a page edit (no diagram change,
        no new concept beyond what's already in `telemetry-attributes.md`).
- [ ] 6. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the changed pages resolves (no 404s).
- [ ] T3. The two Prometheus counter names/labels have been hand-checked
        against `internal/metrics/metrics.go` on `mctl-agent` `main`
        (`mctl_agent_llm_tokens_total`: `model`, `skill`, `ticket_type`,
        `direction`; `mctl_agent_llm_requests_total`: `model`, `skill`,
        `outcome`).
- [ ] T4. The `OTEL_*` variable names have been hand-checked against
        `internal/telemetry/telemetry.go`'s `Enabled()` function on
        `mctl-agent` `main`.

## Rollback
- Revert the three page edits via a revert PR. Low risk — markdown only,
  no code or infra changes.
