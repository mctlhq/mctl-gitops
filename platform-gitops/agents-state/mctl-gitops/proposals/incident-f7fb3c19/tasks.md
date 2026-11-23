# Tasks: incident-f7fb3c19

1. [ ] Determine which child Application of root-app is Degraded and read its health message.
2. [ ] Edit the single offending value or manifest in mctl-gitops for that child.
3. [ ] Verify the change is minimal and does not touch root-app or sync policy.
4. [ ] If no child is Degraded, make no change and report the alert as transient.
