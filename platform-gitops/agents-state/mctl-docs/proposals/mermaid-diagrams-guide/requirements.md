# Mermaid Diagram Types Guide for mctl Docs Contributors

## Context

mctl-docs uses mermaid 11.x to render diagrams in VitePress. Over the last two months
(mermaid@11.13.0 — 2025-03-09, mermaid@11.14.0 — 2025-04-01) new diagram types were added:
Wardley Maps (beta), TreeView, Venn (beta), Ishikawa/fishbone (beta), and the default style
("Neo look") was updated. At the same time the `htmlLabels` parameter for flowchart was
deprecated — potentially breaking existing diagrams.

docs.mctl.ai has no page for documentation authors describing the available diagram types,
syntax and best practices. This complicates onboarding for new contributors and makes it
harder to organically use the new mermaid capabilities to enrich platform documentation.

Source: mermaid@11.14.0 (2025-04-01), mermaid@11.13.0 (2025-03-09).

## User stories

- AS **documentation contributor** I WANT a reference page listing all supported mermaid diagram types
  SO THAT I can choose the right diagram for my content without reading the mermaid.js upstream docs.
- AS **platform engineer** I WANT to know which diagram types are stable vs beta in the current mermaid version
  SO THAT I don't ship beta-only diagrams into production docs without a disclaimer.
- AS **tenant owner contributing docs** I WANT code examples for common diagram types
  SO THAT I can copy-paste and adapt them without syntax errors.
- AS **docs maintainer** I WANT a note about `htmlLabels` deprecation
  SO THAT I can audit existing diagrams and update them before they break at the next mermaid bump.

## Acceptance criteria (EARS)

- WHEN a contributor reads `docs/reference/diagrams.md`
  THE SYSTEM SHALL list all mermaid diagram types available in mermaid 11.x, grouped by stability (stable / beta).
- WHEN a contributor reads the page
  THE SYSTEM SHALL provide a working code example for at least: flowchart, sequence, architecture, Wardley Map.
- IF a diagram type is in beta
  THEN THE SYSTEM SHALL display a `::: warning Beta` callout for that type.
- WHEN a contributor checks the `htmlLabels` section
  THE SYSTEM SHALL clearly state that `htmlLabels` is deprecated in mermaid 11.13+ and show the migration path.
- WHILE VitePress sidebar is updated
  THE SYSTEM SHALL include `diagrams.md` under the "Reference" nav section.

## Out of scope

- Full mermaid upstream documentation mirror (too much maintenance burden).
- Mermaid config customisation beyond what mctl-docs already enables.
- Video tutorials or interactive playground embedding.
- Coverage of diagram types outside mermaid 11.x (e.g. PlantUML, draw.io).
