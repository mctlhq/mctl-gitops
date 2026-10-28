# Design: incident-5e7a3cea

## Confidence: LOW

## Diagnosis
The tool-availability SLO fast burn is explained by MCP tool calls returning isError with "no active session" for user_id 245 (list_dialogs, get_unread_messages). The service is otherwise healthy. Root cause is a missing Telegram session for that account; no skill covered this alert.

## Proposed Fix
No gitops value change is evident. Treat as a duplicate of incident-41b2515a. Do not modify the SLO alert rule to hide the failures.

## Scope
Minimal.
