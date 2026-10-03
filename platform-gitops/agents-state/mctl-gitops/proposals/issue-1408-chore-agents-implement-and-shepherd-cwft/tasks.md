# Tasks: issue-1408-chore-agents-implement-and-shepherd-cwft

All edits are in this repo, on a feature branch with a PR: these are
ClusterWorkflowTemplate changes, so the `gitops-bump` / `release-deploy`
direct-to-main exception in `CLAUDE.md` does not apply. Four files change:
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`,
`.../cwft-mctl-agents-shepherd.yaml`,
`tests/test_cwft_implement_shepherd_work_context_env.py` (new) and
`.github/workflows/validate-manifests.yml`.

- [ ] 1. Declare the five optional parameters in
      `cwft-mctl-agents-implement.yaml` `spec.arguments.parameters`, appended
      after the existing `agent_version` entry (block currently ends at line
      116): `work_item_id`, `execution_id`, `temporal_workflow_id`,
      `temporal_run_id`, `execution_request_id`, each `value: ""`. Each carries
      a comment in the voice of the neighbouring entries stating: optional,
      minted by the dev-loop control plane; correlation only, carried to the
      runner as env and **NOT** forwarded as a CLI flag (unlike
      `cwft-mctl-agents-investigate.yaml`, whose `run_issue_investigator.py`
      has those flags); empty means absent and no value is derived; read by the
      usage producer (`mctl-agents orchestrator/usage_ledger.py`) beside the
      existing `WORKFLOW_NAME` join key; mirrors gitops#1279; owner decision 4
      of mctlhq/.github#50.
      — DoD: `python3 -c` with `yaml.safe_load` prints the parameter names as
      `['service', 'slug', 'force', 'max_proposals', 'agent_image',
      'agent_version', 'work_item_id', 'execution_id', 'temporal_workflow_id',
      'temporal_run_id', 'execution_request_id']` and each of the five new
      entries has `value` equal to the empty string.

- [ ] 2. Same declaration in `cwft-mctl-agents-shepherd.yaml`, appended after
      its `agent_version` entry (block currently ends at line 132), with the
      same five names, the same `value: ""`, and the same comment adapted to
      `run_shepherd.py` (depends on 1 only for comment wording consistency).
      — DoD: the parameter list reads `['service', 'slug', 'dry_run',
      'agent_image', 'agent_version', 'work_item_id', 'execution_id',
      'temporal_workflow_id', 'temporal_run_id', 'execution_request_id']`, all
      five new defaults empty.

- [ ] 3. Bind the five as env vars on `run-implementer`'s `container.env`
      (depends on 1), placed beside the existing `WORKFLOW_NAME` entry (lines
      655-659) rather than beside `WORKFLOW_SERVICE`/`WORKFLOW_SLUG`, under one
      comment naming the usage producer as the reader, gitops#1279 as the
      mirrored change, and stating that these are not consumed by argv:
      `WORKFLOW_WORK_ITEM_ID` -> `{{workflow.parameters.work_item_id}}`,
      `WORKFLOW_EXECUTION_ID` -> `{{workflow.parameters.execution_id}}`,
      `WORKFLOW_TEMPORAL_WORKFLOW_ID` ->
      `{{workflow.parameters.temporal_workflow_id}}`,
      `WORKFLOW_TEMPORAL_RUN_ID` -> `{{workflow.parameters.temporal_run_id}}`,
      `WORKFLOW_EXECUTION_REQUEST_ID` ->
      `{{workflow.parameters.execution_request_id}}`. Names byte-identical to
      `cwft-mctl-agents-investigate.yaml` lines 583-592 — the producer keys on
      names.
      — DoD: each of the five names appears exactly once in that template's
      `env`; no other template in the file gains an `env` entry; no
      `{{workflow.parameters.work_item_id}}` (or the other four) appears
      anywhere in `container.args`, `container.command`, a `script.source` or an
      `initContainers` command in the file.

- [ ] 4. Same env binding on `run-shepherd`'s `container.env` (depends on 2),
      beside its `WORKFLOW_NAME` entry (lines 683-684), with a comment that also
      notes the in-pod implementer subprocess inherits these values, so the
      `review-fixing` path needs no separate threading.
      — DoD: same as task 3, against `cwft-mctl-agents-shepherd.yaml`.

- [ ] 5. Confirm the argv-building blocks are untouched (depends on 3, 4):
      `run-implementer`'s `container.args[2]` lines 410-420 still read
      `set -- python -m orchestrator.run_implementer`, the two `[ -n "$VAR" ]`
      appends for `--service` / `--slug`, the unconditional
      `--max-proposals "$WORKFLOW_MAX_PROPOSALS"`, then the three `printf`
      lines; `run-shepherd`'s lines 439-451 still read
      `set -- python -m orchestrator.run_shepherd`, `--service` / `--slug`, the
      `[ "$WORKFLOW_DRY_RUN" = "true" ]` append for `--dry-run`, then the three
      `printf` lines. No `--work-item-id`-style flag is added anywhere: neither
      entry point accepts one (argparse exit 2 on every run, including the cron
      sweep).
      — DoD: `git diff` on both YAML files shows hunks confined to
      `spec.arguments.parameters` and the runner template's `env:`; `git diff`
      contains no line matching `set -- "\$@" --work-item-id` or
      `--temporal-`; no other step (`commit-and-push`, `post-deploy-verify`,
      `assert-attempt`, `notify-telegram`) and no commit-message or
      `FINGERPRINT` expression changes.

- [ ] 6. Add `tests/test_cwft_implement_shepherd_work_context_env.py` (depends
      on 5), parameterised over both templates, following the
      extract-don't-restate convention of
      `tests/test_cwft_investigate_work_context_argv.py`. Static half:
      `yaml.safe_load` both CWFTs and assert the five parameters exist with an
      empty default, the pre-existing parameters keep their names and defaults,
      each of the five `WORKFLOW_*` names is bound exactly once on the runner
      template to the exact placeholder, and none of the five placeholders
      appears in any interpreted block of either file. Executable half: slice
      each runner's argv region **verbatim** out of `container.args[2]` — start
      marker `set -- python -m orchestrator.run_implementer` (resp.
      `run_shepherd`), end marker the trailing `printf '\n'` — and run it under
      `/bin/sh`, asserting on the captured `→ ...` line for the cases in T1-T5
      below. A missing marker must raise `AssertionError`, never silently check
      an empty string.
      — DoD: `python3 tests/test_cwft_implement_shepherd_work_context_env.py`
      exits 0 against the edited templates, and fails when either template is
      hand-edited to append a `--work-item-id` flag or to drop one env binding.

- [ ] 7. Wire the test into `.github/workflows/validate-manifests.yml` (depends
      on 6) as a `run: python3
      tests/test_cwft_implement_shepherd_work_context_env.py` step placed
      immediately after the existing "Unit-test the investigate CWFT's optional
      work-context argv" step (lines 282-291), with a comment explaining why:
      the implement/shepherd argv is a cross-repo compatibility contract for the
      cron sweep, `mctl_trigger_implementer` and the shepherd cron, and
      env-only is what keeps a hostile identifier out of a root pod holding the
      gitops deploy key. The step needs `pyyaml`, which the surrounding
      `validate` job already installs.
      — DoD: the step is present in the `validate` job and the job is green on
      the PR.

- [ ] 8. Confirm no static gate needs a new exemption (depends on 3, 4): do
      **not** add any of the five names to
      `scripts/validate-shell-param-interpolation.py`'s `CONSTRAINED` set and
      do not add any triple to its `BASELINE`.
      — DoD: `scripts/validate-shell-param-interpolation.py --selftest` and
      `scripts/validate-shell-param-interpolation.py` both pass with that file
      unmodified; `git diff --stat` shows exactly four files changed.

- [ ] 9. Post-merge verification (depends on 5-8): wait ~3 minutes for ArgoCD to
      sync both `ClusterWorkflowTemplate`s (`CLAUDE.md`: Argo snapshots
      templates at submit time), then let one ordinary shepherd cron tick and
      one `mctl_trigger_implementer` run complete and read their archived runner
      step logs with `mctl_get_workflow_logs`.
      — DoD: the `→` line shows exactly the pre-change argv (no new flags) and
      the run reaches `assert-attempt` as before; and one usage record produced
      by those runs carries no empty-string correlation fields, which settles the
      first open question in `requirements.md` (if it does carry them, file a
      follow-up against the producer — do not patch it from this repo).

## Tests

- [ ] T1. Omit-all, implement and shepherd: the five `WORKFLOW_*` vars unset.
      Asserts the echoed argv is exactly
      `python -m orchestrator.run_implementer --max-proposals 1` (with
      `WORKFLOW_MAX_PROPOSALS=1`, `WORKFLOW_SERVICE`/`WORKFLOW_SLUG` empty) and
      `python -m orchestrator.run_shepherd` respectively. This is the "existing
      submits are unchanged" acceptance criterion and the most important
      assertion in the file.
- [ ] T2. Omit-all-explicit: the five vars set to `""`. Output byte-identical
      to T1.
- [ ] T3. Set-all: all five set to benign values (`wi-abc`, `we-123`,
      `dev-loop-xr_1`, `run-9`, `xr_1`). Output byte-identical to T1 — the
      assertion that an env-only channel cannot leak into argv.
- [ ] T4. Injection: the five set to `; touch <tmpdir>/pwned ;` and
      `a" ; id ; "b`. Asserts the sentinel file does not exist, the exit code is
      0, and the output is byte-identical to T1 (the values appear nowhere in
      argv, so unlike the investigate test there is no surviving-token
      assertion — absence is the contract here).
- [ ] T5. Slice-is-live regression, per template: with the five new vars unset,
      `WORKFLOW_SERVICE=mctl-web` / `WORKFLOW_SLUG=issue-1-x` /
      `WORKFLOW_MAX_PROPOSALS=3` still yields
      `--service mctl-web --slug issue-1-x --max-proposals 3`, and
      `WORKFLOW_DRY_RUN=true` still yields `--dry-run`. Without this, a slice
      that silently matched an empty or wrong region would pass T1-T4 while
      checking nothing.
- [ ] T6. Static assertions (part of the same file): five parameters present
      with empty defaults in both templates; pre-existing parameter names and
      defaults unchanged; each `WORKFLOW_*` name bound exactly once on the
      correct runner template with the exact `{{workflow.parameters.<name>}}`
      value; none of the five placeholders present in any `container.args`,
      `container.command`, `script.source` or `initContainers` command of
      either file.
- [ ] T7. Repo-wide gates, unchanged and unsuppressed:
      `scripts/validate-shell-param-interpolation.py --selftest` then
      `scripts/validate-shell-param-interpolation.py`, with no new `BASELINE`
      or `CONSTRAINED` entry; `yamllint` (relaxed, per
      `.github/workflows/yamllint.yml`) and the `kubeconform` step in
      `validate-manifests.yml` pass on both edited templates;
      `python3 tests/test_cwft_investigate_work_context_argv.py` and
      `python3 tests/test_cwft_shepherd_commit_pathspecs.py` still pass
      (neither template region they read is touched).
- [ ] T8. Live smoke, post-merge (= task 9): an omit-all shepherd cron tick and
      an omit-all `mctl_trigger_implementer` run behave exactly as before. The
      set-all half is **pending** on the `mctl-agents` DevLoop child of
      mctlhq/.github#50 actually passing the values — record it as pending
      rather than forcing a synthetic submit through a cron-owned path.

## Rollback

Revert the single PR commit. Both templates return byte-for-byte to their
current state and ArgoCD reconciles them within ~3 minutes; any workflow already
submitted keeps running against the snapshot it captured at submit time, so no
in-flight implement or shepherd run is disturbed.

Nothing can be stranded by the revert. Until the `mctl-agents` DevLoop child of
mctlhq/.github#50 ships, no caller sends these parameters at all, so the revert
is invisible. After it ships, a submit carrying them against a reverted template
fails at submit with an unknown-parameter error — loudly, before any pod runs —
rather than silently dropping the correlation; the narrower fix in that window is
to stop passing them at the caller, which needs no gitops change because an
omitted parameter reproduces today's behaviour exactly.

There is no state to unwind: no `.status.yaml`, artifact, commit message,
incident fingerprint or Vault path depends on this change, and the usage records
already written keep their `argo_workflow_name` join key either way.
