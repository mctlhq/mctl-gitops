# Design: issue-920-security-agents-consume-rotated-agent-cr

## Current state

**The one file-backed reader today.** `orchestrator/github_token.py:refresh_github_token()` reads
`GITHUB_TOKEN_FILE` and overwrites `os.environ["GITHUB_TOKEN"]`. It is called before each `gh`/`git`
subprocess (`run_implementer.py:1730`, `run_issue_investigator.py:374`, `run_shepherd.py:1516,3618`,
`ci_checks.py:338,567`, `run_usage_collector.py:180,280`). On a failed read it keeps the previous value.
It prints `{e}`. For a `UnicodeDecodeError` that message includes the offending byte value, which is one
byte of the token. `tests/test_github_token.py` covers it.

**Already file-backed, held in memory.** `orchestrator/run_token.py:exchange()` reads the projected SA
token from `MCTL_RUN_TOKEN_SA_TOKEN_FILE` (default `/var/run/secrets/mctl-api/token`). The resulting
`art_` run token never enters the environment.

**Env-only credentials (inventory)**:

| Variable | Consumers (read site) | Binding | Class |
|---|---|---|---|
| `MCTL_TOKEN` | `options.py:133` (`mctl_mcp_config` -> `run_token.mcp_auth`), `capability_gateway.py:400`, `action_approvals.py:326`, `commerce.py:631`, `lifecycle/client.py:91`, `lifecycle/claim.py:134`, `run_shepherd.py:250`, `pr_adoption.py:355` (presence only), `temporal/mctl_client.py:24`, `run_token.py:263`, `work_context/client.py` | per client construction / per SDK session | in-process only |
| `MCTL_USAGE_WRITER_TOKEN` | `usage_ledger.py:543` (`UsageRecorder.from_env`, stored as `self._token`, sent at `:704`) | per recorder | in-process only |
| `MCTL_EVIDENCE_WRITER_TOKEN` | `evidence_producer.py:986` (`writer_credentials`, also used by `decision_records.py`) | per call | in-process only |
| `SCOUT_TELEGRAM_BOT_TOKEN` | `run_scout.py:57` | per run | in-process only |
| `GITHUB_TOKEN` | `gh`/`git` children via `os.environ`; `gh auth git-credential` reads it at push time | per subprocess | subprocess env (needed by children) |
| `CLAUDE_CODE_OAUTH_TOKEN`, `_SECONDARY`, `ANTHROPIC_API_KEY`, `_SECONDARY` | `auth.py:detect_auth`, `rotate_to_secondary_auth` (writes primary from secondary into `os.environ`), read by the bundled CLI from its env | per SDK session | CLI child env (needed by the CLI) |

**Session env scrubbing.** `options.py:_scrubbed()` (around line 1287) wraps every
`ClaudeAgentOptions` builder. It blanks `MCTL_TOKEN` (`agent_env_without_mctl_token`,
`options.py:1232`), `MCTL_USAGE_WRITER_TOKEN` (`usage_ledger.py:387`) and `MCTL_EVIDENCE_WRITER_TOKEN`
(`evidence_producer.py:197`). It still passes `GITHUB_TOKEN`, `GITHUB_TOKEN_FILE` and the Anthropic
credential to the CLI child, and therefore to model `Bash`. Builders start from `{**os.environ, ...}`
(for example `options.py:1320`), so anything written into `os.environ` reaches the model unless it is
scrubbed.

