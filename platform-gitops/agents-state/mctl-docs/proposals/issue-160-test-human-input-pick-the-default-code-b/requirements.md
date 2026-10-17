# Pin github-light / github-dark as the default code-block theme for docs.mctl.ai

## Context
Issue mctlhq/mctl-docs#160 asks for one default syntax-highlighting theme for code blocks on the docs site, covering both light and dark mode, chosen between two candidate pairs. The issue author answered the earlier clarification question (request hir-d6dac56542bddcdf): the pair is **github-light / github-dark**.

VitePress 1.6 already uses github-light / github-dark as its implicit Shiki default, and `docs/.vitepress/config.ts` sets no `markdown.theme`. The value of this change is to make the choice explicit and pinned in config, so a future VitePress upgrade that changes its implicit default cannot silently change how code looks, and so the decision is visible to the next reader. The issue is labelled a test issue for an acceptance check of mctlhq/mctl-agents#668 and says "Do not implement"; this proposal is still written as a complete, buildable spec.

## User stories
- AS a docs reader I WANT code blocks highlighted with the familiar GitHub palette SO THAT code is easy to scan.
- AS a docs maintainer I WANT the code-block theme declared explicitly in config SO THAT a VitePress upgrade cannot change it without a reviewed diff.

## Acceptance criteria (EARS)
- WHEN the site is built THE SYSTEM SHALL configure Shiki through `markdown.theme` in `docs/.vitepress/config.ts` with `light: 'github-light'` and `dark: 'github-dark'`.
- WHEN a fenced code block in a supported language is rendered THE SYSTEM SHALL emit inline `--shiki-light` / `--shiki-dark` colour variables taken from github-light and github-dark respectively.
- WHILE the site uses `appearance: 'force-dark'` THE SYSTEM SHALL render code tokens with the github-dark palette.
- WHILE a fenced block uses the `mermaid` language THE SYSTEM SHALL keep rendering it as a `.mermaid-diagram` div through the existing custom fence rule, unaffected by the theme setting.
- IF the configured theme name is not available in the bundled Shiki THEN THE SYSTEM SHALL fail the `vitepress build` rather than ship unhighlighted output.

## Out of scope
- The one-light / one-dark-pro alternative (rejected by the author's answer).
- Changing `appearance: 'force-dark'` or adding a light/dark toggle.
- Restyling code-block background, borders or code-group tabs in `custom.css` / `vitepress-bridge.css`.
- Adding custom Shiki languages or transformers.

## Open questions
- The issue says "Close it after the check. Do not implement." Whether this proposal should actually be implemented is for the reviewer to decide; the spec is complete either way.
- The site sets `appearance: 'force-dark'`, so the github-light half of the pair is configured but never visible today. Assumed acceptable: the issue asks for a pair "for both light and dark mode", and pinning both keeps the config correct if the light appearance is re-enabled.
