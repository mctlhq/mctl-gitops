# Prepare mkdocs.yml for the 1.56.5 markdown_extensions allowlist

## Context
Backstage 1.56.5 limits TechDocs mkdocs.yml markdown_extensions to known names and removes others with a warning. Docs using other extensions would silently render differently after the upgrade.

## User stories
- AS a platform admin I WANT Prepare mkdocs.yml for the 1.56.5 markdown_extensions allowlist SO THAT the portal stays secure and stable.

## Acceptance criteria (EARS)
- WHEN the portal is upgraded to Backstage >= 1.56.5 THE SYSTEM SHALL build all TechDocs without allowlist warnings.
- IF an mkdocs.yml uses an unlisted extension THEN THE SYSTEM SHALL have it replaced or explicitly reviewed before upgrade.
- WHILE the portal runs THE SYSTEM SHALL NOT set dangerouslyAllowAdditionalExtensions.

## Out of scope
- Backstage major upgrades; changes outside agents/mctl-portal.
