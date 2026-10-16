# Tasks: incident-91756910

1. [ ] Locate the assert-attempt step message ("Neither the primary attempt nor the account-2 fallback succeeded") in mctl-agents and the code writing the needs-triage reason.
2. [ ] Add detection of `oauth_org_not_allowed` / "disabled Claude subscription access" in implementer output and emit an explicit auth/org-policy message (needs human: API key or org admin).
3. [ ] Verify the change looks correct and does not alter credential handling or retry behaviour.
