# Tasks: openclaw-gateway-handshake-timeout

- [ ] 1. Update `docs/platform/openclaw.md` — add the "Configuration reference (operations)"
         section from `proposed-content.md` (table + JSON5 example).
         — DoD: file updated, `vitepress build docs` is green.
- [ ] 2. Verify the JSON5 code block renders correctly (VitePress 1.6 syntax highlighting).
         — DoD: `npm run dev` shows highlighted JSON5 without errors.
- [ ] 3. Check `docs/reference/troubleshooting.md` — if there is an existing entry about
         WebSocket or connection timeouts, add a cross-reference to the new config knob.
         — DoD: relevant cross-reference in place (or noted as not applicable).
- [ ] 4. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
         — DoD: content live at docs.mctl.ai/platform/openclaw.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. The external link to openclaw's configuration reference resolves (HTTP 200).
- [ ] T3. Default value (15000 ms) and precedence rule (`OPENCLAW_HANDSHAKE_TIMEOUT_MS`
          overrides config) have been verified against the diff for commit `bcc6a24`.

## Rollback

- Revert the section addition via a PR. Low risk — markdown only, no build impact.
- version-status: unverified (confirm against production mctl-openclaw before publishing).
