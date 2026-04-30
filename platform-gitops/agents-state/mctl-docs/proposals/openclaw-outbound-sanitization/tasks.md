# Tasks: openclaw-outbound-sanitization

- [ ] 1. Apply the "Security" subsection from `proposed-content.md` to
        `mctl-docs/docs/platform/openclaw.md`.
        — DoD: file exists with the new "Security" section; `vitepress build docs` is green.

- [ ] 2. Confirm the mermaid sequence diagram renders correctly.
        — DoD: `npm run dev` opened locally, mermaid block renders without error.

- [ ] 3. Add a cross-link from `docs/security/authentication.md` to the new Security
        subsection in `docs/platform/openclaw.md`.
        — DoD: a `[See also: OpenClaw outbound sanitization](/platform/openclaw#security)`
        link or equivalent appears in `authentication.md`.

- [ ] 4. Verify the production version of `mctl-openclaw` includes commits `c2d31a5` and
        `c5c08c0` before merging. Check `mctl-gitops` deploy history or use an
        `mcp__mctl__*` tool if available.
        — DoD: version confirmed; remove or update the "version-status: unverified" note.

- [ ] 5. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
        — DoD: deployed to `docs.mctl.ai/platform/openclaw`.

## Tests

- [ ] T1. `vitepress build docs` completes with no errors and no warnings.
- [ ] T2. Every link in the updated `openclaw.md` and modified `authentication.md` resolves
         (no 404s via `vitepress build` link checker or manual check).
- [ ] T3. The code block showing the inter-session envelope marker is valid markdown and
         renders as a fenced code block in the browser.
- [ ] T4. The mermaid sequence diagram renders in the VitePress dev server without throwing
         a parse error.

## Rollback

Delete the added "Security" section and the cross-link in `authentication.md` via a
revert PR. Low risk — markdown only; no config changes, no sidebar changes.

## Related proposals

- `openclaw-outbound-security` (created 2026-04-29) — overlapping scope; either
  `proposed-content.md` can be used as the implementation patch.
