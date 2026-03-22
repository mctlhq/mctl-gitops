# mctl — CLI for the mctl.ai platform

Command-line tool for deploying, managing, and deleting services on the mctl.ai platform.
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

### Deploy OpenClaw

```bash
# Template-based onboard with auto-generated host
mctl deploy -t my-team -n openclaw --service-template openclaw \
  --telegram-owner-id 123456789 \
  --telegram-bot-token 123:abc \
  --wait

# Optional: preconfigure a model API key for headless setup
mctl deploy -t my-team -n openclaw --service-template openclaw \
  --secret OPENAI_API_KEY=sk-xxx \
  --wait
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

Authentication: set `MCTL_TOKEN` or `GITHUB_TOKEN`, or fall back to `gh auth token`.
