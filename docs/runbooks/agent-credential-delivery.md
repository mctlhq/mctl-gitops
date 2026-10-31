# Agent credential delivery (mctl-gitops#2288)

Spike mctlhq/mctl-agents#807 gap G2: agent pods used to receive credentials as
`env[].valueFrom.secretKeyRef`, fixed at container start and inherited by every
child process.

## State

- Inventory: `platform-gitops/governance/agent-credential-delivery.yaml`
  (names only, one row per CWFT/template/env var, with `classification` and
  `delivery`).
- Phase 1 (this change): `github-token` is delivered only as a file,
  `/var/run/gh/github-token` (`GITHUB_TOKEN_FILE`), from a `github-token-file`
  Secret volume (`defaultMode: 0440`, `readOnly`, agent container only). The
  token is rotated every 30 min by `rotate-github-app-tokens`; kubelet
  refreshes the volume and `refresh_github_token()` (mctl-agents >= 1.113.0,
  mctlhq/mctl-agents#920) re-reads it before each gh/git call. Shell
  `gh auth setup-git` calls get the token in that one command's env only.
- Every other credential (Claude OAuth tokens, `mctl-token`, usage/evidence
  writer tokens, scout Telegram) stays `env-seed` and is long-lived with no
  short-lived form; they move in mctl-gitops#2296.

## What this does not claim

A file in the same container is readable by the model's `Bash` tool. Per
credential: `NO_LONG_LIVED_SECRET_ENV_SEED` is true only for `delivery: file`
rows, `SHORT_LIVED_OR_ROTATABLE` only for `github-token`, and
`MODEL_SHELL_CANNOT_READ_CREDENTIAL_BYTES` is false for all rows
(mctlhq/mctl-agents#869).

## CI

`scripts/validate-agent-credential-delivery.py` (with `--selftest`) and
`tests/test_agent_credential_delivery.py` run in `validate-manifests.yml`. They
fail on an unlisted agent `secretKeyRef`, a restored env seed for a `file` row,
a file volume looser than `0440` or not `readOnly`, or a credential volume
mounted in an initContainer.

## Rollback

Revert the migration commit: it restores the `GITHUB_TOKEN` `secretKeyRef`,
the old shell guards and the inventory rows in one change. ArgoCD syncs in
about 3 min; running workflows keep their submit-time template. No Vault or
Secret data is changed. An unreadable file shows up as a gh auth failure on the
first run after sync.
