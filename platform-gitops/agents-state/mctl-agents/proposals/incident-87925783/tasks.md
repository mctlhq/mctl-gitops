# Tasks: incident-87925783

1. [ ] Check Dockerfile for Python dependencies - verify `temporalio` package is listed in requirements.txt or setup.py
2. [ ] Add `temporalio` to Python dependencies if missing (check version compatibility with installed temporalio server)
3. [ ] Verify Kubernetes deployment values.yaml has volumeMounts for /workdir/mctl-gitops
4. [ ] Verify volume definition points to correct persistent volume or volume claim
5. [ ] Rebuild mctl-agents Docker image with updated dependencies
6. [ ] Push new image tag to registry
7. [ ] Update mctl-agents service image.tag in values.yaml to the new build
8. [ ] Trigger manual test deployment and verify Temporal worker starts successfully
