# Tasks: issue-1979-governance-require-reviewed-content-bind

- [ ] 1. Add a `refuse <code> <message>` function to the `flip-status` script in `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`. Add the `refusal_code` output parameter (`valueFrom.path: /tmp/refusal_code`, `default: ""`). — DoD: every refusal path in the new checks prints one `approve_refusal: code=... service=... slug=... expected=... current=...` line on stderr and writes the code file. stdout stays exactly `flipped` or `noop`.
- [ ] 2. Remove the unbound mode (depends on 1). — DoD:
  - An empty `WORKFLOW_EXPECTED_DIGEST` refuses with `approval_content_unbound` before the status is read.
  - The format check runs unconditionally and refuses with `approval_content_digest_malformed`.
  - Both digest comparisons (accepted-noop path and pre-edit mismatch) lose their `[ -n ... ]` guards and refuse with `approval_content_mismatch`.
  - No `.status.yaml` byte changes on any refusal.
- [ ] 3. Bind the record to the reviewed digest (depends on 2). — DoD: the approval block writes `content_digest: '<expected>'` and `digest_binding: 'reviewed'`. The parameter comment says "Required", with no mention of the #658 flip-time fallback. The annotation's step 2 text describes the new contract.
- [ ] 4. Add `scripts/proposal-content-digest.py` (directory and `--rev <commit>` modes, plus `--selftest`). — DoD: the output equals the CWFT-computed digest for the same files. `--selftest` runs the digest loop extracted from the CWFT on a fixture and compares.
- [ ] 5. Add `tests/test_cwft_mctl_agents_approve_digest_binding.py` and wire it, together with `scripts/proposal-content-digest.py --selftest`, into `.github/workflows/validate-manifests.yml` as `run:` steps (depends on 2, 3, 4). — DoD: CI runs both, and both pass on the changed template.
- [ ] 6. File (or link) the mctl-api companion issue. — DoD: the issue covers making `expected_content_digest` required for `mctl-agents-approve` and `mctl_trigger_approve`, refusing before submit with 400 `approval_content_unbound`, recording the code on the failed audit row, and confirming that `approval_ref` is forwarded (see Open questions). It is referenced from the PR description.

## Tests
- [ ] T1. Empty digest on a `proposed` proposal: exit 1, code `approval_content_unbound`, `.status.yaml` unchanged, no `/tmp/status-out`.
- [ ] T2. Empty digest on an `accepted` proposal: exit 1, code `approval_content_unbound` (no silent `noop`).
- [ ] T3. Malformed digest (`sha256:XYZ`, a missing prefix, 63 hex characters): exit 1, code `approval_content_digest_malformed`, file unchanged.
- [ ] T4. Reviewed digest A, then `design.md` edited so the content hashes to B: exit 1, code `approval_content_mismatch`, the message names both A and B, file unchanged.
- [ ] T5. Matching digest: stdout `flipped`, `status: accepted`, `approval.content_digest` equals the supplied digest and the independently computed digest, `approval.digest_binding == 'reviewed'`.
- [ ] T6. Already `accepted` with the same recorded digest: stdout `noop`, exit 0.
- [ ] T7. Already `accepted` with a different or absent recorded digest: exit 1, code `approval_content_mismatch`.
- [ ] T8. Self-binding regression guard: T1 and T4 fail if either `[ -n "$WORKFLOW_EXPECTED_DIGEST" ]` guard is reinstated. Verify by temporarily applying the old guard in the extracted source inside the test (a mutation check), and assert that the mutated script would flip.
- [ ] T9. `scripts/proposal-content-digest.py --selftest` parity with the CWFT loop, including the absent-file framing (`<name>\n-\n`) for a missing `proposed-content.md`.
- [ ] T10. Existing CI still passes: `scripts/validate-shell-param-interpolation.py` (no inline `{{workflow.parameters.*}}` in the new script lines) and `scripts/validate-agents-state-approval.py`.

## Rollback
Revert the PR. The CWFT returns to the optional-digest behaviour, ArgoCD resyncs the ClusterWorkflowTemplate in about 3 minutes, and Workflows submitted after that snapshot the old template. No data migration needs undoing. Records flipped in the meantime carry an extra `approval.digest_binding` key, which is harmless to readers that ignore it and does not need to be removed. The helper script and test are additive and are removed by the same revert.
