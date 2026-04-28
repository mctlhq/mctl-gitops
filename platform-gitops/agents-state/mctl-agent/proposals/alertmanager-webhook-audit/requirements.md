# Audit and Harden POST /api/v1/alerts for AlertManager v0.32.0 Payload Changes

## Context

AlertManager v0.32.0 (released 2026-04-08) introduced several changes to the webhook payload
contract: silence annotations are now included in alert groups, multiple matcher-set silences are
supported, webhook payload templating is available, and new template functions (`dict`, `map`,
`append`) were added. These changes add new optional fields to the JSON payload that
`mctl-agent` receives at `POST /api/v1/alerts`.

The `POST /api/v1/alerts` endpoint is the sole entry point for all self-healing in `mctl-agent`.
Every ticket, PR, skill execution, and Telegram notification originates from a webhook call to
this endpoint. If the Go struct used to decode incoming payloads does not account for the new
fields — or if the decoder is configured to reject unknown fields in production — parse errors or
silent field drops can stall the entire pipeline. The service currently routes 8 PR-capable alert
types and 4 diagnose-only alert types; a silent parse failure would suppress all of them.

## User stories

- AS a platform engineer I WANT the `POST /api/v1/alerts` handler to correctly parse
  AlertManager v0.32.0 webhook payloads SO THAT all existing routed alert types continue to
  create tickets and open PRs without manual intervention after the AlertManager upgrade.
- AS an on-call SRE I WANT silence annotations from AlertManager v0.32.0 payloads to be stored
  in the ticket evidence SO THAT I can see whether an alert was silenced when reviewing a ticket
  in the MCP tools or Telegram notifications.

## Acceptance criteria (EARS)

- WHEN AlertManager sends a v0.32.0 webhook payload (including `SilenceAnnotations` and
  `MatcherSets` fields), THE SYSTEM SHALL parse it without returning an error and SHALL route the
  alert to the correct skill.
- WHEN an unknown field is present in the incoming webhook JSON body, THE SYSTEM SHALL log it at
  WARN level and continue processing the request without dropping the alert.
- WHEN a silence annotation is present in the webhook payload, THE SYSTEM SHALL store it as part
  of the ticket evidence for that alert.
- IF the webhook body cannot be parsed as a valid AlertManager payload, THE SYSTEM SHALL return
  HTTP 400 and SHALL increment the `alertmanager_payload_parse_errors_total` counter.
- WHILE processing alerts, THE SYSTEM SHALL NOT silently drop any alert whose type matches a
  known routed alert type.
- WHEN a v0.31.x AlertManager payload is received (without the new v0.32.0 fields), THE SYSTEM
  SHALL continue to parse and route it correctly, with no regressions.

## Out of scope

- Adding support for alert types not currently in the routed set (8 PR-capable + 4
  diagnose-only). New alert type routing is a separate proposal.
- Implementing a UI or dashboard for viewing silence annotations.
- Changes to AlertManager's configuration, alert rules, or routing trees.
- Full JSON Schema validation of the payload beyond the field-level struct audit performed in
  this proposal.
- Automating AlertManager version tracking via Renovate or similar tooling (a valid but separate
  concern).
