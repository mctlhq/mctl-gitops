# readOnlyRootFilesystem on mctl-agents agent steps (807 G4)

## Context

Gap G4 of spike mctlhq/mctl-agents#807 (decision `HARDEN_IN_PLACE`) found that no
mctl-agents agent step sets `readOnlyRootFilesystem`, and that `argo-workflows`
has no Pod Security label in GitOps. Agent pods stay in `argo-workflows`, so this
proposal hardens the agent templates in place. The model-driven shell in each
agent step (the container running `{{workflow.parameters.agent_image}}`) can
currently write anywhere in its image layer, including `/app`, where the agent
code and prompts live. A read-only root confines writes to a few named,
size-limited volumes.

Today `scripts/validate-agent-pod-security.py` (mctl-gitops#1717) checks
`runAsNonRoot`, `runAsUser`, `fsGroup`, seccomp, `allowPrivilegeEscalation` and
`capabilities.drop: [ALL]` on every `agent_image` step. It does not check
`readOnlyRootFilesystem`. This proposal adds the control to all 7 current agent
steps, adds the smallest set of writable `emptyDir` mounts that real runs need,
inventories every init container and sidecar in the same pods, and makes CI
require the field.

## User stories

- AS a platform security owner I WANT every agent step container to run with a
  read-only root filesystem SO THAT a model-driven shell cannot change the agent
  image's code, prompts or tooling at runtime, and can write only to declared,
  size-limited volumes.
- AS a reviewer of a new or changed agent CWFT I WANT CI to fail when an agent
  step lacks `readOnlyRootFilesystem: true` SO THAT the control cannot be
  dropped by accident.
- AS an operator I WANT each writable mount and each init container or sidecar
  to be documented, with its consumer and a statement of whether it is hardened,
  SO THAT no unreviewed container becomes a writable or root path around the
  agent-step hardening.
- AS an implementer-agent operator I WANT the implementer to keep cloning,
  editing and running a repository's tests SO THAT the hardening does not
  break the dev loop.

## Acceptance criteria (EARS)

- WHILE a ClusterWorkflowTemplate under
  `platform-gitops/argo-workflows/cluster-templates/` has a template whose image
  contains `workflow.parameters.agent_image`, THE SYSTEM SHALL set
  `container.securityContext.readOnlyRootFilesystem: true` on that template.
  (Today that covers 7 steps: `run-implementer`, `run-investigator`,
  `run-shepherd`, `run-reconcile`, `run-orchestrator`, `scout` and
  `collect-usage`. The validator finds them by matching that image expression
  at run time, so the list is not hard-coded.)
- WHEN `scripts/validate-agent-pod-security.py` runs against a template where an
  agent step lacks `readOnlyRootFilesystem: true` (field missing or `false`),
  THE SYSTEM SHALL exit non-zero and name the file, the template and the field.
- WHEN `scripts/validate-agent-pod-security.py --selftest` runs, THE SYSTEM SHALL
  prove that each of these fails validation:
  (a) the fixture with `readOnlyRootFilesystem` removed;
  (b) the fixture with `readOnlyRootFilesystem: false`;
  (c) a fixture that adds a second, new agent step without the field.
  It SHALL also prove that the fully hardened fixture still passes.
- WHEN the validator runs against a real template copy with the field removed
  from an existing agent step (for example `run-implementer`), THE SYSTEM SHALL
  fail. This is recorded as the "proven red" evidence in the PR.
- WHILE an agent step has a read-only root, THE SYSTEM SHALL give it writable
  storage only through `emptyDir` volumes. Each one SHALL carry a `sizeLimit`
  and a comment naming its mount path, the process that writes to it, and the
  evidence (a real run or a code path) that showed the write is needed.
- IF a writable mount is not needed by a tested run of that agent kind, THEN THE
  SYSTEM SHALL NOT add it to that agent kind's step.
- THE SYSTEM SHALL NOT mount a writable volume over `/`, `/app`, `/usr`, `/etc`
  or the whole of `$HOME`'s parent, unless the PR records a measured need that a
  narrower mount cannot meet. In that case the mount must be narrowed to the
  measured subtree.
- WHILE an agent CWFT defines init containers or sidecars, THE SYSTEM SHALL
  document each one in a single inventory table. The table SHALL classify each
  as (i) inside this issue's invariant, (ii) hardened elsewhere (naming the
  issue or validator), or (iii) a documented residual. This applies to the
  template-level `wait-egress-proxy` and `clone-gitops` init containers and to
  Argo's controller-injected `init` and `wait` containers.
- WHEN this change is rolled out, THE SYSTEM SHALL complete one real run of each
  agent kind successfully on the hardened templates: investigate, implement,
  shepherd, reconcile, run (orchestrator), scout and usage-collector. The
  implement run SHALL clone a target repository, edit it and execute that
  repository's tests.
- IF a real run fails with `Read-only file system` (EROFS), THEN THE SYSTEM SHALL
  record the failing path. The fix SHALL be either the narrowest `emptyDir` that
  covers it or an env-var redirect onto an existing mount, never removing
  `readOnlyRootFilesystem`.

## Out of scope

- `pod-security.kubernetes.io/warn` and `audit: restricted` labels on
  `argo-workflows` and the sweep of what `restricted` rejects (mctl-gitops#1719).
- Making the `clone-gitops` init containers non-root (mctl-gitops#1720).
- `pod-security.kubernetes.io/enforce: restricted` on `argo-workflows`, and any
  namespace split. #807 did not choose a split, and platform helper steps run as
  root.
- Hardening the non-agent helper steps in the same CWFTs: `commit-and-push`,
  `flip-status`, `notify-telegram`, `assert-*` and `post-deploy-verify`. They do
  not run `agent_image`. They are listed in the inventory as residuals.
- `cwft-mctl-agents-approve.yaml`: it has no `agent_image` step.
- Configuring a controller-wide `executor.securityContext` for Argo's injected
  `init`/`wait` containers. That is a namespace-wide change and belongs to the
  #1719 sweep; it is inventoried here as a residual.

## Open questions

- The agent image's `/entrypoint.sh` symlinks
  `<STATE_DIR>/<svc>/proposals` onto `/app/agents/<svc>/proposals/`. The
  `STATE_DIR` comment in `cwft-mctl-agents-implement.yaml` and
  `cwft-mctl-agents-shepherd.yaml` says so. That write lands on the image root
  and will fail with EROFS. Two fixes are possible:
  (a) mctl-agents changes the entrypoint, or bakes the link into the image at
  build time, so that it points at a writable path;
  (b) an `emptyDir` is mounted over each `/app/agents/<svc>/proposals`.
  Option (b) only works if those directories are empty in the image. This
  proposal assumes (a) as a prerequisite mctl-agents change, with (b) as the
  fallback if the directories are confirmed empty. The implementer must confirm
  against the image before choosing.
- Claude Code, `gh auth setup-git` (which writes `~/.gitconfig`), git, Python and
  language toolchains used by repository tests write under `$HOME` and `/tmp`.
  The exact subpaths (`~/.claude`, `~/.claude.json`, `~/.config/gh`,
  `~/.cache`, `~/go`, npm/pip caches) were not observed in this run. They have
  to be discovered from real runs (task 1). The proposal plans one
  size-limited `emptyDir` at `$HOME` (not its parent), plus one at `/tmp`. These
  are narrowed only where a run shows that a narrower mount is enough.
- Deployed run history could not be read here
  (`mctl_list_recent_agent_runs` returned "admin group membership required"). So
  live writable-path evidence and the current image's `HOME` path are unknown.
