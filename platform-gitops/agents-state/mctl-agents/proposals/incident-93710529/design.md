# Design: incident-93710529

## Confidence: LOW

## Diagnosis
The shepherd run itself exited normally in the logs read, but its single `gh api graphql` call for the PR snapshot of mctlhq/mctl-agents#990 hit a GitHub HTTP 503 ("No server is currently available"). The shepherd treated this as "could not fetch PR snapshot", returned `wait`, and advanced nothing; the workflow's assert-attempt step then marked both attempts Failed and printed a message that blames Claude usage limits, which is misleading here. The root cause is a transient GitHub outage with no retry in the snapshot fetch. No skill matched because this is a generic workflow_failed incident. The implementer should verify against the current orchestrator code before applying, and confirm the failure is not recurring (a single 503 may need no change beyond retry).

## Proposed Fix
In the mctl-agents orchestrator, in the shepherd's GraphQL PR snapshot helper (the function that runs `gh api graphql` and emits "warn: gh graphql failed"), retry up to 3 times with exponential backoff (for example 2s, 4s, 8s) when the error is HTTP 502/503/504 or a network error. Do not retry on 4xx. Separately, make the assert-attempt message list "PR snapshot fetch error (GitHub 5xx)" as a possible cause alongside the usage limit.

## Scope
Minimal. Only the snapshot fetch retry and the assert-attempt message text. Do not change budget caps, auth, or merge logic.
