# Tasks: incident-93696306

1. [ ] Find the admins tenant ResourceQuota definition (admins-quota) in mctl-gitops and note current requests.memory (2Gi).
2. [ ] Raise requests.memory to 2560Mi (or apply Option B in design.md if the quota cannot change); confirm limits.memory and cluster headroom still fit.
3. [ ] Verify the diff touches only that field and the YAML renders; no image tag bump needed (1.117.0 is already configured).
