# Set an explicit default code-block syntax-highlighting theme for docs.mctl.ai

## Context
Issue mctlhq/mctl-docs#160 asks for one default syntax-highlighting theme for
code blocks on the docs site, covering both light and dark mode. Two
candidate pairs are named: `github-light` / `github-dark` (familiar GitHub
look) and `one-light` / `one-dark-pro` (higher contrast, closer to the MCTL
design tokens). The issue states the choice belongs to the requester and
cannot be inferred from the repository, so a clarification question has been
filed (`human-input/draft.json`).

Today `docs/.vitepress/config.ts` sets no `markdown.theme`, so VitePress
1.6.4 falls back to its built-in Shiki default, which is the
`github-light` / `github-dark` pair. The issue is also marked as a test issue
("Close it after the check. Do not implement."); this proposal is complete so
that an implementer could build it, but the reviewer should honour that note.

## User stories
- AS a docs reader I WANT code blocks highlighted with a deliberately chosen,
  consistent theme SO THAT code is readable and matches the site's look.
- AS a docs maintainer I WANT the theme pinned explicitly in config SO THAT a
  VitePress upgrade cannot silently change how code blocks look.

## Acceptance criteria (EARS)
- WHEN the site is built THE SYSTEM SHALL highlight fenced code blocks using
  the theme pair recorded in `markdown.theme` in `docs/.vitepress/config.ts`,
  as `{ light: <light theme>, dark: <dark theme> }`.
- WHEN the requester has answered the clarification THE SYSTEM SHALL use the
  chosen pair: either `github-light` / `github-dark` or `one-light` /
  `one-dark-pro`.
- IF no answer is available at implementation time THEN THE SYSTEM SHALL use
  `github-light` / `github-dark`, which equals the current VitePress default
  and therefore causes no visual change.
- WHILE `appearance: 'force-dark'` remains set THE SYSTEM SHALL render code
  blocks with the dark theme of the pair on every page.
- WHILE the theme is applied THE SYSTEM SHALL keep rendering ```mermaid
  fences as `<div class="mermaid-diagram">` via the existing
  `markdown.config` fence override.
- WHEN `bun run build` runs THE SYSTEM SHALL complete without errors
  (existing mermaid-links test, llms generation and VitePress build).

## Out of scope
- Enabling a light-mode toggle or changing `appearance: 'force-dark'`.
- Custom or self-authored Shiki themes, or remapping theme colours to MCTL
  design tokens via CSS.
- Changes to code-block chrome in `docs/.vitepress/theme/custom.css`
  (borders, `--vp-code-block-bg`, code-group tabs).
- Any change to deployment (`services/admins/mctl-docs/values.yaml`).

## Open questions
- BLOCKING (clarification filed): which pair does the requester want,
  `github-light` / `github-dark` or `one-light` / `one-dark-pro`? The
  proposal proceeds with `github-light` / `github-dark` as the no-change
  fallback; the only difference between the two outcomes is the two strings
  in `markdown.theme`.
- The site is `appearance: 'force-dark'`, so the light theme of the pair is
  never shown today. It is still configured so the choice holds if a light
  mode is ever enabled.
- `custom.css` sets `--vp-code-block-bg` to `--surface-card` (#15181d). With
  `one-dark-pro`, whose native background is different, the block background
  stays the MCTL surface colour (VitePress uses the CSS variable, not the
  theme background). The reviewer should confirm that is desired.
- The issue says "Do not implement" (test issue). Confirm whether this
  proposal should be approved at all.
