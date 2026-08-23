# Tasks: incident-87490553

1. [ ] Locate post-deploy-verify implementation in mctl-agents orchestrator source
2. [ ] Identify the DEGRADED_STATE_GRACE_PERIOD_SECONDS variable or equivalent timeout
3. [ ] Increase grace period from 120 seconds to 240 seconds
4. [ ] Add one-time retry logic: if app is still Degraded after grace period, wait and check again (one retry)
5. [ ] Verify the logic correctly handles both transient and persistent Degraded states
6. [ ] Test the change locally or in a preview environment
7. [ ] After merge, monitor the next scheduled shepherd run (typically Saturday 00:00 UTC) to confirm the workflow completes
8. [ ] If labs-mctl-telegram is still Degraded after the extended grace period, create a follow-up incident for the mctl-telegram service
