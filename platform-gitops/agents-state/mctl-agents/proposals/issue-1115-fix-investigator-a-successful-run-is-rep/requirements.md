# Investigator: catch triplets written outside $PROPOSAL_DIR, say where they went, and stop the blind fallback

## Context

In `mctl-agents-investigate-0e522ac8` (mctl-api#549, 2026-11-22) the agent finished
with `subtype='success'`, but `investigate()` reported `agent did not write:
requirements.md, design.md, tasks.md` (`outcome_reason="agent-output-missing"`). The
account-2 fallback then ran and failed, and nothing was published. The issue treats the
cause as not established. The code and the gitops checkout answer it:

- `_staging_dir()` (`orchestrator/run_issue_investigator.py`) creates staging at
  `agents-state/<service>/.staging-XXXX`, one level ABOVE `proposals/`, on purpose.
  `$PROPOSAL_DIR` is set to that path.
- The tool results in the log show the agent wrote to
  `agents-state/mctl-api/proposals/.staging-kptjmuhc/`. The basename is the same, but
  the parent is the wrong one.
- The CWFT's collect step only hands off paths that match
  `agents-state/*/proposals/*/**`. That is why the same three files were "handed off"
  from `proposals/.staging-kptjmuhc/`. The triplet check, which correctly reads the real
  staging directory, found it empty.
- `platform-gitops/agents-state/mctl-api/proposals/.staging-kptjmuhc/` (design.md,
  requirements.md, tasks.md, with no `.status.yaml`) is present on mctl-gitops main today.
  So the misplaced output was also committed as a bogus "proposal".

None of the three hypotheses in the issue holds. The wrapper move (hypothesis 1) is
already covered by passing tests in which a fake agent writes into the path it is given.
The `.staging-` prefix is shared (hypothesis 2), but no code globs on it. `_is_plain_file`
(hypothesis 3) did not reject anything, because there was nothing to reject. The defect is
twofold. The investigator lets file-edit tools write anywhere. And when the triplet is
absent, its failure message does not say where it looked or where the output went.

## User stories

- AS an operator reading a failed investigate run I WANT the failure message to name the
  staging path that was checked, what it contained, and any misplaced triplet nearby SO THAT
  I can tell "the agent wrote nothing" apart from "the agent wrote it in the wrong place"
  without reading a 1939-line log.
- AS the platform I WANT the investigator's Write/Edit tools confined to `$PROPOSAL_DIR`
  SO THAT a wrong path is refused at write time and the agent corrects itself within the
  same run, instead of losing about 10 minutes and about $2.58.
- AS the account-2 quota owner I WANT a primary that produced output in the wrong place
  not to trigger the fallback SO THAT a second paid attempt is not spent on a failure that
  is not a quota problem.

## Acceptance criteria (EARS)

- WHEN the investigator agent calls Write, Edit, MultiEdit or NotebookEdit with a target
  that does not resolve (realpath) inside `$PROPOSAL_DIR` THE SYSTEM SHALL deny the call
  with a message that names the exact `$PROPOSAL_DIR` path to write under.
- WHEN the target resolves inside `$PROPOSAL_DIR` THE SYSTEM SHALL allow the call
  (unchanged behaviour), and the existing read-only gitops-context guard SHALL still apply.
- IF the triplet check finds any of `requirements.md`, `design.md`, `tasks.md` missing
  THEN THE SYSTEM SHALL include in `InvestigateResult.error`: the resolved staging path
  that was checked, the original (pre-wrapper) staging path, a bounded listing of the
  staging directory, and for each missing name whether it exists, its file type and
  whether it is a symlink.
- IF the triplet is missing from staging AND a directory named with the staging basename
  exists under `proposal_dir.parent` (that is, `proposals/<staging basename>/`) holding any
  triplet file THEN THE SYSTEM SHALL report the run with
  `outcome_reason="agent-output-misplaced"`, name that path in the error, and SHALL NOT
  publish or move those files.
- WHEN the outcome is `agent-output-misplaced` THE SYSTEM SHALL exit with a distinct,
  documented exit code (`EXIT_NOT_RETRYABLE`, 3) instead of 1, so the CWFT can skip the
  account-2 fallback.
- WHILE the outcome is `agent-output-missing` with no misplaced output found THE SYSTEM
  SHALL keep exit code 1 and the existing message prefix `agent did not write: <names>`,
  so current tests and log searches stay valid.
- IF a triplet name is present in staging but is not a regular file THEN THE SYSTEM SHALL
  keep the existing `(present but not a regular file: ...)` text.
- WHEN the investigator exits, THE SYSTEM SHALL leave no `proposals/.staging-*` directory
  that it can attribute to this run. A misplaced directory whose basename equals this
  run's staging basename SHALL be removed in the `finally` cleanup, through the same
  fd-checked removal used for the wrapper, so the CWFT collect step cannot hand it off.

## Out of scope

- Changing the CWFT `investigate-fallback` `when:` expression and its collect-step
  `ALLOWED` regex in mctl-gitops (`cwft-mctl-agents-investigate.yaml`). This proposal
  defines the exit-code contract. The gitops change is a follow-up PR in mctl-gitops,
  listed in tasks.md.
- Removing the already committed `agents-state/mctl-api/proposals/.staging-kptjmuhc/`
  from mctl-gitops main. That is an operator cleanup in mctl-gitops.
- Confining Bash writes. Bash stays unrestricted, as `_ReadOnlyDirsHook` documents. The
  diagnostics and cleanup cover a Bash-written misplacement.
- Re-running mctl-api#549.

## Open questions

- Why the agent put the files under `proposals/` is not established. The likely cause is
  that the model mixed the documented proposal layout (`proposals/<slug>/`) with the
  staging basename. No prompt change is proposed beyond the hook's deny message. If misplacement
  recurs after the hook ships, consider stating the absolute `$PROPOSAL_DIR` path in the
  prompt.
- Exit code 3 is assumed to be unused by the investigate CWFT. The implementer should grep
  the CWFT and `assert-attempt` before fixing the value.
- Should a misplaced triplet be salvaged (moved into staging and published) instead of
  refused? This proposal refuses it. The files bypassed every staging check, and a Bash
  process could still be writing them. Salvage can come later if refusal proves costly.
