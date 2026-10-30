# Design: issue-1979-governance-require-reviewed-content-bind

## Current state

### The approve CWFT
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml` (ClusterWorkflowTemplate `mctl-agents-approve`) has two steps: `flip-status` and `commit-and-push`. `commit-and-push` runs only when `flip`'s result is `flipped`.

- Parameter `expected_content_digest` defaults to `""`. Its comment reads: "Empty keeps the #658 behaviour: record the digest of whatever is there at flip time."
- `flip-status` script (env `WORKFLOW_EXPECTED_DIGEST`):
  - validates the format only `if [ -n "$WORKFLOW_EXPECTED_DIGEST" ]`;
  - on `status: accepted`, compares the recorded `content_digest` with the expected one only when an expected digest is set. Otherwise it is an unconditional `noop`;
  - computes `CONTENT_DIGEST` over `requirements.md design.md tasks.md proposed-content.md`, framed as `<name>\n<len>\n<bytes>` or `<name>\n-\n`, then SHA-256. This must match mctl-agents `proposal_state.proposal_content_digest`;
  - refuses on a mismatch only `if [ -n "$WORKFLOW_EXPECTED_DIGEST" ] && [ "$CONTENT_DIGEST" != "$WORKFLOW_EXPECTED_DIGEST" ]`;
  - writes `approval: {approved_by, approved_at, content_digest: $CONTENT_DIGEST}` and an optional `approval_ref`.
- So with an empty digest, the bytes first observed in the pod's fresh `git clone --depth=1` become the approved content. This is the self-binding the issue describes.
- Refusals are free-text `echo "❌ ..." >&2; exit 1`. There is no typed code and no output parameter. The `flip-status` outputs are only the `status-update` artifact and the stdout `result`.

### Other gitops pieces
- `scripts/validate-agents-state-approval.py` (CI step "Validate agents-state approval records" in `.github/workflows/validate-manifests.yml`) checks only that a gated `accepted` record names a real approver. It mirrors mctl-agents `human_approval_satisfied()` and does not look at digests.
- `tests/test_cwft_shepherd_commit_pathspecs.py` sets the precedent of extracting a CWFT's real `script.source` with `yaml.safe_load` and running it in a scratch git repo. The `tests/test_cwft_*.py` files are wired as explicit `python3 tests/...` steps in `validate-manifests.yml`. No test covers `cwft-mctl-agents-approve.yaml` today.

### Callers, from the CWFT annotation and the mctl-api manifest
- The Temporal DevLoopWorkflow, via the mctl-api operation `mctl-agents-approve`, after the `aar_` grant is verified and spent. mctl-api sets `expected_content_digest` from the grant's `artifact_hash`.
- `mctl_trigger_approve` (MCP), which posts straight to `/api/v1/operations/mctl-agents-approve/execute` with `expected_content_digest` optional. This is noted in the mctlhq/.github#182 spike design at `agents-state/.github/proposals/issue-182-spike-evaluate-mctl-governance-beyond-hu/design.md`, which read mctl-api `internal/operations/registry.go` and `internal/mcp/server.go`.
- A hand-submitted Workflow referencing the CWFT.
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` sets `MCTL_AGENTS_APPROVE_LEGACY_APPROVER: "false"`. With that setting, a DevLoop approve without a grant gets 409 `approval_grant_missing`, and a relayed approver gets 400. Direct admin calls are still possible.

### Deployed state checked
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api image `ghcr.io/mctlhq/mctl-api` tag `4.107.0`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: mctl-agents tag `1.86.1`.
- `mctl_list_recent_operations` (last 50 audit entries, 2026-10-19):
  - The only `mctl-agents-approve` execution is a DevLoop grant spend at 05:16:30 for `mctl-api/issue-700-...`.
  - That execution carries `expected_content_digest=sha256:9b0ce40c...` and `grant_ref=aar_9191404a...`. It is preceded by `action_approval.decision` and `action_approval.consume` with the same `artifact_hash`.
  - No digest-less direct approve appears in that window. The window is short, so older direct use is not observed. That is not the same as observed absent.
- `platform-gitops/agents-state/*/proposals/*/.status.yaml` in the clone:
  - 8 records carry `approval.content_digest` without `approval_ref`. They are all `merged` and were approved between 2026-10-17 and 2026-10-19.
  - One of them is `mctl-api/issue-700-...`, which was approved through a grant according to the audit log. Either the deployed mctl-api does not yet forward `approval_ref`, or the record cannot distinguish a grant approval from an unbound one. This is recorded under Open questions in requirements.md.
- The CWFT's git history is shallow in this clone (`git log` shows only `8c0f9d3`), so the date the `approval_ref` parameter landed was not observed.

## Proposed solution

Make the CWFT the enforcement point. It is the only writer that every caller (DevLoop, MCP, hand-submitted Workflow) passes through, and it is the only place that sees the bytes that will be committed. A rule enforced only in mctl-api would leave hand-submitted Workflows unbound.

