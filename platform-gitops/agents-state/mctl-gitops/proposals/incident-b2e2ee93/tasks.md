# Tasks: incident-b2e2ee93

1. [ ] Verify the current resource requests/limits for nfc-monitoring-kube-state-metrics Deployment
2. [ ] Check Deployment events and pod logs for scheduling or image pull failures
3. [ ] Increase CPU/memory requests if node pool capacity is saturated, or scale the node pool
4. [ ] Verify the image is accessible and the tag is correct
5. [ ] Confirm the Deployment rollout completes and at least one replica is Running
6. [ ] Verify AlertManager alert clears after Deployment is healthy
