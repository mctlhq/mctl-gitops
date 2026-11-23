# Design: issue-1115-fix-investigator-a-successful-run-is-rep

## Current state

Publish path, `orchestrator/run_issue_investigator.py`, in `investigate()`:

1. `_staging_dir(proposal_dir)` (around line 485) returns
   `mkdtemp(dir=proposal_dir.parent.parent, prefix=".staging-")`. That is
   `agents-state/<service>/.staging-XXXX`, deliberately NOT under `proposals/`, so the CWFT
   `git add ':(glob)platform-gitops/agents-state/*/proposals/*/**'` cannot commit it.
2. `_run_agent(..., staging.resolve())` (around line 3978) passes that path on. The
   builders in `orchestrator/options.py` (`build_issue_investigator_options`, around line
   1510, and `build_issue_investigator_options_from_plan`, around line 1555) set
   `env["PROPOSAL_DIR"]`, add it to `add_dirs`, and allow `Write`/`Edit`/`Bash`.
   `permission_mode="acceptEdits"` applies. The only file-edit hook is `_ReadOnlyDirsHook`
   (around line 1165), which denies edits INSIDE the read-only gitops dirs. Nothing denies
   an edit OUTSIDE `$PROPOSAL_DIR`, so a Write to any path succeeds.
3. After the agent returns, `_verify_staging`, a wrapper
   `mkdtemp(dir=staging.parent, prefix=".staging-")`, `os.replace(staging, wrapper/"staging")`,
   `wrapper_fd`/`staging_fd` (around lines 3983-4056).
4. The triplet check (around lines 4070-4081):
   `missing = [n for n in TRIPLET if not _is_plain_file(staging / n)]`. The error is
   `agent did not write: ...`, plus `(present but not a regular file: ...)` only when the
   path exists. `outcome_reason="agent-output-missing"`.
5. `main()` (around line 4805) prints `fail <service>/<slug>: <error>` and calls
   `sys.exit(1)` for every error.

The existing tests `test_a_triplet_document_written_as_a_symlink_is_refused`,
`..._as_a_directory_...` and `test_a_genuinely_absent_document_still_reads_as_absent`
(`tests/test_run_issue_investigator.py`, around lines 1873-1928), together with the
success-path tests that use `_investigate_harness` (around line 595), already run a fake
agent through the full move-and-check sequence and pass. That rules out hypothesis 1: the
wrapper move does not lose files written into the path the agent was given.

