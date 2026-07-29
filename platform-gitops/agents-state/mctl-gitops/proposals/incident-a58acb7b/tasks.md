# Tasks: incident-a58acb7b

1. [ ] Examine the Argo Workflows alertmanager rules or resource configuration in mctl-gitops
2. [ ] Increase the pod ContainerWaiting alert timeout from 1 hour to 2 hours, or increase Argo Workflows controller CPU/memory requests
3. [ ] If a rule change was made, verify the updated rule syntax and that it targets only long-hanging pods
4. [ ] If a resource limit was increased, verify Argo Workflows controller replicas and pod resource allocations look correct
5. [ ] Monitor the argo-workflows tenant for recurrence of this alert after deployment
