# Tasks: openclaw-active-hours-scheduling

- [ ] 1. **Resolve the TODO** — contact the author of `mctl-openclaw@10448a0` (or read
        `src/infra/heartbeat-active-hours.ts` directly) to confirm the exact YAML/JSON
        config key name(s) for the `active-hours` feature (field name, start/end format,
        timezone format). Update the TODO marker in `proposed-content.md` with the real
        values before applying.
        — DoD: TODO marker replaced with confirmed config syntax.

- [ ] 2. **Apply `proposed-content.md` to `docs/platform/openclaw.md`** — paste the
        "Agent scheduling: active hours" subsection into the page at the appropriate
        location (after existing content, before any footer/see-also block).
        — DoD: file exists with the new subsection, `vitepress build docs` is green.

- [ ] 3. **Add troubleshooting cross-link** — open `docs/reference/troubleshooting.md`
        and add a bullet under a relevant section (e.g. "Agent issues") pointing to the
        new subsection:
        `Agent appears silent → check [active-hours configuration](/platform/openclaw#agent-scheduling-active-hours)`.
        — DoD: link resolves correctly.

- [ ] 4. **Local render check** — run `npm run dev` and open
        `http://localhost:5173/platform/openclaw` (or `/platform/openclaw.html`).
        Verify: subsection heading renders, YAML code block is highlighted, any optional
        mermaid diagram renders.
        — DoD: page renders with no errors; mermaid (if included) is visible.

- [ ] 5. **Open a PR against `mctlhq/mctl-docs`**, request code review, merge.
        — DoD: deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` completes with no errors and no warnings.
- [ ] T2. Every link in the new subsection resolves (anchor `#agent-scheduling-active-hours`
          reachable from the troubleshooting page cross-link).
- [ ] T3. The YAML example in the subsection has been hand-verified against a real
          OpenClaw config file (from `mctl-gitops` or `mctl-openclaw` docs directory).

## Rollback

- Remove the added subsection from `docs/platform/openclaw.md` and the bullet from
  `docs/reference/troubleshooting.md` via a revert PR.
- Low risk — markdown only, no build system changes.
