# Tasks: incident-a6a813e1

1. [ ] In the mctl-telegram repo, grep for the log strings "bridge: authentication failed" and "JWT expired" to locate the bridge's session-auth/token code.
2. [ ] Determine the JWT's configured TTL and compare it to the observed ~60s borrow/retry interval; confirm whether the token is refreshed before each borrow or only minted once and reused past expiry.
3. [ ] Apply the smallest fix that keeps the bridge's token valid for the full borrow cycle: either extend the TTL to safely exceed the borrow interval, or add/repair a proactive refresh before each borrow attempt.
4. [ ] Verify the fix locally or via logs: "bridge: authentication failed" / "JWT expired" should no longer recur at a steady cadence.
5. [ ] If the token TTL is a config value (env var or Helm value) rather than hardcoded, bump the corresponding image tag or config in mctl-gitops as needed so the fix is deployed.
