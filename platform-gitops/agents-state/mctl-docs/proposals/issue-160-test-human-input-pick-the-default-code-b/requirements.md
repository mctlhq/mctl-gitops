# Set an explicit default code-block syntax theme for docs.mctl.ai

## Context
Issue mctlhq/mctl-docs#160 asks for one default syntax-highlighting theme for
fenced code blocks on the docs site, covering both light and dark mode. The
issue names two candidate pairs: `github-light` / `github-dark` (familiar
GitHub look) and `one-light` / `one-dark-pro` (higher contrast, closer to the
MCTL design tokens). It says the choice belongs to the requester and cannot be
inferred from the repository.

Today `docs/.vitepress/config.ts` sets no `markdown.theme`, so the site
silently relies on the VitePress 1.6 built-in default. Pinning the theme
explicitly makes the look a deliberate, reviewable decision. The issue is
marked as a test issue for the human-input flow (mctlhq/mctl-agents#668) and
says "Do not implement". This proposal is complete, but implementing it is
expected to stay on hold. A clarification question has been filed for the
choice. Until it is answered, the proposal assumes option 1
(`github-light` / `github-dark`).

## User stories
- AS a docs reader I WANT code blocks highlighted with a consistent, legible theme SO THAT examples are easy to read.
- AS a docs maintainer I WANT the theme set explicitly in config SO THAT a VitePress upgrade cannot change it without anyone noticing.

## Acceptance criteria (EARS)
- WHEN the site is built with `bun run build` THE SYSTEM SHALL highlight fenced code blocks with the selected pair: `light` = the chosen light theme, `dark` = the chosen dark theme. Assumed until answered: `github-light` / `github-dark`.
- WHILE `appearance` is `'force-dark'` in `docs/.vitepress/config.ts` THE SYSTEM SHALL render code blocks with the dark theme of the selected pair.
- WHEN the light theme of the pair would be used (if `appearance` stops being forced dark) THE SYSTEM SHALL use the light theme of the same pair.
- WHILE the theme is applied THE SYSTEM SHALL keep the code block background from `--vp-code-block-bg` (`docs/.vitepress/theme/custom.css`, `vitepress-bridge.css`) and leave `mermaid` fences rendered by the custom fence rule.
- IF the requester picks the other option THEN THE SYSTEM SHALL need only the two theme name strings in `markdown.theme` changed, with no other code changes.

## Out of scope
- Changing `appearance: 'force-dark'` or adding a light/dark toggle.
- Restyling inline code (`--vp-code-bg` / `--vp-code-color`) or code-group tabs.
- Custom or forked Shiki theme JSON files, and per-language overrides.
- Any change to deployment (`services/admins/mctl-docs/values.yaml`).

## Open questions
- BLOCKING (clarification filed in `human-input/draft.json`): which pair should be used, `github-light` / `github-dark` or `one-light` / `one-dark-pro`? Assumed until answered: `github-light` / `github-dark`. It equals the VitePress 1.6 default, so the assumption changes nothing visually.
- The issue says "Do not implement" (test issue). A reviewer must decide whether this proposal is ever approved for implementation.
- Because the site is forced dark, only the dark theme of the pair is visible today. Should the light theme still be pinned? The proposal pins both, as the issue asks.
