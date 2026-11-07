# Evaluate Zensical TechDocs engine ahead of Material for MkDocs sunset

## Context
Backstage 1.56.3 adds an experimental Zensical engine for TechDocs as a migration path before Material for MkDocs shuts down. We use TechDocs, so we need a plan before a forced migration. A related TechDocs CVE (markdown_extensions injection) is addressed separately in backstage-security-patch-bundle.

## User stories
- AS a platform admin I WANT a tested migration path SO THAT TechDocs keeps working when Material for MkDocs is retired.

## Acceptance criteria (EARS)
- WHEN the spike is run THE SYSTEM SHALL build at least three representative docs sites with the Zensical module in a non-production environment.
- WHEN the spike finishes THE SYSTEM SHALL produce a written go/no-go report with differences, build time and memory figures.
- WHILE the spike runs THE SYSTEM SHALL NOT change production TechDocs configuration in `admins` or any workload in `labs`.
- IF Zensical output is not equivalent for existing docs THEN THE SYSTEM SHALL record the gaps and defer adoption.

## Out of scope
- Production cutover; docs content rewrites; replacing TechDocs.
