# labs/claude-remote

Persistent `claude --remote-control` session running in the `labs` namespace,
accessible from any device via [claude.ai/code](https://claude.ai/code).
Device name registered with Anthropic: **`claude-remote`**.

- Source: [`mctlhq/mctl-claude-remote`](https://github.com/mctlhq/claude-remote)
- Image: `ghcr.io/mctlhq/claude-remote:<semver>`
- Ingress: `claude-remote.mctl.ai` (forward-auth via Backstage OIDC) — exposes
  `/healthz` only; the actual remote-control transport runs outbound to
  Anthropic's cloud.

## How state persists

`/workspace` lives in an `emptyDir` volume, mirrored to MinIO every 10s by the
`s3-sync` sidecar at prefix `s3://platform-state/labs/claude-remote/`. On pod
start the `restore-state` initContainer pulls everything back. This includes
the rotating OAuth credentials (`.claude/.credentials.json`), so device
identity survives pod restarts and Recreate rollouts.

## First-time bootstrap (one-off, manual)

`--remote-control` device registration requires a **full-scope OAuth login**.
Tokens from `claude setup-token` (the long-lived form intended for SDK use)
are inference-only by Anthropic policy and are rejected at remote-control
init with:

```
[WARN] Remote Control requires a full-scope login token.
Long-lived tokens (from `claude setup-token` or CLAUDE_CODE_OAUTH_TOKEN)
are limited to inference-only for security reasons.
Run `claude auth login` to use Remote Control.
```

**`CLAUDE_CODE_OAUTH_TOKEN` env var is deliberately NOT set in this chart.**
If it were, claude would prefer it over `~/.claude/.credentials.json` and
silently fall back to inference-only mode, even though the on-disk full-scope
credentials are sitting right there. We learned this the hard way (PR #259).
`claude auth status` is the diagnostic — `authMethod: "oauth_token"` means
the env var won; `authMethod: "claude.ai"` means credentials.json is in use.

So the very first time this service is deployed (or after MinIO state for it
is wiped), run `claude auth login` inside the pod once:

```sh
export KUBECONFIG=.../mctl-gitops/infrastructure/k3s-preview/kubeconfig.yaml
POD=$(kubectl --context mctl-preprod -n labs get pods \
  -l app.kubernetes.io/instance=labs-claude-remote -o name | head -1)

kubectl --context mctl-preprod -n labs exec -it "$POD" -c base-service \
  -- /workspace/.local/bin/claude auth login
```

Follow the prompts:

1. claude prints an OAuth URL — open on phone or any browser, sign in to your
   claude.ai account.
2. claude.ai shows a short code → paste into the terminal → enter.
3. `Login successful.` — credentials written to
   `/workspace/.claude/.credentials.json` (mode 0600).
4. Wait ~10s for `s3-sync` to mirror the file to MinIO.
5. Delete the pod so the running `claude --remote-control` re-reads
   credentials at startup:

   ```sh
   kubectl --context mctl-preprod -n labs delete pod "$POD"
   ```

After the new pod comes up, claude.ai → Code should list `claude-remote`
as a connected device. Verify in logs that the welcome banner now shows
`<email>'s Organization` and 5+ ESTABLISHED outbound sockets exist.

## Why this is OK from a GitOps perspective

OAuth credentials are **rotating, stateful** secrets — the access token is
refreshed each hour and the file gets rewritten. That makes them a bad fit
for Vault + ExternalSecret (which would freeze the file at bootstrap and
break login when the refresh-token rotation cycle starts). MinIO is the
correct state store: `s3-sync` continuously persists the rotation, and
`restore-state` makes the bootstrap reproducible from pod-restart onwards.

What lives in git: the contract (volumes, sidecar, init container,
ingress). What lives in MinIO: the credentials themselves. The only
out-of-band action is the one-time human OAuth flow above.

## Why the npm-global vs native binary inconsistency

`Dockerfile` installs `@anthropic-ai/claude-code` via npm → ends up at
`/usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`.
A previous diagnostic also ran `claude install latest` inside the pod
which placed a native build at `/workspace/.local/bin/claude` — this is
persisted via MinIO and `claude doctor` will warn `Native installation
exists but ~/.local/bin is not in your PATH`. The warning is harmless;
the entrypoint deliberately uses the npm-global `claude` to keep the
binary in the image and avoid relying on workspace-state for the
executable. Don't add `~/.local/bin` to PATH unless you also remove
the bootstrap copy from MinIO.

## Connecting

- **Phone / web**: claude.ai → Code tab → tap `claude-remote`.
- **Local CLI**: `claude --remote claude-remote` (binds to the in-cluster
  session over Anthropic's cloud).

The pod's REPL runs in `/workspace`. Anything written there is mirrored to
MinIO; on next pod start it comes back. Don't put credentials for *other*
systems in `/workspace` unprotected — anyone with `--remote claude-remote`
access via your claude.ai account can read it.
