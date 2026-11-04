# Make the agent entrypoint work with readOnlyRootFilesystem

## Context
When `STATE_DIR` is set, `/entrypoint.sh` rewrites the image filesystem at every
container start. For every directory under `/app/agents/` other than `_mentor`, it runs
`rm -rf` on `inbox` and `proposals` and then `ln -s` to
`${STATE_DIR}/<name>/{inbox,proposals}`. It also replaces
`/app/agents/_mentor/digest` with a symlink to `${STATE_DIR}/_mentor/digest`. The
script runs under `set -e`. With `readOnlyRootFilesystem: true` (mctlhq/mctl-gitops#2290,
807 G4), the first `rm` therefore aborts every agent step before the Python
orchestrator starts. As a result, nobody can even find out which other paths an agent
run writes.

Only two runtimes still rely on those links. The service agent runs with
`cwd=/app/agents/<svc>` and writes relative `inbox/` and `proposals/`. The mentor runs
with `cwd=/app/agents`, reads `<svc>/proposals/` and writes `_mentor/digest/`. The
investigator, implementer, shepherd, incident responder and PR adoption already resolve
`STATE_DIR` directly (`DEFAULT_STATE_DIR` in `orchestrator/run_*.py`). This proposal
moves the service agent and mentor to the same model: the code resolves the state
directories from `STATE_DIR` (approach (a) in the issue), and the entrypoint no longer
writes anything under `/app`.

## User stories
- AS a platform operator I WANT agent steps to start with `readOnlyRootFilesystem: true` SO THAT mctl-gitops#2290 can harden the agent pods and find their real writable paths.
- AS a service-agent / mentor run I WANT my inbox, proposals and digest to resolve to `STATE_DIR` SO THAT my output still lands in the mctl-gitops `agents-state` tree that the workflow commits.
- AS a developer running locally or in CI without `STATE_DIR` I WANT the baked-in `agents/<svc>/inbox|proposals` and `agents/_mentor/digest` paths to keep working SO THAT local runs behave as they do today.

## Acceptance criteria (EARS)
- WHEN `/entrypoint.sh` runs with `STATE_DIR` set THE SYSTEM SHALL `exec` the given command without creating, removing or linking any path under `/app`.
- WHEN `/entrypoint.sh` runs with `STATE_DIR` set against a read-only copy of `/app` THE SYSTEM SHALL exit with the status of the executed command, not with an `rm`/`ln` error.
- WHEN `STATE_DIR` is set THE SYSTEM SHALL resolve each service agent's inbox to `${STATE_DIR}/<svc>/inbox`, its proposals to `${STATE_DIR}/<svc>/proposals`, and the mentor digest to `${STATE_DIR}/_mentor/digest`, creating those directories (under `STATE_DIR` only) if missing.
- WHILE `STATE_DIR` is unset THE SYSTEM SHALL resolve those directories to `agents/<svc>/inbox`, `agents/<svc>/proposals` and `agents/_mentor/digest` under the repo or image root, as today.
- WHEN a service agent runs THE SYSTEM SHALL give the session the absolute inbox and proposals paths in its prompt and grant it access to them via `add_dirs`. Its `cwd` stays `agents/<svc>` so that `CLAUDE.md`, `.claude/` and `context/` still load.
- WHEN the mentor runs THE SYSTEM SHALL give it the absolute proposals directory of every service in `SERVICES` that has a baked `agents/<svc>/` directory in the image, and the absolute digest target path. That is exactly the set the entrypoint links cover today (mctl-agent, mctl-agents, mctl-api, mctl-docs, mctl-gitops, mctl-portal, mctl-web at the time of writing); computing it as `[s for s in SERVICES if (AGENTS_DIR / s).is_dir()]` keeps it correct as scaffolds change. Services without a scaffold (for example mctl-telegram, mctl-support, mctl-design) SHALL NOT be added: today their relative paths do not exist and the mentor skips them, so adding them would widen the weekly digest to every DevLoop proposal. Widening the mentor's scope is a separate decision, out of scope here. Digest rotation (`_rotate_old_digests`) SHALL run on the resolved digest directory.
- WHILE `STATE_DIR` is set THE SYSTEM SHALL keep the investigator, implementer, shepherd, incident-responder and reconcile paths reading and writing under `STATE_DIR` unchanged, and the existing test suite SHALL stay green.
- IF a test runs the current (pre-change) entrypoint against a read-only `/app` copy with `STATE_DIR` set THEN that test SHALL fail.
- WHEN the change is released THE SYSTEM SHALL have a published image version recorded on mctlhq/mctl-gitops#2290.

## Out of scope
- The GitOps `readOnlyRootFilesystem` flag, `emptyDir`/writable mounts and CWFT edits (mctlhq/mctl-gitops#2290).
- Other runtime writes under the root filesystem (for example `__pycache__`, `$HOME`, `/tmp`). This change only makes them discoverable by getting past the entrypoint.
- Changing `DEFAULT_STATE_DIR` semantics of the investigator, implementer, shepherd or incident responder.

## Open questions
- Should `/entrypoint.sh` keep `mkdir -p` of the `STATE_DIR` sub-directories, which is a write outside `/app` and safe? This proposal moves directory creation into Python (the resolver creates them on use) and keeps the entrypoint as a pure `exec`. The CWFTs still call `/entrypoint.sh` explicitly, so the file and its path must stay.
- The current entrypoint also creates empty `STATE_DIR/<_generic|_manifests|_scout|_shepherd|_incident-responder>/{inbox,proposals}`. Git does not commit empty directories, so dropping them is assumed harmless. Reviewer to confirm that nothing depends on these directories existing.
- The service-agent sub-agent prompts (`agents/<svc>/.claude/agents/{researcher,analyst,spec-writer}.md`) and `agents/<svc>/CLAUDE.md` refer to relative `inbox/` and `proposals/`. They must be reworded to use the absolute paths passed down in the task. If an LLM ignores that and writes a relative path, the write fails on a read-only root instead of being lost silently. Watch the first production runs.