### 1. Remove the unbound mode in `flip-status`
- Change the `expected_content_digest` parameter comment to "Required." The default value stays `""` so that an omitted argument resolves and is refused with a typed code, rather than failing Argo submission with an opaque error.
- At the top of the script, before any status read: if `WORKFLOW_EXPECTED_DIGEST` is empty, call `refuse approval_content_unbound`. Validate the format unconditionally after that, calling `refuse approval_content_digest_malformed`.
- Drop the `[ -n "$WORKFLOW_EXPECTED_DIGEST" ] &&` guards in front of the accepted-path comparison and the mismatch comparison. Both comparisons become unconditional. An accepted record with a missing or different digest calls `refuse approval_content_mismatch`.
- Write `content_digest: '$WORKFLOW_EXPECTED_DIGEST'`, the reviewed value, which by this point equals `CONTENT_DIGEST`. Also write a new line, `digest_binding: 'reviewed'`. A reader can then tell a record bound by this version from a pre-change record whose digest may be self-bound. mctl-agents ignores unknown approval keys today, which is to be confirmed in the follow-up noted in Open questions.
- All checks still happen before the first `sed -i` / `printf >>` on `.status.yaml`. That ordering is what "rejected before state changes" means here.

### 2. Typed refusal evidence
- Add a shell function `refuse <code> <message>`. It:
  - prints the human message;
  - prints one line, `approve_refusal: code=<code> service=<svc> slug=<slug> expected=<digest|-> current=<digest|->`, on stderr. The values are already constrained to safe charsets by the existing guards;
  - writes `<code>` to `/tmp/refusal_code`;
  - runs `exit 1`.
- Add the output parameter `refusal_code` (`valueFrom.path: /tmp/refusal_code`, `default: ""`) to `flip-status`. The closed code set is `approval_content_unbound`, `approval_content_mismatch` and `approval_content_digest_malformed`.
- Other existing failures (missing service/slug, bad status) keep their messages. They may adopt `refuse` with existing-shaped codes, but this proposal does not require it.
- stdout stays exactly `flipped` or `noop`, so the step-list `when` is unaffected.

### 3. A digest helper for direct approvers
- New file `scripts/proposal-content-digest.py`.
- It computes the same framing (file order `requirements.md design.md tasks.md proposed-content.md`) over a proposal directory, or over `git show <rev>:<path>` with `--rev`.
- An admin reviewing a proposal at commit X runs `scripts/proposal-content-digest.py --rev X platform-gitops/agents-state/<svc>/proposals/<slug>` and passes the output to `mctl_trigger_approve` as `expected_content_digest`.
- Its self-test pins parity with the CWFT by running the extracted CWFT digest loop on the same fixture.

### 4. Regression tests
- New test `tests/test_cwft_mctl_agents_approve_digest_binding.py`, following the pattern of `test_cwft_shepherd_commit_pathspecs.py`.
- It loads the template, extracts the `flip-status` `script.source`, and rewrites the `/workdir/mctl-gitops` prefix to a temp dir. It then runs the source with `sh` against fixture proposals, with `WORKFLOW_*` env set.
- It asserts on exit code, the stdout result, the `approve_refusal` code, the `/tmp/refusal_code` contents (redirected per test), and that `.status.yaml` bytes are unchanged on every refusal.
- Add it as a `run: python3 tests/...` step in `validate-manifests.yml`.

### 5. Documentation
- Update the CWFT annotation (step 2 text and "Triggered by").
- Point the companion mctl-api issue at the new contract: make the operation parameter required and return 400 `approval_content_unbound` before submit, attach the code to the audit row, and change the `mctl_trigger_approve` description.

## Alternatives
- **Keep the unbound mode behind an explicit flag** (for example `binding_mode=unbound`, recorded as `digest_binding: 'unbound'`). Dropped. Audit evidence shows no current caller needs it. The issue prefers removal, and an opt-in switch is exactly the kind of mode that gets passed by default later. If a need appears, the typed refusal makes it visible, and the caller can supply a digest computed with the new helper.
- **Enforce only in mctl-api** (make the operation parameter required). Dropped as the sole fix. A hand-submitted Workflow bypasses mctl-api, and the CWFT would still self-bind. This is kept as a complementary companion change.
- **A CI validator that flags `accepted` records without `digest_binding: reviewed`.** Dropped for now. Historical records legitimately lack it, and the cutover cannot be dated from the record alone. A commit-range-based check adds complexity for little gain once the only writer refuses unbound flips. It can be revisited when mctl-agents starts requiring the field.

## Platform impact
- **Migrations:** none. Existing `.status.yaml` records are untouched. The new `digest_binding` key appears only on records flipped after rollout.
- **Backward compatibility:**
  - The DevLoop path always sends the grant's `artifact_hash`, so it is unchanged, including idempotent retries: an accepted record carrying the same digest stays a `noop`.
  - A direct `mctl_trigger_approve` without a digest stops working and fails with `approval_content_unbound`. This is the intended break.
  - An accepted record approved before #658 (no `content_digest`) can no longer be re-approved as a `noop`. Such a record is only re-approved by a retry, which would carry a digest that cannot match, so refusal is correct.
- **Ordering:** this change can land before the mctl-api companion change. The CWFT then becomes the refusal point. After mctl-api lands, the refusal moves earlier, to before submit. Per CLAUDE.md, wait about 3 minutes after merge for the ArgoCD sync before relying on the new behaviour.
- **Resources:** none. This is the same pod with a few extra shell lines.
- **Risks and mitigations:**
  - Argo might not collect `outputs.parameters` from a step that exits non-zero, which would leave `refusal_code` empty. The stderr `approve_refusal:` line is the primary evidence and is always present. The implementer should verify output collection on the deployed Argo version, and the test covers the file contents.
  - Digest framing drift between the helper, the CWFT and mctl-agents. The helper's self-test runs the extracted CWFT loop, and the CWFT comment already points at mctl-agents `tests/test_proposal_digest.py`.
  - Writing the expected rather than the computed digest could hide a bug. This is mitigated because the unconditional equality check precedes the write, and the test asserts equality with the computed digest on the happy path.