**Residual boundary.** `docs/spikes/807-agent-isolation-k8s.md` ("Layering with app-layer controls")
states that model `Bash` runs in the same container and is not mediated by in-process controls.
`docs/spikes/852-sandbox-isolation-delta.md` D4 records that model `Bash` inherits the full pod env.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`:
  - `CLAUDE_CODE_OAUTH_TOKEN`, `GITHUB_TOKEN`, `MCTL_USAGE_WRITER_TOKEN` and `MCTL_EVIDENCE_WRITER_TOKEN`
    come from `secretKeyRef`.
  - `GITHUB_TOKEN_FILE=/var/run/gh/github-token` comes from the `github-token-file` Secret volume.
  - The run token runs in enforce mode with the projected SA token at `/var/run/secrets/mctl-api/token`.
  - The main container has no `MCTL_TOKEN`.
  - The shell preamble tests `$CLAUDE_CODE_OAUTH_TOKEN` (fallback) and `$GITHUB_TOKEN`, then runs
    `gh auth setup-git`.
  - The notify-telegram exit handler keeps `TG_BOT_TOKEN` and `MCTL_TOKEN` and calls curl from shell.
- `cwft-mctl-agents-implement.yaml` and `cwft-mctl-agents-shepherd.yaml`: the same pattern, plus a
  `MCTL_TOKEN` `secretKeyRef` in the main container (implement:766, shepherd:784).
- `cwft-mctl-agents-run.yaml`: `CLAUDE_CODE_OAUTH_TOKEN`, `MCTL_TOKEN` and `GITHUB_TOKEN` from
  `secretKeyRef`, with no `GITHUB_TOKEN_FILE`.
- `cwft-mctl-agents-scout.yaml`: `CLAUDE_CODE_OAUTH_TOKEN`, `GITHUB_TOKEN` and `SCOUT_TELEGRAM_BOT_TOKEN`
  from `secretKeyRef`.
- `cwft-mctl-agents-reconcile.yaml`: `GITHUB_TOKEN` from `secretKeyRef`.
- `services/admins/mctl-agents-worker/values.yaml`:
  - `GITHUB_TOKEN_FILE=/var/run/secrets/github/GITHUB_TOKEN` is set.
  - `MCTL_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` and `GITHUB_TOKEN` are env secrets.
  - A comment calls the OAuth token long-lived and operator-rotated.
  - A comment explains why `GH_TOKEN` is deliberately absent.
- `services/admins/mctl-agents-worker-exec/values.yaml`: `MCTL_TOKEN` only.
- `argo-workflows/secrets/mctl-agents-secrets.yaml`: an ExternalSecret from Vault `platform/mctl-agents`.
  Key names were read; no values were read.
- mctl-gitops#2288's planned paths were not observable from this checkout (see Open questions).
- MCP tools: not used. The gitops checkout was sufficient for manifest state.

## Proposed solution

### 1. `orchestrator/credential_files.py` (new): one reader contract

```python
@dataclass(frozen=True)
class CredentialSpec:
    name: str            # e.g. "MCTL_USAGE_WRITER_TOKEN"
    klass: str           # "in-process" | "subprocess-env" | "cli-env"
    lifetime: str        # "short-lived (kubelet-refreshed)" | "long-lived, operator-rotated" ...

INVENTORY: tuple[CredentialSpec, ...]   # the table above, names only

def read_credential(name: str, env: Mapping[str, str] | None = None) -> str:
    """Value of credential `name` for the operation about to run.
    `<name>_FILE` set -> read file now (strip); on OSError/UnicodeDecodeError/empty -> last-good
    value from that file in this process, else env `<name>`, else "". Never writes os.environ.
    Logs name, path and type(exc).__name__ only."""

def file_env_names() -> frozenset[str]   # {"<name>_FILE" for in-process specs}

RESIDUAL_BOUNDARY = ("A credential file in a filesystem readable by model Bash, and any credential "
                     "a CLI child needs in its env, is obtainable by the model shell; "
                     "mctlhq/mctl-agents#869 owns that boundary.")
