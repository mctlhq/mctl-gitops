# Design: mermaid-diagrams-guide

## Source commits
- n/a — signal from GitHub releases (no sibling-repo git SHA)
- mermaid-js/mermaid@11.14.0 (2025-04-01) — Wardley Maps beta, TreeView, Neo look, SVG ID fixes
- mermaid-js/mermaid@11.13.0 (2025-03-09) — Venn beta, Ishikawa beta, htmlLabels deprecated

## Current documentation state
- `docs/reference/faq.md` — general-purpose FAQ; nothing about mermaid.
- `docs/reference/troubleshooting.md` — exists; no section on diagrams.
- `docs/mcp/examples.md` — MCP examples, may contain diagrams but is not a diagram guide.
- **Page is missing** — a new location is needed: `docs/reference/diagrams.md`.
- An entry in `.vitepress/config.ts` (or `config.mts`) is also needed — sidebar "Reference" section.

## Proposed solution

### New page: `docs/reference/diagrams.md`

Content (details in `proposed-content.md`):
1. **Introductory paragraph** — mermaid in mctl-docs, current version, link to upstream.
2. **Diagram-types table** — name, stability (stable/beta), short description, code example.
3. **Code examples** — flowchart (basic), sequence diagram (a platform flow), architecture diagram
   (with mctl components), Wardley Map (beta example), Venn (beta), Ishikawa (beta).
4. **htmlLabels deprecation notice** — what is deprecated and how to migrate.
5. **Neo look / style** — description of the new default style.
6. **Best practices** — when to use mermaid vs when a bullet list suffices.

### Update to `.vitepress/config.ts`
Add an entry to the "Reference" sidebar:
```ts
{ text: 'Diagram Types', link: '/reference/diagrams' }
```

## Alternatives
1. **Add separate Q&As about diagrams to the FAQ** — does not scale beyond >5 types;
   rejected.
2. **Link to the upstream mermaid docs only** — contributors are left without examples in the
   mctl platform context; rejected.

## Impact
- VitePress sidebar: yes — add a line in the "Reference" section in `.vitepress/config.ts`.
- Mermaid diagrams: yes — the page itself contains mermaid blocks (verify rendering).
- Versioning: no — applies to the current branch and will be updated together with mermaid bumps.
