# Tasks: openclaw-session-observability

## Implementation tasks

- [ ] 1. Read the current `docs/platform/openclaw.md` in `mctlhq/mctl-docs`.
        Identify the end of the existing content and the best insertion point(s)
        for the three new sections (session management, fallback model,
        observability).
        — DoD: insertion points identified, existing structure understood.

- [ ] 2. Confirm the full list of `openclaw_llm_*` Prometheus counter names and
        any additional labels with the author of `mctl-openclaw:b23903e`.
        — DoD: counter names confirmed or TODO markers left inline.

- [ ] 3. Confirm the exact URL format for the `/metrics` endpoint per tenant
        with the author of `mctl-openclaw:4c46cf1`.
        — DoD: URL pattern confirmed or TODO marker left inline.

- [ ] 4. Add the "Session management" section to `docs/platform/openclaw.md`
        using the content from `proposed-content.md`.
        Include: context compaction description, `keepRecentTokens` parameter,
        and Telegram session idle timeout behaviour.
        — DoD: section present, no invented values for compaction threshold or
        idle timeout duration (use TODO markers for unconfirmed numbers).

- [ ] 5. Add the "Fallback model" section to `docs/platform/openclaw.md` using
        the content from `proposed-content.md`.
        Include: Claude Haiku as the current fallback for `ovk` and `labs`,
        reference commit `mctl-gitops:3e792eb` 2026-05-10, and note that the
        value is configurable per tenant via mctl-gitops.
        — DoD: section present, `ovk` and `labs` tenants named explicitly.

- [ ] 6. Add the "Observability" section to `docs/platform/openclaw.md` using
        the content from `proposed-content.md`.
        Include: `/metrics` endpoint URL, `openclaw_llm_*` counter family,
        `provider` label values, Prometheus scrape config example, and a PromQL
        example.
        — DoD: section present, scrape config and PromQL are syntactically correct.

- [ ] 7. (If needed) Update `.vitepress/config.{js,ts}` — sidebar / nav entry.
        No structural change expected; verify and skip if not needed.
        — DoD: confirmed no sidebar change required.

- [ ] 8. Run `npm run dev` locally and open `docs/platform/openclaw.md`.
        — DoD: page renders, mermaid diagram renders (if included), no broken
        anchors.

- [ ] 9. Cross-link check: confirm `docs/platform/components.md` and
        `docs/platform/architecture.md` have an appropriate link to the OpenClaw
        page for the observability and session management additions. Add links if
        absent.
        — DoD: cross-references in place.

- [ ] 10. Open a PR against `mctlhq/mctl-docs`, run code review, merge.
         — DoD: changes deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` completes with no errors and no warnings.
- [ ] T2. Every internal link in `docs/platform/openclaw.md` resolves (no 404s).
- [ ] T3. The Prometheus scrape config example is validated: either tested against
          the live `/metrics` endpoint of a labs or ovk OpenClaw instance, or
          confirmed syntactically correct by the commit author of
          `mctl-openclaw:4c46cf1`.
- [ ] T4. The PromQL example is checked for syntax correctness (can be validated
          with `promtool check rules` or against a Prometheus instance).
- [ ] T5. If a mermaid diagram is included, it renders without console errors
          in the local dev server.

## Rollback

Revert the PR. Changes are markdown only. Low risk.