```

The last-good cache is a module-level `dict[name, str]`. It is in memory only and is never serialized.
It mirrors `refresh_github_token()`'s behaviour during a mid-rotation race: a Secret volume update is
not atomic from the reader's side.

### 2. In-process-only consumers read through `read_credential`, per operation where possible

- `usage_ledger.UsageRecorder`: store a token *source* (a callable, defaulting to
  `lambda: read_credential(TOKEN_ENV, env)`) instead of a frozen string. Resolve it at each delivery
  (`:704`). `enabled` and `_off_reason` stay computed from a first resolution, and an explicit `token=`
  argument (used in tests) is still honoured.
- `evidence_producer.writer_credentials` / `_credentials`: call `read_credential(TOKEN_ENV, env)`. They
  already run per call.
- `MCTL_TOKEN` consumers: replace the `os.environ.get("MCTL_TOKEN", "")` sites listed in Current state
  with `read_credential("MCTL_TOKEN")`. The REST clients (`action_approvals`, `commerce`,
  `lifecycle/client`, `lifecycle/claim`, `temporal/mctl_client`, `work_context/client`) resolve it per
  request when no explicit `token` was injected. `mctl_mcp_config()` and `capability_gateway` bind it
  once per SDK session because the header is part of the server config; rotation is picked up at the
  next session (Open question).
- `run_scout.py:57`: `read_credential("SCOUT_TELEGRAM_BOT_TOKEN")`.

None of these paths writes to `os.environ`.

### 3. Scrub the `_FILE` pointers too

Extend `_scrubbed()` to blank every name in `credential_files.file_env_names()` in addition to the
existing blanks. This is not a secrecy boundary: the files stay readable at their mount path. It does
mean the new mechanism adds nothing to the session env, not even a path, and the existing builder guard
in `tests/test_usage_ledger.py` still applies.

### 4. GITHUB_TOKEN: keep the existing contract, remove the seed dependency

- Reimplement `refresh_github_token()` on `read_credential("GITHUB_TOKEN")`. It must keep writing
  `os.environ["GITHUB_TOKEN"]`, because the `gh`/`git` children (including `gh auth git-credential`)
  need it.
- Change the log line to the exception type name, which closes the one-byte leak.
- Call `refresh_github_token()` once at the top of each entrypoint `main()` (`run_issue_investigator`,
  `run_implementer`, `run_shepherd`, `run_usage_collector`, `run_scout`, `run_all`, the Temporal
  worker entrypoint). `run_all` is the entrypoint of `cwft-mctl-agents-run.yaml` and today calls
  `refresh_github_token()` nowhere, so without it the `run` kind keeps needing the env seed. With the env seed removed, the first call then authenticates from the file.
- This credential stays in the subprocess-env class, visible to model `Bash` (#869 residual).

### 5. Anthropic credential: file-backed, session-scoped

- `auth.py` resolves each of the four names through `read_credential` in `detect_auth()`.
- A new `auth.session_auth_env() -> dict[str, str]` returns the single active credential variable. The
  dict is merged into `options.env` inside `_scrubbed()` and is never written to `os.environ`.
- `rotate_to_secondary_auth()` sets a module flag that selects the secondary source for the next
  `session_auth_env()`. It no longer copies the secondary value into `os.environ`.
- On the env-only path (no `_FILE`) behaviour is unchanged.
- The bundled CLI must hold this credential in its own env, so model `Bash` can still read it (#869
  residual). It is long-lived (Pro/Max OAuth) and cannot rotate mid-session; the inventory records
  exactly that.

### 6. Inventory and residual-boundary doc

`docs/security/credential-files.md` holds:
- for each `INVENTORY` entry: the variable, its `_FILE` name, its consumers, how it is bound
  (per operation or per session), its class and its lifetime class. Names only, no values.
- a "Contract for mctl-gitops#2288" section: which seeds can be removed once this ships, and which
  CWFT shell lines currently test `$VAR` and must switch to `[ -s "$VAR_FILE" ]` on the gitops side.
- the `RESIDUAL_BOUNDARY` sentence verbatim.

A test keeps the doc and `INVENTORY` in sync.

## Alternatives

1. **Generalize `refresh_github_token()`: copy each file into `os.environ` before use.** This is the
   smallest change, but it re-seeds every in-process credential into the env that `_scrubbed()` and
   every subprocess inherit. That is exactly what the issue forbids. Dropped.
2. **A credential-injecting proxy or mediated helper now.** The issue lists it as a non-goal, and #869
   owns mediation. Building it here would create a second mechanism. Dropped; the reader is designed so
   #869 can wrap `read_credential` behind its helper.
3. **Read each file once at startup and cache it for the process lifetime.** This is simpler but
   defeats rotation for 2h pods and the Temporal worker. Dropped, except where a consumer binds once per
   session by construction (MCP header, CLI env).

## Platform impact

- **Backward compatibility:** every reader falls back to the `<NAME>` env var when `<NAME>_FILE` is
  unset. The image can deploy before mctl-gitops#2288, and old manifests keep working. #2288 can then
  drop seeds one by one. The CWFT shell preambles that test `$GITHUB_TOKEN` / `$CLAUDE_CODE_OAUTH_TOKEN`
  must change in #2288 in the same commit that removes those seeds; the inventory doc lists them.
- **Migrations:** none. No persisted state changes.
- **Resource impact:** one small file read per credentialed operation, which is negligible next to the
  HTTP call it precedes.
- **Risks and mitigations:**
  - *Mid-rotation partial read:* mitigated by the last-good cache and UTF-8 failure handling.
  - *An accidental `os.environ` write by a future consumer:* mitigated by T3, which runs every
    in-process consumer and asserts `os.environ` is unchanged, and by T4, which inspects `_scrubbed()`
    output.
  - *Logging leaks:* mitigated by logging the exception type name only (T6).
  - *False security claim:* the `RESIDUAL_BOUNDARY` constant and doc. GITHUB_TOKEN and the Anthropic
    credential stay readable by model `Bash`, and so do mounted files, until #869 lands.
