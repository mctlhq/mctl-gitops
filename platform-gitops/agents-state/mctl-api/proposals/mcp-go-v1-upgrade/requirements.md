# Upgrade mark3labs/mcp-go 0.31 to 1.5.0

## Context
We run mcp-go 0.31 (ADR 0001). v1.5.0 (30 Oct) bounds the SSE message endpoint body read (#1119), refuses subscriptions/listen when the response cannot stream (#1138), delivers per-request notifications on the POST stream (#1117), and fixes OAuth localhost redirect host handling (#1125). These harden the public MCP endpoint. A client-transport redirect credential-leak report exists (nil CheckRedirect); exact ID unconfirmed, relevant only if we use the client transport.

## User stories
- AS a platform operator I WANT bounded request reads on the MCP endpoint SO THAT oversized payloads cannot exhaust memory.
- AS a Claude.ai connector user I WANT the OAuth flow to stay compatible SO THAT the connector keeps working.

## Acceptance criteria (EARS)
- WHEN the service is built THE SYSTEM SHALL depend on github.com/mark3labs/mcp-go v1.5.0.
- WHEN a client posts an oversized body to the SSE message endpoint THE SYSTEM SHALL reject it without unbounded buffering.
- WHEN any of the 24 MCP tools is invoked THE SYSTEM SHALL return results identical in schema to the pre-upgrade behavior.
- WHILE auth is required THE SYSTEM SHALL continue to check org membership on all write tools.
- IF the MCP Inspector validation fails for any tool THEN THE SYSTEM SHALL NOT proceed with the upgrade.

## Out of scope
- Replacing mcp-go or changing transport (forbidden by ADR 0001).
- Adding new MCP tools.
