# Tasks: openclaw-outbound-security

- [ ] 1. Update `docs/platform/openclaw.md` — paste the "Security" section from
         `proposed-content.md` into the appropriate position (after the overview /
         channels section, before any troubleshooting content).
         — DoD: file exists, `vitepress build docs` is green.
- [ ] 2. Verify the mermaid sequence diagram renders correctly.
         — DoD: `npm run dev` shows the diagram without errors in the browser.
- [ ] 3. Add a cross-link from `docs/security/authentication.md` to the new section
         (a one-liner: "For outbound message sanitization in the OpenClaw gateway, see
         [OpenClaw Security](/platform/openclaw#security).").
         — DoD: cross-reference in place and resolves.
- [ ] 4. (Optional) If `docs/platform/openclaw.md` already has an in-page Table of
         Contents, confirm the new "Security" heading appears in it.
         — DoD: TOC entry visible in local preview.
- [ ] 5. Open a PR against `mctlhq/mctl-docs`, run code review, merge.
         — DoD: content live at docs.mctl.ai/platform/openclaw.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Links in the new section resolve: cross-link to `docs/security/authentication.md`
          returns 200.
- [ ] T3. The inter-session envelope format example
          (`[Inter-session message … isUser=false]`) has been cross-checked against the
          openclaw CHANGELOG for commit `c5c08c0` (or `1e9faa2` diff) to confirm accuracy.

## Rollback

- Revert the section addition via a PR. Low risk — markdown only, no build impact.
- version-status: unverified (confirm against production mctl-openclaw before publishing).
