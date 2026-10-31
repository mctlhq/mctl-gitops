# Tasks: issue-2290-security-agents-readonlyrootfilesystem-o

- [ ] 1. Re-inventory the agent steps and discover their writable paths.
  Re-run the inventory: every template under
  `platform-gitops/argo-workflows/cluster-templates/` whose image contains
  `workflow.parameters.agent_image` (7 at 633112e). For each agent kind, run a
  debug submission with `readOnlyRootFilesystem: true` and only `/tmp` and
  `$HOME` mounted. Also list image-layer writes from a run without the flag
  (`find / -xdev -newer /proc/1 -type f`). Confirm the image's `HOME`, and
  whether `/app/agents/*/proposals` is empty in
  `ghcr.io/mctlhq/mctl-agents:<pin>`.
  — DoD: `docs/runbooks/agent-readonly-rootfs.md` holds a per-kind table of
  writable paths, each with its writer and the evidence (workflow name or code
  path).
- [ ] 2. Remove the runtime write under `/app` (depends on 1).
  Preferred: open an mctl-agents PR so that `/entrypoint.sh` no longer creates
  the `/app/agents/<svc>/proposals` symlinks at runtime (bake them at build time,
  or point them at a writable path), and release a new image. Fallback, only if
  task 1 shows those directories are empty in the image: an `emptyDir` per
  `/app/agents/<svc>/proposals` path.
  — DoD: an agent step on the chosen image writes nothing under `/app`. The
  image version, or the fallback decision, is recorded in the runbook.
- [ ] 3. Harden the 7 agent steps (depends on 1, 2).
  In `cwft-mctl-agents-{implement,investigate,shepherd,run,reconcile,scout,usage-collector}.yaml`:
  add `readOnlyRootFilesystem: true` to the agent container's
  `securityContext`, and add only the `emptyDir` mounts that task 1 proved
  necessary. Baseline: `/tmp`, and `$HOME` or narrower subpaths/env redirects,
  each with a `sizeLimit` and a comment naming path, consumer and evidence. If
  task 2 took the image route, bump `agent_image` defaults to the new image.
  Leave `workdir`, `TMPDIR`, `clone-gitops` and `wait-egress-proxy` unchanged.
  — DoD: all 7 steps carry the field. No mount covers `/`, `/app`, `/usr`,
  `/etc` or `/home` as a whole. `helm`/`kubeconform` validation in
  `validate-manifests.yml` passes.
- [ ] 4. Enforce the invariant in the validator (can run in parallel with 3; it
  merges with or after 3). In `scripts/validate-agent-pod-security.py`:
  - make `check_template` require container
    `securityContext.readOnlyRootFilesystem is True`;
  - add `readOnlyRootFilesystem: True` and an `emptyDir` `/tmp` mount to
    `_fixture()`;
  - add selftest cases "no readOnlyRootFilesystem", "readOnlyRootFilesystem
    false" and "new unprotected agent step" (a second agent template without the
    field), each expected to fail, with "hardened" still expected to pass;
  - optionally also scan `spec.workflowSpec.templates`;
  - update the docstring to cite #2290.
  — DoD: `--selftest` prints `selftest ok`. The default run passes on the
  hardened tree and fails on a copy with the field removed from
  `run-implementer`, and that failing output is pasted in the PR.
- [ ] 5. Write the init container / sidecar inventory (depends on 1).
  In `docs/runbooks/agent-readonly-rootfs.md`, classify each of these as inside
  the invariant, hardened elsewhere or a documented residual, with its owner
  issue: `wait-egress-proxy`, `clone-gitops` (#1720), Argo-injected
  `init`/`wait` (#1719), the helper `script:` steps and their `clone-gitops`
  (#1719), and `sidecars` (none). Add a one-line pointer comment to the runbook
  in each agent CWFT. Link the runbook from `CLAUDE.md`'s Secrets/runbooks list.
  — DoD: every init container and sidecar that appears in an agent CWFT has a
  row in the table. None is described as inheriting the agent-step invariant.
- [ ] 6. Verify with real runs (depends on 3, 4, 5, merged and synced).
  After ArgoCD syncs (about 3 minutes), trigger one run each of investigate,
  implement (a proposal whose repo has a test suite), shepherd, reconcile
  (`dry_run=true`), run (`mctl_trigger_single_service`), scout and
  usage-collector.
  — DoD: all 7 succeed with no EROFS in their logs. The implementer log shows
  the clone, the edit and the test command executing. Workflow names are
  recorded in the runbook and on the issue.

## Tests

- [ ] T1. `scripts/validate-agent-pod-security.py --selftest` passes, and
  includes the three new failure cases and the hardened pass case.
- [ ] T2. `scripts/validate-agent-pod-security.py` exits 0 on the PR tree.
- [ ] T3. Red proof: copy the cluster-templates dir to a temp directory, delete
  `readOnlyRootFilesystem` from `run-implementer`, and run
  `scripts/validate-agent-pod-security.py --dir <tmp>`. It exits 1 and names
  `cwft-mctl-agents-implement.yaml:run-implementer`.
- [ ] T4. CI's `validate-manifests.yml` "Validate agent pod security context"
  step and the manifest render/kubeconform steps are green on the PR.
- [ ] T5. On the real runs, output artifacts written under `/tmp`
  (`/tmp/state-out`, `/tmp/proposal-out`, `/tmp/onexit`) are collected, and the
  downstream `commit-and-push` and `notify-telegram` steps consume them as before.
- [ ] T6. The implementer real run executes the target repo's test command
  successfully, with toolchain caches written only to the declared mounts.

## Rollback

Per affected agent step, revert the gitops PR: remove
`readOnlyRootFilesystem: true` and the added `emptyDir` volumes and mounts, and
restore the previous `agent_image` default if it was bumped. If the validator
change has merged, revert its `readOnlyRootFilesystem` assertion in the same
revert, or CI will block the rollback. New submissions use the reverted
templates once ArgoCD syncs (about 3 minutes). In-flight runs keep their
snapshotted templates. The mctl-agents entrypoint change is backward-compatible
(the links still resolve), so it does not need reverting.
