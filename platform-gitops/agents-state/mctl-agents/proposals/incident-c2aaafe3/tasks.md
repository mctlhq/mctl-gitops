# Tasks: incident-c2aaafe3

1. [ ] Locate the mctl-agents Dockerfile in the service repository (services/admins/mctl-agents/Dockerfile)
2. [ ] Find the pip install line that installs Python packages
3. [ ] Add temporalio to the pip install command or requirements list
4. [ ] Verify the Dockerfile syntax is correct
5. [ ] Rebuild the mctl-agents image with the updated Dockerfile
6. [ ] Deploy the new image to the admins namespace
7. [ ] Monitor mctl-agents pod logs to confirm the Temporal worker starts without ModuleNotFoundError
8. [ ] Verify incident-responder and shepherd workflows execute successfully
