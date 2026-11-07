# Tasks: incident-94044279

1. [ ] Read the .status.yaml of proposal issue-1026-devloop-part-m-m2b-1a-worker-restart-gap under agents-state/mctl-agents/proposals/ and note the needs-triage reason.
2. [ ] If the reason is a usage limit / HTTP 429 or an unset fallback token, make no change and state that in the output; do not touch secrets.
3. [ ] If the reason is a different, concrete failure, apply the minimal fix for that single cause and verify the change looks correct.
