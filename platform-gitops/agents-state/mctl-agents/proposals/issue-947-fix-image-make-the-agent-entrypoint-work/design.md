# Design: issue-947-fix-image-make-the-agent-entrypoint-work

## Current state
- `entrypoint.sh`: `set -e`. When `STATE_DIR` is non-empty it runs
  `mkdir -p ${STATE_DIR}/_mentor/digest`. It then loops over `/app/agents/*/`, skipping
  only `_mentor`, and runs `mkdir -p ${STATE_DIR}/<name>/{inbox,proposals}`,
  `rm -rf ${svc_dir}inbox ${svc_dir}proposals` and two `ln -s`. Finally it runs
  `rm -rf /app/agents/_mentor/digest` plus `ln -s`, then `exec "$@"`. The loop also covers
  `_generic`, `_manifests`, `_scout`, `_shepherd` and `_incident-responder`, which
  creates empty state dirs for them.
- `Dockerfile`: `COPY agents/ ./agents/` and `COPY entrypoint.sh /entrypoint.sh`. It then
  runs `chown -R app:app /app` and sets `ENTRYPOINT ["/entrypoint.sh"]`. Its comment says
  "inbox/ proposals/ digest/ live in mctl-gitops/agents-state/ and are linked in by the
  entrypoint wrapper at runtime". `.gitignore` ignores `agents/*/inbox/`,
  `agents/*/proposals/` and `agents/_mentor/digest/`.
- `config/settings.py`: `AGENTS_DIR = REPO_ROOT / "agents"`,
  `MENTOR_DIR = AGENTS_DIR / "_mentor"`. There is no state-dir helper.
- Consumers that already resolve `STATE_DIR` directly and do not need the links:
  - `orchestrator/run_issue_investigator.py` (`DEFAULT_STATE_DIR`, `state_dir / service / "proposals"`);
  - `orchestrator/run_implementer.py` (`DEFAULT_STATE_DIR`, `--state-dir`);
  - `orchestrator/run_shepherd.py` (`DEFAULT_STATE_DIR`, `_discover_refs`);
  - `orchestrator/run_incident_responder.py` (`INCIDENT_STATE_DIR` via `options.py`);
  - `orchestrator/pr_adoption.py` (`_all_proposal_pr_urls(state_dir)`).

  `run_implementer.py:1812` only reads the baked-in `agents/<svc>/.claude/agents/implementer.md`.
- Consumers that depend on the links:
  - `orchestrator/run_service_agent.py::run_service_agent` sets
    `service_dir = AGENTS_DIR / service`. `options.build_service_agent_options` sets
    `cwd=service_dir` (comment: "CLAUDE.md, .claude/, inbox/, proposals/"). `PROMPT` and
    the sub-agent files `agents/<svc>/.claude/agents/{researcher,analyst,spec-writer}.md`
    plus `agents/<svc>/CLAUDE.md` use relative `inbox/` and `proposals/`.
  - `orchestrator/run_mentor.py::run_mentor` calls
    `_rotate_old_digests(MENTOR_DIR / "digest")`. `build_prompt()` targets
    `_mentor/digest/<YYYY-WNN>.md` and says "Read `proposals/` in every agent repo".
    `options.build_mentor_options` sets `cwd=mentor_dir.parent`. `agents/_mentor/CLAUDE.md`
    refers to `agents/<service>/proposals/` and `_mentor/digest/`.
