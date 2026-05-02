# Alertmanager v0.32.x Webhook Contract: Validate and Harden POST /api/v1/alerts

## Context
mctl-agent's core ingestion path is `POST /api/v1/alerts`, which receives AlertManager webhook payloads and converts them into internal tickets. The parsing logic was written against an earlier AlertManager webhook schema. AlertManager v0.32.0 (released 2026-04-08, latest: v0.32.1 on 2026-04-29) introduced two changes that may affect the payload structure:

1. **Webhook payload templating** — operators can now customise the webhook body using Go templates, potentially changing field names, adding new top-level keys, or altering nested structures.
2. **Multiple matcher set silences** — the `matchers` field in silence objects now supports an array of matcher sets (OR logic), changing the silence object schema.

If the platform upgrades its AlertManager instance to v0.32.x and the mctl-agent handler silently misparses the new envelope, alert ingestion stops entirely — the service receives POST requests but creates no tickets and no self-healing occurs. This is a silent failure mode with high operational impact.

This proposal validates the current parser against the v0.32.x schema and hardens it so unknown or restructured fields degrade gracefully rather than silently.

## User stories
- AS a platform engineer I WANT the `POST /api/v1/alerts` handler to correctly parse AlertManager v0.32.x payloads SO THAT alert ingestion continues working after the platform's AlertManager upgrade.
- AS an on-call engineer I WANT the handler to log a structured warning when it receives an unrecognised payload field SO THAT schema drift is visible in logs rather than silently dropped.
- AS a developer I WANT the handler to be tested against the canonical v0.32.x AlertManager webhook schema SO THAT regressions are caught in CI before deployment.

## Acceptance criteria (EARS)
- WHEN the handler receives an AlertManager v0.32.x webhook payload, THE SYSTEM SHALL correctly parse `alerts[].labels`, `alerts[].annotations`, `alerts[].status`, `alerts[].startsAt`, and `alerts[].endsAt` into the internal ticket structure.
- WHEN the payload contains a top-level `groupLabels` or `commonLabels` field with template-expanded values, THE SYSTEM SHALL retain those values in the ticket's metadata without error.
- WHEN the payload contains an unrecognised top-level field, THE SYSTEM SHALL log a WARNING with the field name and continue processing rather than returning a 400 or dropping the entire payload.
- WHEN the `silences` array contains a silence with multiple matcher sets (v0.32.x format), THE SYSTEM SHALL parse the silence without error and apply it correctly to alert suppression logic.
- WHILE the AlertManager version is ≤ v0.31.x, THE SYSTEM SHALL continue to parse the legacy webhook format without regressions (backward compatibility).
- IF the webhook body cannot be decoded as JSON, THE SYSTEM SHALL return HTTP 400 with a structured error body and log at ERROR level (existing behaviour must not regress).
- WHEN the handler is started, THE SYSTEM SHALL log the AlertManager webhook schema version it was built against (e.g. `alertmanager_schema_version=v0.32`) as a structured field at INFO level.

## Out of scope
- Handling all AlertManager alert types — only the 12 routed alert types defined in `context/architecture.md` are in scope (per the known constraint: "Do not propose handling ALL AlertManager alerts").
- Changing the URL or authentication mechanism of the webhook endpoint.
- Modifying AlertManager configuration or templates on the platform side.
- Support for AlertManager v0.33.x or later (tracked in a future proposal).
