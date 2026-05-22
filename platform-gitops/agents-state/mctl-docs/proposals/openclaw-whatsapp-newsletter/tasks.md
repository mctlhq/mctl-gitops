# Tasks: openclaw-whatsapp-newsletter

- [ ] 1. Update `docs/platform/openclaw.md` with the content from
        `proposed-content.md` — add the "WhatsApp outbound target formats" subsection.
        — DoD: file exists with the new subsection; `vitepress build docs` is green.

- [ ] 2. No `.vitepress/config` changes needed — `openclaw.md` is already in the nav
        and sidebar. Skip this step.

- [ ] 3. Run `npm run dev` locally and open `docs/platform/openclaw.md`.
        — DoD: new section renders correctly; the Markdown table is properly aligned;
        the code block has syntax highlighting (`bash`); the NOTE callout (if using a
        VitePress `::: info` container) renders with the correct style.

- [ ] 4. Cross-link check: add a one-line cross-reference in
        `docs/reference/troubleshooting.md` under a relevant "WhatsApp" entry (create
        one if it doesn't exist):
        > "WhatsApp newsletter messages not delivered: confirm you are using the
        > `@newsletter` JID format and that mctl-openclaw ≥ 2026.5.2 is deployed
        > ([WhatsApp outbound targets](/platform/openclaw#whatsapp-outbound-target-formats))."
        — DoD: cross-reference in place and link resolves.

- [ ] 5. Open a PR against `mctlhq/mctl-docs`, run code review, merge.
        — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` completes with no errors and no warnings.
- [ ] T2. The anchor `#whatsapp-outbound-target-formats` resolves on the built page
        (used by the troubleshooting cross-link).
- [ ] T3. The CLI example `openclaw message send --channel whatsapp --target 120363123456789@newsletter --message "..."` has been hand-verified against the upstream OpenClaw docs (`mctl-openclaw docs/cli/message.md` at commit `0fad53a`) — no field names invented.

## Rollback
- Delete the added subsection via a revert PR. Low risk — Markdown only, no
  config changes.