What actually happened in mctl-api#549: the log's tool results show writes to
`agents-state/mctl-api/proposals/.staging-kptjmuhc/`, but staging was
`agents-state/mctl-api/.staging-kptjmuhc/`. The CWFT collect step
(`cwft-mctl-agents-investigate.yaml`, the `COLLECT` heredoc, `ALLOWED =
^platform-gitops/agents-state/[^/]+/proposals/[^/]+/[^/]+`) matched the misplaced files and
printed `handing off ...`. `commit-and-push` then committed them.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`:
  `investigate-fallback` runs `when: "{{steps.investigate.status}} != Succeeded"`, so any
  non-zero exit triggers the fallback. The collect step's `ALLOWED` regex accepts
  `proposals/.staging-*/...`. `print("handing off %s" % rel)` is the source of the log
  lines quoted in the issue.
- `platform-gitops/agents-state/mctl-api/proposals/` in the gitops checkout: contains
  `.staging-kptjmuhc/` (design.md 30494 B, requirements.md 9529 B, tasks.md 7486 B, no
  `.status.yaml`). This confirms that the misplaced output reached main. It also contains
  `issue-549-evaluate-agent-payment-rail-interoperabi/` with a `.status.yaml`, which is
  presumably from a later run (not verified). Across all services, exactly one
  `proposals/.staging-*` entry exists.
- `git log` on that path in the gitops checkout points to a later bulk commit (ff74191),
  so the checkout is probably shallow and the exact introducing commit was not identified.
- The archived Argo log was not read in this run. The log facts above come from the issue
  body.

## Proposed solution

### 1. Confine file-edit tools to `$PROPOSAL_DIR` (prevention)

Add a frozen dataclass `_WriteConfinementHook(allowed: tuple[str, ...])` in
`orchestrator/options.py`, next to `_ReadOnlyDirsHook`. It reuses `_containing_dir`
(realpath plus commonpath) and `_FILE_EDIT_TOOLS`. It denies when the target is not inside
`allowed` and fails closed on unreadable input, exactly as its sibling does. The deny text:
`"<target> is outside $PROPOSAL_DIR; write the proposal files under <proposal_dir>"`. That
gives the agent the absolute path to retry with. Wire it through a
`_write_confinement_hooks([str(proposal_dir)])` composed with `_compose_hooks` in both
investigator builders (legacy, declarative without a gateway, and with a gateway), so the
equivalence tests in `tests/test_options.py` keep holding. `proposal_dir` is the staging
path at that point, so the agent's `human-input/draft.json` stays allowed.

### 2. Diagnostic failure message (observation)

Add `_triplet_diagnostics(staging_fd, staging_path, original_staging, proposals_dir) -> str`
in `run_issue_investigator.py`:

- `checked=<staging resolved path>`, `original=<pre-wrapper staging path>`;
- `listing=[...]`: `os.listdir(staging_fd)`, sorted and capped at 20 names (names are
  `repr()`'d so control characters cannot forge log lines);
- for each missing name: `os.stat(name, dir_fd=staging_fd, follow_symlinks=False)`,
  rendered as `name: absent` or `name: type=<regular|dir|symlink|fifo|...> symlink=<bool>`.
  An `OSError` other than `FileNotFoundError` is rendered as `stat-error=<errno name>`,
  never as "absent".
- `misplaced=<path>` when `proposals_dir / original_staging.name` exists as a real
  directory (lstat, not a symlink) and holds at least one triplet name as a plain file.

Reads go through `staging_fd`, which is consistent with `_landed_triplet_defects`. The
check `missing = ...` itself is unchanged. The message is
`agent did not write: <names>` + the existing wrong-type suffix + `; ` + diagnostics, so the
existing assertions still match. `original_staging` is captured before the wrapper move,
when `staging` is reassigned (around line 4026). A new local holds it.

### 3. Misplaced output: distinct outcome, no blind fallback, no stray commit

- When `misplaced` is found: `outcome_reason="agent-output-misplaced"` (a valid slug under
  `_validate_outcome`), `outcome_code="failed"`.
- Add `InvestigateResult.retryable: bool = True` (defaulted, so every existing
  construction is unchanged). It is set False for `agent-output-misplaced`. `main()` exits
  `EXIT_NOT_RETRYABLE = 3` when `result.error and not result.retryable`, and 1 otherwise.
  The summary line is unchanged.
- In the `finally` cleanup, remove `proposals_dir / original_staging.name` when, and only
  when, it is a real directory (lstat, `O_NOFOLLOW` fd) whose basename equals this run's
  staging basename. The basename is a random mkdtemp suffix, so no other run's proposal
  can carry that name. A `.staging-*` name can never be a valid slug, because
  `_parse_issue_url` and slug derivation produce `issue-...`. Because the directory is
  removed before the CWFT collect step runs, it can no longer be committed. The error
  message still names the path, so the operator can find the contents in the log's tool
  results.

### 4. Follow-up in mctl-gitops (separate PR, not in this repo)

- In `cwft-mctl-agents-investigate.yaml`, have `run-investigator` export the
  investigator's RC as an output parameter, and change `investigate-fallback`'s `when:` to
  also require `rc != 3`.
- Tighten `ALLOWED` to reject a proposal component starting with `.`
  (`proposals/[^/.][^/]*/`), as a second line of defence.
- Remove the committed `agents-state/mctl-api/proposals/.staging-kptjmuhc/`.

## Alternatives

- **Salvage the misplaced triplet**: move it into staging and publish. Rejected. The files
  never passed the staging identity checks, a background Bash process may still be writing
  them, and the confinement hook makes the case rare. Refusing keeps one code path.
- **Move staging under `proposals/`** so a "natural" guess lands in the right place.
  Rejected. `_staging_dir` is outside `proposals/` precisely so the CWFT glob can never
  commit a leftover staging directory after a hard kill.
- **Only improve the message**. Rejected as insufficient: the run still fails, spends the
  fallback, and commits garbage. The issue's Wanted item 3 explicitly asks for no blind
  fallback.
- **Skip the fallback for every `agent-output-missing`**. Rejected. A rate limit hit while
  the agent was writing is already raised as `RateLimitExhaustedError`, but a genuinely
  absent triplet from a crashed or limited account is still a case the fallback can fix.
  Only the misplaced case is provably not a quota problem.

## Platform impact

- No migration. `InvestigateResult.retryable` defaults to True. Exit code 3 is new, and
  until the gitops follow-up lands the CWFT treats it like 1 (the fallback still runs),
  which is current behaviour, so the rollout order does not matter.
- Risk: the confinement hook denies a write the agent legitimately needs. The investigator
  is told to write only into `$PROPOSAL_DIR`, and Bash is unaffected. Mitigation: the deny
  text names the correct path, and tests cover `human-input/draft.json` and nested paths.
- Risk: the cleanup deletes the wrong directory. Mitigation: exact basename match on a
  random mkdtemp suffix, lstat or `O_NOFOLLOW`, and a refusal to follow a symlink, with the
  same discipline as the wrapper cleanup (`_path_matches_fd`).
- No resource impact. A few extra syscalls run on the failure path only.
