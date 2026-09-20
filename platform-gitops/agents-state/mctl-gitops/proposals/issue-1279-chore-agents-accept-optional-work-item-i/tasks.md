# Tasks: issue-1279-chore-agents-accept-optional-work-item-i

All edits are in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`
unless stated otherwise. One commit, one PR, feature branch (this is a template
change, so the `gitops-bump` / `release-deploy` direct-to-main exception in
`CLAUDE.md` does not apply).

- [ ] 1. Declare `work_item_id` and `execution_id` in
      `spec.arguments.parameters`, after the existing `agent_version` entry
      (currently ends at line 91). Both `value: ""`. Each carries a comment in
      the style of the neighbouring entries stating: optional; minted by the
      caller; forwarded as `--work-item-id` / `--execution-id`; omitted
      entirely when empty; no default invented; consumed by
      `mctl-agents#267`; and that the flags require an `agent_image` from the
      mctl-agents release that added them (the same shape as the existing
      "pin >=1.11.0" note on `run-investigator`).
      — DoD: `python3 -c "import yaml,sys; d=yaml.safe_load(open(...)); print([p['name'] for p in d['spec']['arguments']['parameters']])"`
      prints `['issue_url', 'agent_image', 'agent_version', 'work_item_id', 'execution_id']`,
      and both new entries have `value` equal to the empty string.

- [ ] 2. Bind both parameters as environment variables on the
      `run-investigator` template's `container.env` (depends on 1), beside the
      existing `WORKFLOW_ISSUE_URL` entry at lines 490-495:
      `WORKFLOW_WORK_ITEM_ID` -> `{{workflow.parameters.work_item_id}}` and
      `WORKFLOW_EXECUTION_ID` -> `{{workflow.parameters.execution_id}}`, under
      a comment pointing at `scripts/validate-shell-param-interpolation.py` as
      the thing that enforces this rather than convention.
      — DoD: both names appear exactly once in that template's `env`; no
      `{{workflow.parameters.work_item_id}}` or
      `{{workflow.parameters.execution_id}}` appears anywhere inside
      `container.args`, `script.source`, or an `initContainers` command in the
      file. Do NOT add either name to that script's `CONSTRAINED` set.

- [ ] 3. Append the two flags conditionally in the `run-investigator`
      `container.args` shell body (depends on 2), inserted between the existing
      `set -- python -m orchestrator.run_issue_investigator --issue-url
      "$WORKFLOW_ISSUE_URL"` (lines 338-339) and the `printf '→'` echo block
      (lines 340-342), using the `[ -n "$VAR" ]` idiom verbatim from
      `cwft-mctl-agents-implement.yaml:411-417`:
      `if [ -n "$WORKFLOW_WORK_ITEM_ID" ]; then set -- "$@" --work-item-id "$WORKFLOW_WORK_ITEM_ID"; fi`
      and the same for `--execution-id`. `--issue-url` stays first and
      unconditional; the `[ -z "$WORKFLOW_ISSUE_URL" ]` fail-fast guard above
      is untouched.
      — DoD: the block sits strictly before the `printf ' %s' "$@"` line and
      strictly after the seeding `set --`; nothing is added after the
      `set +e; "$@"` invocation at lines 352-356; the `[ "$VAR" = "true" ]`
      boolean idiom is NOT used (these are value flags, not store-true flags).

- [ ] 4. Confirm the sibling steps are deliberately untouched (depends on 3):
      no change to `commit-and-push` (commit message still
      `chore(agents): investigate ${WORKFLOW_ISSUE_URL} ${DATE}`), no change to
      `notify-telegram` (the incident `FINGERPRINT` stays
      `workflow_failed:${WORKFLOW_TEMPLATE_KIND}:${WORKFLOW_ISSUE_URL}`), no
      change to `assert-attempt`, and no change to the `investigate-issue`
      steps block — the fallback inherits the same `run-investigator` template
      and therefore the same env, so there is nothing to thread there.
      — DoD: `git diff --stat` on the PR shows one YAML file changed plus the
      test and its CI step from tasks 5-6; the diff hunks in the YAML are
      confined to `spec.arguments.parameters` and the `run-investigator`
      template.

- [ ] 5. Add `tests/test_cwft_investigate_work_context_argv.py` (depends on 3)
      — loads the CWFT with `yaml.safe_load`, slices the argv-building region
      **verbatim** out of the `run-investigator` template's
      `container.args[2]` (from the `if [ -z "$WORKFLOW_ISSUE_URL" ]` guard
      through the trailing `printf '\n'`), and runs that slice under
      `/bin/sh` with the env vars set per case, asserting on the captured
      `→ ...` line. Follows the extract-don't-restate convention documented in
      `tests/test_tpl_git_commit_yq.py` and
      `tests/test_rotate_github_token_scope.py`. The slice must not invoke
      python — the real call is further down the body, after `set +e`.
      — DoD: `python3 tests/test_cwft_investigate_work_context_argv.py` exits 0
      against the edited template, and fails if the slice markers cannot be
      found (a rename must break the test loudly, not skip it).

