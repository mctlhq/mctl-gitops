# Tasks: incident-87497762

1. [ ] Access mctl-telegram service code and identify session initialization logic in the MCP tool layer
2. [ ] Check recent changes in the current deployed version (0.50.1) that might have affected session management
3. [ ] Verify that session state is being properly initialized when the service container starts
4. [ ] Review logs for any initialization errors or warnings related to MCP connections or session setup
5. [ ] Add debugging or logging to understand why user_id=1 (canary probe) has "no active session"
6. [ ] Identify the root cause of the missing session state
7. [ ] Implement the fix (code or configuration change)
8. [ ] Deploy the fixed version to labs-mctl-telegram
9. [ ] Verify the canary probe now passes with ok=true
10. [ ] Confirm the service health changes from Degraded to Healthy in ArgoCD
