# mctl — CLI for the mctl.ai platform

Command-line tool for deploying, managing, and deleting services on the mctl.ai platform.
Same operations as the Backstage UI, but from your terminal.

## Prerequisites

- A browser on this machine for `mctl auth login`. The [gh CLI](https://cli.github.com/)
  is only needed for the deprecated `MCTL_AUTH=github` path.
- Go 1.26.9+ (for building from source). The `go` directive in `go.mod` is a
  minimum, not a pin, so a newer toolchain always satisfies it. The floor is
  1.26.9 because it closes the reachable `net/http`, `net/textproto` and
  `crypto/tls` advisories (GO-2026-6603..6617) that the 1.25 line never got a
  fix for (verified with `govulncheck`: 9 reachable under
  `GOTOOLCHAIN=go1.25.13`, clean under go1.26.9). Being "above the floor" is
  not the same as being patched: check a newer minor line with `govulncheck`
  too.

## Install

```bash
cd cli/mctl
make install
```

Or build locally:

```bash
make build
./mctl --help
```

## Signing in

```bash
mctl auth login      # browser sign-in with your MCTL account
mctl auth status     # shows the sign-in and asks the API who you are
mctl auth logout     # revokes the sign-in and removes it from this machine
```

`mctl auth login` signs you in through the mctl API's own OAuth server, the
same one MCP clients use: the CLI registers itself as a public client,
opens the browser, and receives the result on a loopback port
(authorization code with PKCE). The API sends you to auth.mctl.ai and then
issues its own token, which carries the tenant and admin access of your
linked account. If the sign-in ends with no access, link your account once
at `https://api.mctl.ai/identity/link/zitadel`.

The sign-in is stored in `<user config dir>/mctl/api-token.json` (mode 600
on Unix; override with `MCTL_API_TOKEN_FILE`) and refreshed automatically.
It is bound to the API it was issued by: with another `MCTL_API_URL` it is
not sent, and you sign in again.

Which credential a command sends, first match wins:

1. `MCTL_TOKEN`, when set.
2. What `MCTL_AUTH` selects: `zitadel` for a raw ZITADEL token (below), or
   `github` for the GitHub token (`GITHUB_TOKEN`, then `gh auth token`).
   Any other value is an error. `MCTL_AUTH=github` is **deprecated**: it
   prints a one-line warning on stderr and stops working once the API no
   longer accepts GitHub tokens (mctlhq/mctl-api#525).
3. The stored sign-in from `mctl auth login`.

With none of these, the command fails and asks you to run `mctl auth login`.
The GitHub token is never used implicitly: earlier versions fell back to it
when there was no stored sign-in, and that fallback is gone. A stored sign-in
that cannot be read or refreshed is an error as well.

### Raw ZITADEL token

`mctl auth login --zitadel` signs in directly at auth.mctl.ai (the
`mctl-cli` application of project "MCTL API") and `MCTL_AUTH=zitadel` sends
that token. It carries no tenant or admin access in mctl-api
(mctlhq/mctl-api#435, #377), so it is only useful for identity checks; use
plain `mctl auth login` for everything else. The token lives in
`<user config dir>/mctl/zitadel-token.json` (`MCTL_ZITADEL_TOKEN_FILE`);
`MCTL_ZITADEL_ISSUER` and `MCTL_ZITADEL_CLIENT_ID` override the defaults.
`mctl auth logout --zitadel` removes it.

## Usage

### Deploy a service

```bash
# Web service with ingress
mctl deploy -t my-team -n my-api -r mctlhq/my-api -g v1.0.0 \
  --host my-api.preview.mctl.ai

# Background worker (no --host)
mctl deploy -t my-team -n my-worker -r mctlhq/my-worker -g v1.0.0

# With env vars and secrets
mctl deploy -t my-team -n my-api -r mctlhq/my-api -g v1.0.0 \
  --host my-api.preview.mctl.ai \
  --env LOG_LEVEL=info --env PORT=3000 \
  --secret API_KEY=sk-xxx

# Wait for completion
mctl deploy -t my-team -n my-api -r mctlhq/my-api -g v1.0.0 --wait
```

### Update service config

```bash
mctl config -t my-team -n my-api --env LOG_LEVEL=debug --secret DB_PASS=newpass
```

### Delete a service

```bash
# Interactive confirmation
mctl delete -t my-team -n my-api

# Skip confirmation
mctl delete -t my-team -n my-api -y
```

### Check auth

```bash
mctl auth status
```

## How it works

`mctl` calls the mctl-api REST endpoint to trigger platform operations via Argo Workflows:

| Command | API Operation | Action |
|---------|---------------|--------|
| `mctl deploy` | deploy-service | onboard |
| `mctl config` | deploy-service | update-config |
| `mctl delete` | retire-service | — |
| `mctl status` | (read) | GET /api/v1/status |
| `mctl logs` | (read) | GET /api/v1/logs |

Authentication: see [Signing in](#signing-in).
