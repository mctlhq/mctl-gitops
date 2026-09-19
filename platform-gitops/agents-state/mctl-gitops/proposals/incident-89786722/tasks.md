# Tasks: incident-89786722

1. [ ] In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`,
   add `activeDeadlineSeconds: 7200` to the `run-implementer` template
   (the template starting at `- name: run-implementer`, currently line 238),
   at the same indentation level as `outputs:` / `inputs:` / `container:`.
2. [ ] In the same file, change `spec.activeDeadlineSeconds` from `7200` to
   `16200` (line 59), and update the surrounding comment to explain the new
   split: a 7200s ceiling per implementer attempt (now enforced on the
   `run-implementer` template) plus headroom for a fallback attempt,
   commit-and-push retries, and assert-attempt.
3. [ ] Verify the YAML still parses and the `run-implementer` template block
   is well-formed (correct indentation matching sibling keys).
4. [ ] No image tag bump needed — this is a workflow-template-only config
   change with no code changes to `mctl-agents`.
   Note: if an earlier sibling proposal (incident-89786271 / -89786272 /
   -89786602) already applied this exact change, this task becomes a no-op
   verification instead of a duplicate edit.
