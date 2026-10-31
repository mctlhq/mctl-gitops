# Tasks: issue-920-security-agents-consume-rotated-agent-cr

- [ ] 1. Add `orchestrator/credential_files.py`: `CredentialSpec`, `INVENTORY` (the design's table,
  names and lifetime classes only), `read_credential(name, env=None)` with the `<NAME>_FILE` ->
  last-good -> env `<NAME>` -> "" order, `file_env_names()` and `RESIDUAL_BOUNDARY` — DoD: the module
  has no `os.environ` writes; failed reads log the name, path and `type(exc).__name__` only; ruff and
  mypy are clean.
- [ ] 2. Reimplement `orchestrator/github_token.py:refresh_github_token()` on `read_credential`
  (depends on 1) — DoD: same public behaviour (it writes `os.environ["GITHUB_TOKEN"]`); the log line no
  longer interpolates the exception message; `tests/test_github_token.py` passes, with assertions
  updated only for the log text.
- [ ] 3. Call `refresh_github_token()` once at the start of `main()` in `run_issue_investigator.py`,
  `run_implementer.py`, `run_shepherd.py`, `run_usage_collector.py`, `run_scout.py`, `run_all.py`
  (entrypoint of `cwft-mctl-agents-run.yaml`) and the Temporal worker entrypoint (depends on 2) — DoD: with only `GITHUB_TOKEN_FILE` set, the first `gh` call
  inherits the file's token.
- [ ] 4. Switch the usage writer: `UsageRecorder` holds a token source and resolves it per delivery
  (`usage_ledger.py:543`, `:704`) (depends on 1) — DoD: `enabled` and `_off_reason` are unchanged for
  the env path; an explicit `token=` still wins.
- [ ] 5. Switch the evidence writer: `evidence_producer.writer_credentials` / `_credentials` use
  `read_credential` (depends on 1) — DoD: `decision_records.py` gets the same file-backed token through
  `writer_credentials`.
- [ ] 6. Switch the `MCTL_TOKEN` read sites (`options.py:133`, `capability_gateway.py:400`,
  `action_approvals.py:326`, `commerce.py:631`, `lifecycle/client.py:91`, `lifecycle/claim.py:134`,
  `run_shepherd.py:250`, `pr_adoption.py:355`, `temporal/mctl_client.py:24`, `run_token.py:263`,
  `work_context/client.py`) to `read_credential("MCTL_TOKEN")`. REST clients resolve per request when no
  token was injected (depends on 1) — DoD: `validate_manifest.py`'s save/restore of `MCTL_TOKEN` still
  works; no new `os.environ` writes.
- [ ] 7. Switch `run_scout.py:57` to `read_credential("SCOUT_TELEGRAM_BOT_TOKEN")` (depends on 1) —
  DoD: the existing "required" error path still fires when neither the file nor the env var is set.
- [ ] 8. Make the Anthropic credential file-backed and session-scoped in `orchestrator/auth.py`:
  `detect_auth()` resolves through `read_credential`, a new `session_auth_env()` returns the active
  variable, and `rotate_to_secondary_auth()` flips a module selector instead of writing `os.environ`
  (depends on 1) — DoD: the env-only path behaves exactly as today; with `_FILE` set, `os.environ`
  never gains the value.
- [ ] 9. Extend `options.py:_scrubbed()`: blank every `file_env_names()` entry and merge
  `auth.session_auth_env()` into `options.env` (non-provider sessions only; the provider path keeps
  blanking Anthropic credentials) (depends on 1, 8) — DoD: the existing scrub tests pass.
- [ ] 10. Write `docs/security/credential-files.md`: the inventory table, the "Contract for
  mctl-gitops#2288" section (which seeds can be removed, and which CWFT shell checks of
  `$GITHUB_TOKEN` / `$CLAUDE_CODE_OAUTH_TOKEN` must switch to `[ -s "$..._FILE" ]`), and
  `RESIDUAL_BOUNDARY` verbatim (depends on 1) — DoD: no credential values appear; lifetimes not observed
  are written as "not observed".
- [ ] 11. Add a CHANGELOG entry (handled by release-please through the commit message) (depends on 2-10).

## Tests

- [ ] T1. Parametrized over every in-process `INVENTORY` entry: with `<NAME>` unset and `<NAME>_FILE`
  pointing at a tmp file, the real consumer (UsageRecorder delivery with a stub transport,
  `writer_credentials`, a lifecycle/approvals client request with a stub transport,
  `mctl_mcp_config()`, the scout token read) sends the file's value. This fails if the file reader is
  removed.
- [ ] T2. Rotation: for each per-operation consumer, write value A, perform an operation, write value B,
  perform a second operation, and assert the second sent B. For GITHUB_TOKEN, assert that a stub
  subprocess sees B after `refresh_github_token()`.
- [ ] T3. No env re-seed: snapshot `os.environ` before and after every T1/T2 consumer call and assert it
  is unchanged for in-process credentials and for the Anthropic credential when file-backed. This fails
  if the env seed is restored.
- [ ] T4. Session env: for every `ClaudeAgentOptions` builder in `options.py`, with file-backed
  credentials, assert that `options.env` contains no in-process credential value and no `*_FILE`
  pointer for in-process credentials, and contains the Anthropic credential only under its single
  active variable name.
- [ ] T5. Fallbacks: unreadable file, empty file and invalid UTF-8 (the last-good value is used); `_FILE`
  unset (the env value is used); neither set (the consumer's "not set" path runs).
- [ ] T6. Log hygiene: an invalid-UTF-8 file whose bytes include a marker: captured stdout and logs
  contain neither the marker nor any byte value from the file, only the variable name, the path and
  `UnicodeDecodeError`.
- [ ] T7. 429 rotation: with both primary and secondary file-backed, `rotate_to_secondary_auth()` makes
  the next `session_auth_env()` return the secondary value and leaves `os.environ` unchanged.
- [ ] T8. Residual boundary: `RESIDUAL_BOUNDARY` names `#869`, and `docs/security/credential-files.md`
  contains it verbatim and lists every `INVENTORY` name (and no others).

## Rollback

The change is backward compatible: every reader falls back to the `<NAME>` env var when `<NAME>_FILE`
is unset. To roll back, revert the PR and release the previous image tag. Rolling back while
mctl-gitops#2288 has already removed an env seed breaks that consumer. In that case, first re-add the
`secretKeyRef` seed in gitops (revert the matching #2288 commit), then roll the image back. #2288
should therefore remove seeds only after this release is deployed, one credential at a time.