- Tests: `tests/test_run_mentor.py`, `tests/test_run_service_agent.py` and
  `tests/test_options.py` cover these runners and builders. No test exercises
  `entrypoint.sh`. `tests/test_portable_runtime_isolation.py` only lists it as a guarded
  file. `.github/workflows/pr-validation.yml` builds the image and runs import and
  non-root smokes.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/*.yaml`: every agent CWFT
  (`implement`, `investigate`, `reconcile`, `run`, `scout`, `shepherd`, `usage-collector`)
  and `wft-lifecycle-bootstrap` set `command: ["/entrypoint.sh"]` explicitly. The path
  and file must therefore keep existing.
- `cwft-mctl-agents-run.yaml`: `STATE_DIR=/workdir/mctl-gitops/platform-gitops/agents-state`,
  with `RUN_MODE`/`RUN_SERVICE` dispatch. No `TMPDIR` is set. The commit step refuses
  changes outside `platform-gitops/agents-state/` (`OUT_OF_SCOPE` check) and runs
  `git add platform-gitops/agents-state/`. `agent_image` default is
  `ghcr.io/mctlhq/mctl-agents:1.112.3`. `readOnlyRootFilesystem: true` appears only on
  the alpine helper containers, not on the agent container yet.
- `implement`, `investigate` and `shepherd` CWFTs set `TMPDIR` onto the workdir volume.
- `.release-please-manifest.json` in the clone: current version 1.112.3.
- mctl MCP tools were not used. The agent image is a set of Argo workflow templates,
  not a tenant service, so the relevant deployed state is the CWFTs above.

## Proposed solution
Approach (a): code resolves the state directories from `STATE_DIR`, falling back to
the baked-in `agents/...` paths when `STATE_DIR` is unset. The entrypoint becomes a
pure `exec`.

Why (a) and not (b), build-time links to a fixed writable mount:
- (b) bakes `/workdir/mctl-gitops/platform-gitops/agents-state` (or another fixed path)
  into the image. With `STATE_DIR` unset (local, CI, `docker run`) the links dangle, so
  local behaviour breaks, which violates the issue's "keep local/CI behaviour".
- A separate fixed writable location (for example under `/tmp`) would need a new mount
  in every CWFT. The run CWFT has no `TMPDIR`, and its commit step forbids writes in the
  gitops checkout outside `agents-state/`. Either way the round-trip would hinge on GitOps
  wiring that is out of scope here.
- Investigator, implementer and shepherd already follow (a), so this makes the codebase
  consistent instead of keeping two mechanisms.

Changes:
1. `config/settings.py`: add a small resolver.
   - `agent_state_root() -> Path`: `Path(os.environ["STATE_DIR"])` when set and non-empty,
     else `AGENTS_DIR`. It is read at call time, not import time, so tests can monkeypatch it.
   - `service_inbox_dir(svc)`, `service_proposals_dir(svc)`, `mentor_digest_dir()`: return
     `agent_state_root() / svc / "inbox"` and so on (`/ "_mentor" / "digest"` for the
     digest). With `STATE_DIR` unset this yields exactly `AGENTS_DIR/<svc>/inbox` and the
     other current paths.
   - `ensure_dir(path)`: `mkdir(parents=True, exist_ok=True)`. Callers use it only on
     these resolved paths, so with `STATE_DIR` set nothing is created under `/app`.
2. `entrypoint.sh`: delete the whole `STATE_DIR` block, including `rm`, `ln` and `mkdir`.
   Keep `#!/bin/sh`, `set -e`, `exec "$@"` and a header comment saying the state
   directories are resolved in Python (`config.settings.agent_state_root`) and that the
   script must not write under `/app` (readOnlyRootFilesystem, mctl-gitops#2290).
3. `orchestrator/run_service_agent.py`:
   - Resolve and `ensure_dir` the inbox and proposals directories before the session.
   - Turn `PROMPT` into `build_prompt(inbox_dir, proposals_dir)`. It names the absolute
     paths and tells the agent to pass them verbatim to the researcher, analyst and
     spec-writer sub-agents. The existing step wording otherwise stays.
   - `build_service_agent_options(service_dir, model, state_dirs=...)`: keep `cwd=service_dir`.
     Append the inbox and proposals dirs to `add_dirs` (alongside `_sibling_add_dirs`) and
     update the cwd comment. When `STATE_DIR` is unset the extra dirs sit inside `cwd`;
     adding them again is harmless.
4. `orchestrator/run_mentor.py`:
   - `run_mentor` calls `_rotate_old_digests(mentor_digest_dir())` after `ensure_dir`.
   - `build_prompt()` lists `service_proposals_dir(s)` for each `s` in `SERVICES` and the
     absolute digest path `mentor_digest_dir() / f"{y}-W{w:02d}.md"`.
   - `build_mentor_options` adds `agent_state_root()` to `add_dirs`, so the session may
     read proposals and write the digest. `cwd` stays `agents/`.
5. Prompt files: reword the relative-path references in
   `agents/<svc>/CLAUDE.md` and `agents/<svc>/.claude/agents/{researcher,analyst,spec-writer}.md`
   (mctl-web, mctl-api, mctl-docs, mctl-gitops, mctl-portal, mctl-agent) and in
   `agents/_mentor/CLAUDE.md`. They now say the inbox, proposals and digest directories
   are the absolute paths given in the task prompt. Do not edit `agents/_manifests/*/agent.yaml`:
   their content hash is pinned by gitops release bindings (`tools/check_binding_hash.py`).
   If the declarative resolver hashes prompt sources too, run that check and follow
   `docs/runbooks/agent-yaml-binding-repin.md`.
6. `Dockerfile`: update the comment above `COPY agents/` ("linked in by the entrypoint
   wrapper" becomes "resolved from STATE_DIR by config.settings"). No functional change.
7. New test `tests/test_entrypoint_readonly.py`:
   - Copy the repo's `agents/` into a temp `app/agents`, then make the tree read-only
     (`chmod -R a-w`; skip when running as root, because root ignores mode bits).
   - Copy `entrypoint.sh` into a temp dir. Rewrite the literal `/app` to the temp app root
     with a `sed`-style substitution, so the test also runs against the old script, which
     hard-codes `/app`.
   - Run `sh <copy> sh -c 'echo started'` with `STATE_DIR=<tmp state>`. Assert exit 0,
     `started` in stdout, and an identical before/after snapshot (paths, file types,
     symlink targets) of the app tree.
   - A second case runs the pre-change script body, kept as a fixture string in the test
     with a comment, and asserts it fails. That proves the test detects the regression,
     as the issue's acceptance criteria require.
   - Optionally add a CI step in `pr-validation.yml`:
     `docker run --read-only -e STATE_DIR=/tmp/s --tmpfs /tmp "$IMAGE" true`.
8. Resolver unit tests plus updated runner and option tests (see tasks.md).

## Alternatives
- (b) Build-time symlinks `/app/agents/<svc>/{inbox,proposals}` and `/app/agents/_mentor/digest`
  pointing at a fixed writable location. Dropped because the links dangle with
  `STATE_DIR` unset (breaks local/CI) and because they need new GitOps mounts that are out of scope.
- `emptyDir` over each `/app/agents/<svc>/...`. Explicitly excluded by the issue: the
  service set changes with the image.
- Per-run writable workspace (for example `$TMPDIR/agents/<svc>/`) containing symlinks to
  the baked-in `CLAUDE.md`, `.claude` and `context` and to the `STATE_DIR` inbox and
  proposals, used as the session `cwd`. This would keep every relative prompt unchanged.
  Dropped for now because the run CWFT sets no `TMPDIR`, so this would depend on a
  writable `/tmp` that mctl-gitops#2290 has not provided yet. It remains a fallback if
  the absolute-path prompts prove unreliable.

## Platform impact
- Migration: none for data. The `agents-state` layout is unchanged. Image consumers keep
  calling `/entrypoint.sh`.
- Backward compatibility: when `STATE_DIR` is unset, the resolved paths are byte-identical
  to today's. When `STATE_DIR` is set, outputs land in the same `agents-state/<svc>/...`
  locations as before.
- Behaviour change: empty `STATE_DIR/_generic|_manifests|...` directories are no longer
  created. They were never committed, because git does not track empty directories.
- Risk: an LLM sub-agent writes a relative `inbox/...` path under `cwd`. In production
  (read-only root) the write fails visibly; today's writable root would keep the write
  in-container and lose it. Mitigation: absolute paths in the main prompt and the
  sub-agent prompts, `add_dirs` grants, and checking the first `RUN_MODE=full` run's
  committed output.
- Risk: other root-filesystem writes (for example `.pyc`, `$HOME/.claude`) surface once
  the entrypoint passes. That is intended; it is what #2290 needs to discover.
- Release: release-please cuts the next version (after 1.112.3). Record that tag on
  mctlhq/mctl-gitops#2290.
- Resource impact: none.
