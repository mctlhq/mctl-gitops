# Pick and pin the default code-block syntax theme for docs.mctl.ai

## Context
Issue mctlhq/mctl-docs#160 asks for one explicit default syntax-highlighting theme pair (light + dark) for fenced code blocks on the docs site. Two candidates are offered: `github-light` / `github-dark` (familiar GitHub look) and `one-light` / `one-dark-pro` (higher contrast, closer to MCTL design tokens). The issue states the choice belongs to the requester and cannot be inferred from the repository.

Today `docs/.vitepress/config.ts` sets no `markdown.theme`, so VitePress 1.6 falls back to its built-in Shiki default, which is `github-light` / `github-dark`. The site also sets `appearance: 'force-dark'`, so only the dark half of any pair is currently rendered. The issue is explicitly a test issue for the human-input flow (mctlhq/mctl-agents#668) and says "Do not implement"; this proposal is nevertheless complete so the flow can be exercised end to end.

## User stories
- AS a docs reader I WANT code blocks highlighted with a deliberate, consistent theme SO THAT code is readable and matches the site.
- AS a docs maintainer I WANT the theme pinned explicitly in config SO THAT a VitePress upgrade cannot silently change it.

## Acceptance criteria (EARS)
- WHEN the site is built THE SYSTEM SHALL configure `markdown.theme` in `docs/.vitepress/config.ts` as an object `{ light: <chosen-light>, dark: <chosen-dark> }` using exactly the pair the requester selected.
- WHILE `appearance` is `'force-dark'` THE SYSTEM SHALL render fenced code blocks with the chosen dark theme.
- IF the site appearance is later changed to allow light mode THEN THE SYSTEM SHALL render fenced code blocks with the chosen light theme without further config change.
- WHEN a fence has language `mermaid` THE SYSTEM SHALL continue to render it as a `.mermaid-diagram` div (the custom fence override in `markdown.config` is unchanged).
- WHEN `bun run build` runs THE SYSTEM SHALL complete successfully, including the existing `mermaid-links.test.ts` test.

## Out of scope
- Changing `appearance: 'force-dark'` or enabling a light-mode toggle.
- Restyling code-block chrome (border, background, tabs) in `docs/.vitepress/theme/custom.css` or `vitepress-bridge.css`.
- Custom or token-derived Shiki themes.
- Any change to deployed config in mctl-gitops.

## Open questions
- BLOCKING: which pair does the requester want - option 1 (`github-light` / `github-dark`) or option 2 (`one-light` / `one-dark-pro`)? A clarification question has been filed. Until answered, this proposal proceeds on option 1, because it is VitePress's current implicit default: pinning it is a zero-visual-change, lowest-risk step, and switching to option 2 is a two-string edit.
- The site is `force-dark`; the light theme of either pair is currently never shown. Is pinning the light half still wanted (assumed yes, per the issue wording "for both light and dark mode")?
- The issue says "Close it after the check. Do not implement." The reviewer should decide whether this proposal is ever accepted.