- [ ] 6. Wire the test into `.github/workflows/validate-manifests.yml`
      (depends on 5) as a `run: python3 tests/test_cwft_investigate_work_context_argv.py`
      step, placed beside the existing "Unit-test the release-deploy bump
      script" step, with a comment saying why the assertion exists (the
      omit-both argv is a cross-repo compatibility contract, not a style
      preference).
      — DoD: the step is present in the `validate` job and the job is green on
      the PR.

- [ ] 7. Post-merge verification (depends on 4-6) — wait ~3 minutes for ArgoCD
      to sync the `ClusterWorkflowTemplate` (`CLAUDE.md`: Argo snapshots
      templates at submit time), then run test T4 below against the live
      cluster.
      — DoD: the archived step log for a real omit-both investigate run shows
      `→ python -m orchestrator.run_issue_investigator --issue-url <url>` with
      no trailing flags.

## Tests

- [ ] T1. Omit-both case — neither `WORKFLOW_WORK_ITEM_ID` nor
      `WORKFLOW_EXECUTION_ID` set (and separately: both set to `""`). Asserts
      the echoed argv is exactly
      `python -m orchestrator.run_issue_investigator --issue-url https://github.com/mctlhq/x/issues/1`.
      This is the acceptance criterion "the command line unchanged from today"
      and is the single most important assertion in the file.
- [ ] T2. Both-set case — asserts the echoed argv is exactly
      `python -m orchestrator.run_issue_investigator --issue-url <url>
      --work-item-id wi-abc --execution-id ex-123`, in that order.
- [ ] T3. One-of-two cases, parameterised over both directions — only
      `work_item_id` set yields `--work-item-id` and no `--execution-id`; only
      `execution_id` set yields `--execution-id` and no `--work-item-id`.
      Covers "omitted entirely when unset" independently for each flag.
- [ ] T4. Injection case — set `WORKFLOW_WORK_ITEM_ID` to
      `; touch /tmp/pwned-$$` and `WORKFLOW_EXECUTION_ID` to `a" ; id ; "b`,
      run the slice, and assert the sentinel file does not exist and the value
      survives as one argv token. Proves the `set --` construction, not just
      the `if` guards.
- [ ] T5. Required-parameter regression — empty `WORKFLOW_ISSUE_URL` with both
      new identifiers set still exits non-zero with the existing
      `issue_url parameter is required` message. The new code must not make an
      invalid submit look runnable.
- [ ] T6. Static gates, unchanged and unsuppressed —
      `scripts/validate-shell-param-interpolation.py --selftest` then
      `scripts/validate-shell-param-interpolation.py` both pass with no new
      `BASELINE` or `CONSTRAINED` entry; `yamllint` (relaxed, per
      `.github/workflows/yamllint.yml`) and the `kubeconform` step in
      `validate-manifests.yml` both pass on the edited file.
- [ ] T7. Live smoke, post-merge — submit an investigate run the existing way
      (omitting both parameters, e.g. via `mctl_trigger_issue`) and read the
      archived `run-investigator` step log with `mctl_get_workflow_logs`;
      the `→` line must show no new flags and the run must reach
      `assert-attempt` as it did before. The both-set half of this smoke test
      is blocked on `mctl-api#335` and on an `agent_image` containing the
      `mctl-agents#267` flags — record it as pending rather than forcing it.

## Rollback

Revert the single PR commit. The template returns byte-for-byte to its current
state; ArgoCD reconciles it within ~3 minutes, and any workflow already
submitted keeps running against the snapshot it captured at submit time, so no
in-flight run is disturbed.

Nothing can be stranded by the revert: until `mctlhq/mctl-api#335` ships, no
caller is able to send the two parameters at all, and after it ships a submit
carrying them against the reverted template is either rejected by the registry
or — if the registry allows them while Argo no longer declares them — fails at
submit with an unknown-parameter error rather than running with the
identifiers silently dropped. There is no persisted state, no artifact schema,
and no committed file whose shape depends on this change.

If the flags turn out to break a run because the pinned `agent_image` predates
`mctl-agents#267` (the argparse exit-2 path described in `design.md`), the
narrower rollback is to stop passing the parameters at the caller — no gitops
change at all — because an omitted parameter reproduces today's behaviour
exactly. Reverting this commit is the wider option and is only needed if the
template itself is implicated.
