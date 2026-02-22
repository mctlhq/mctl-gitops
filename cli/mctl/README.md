# mctl — CLI for the mctl.me platform

Command-line tool for deploying, managing, and deleting services on the mctl.me platform.
Same operations as the Backstage UI, but from your terminal.

## Prerequisites

- [gh CLI](https://cli.github.com/) installed and authenticated (`gh auth login`)
- Go 1.21+ (for building from source)

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

## Usage

### Deploy a service

```bash
# Web service with ingress
mctl deploy -t my-team -n my-api -r mctlhq/my-api -g v1.0.0 \
  --host my-api.preview.mctl.me

# Background worker (no --host)
mctl deploy -t my-team -n my-worker -r mctlhq/my-worker -g v1.0.0

# With env vars and secrets
mctl deploy -t my-team -n my-api -r mctlhq/my-api -g v1.0.0 \
  --host my-api.preview.mctl.me \
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

`mctl` dispatches the same GitHub Actions workflows that Backstage templates use:

| Command | Workflow | Action |
|---------|----------|--------|
| `mctl deploy` | `release-service.yml` | `onboard` |
| `mctl config` | `release-service.yml` | `update-config` |
| `mctl delete` | `retire-service.yml` | — |

Authentication uses your existing `gh` CLI token — no separate login needed.
