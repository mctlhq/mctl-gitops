# Consume rotated agent credentials through file-backed readers, not env seeds (#807 G2, runtime side)

## Context

mctlhq/mctl-agents#807 G2 ranks "long-lived tokens in env vars" as a high gap. The fix it names is
short-lived, file-mounted credentials, following the existing `GITHUB_TOKEN_FILE` pattern
(`orchestrator/github_token.py`). mctlhq/mctl-gitops#2288 owns the pod-manifest side: it moves
`env[].valueFrom.secretKeyRef` seeds in `cwft-mctl-agents-*.yaml` and `services/admins/mctl-agents-worker*`
to Secret volume mounts. That move only works if the mctl-agents runtime reads each credential from a
mounted file. The runtime must also avoid copying file contents back into `os.environ`, where every
SDK session, every `gh`/`git` child and the model's `Bash` tool would inherit them. Today only
GITHUB_TOKEN has a file reader. MCTL_TOKEN, MCTL_USAGE_WRITER_TOKEN, MCTL_EVIDENCE_WRITER_TOKEN,
CLAUDE_CODE_OAUTH_TOKEN(_SECONDARY), ANTHROPIC_API_KEY(_SECONDARY) and SCOUT_TELEGRAM_BOT_TOKEN are
read from env only.

This proposal owns only the runtime contract: an explicit `<NAME>_FILE` reader per credential, read at
the credentialed operation, with a credential inventory. File mounting is not a secrecy boundary while
the model's `Bash` shares the container filesystem. That stronger property belongs to
mctlhq/mctl-agents#869, and this proposal states the residual boundary explicitly instead of claiming it.

## User stories

- AS a platform operator I WANT every agent credential to be readable from a mounted file SO THAT
  mctl-gitops#2288 can delete the `secretKeyRef` env seed without breaking investigator, implementer,
  shepherd, run, scout or the Temporal worker.
- AS a security reviewer I WANT in-process-only credentials (mctl-api tokens, writer tokens, the scout
  bot token) never to be written into `os.environ` SO THAT the new reader path adds no credential to the
  model subprocess environment.
- AS an operator rotating a credential I WANT the next credentialed operation to read the new file
  content SO THAT a rotation takes effect without restarting a 2h pod.
- AS the #869 owner I WANT the residual boundary named in code and docs SO THAT nobody reads file
  mounting as model-shell isolation.

## Acceptance criteria (EARS)

- WHEN a credential `<NAME>` in the inventory is consumed AND `<NAME>_FILE` names a readable, non-empty
  file THE SYSTEM SHALL use the file's stripped content for that operation, read at the moment of the
  operation (or at session construction where the consumer binds the credential once per session, as
  listed in the inventory).
- WHEN the content of `<NAME>_FILE` is replaced between two credentialed operations THE SYSTEM SHALL use
  the new content in the second operation, wherever the consumer reads per operation.
- IF `<NAME>_FILE` is set but unreadable, empty or not valid UTF-8 THEN THE SYSTEM SHALL use the
  last-good value read from that file in this process, or the `<NAME>` env value when there is no
  last-good value, or treat the credential as absent. The consumer's existing "not set" behaviour then
  applies.
- IF a file read fails THEN THE SYSTEM SHALL log only the variable name, the path and the exception
  type name, never the exception message (a UnicodeDecodeError message embeds a credential byte) and
  never any file content.
- WHILE a credential is in the in-process-only class (MCTL_TOKEN, MCTL_USAGE_WRITER_TOKEN,
  MCTL_EVIDENCE_WRITER_TOKEN, SCOUT_TELEGRAM_BOT_TOKEN) THE SYSTEM SHALL NOT write its file content to
  `os.environ`, to any `ClaudeAgentOptions.env`, to argv, to logs, to Temporal/Argo metadata, to
  exception text or to persisted artifacts.
- WHILE an SDK session env is built by `_scrubbed()` in `orchestrator/options.py` THE SYSTEM SHALL blank
  both `<NAME>` and `<NAME>_FILE` for every in-process-only credential.
- WHEN GITHUB_TOKEN is consumed THE SYSTEM SHALL keep the existing `refresh_github_token()` contract:
  refresh `os.environ["GITHUB_TOKEN"]` from `GITHUB_TOKEN_FILE` before each `gh`/`git` subprocess. It
  SHALL also do so once at entrypoint start, so a pod without the GITHUB_TOKEN env seed authenticates
  its first call.
- WHEN an SDK session is built and the Anthropic credential is file-backed
  (`CLAUDE_CODE_OAUTH_TOKEN_FILE`, `CLAUDE_CODE_OAUTH_TOKEN_SECONDARY_FILE`, `ANTHROPIC_API_KEY_FILE`,
  `ANTHROPIC_API_KEY_SECONDARY_FILE`) THE SYSTEM SHALL resolve it in `orchestrator/auth.py` and put it
  into that session's `options.env` only, not into `os.environ`.
- WHEN `rotate_to_secondary_auth()` runs on a 429 THE SYSTEM SHALL switch the next session to the
  secondary credential, read from its file if file-backed, without copying it into `os.environ`.
- WHERE a credential has no short-lived or rotatable form THE SYSTEM SHALL record only its variable name,
  its consumer and its lifetime class in the inventory (`docs/security/credential-files.md`), never a
  value.
- THE SYSTEM SHALL state in `orchestrator/credential_files.py` and in the inventory doc that a credential
  file in a filesystem readable by model `Bash`, and any credential the CLI child needs in its env
  (GITHUB_TOKEN, the Anthropic credential), remains obtainable by the model shell until #869 lands.

## Out of scope

- Changing GitOps manifests (mctl-gitops#2288), including the CWFT shell preambles that test
  `$CLAUDE_CODE_OAUTH_TOKEN` / `$GITHUB_TOKEN` and the notify-telegram exit handlers' `TG_BOT_TOKEN` /
  `MCTL_TOKEN` curl calls.
- A credential-injecting proxy or a mediated credential helper for `gh`/`git` from model `Bash` (#869).
- Rotating or shortening credentials the provider cannot rotate (Claude Pro/Max OAuth tokens, static
  mctl-api service tokens).
- Experimental tools not run by any agent CWFT: `tools/hetzner_inference_spike.py`,
  `tools/semantic_decision_spike.py`, `tools/check_binding_hash.py`.
- Changing `orchestrator/run_token.py`, which is already file-backed (`MCTL_RUN_TOKEN_SA_TOKEN_FILE`) and
  holds the run token in memory.

## Open questions

- mctl-gitops#2288's final mount paths and variable names are not visible from this clone. The proposal
  assumes the `<NAME>_FILE` convention (as `GITHUB_TOKEN_FILE` uses today) and accepts any path.
- The MCP bearer header for `MCTL_TOKEN` is bound once per SDK session in `mctl_mcp_config()`. Rotation
  therefore takes effect at the next session, not mid-session. Enforce-mode runs already use the run
  token. Is per-session rotation acceptable for MCTL_TOKEN? This proposal assumes yes.
- The exact lifetimes of CLAUDE_CODE_OAUTH_TOKEN and the static mctl-api service tokens were not
  observed. The inventory records them as "long-lived, operator-rotated" with "exact lifetime: not
  observed".
- Should the transitional env fallback (`<NAME>` when `<NAME>_FILE` is unset) be removed after #2288
  lands? This proposal keeps it, so the change can deploy before the manifests change. Removal is a
  follow-up.
