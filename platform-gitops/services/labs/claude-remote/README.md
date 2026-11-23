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

`/workspace` lives in an `emptyDir` volume, mirrored to Cloudflare R2 every 5 minutes
(the credentials file within 60s of a change, because the refresh token rotates) by the
`s3-sync` sidecar at prefix `s3://claude-remote-state/labs/claude-remote/`. On pod
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

So the very first time this service is deployed (or after R2 state for it
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
4. Wait up to ~60s for `s3-sync` to mirror the file to R2.
5. Delete the pod so the running `claude --remote-control` re-reads
   credentials at startup:

   ```sh
   kubectl --context mctl-preprod -n labs delete pod "$POD"
   ```

After the new pod comes up, claude.ai → Code should list `claude-remote`
as a connected device. Verify in logs that the welcome banner now shows
`<email>'s Organization` and 5+ ESTABLISHED outbound sockets exist.

## Resuming after a pause (`replicaCount: 0` back to `1`)

`values.yaml` carries `replicaCount: 0` while the Claude account this pod signs
in with is on hold (paused 2026-10-29). Nothing in the `s3-sync` sidecar runs
while it is 0, so a change to that script, such as the 5-minute mirror cadence
(`MIRROR_EVERY`) added to cut R2 Class A operations, is not exercised until the
pod comes back. Verify it then, in this order, before leaving the pod alone:

1. **Precondition.** The account question is settled and `claude auth login`
   works from this pod (see First-time bootstrap). Resuming with a held account
   restarts the rejected-request loop that caused the pause.
2. **Resume by PR.** Set `replicaCount: 1`, merge, let Argo sync. Never
   `kubectl scale`: Argo reverts it.
3. **The sidecar is up and not refusing.** `restore-state` completed and
   `s3-sync` is running:

   ```sh
   kubectl --context mctl-preprod -n labs get pods -l app.kubernetes.io/instance=labs-claude-remote
   kubectl --context mctl-preprod -n labs logs "$POD" -c s3-sync --tail=50 | grep -c 'cred-guard'   # expect 0
   ```

   A `[cred-guard] REFUSING` line means the local credentials are empty or
   expired; stop here and use Mode A below. R2 still holds the last good copy.
4. **Credentials reach R2 within about a minute.** The credentials file is
   checked on every 60 s tick and copied only when its content changed, so right
   after a fresh login both objects must exist and be recent:

   ```sh
   kubectl --context mctl-preprod -n labs exec "$POD" -c s3-sync -- sh -lc \
     'mc ls s3/claude-remote-state/labs/claude-remote/.claude/ | grep credentials'
   # expect .credentials.json and .credentials.json.lastgood, both with a fresh timestamp
   ```

5. **The rest of `/workspace` follows within about 5 minutes** (full mirror
   every `MIRROR_EVERY` ticks): a new transcript under
   `.claude/projects/-workspace/*.jsonl` appears in R2 after one cycle.
6. **R2 cost stays where the change says it should.** R2 bills Class A
   operations in whole 1M blocks above a free 1M per cycle (the 22nd to the
   21st), and this bucket alone produced about 134k of them (~19k a day) in
   the week of 2026-10-22, before the cadence change. After a day running,
   `r2_ops_budget_class_a_used` (vm-rules/r2-ops-budget.yaml) should rise far
   slower than that. If the bucket is back near 19k a day, the cadence did not
   take effect: check the `s3-sync` args for `MIRROR_EVERY`. An
   `R2OpsClassAHeadingOverFreeTier` alert in the first days after a resume is
   the same signal.

If any step fails, set `replicaCount` back to 0 by PR rather than debugging with
the pod running against a possibly held account.

## Recovery runbook — wedged or disconnected session

Two distinct failure modes drop the device; recovery differs. Identify which
one first.

### Mode A — credential-wipe loop (pod CrashLoops / 503 / "Not logged in")

Symptom: base-service restart-loops, liveness fails, `claude auth status` →
`authMethod: "none"`. Cause: the OAuth login was lost and the `s3-sync` mirror
propagated the local logout to R2, so `restore-state` has nothing to pull.

Recovery: re-run the **First-time bootstrap** `claude auth login` above in a
real interactive TTY (`exec -it`), wait ~60s for the R2 mirror, verify
`.credentials.json` landed, then delete the pod.

### Mode B — websocket-wedge (pod healthy, claude.ai says "Remote Control disconnected")

Symptom: claude.ai shows the session "stopped responding", but the pod is
`Running`/`Ready` with `restarts=0` and `claude auth status` is fine. The
process is alive but its event loop is stalled (typically after a long blocking
poll loop), so the relay websocket died while the TCP connection lingers
ESTABLISHED.

**This self-heals — the steps below are a manual fallback.** Two layers,
fastest first:

- **In-pod watchdog (`0.8.0+`):** an entrypoint background loop detects unread
  relay data in the socket receive queue and, after `WATCHDOG_STALL_SECONDS`
  (120s), kills the wedged claude leaf so the supervisor relaunches it in-pod
  with `--resume` — no pod recreate.
- **kubelet backstop (`0.7.0+`):** `/healthz` detects the same stall
  (`RELAY_STALL_MS`, 120s) and fails liveness → kubelet recreates the pod →
  resume via `--resume` (`0.5.0+`). Covers the case where the in-pod relaunch
  can't recover.

Use the steps below only to recover faster than the watchdog, or to resume a
*specific* session.

Set up access:

```sh
export KUBECONFIG=.../mctl-gitops/infrastructure/k3s-preview/kubeconfig.yaml
POD=$(kubectl --context mctl-preprod -n labs get pods \
  -l app.kubernetes.io/instance=labs-claude-remote -o name | head -1)
POD=${POD#pod/}
```

1. **Confirm it's wedged (read-only).** Find the claude PID (the process whose
   cmdline contains `--remote-control` and is *not* the `sh -c` wrapper) and
   check it is idle and not draining its relay socket:

   ```sh
   # CPU delta ~0 over 3s = blocked event loop
   kubectl --context mctl-preprod -n labs exec "$POD" -c base-service -- sh -lc '
     read _ _ _ _ _ _ _ _ _ _ _ _ _ u1 _ < /proc/<PID>/stat; sleep 3
     read _ _ _ _ _ _ _ _ _ _ _ _ _ u2 _ < /proc/<PID>/stat
     echo "cpu delta=$((u2-u1)) (0=blocked)"'
   # unread relay backlog (rxq>0 on a :443 socket = not draining = wedged)
   kubectl --context mctl-preprod -n labs exec "$POD" -c base-service -- sh -lc '
     awk "NR>1 && \$4==\"01\" && \$3 ~ /:01BB$/ {print \"txq:rxq=\" \$5}" \
       /proc/net/tcp /proc/net/tcp6'
   ```

   A frozen TUI timer in the logs ("Channeling… (Ns)" not advancing) is the
   tell-tale.

2. **Snapshot the recovery point.** Record the session UUID and confirm it is in
   R2 *before* any destructive step. A restart creates a *newer* blank
   session, so a later resume must target this UUID explicitly — not "newest".

   ```sh
   kubectl --context mctl-preprod -n labs exec "$POD" -c base-service -- sh -lc \
     'ls -t /workspace/.claude/projects/*/*.jsonl | head -1'   # -> <UUID>.jsonl
   kubectl --context mctl-preprod -n labs exec "$POD" -c s3-sync -- sh -lc \
     'mc ls s3/claude-remote-state/labs/claude-remote/.claude/projects/-workspace/<UUID>.jsonl'
   ```

3. **(Historical) targeted PTY interrupt — skip it.** A single ESC into the PTY
   master does **not** revive a `--remote-control` session (input arrives from
   the relay, not local stdin), so this is retained only as context. Note also
   that as of `0.8.0` PID 1 is the **supervisor shell**, not `script` — the PTY
   master now lives on the `script` child (the `script -qfc "claude
   --remote-control …"` process), not `/proc/1/fd/*`. Just let the watchdog act
   or go straight to the restart below; never spray ESC/Ctrl-C across `/proc`.

4. **Graceful restart.** Once confirmed wedged and the transcript is verified in
   R2:

   ```sh
   kubectl --context mctl-preprod -n labs delete pod "$POD"
   ```

   `terminationGracePeriodSeconds: 60` lets `s3-sync` flush; `restore-state`
   pulls creds + transcripts back. On `0.5.0+` the new pod auto-resumes the
   latest session (entrypoint `--resume`); look for
   `[entrypoint] resuming session <uuid>` in the logs.

5. **Resume a *specific* session.** To bring back a particular conversation
   instead of the newest, set `RESUME_SESSION_ID: "<uuid>"` in this service's
   `values.yaml` and let ArgoCD roll the pod. Set `RESUME_SESSION: "false"` to
   force a fresh session (e.g. if a transcript is corrupt).

Post-recovery checks: `claude auth status` → `authMethod: claude.ai` /
`subscriptionType: max`; pod `Ready` (so `/healthz` is 200); the resume-target
transcript still present in R2; entrypoint log shows the resumed session id.

## Why this is OK from a GitOps perspective

OAuth credentials are **rotating, stateful** secrets — the access token is
refreshed each hour and the file gets rewritten. That makes them a bad fit
for Vault + ExternalSecret (which would freeze the file at bootstrap and
break login when the refresh-token rotation cycle starts). R2 is the
correct state store: `s3-sync` continuously persists the rotation, and
`restore-state` makes the bootstrap reproducible from pod-restart onwards.

What lives in git: the contract (volumes, sidecar, init container,
ingress). What lives in R2: the credentials themselves. The only
out-of-band action is the one-time human OAuth flow above.

## Why the npm-global vs native binary inconsistency

`Dockerfile` installs `@anthropic-ai/claude-code` via npm → ends up at
`/usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`.
A previous diagnostic also ran `claude install latest` inside the pod
which placed a native build at `/workspace/.local/bin/claude` — this is
persisted via R2 and `claude doctor` will warn `Native installation
exists but ~/.local/bin is not in your PATH`. The warning is harmless;
the entrypoint deliberately uses the npm-global `claude` to keep the
binary in the image and avoid relying on workspace-state for the
executable. Don't add `~/.local/bin` to PATH unless you also remove
the bootstrap copy from R2.

## Connecting

- **Phone / web**: claude.ai → Code tab → tap `claude-remote`.
- **Local CLI**: `claude --remote claude-remote` (binds to the in-cluster
  session over Anthropic's cloud).

The pod's REPL runs in `/workspace`. Anything written there is mirrored to
R2; on next pod start it comes back. Don't put credentials for *other*
systems in `/workspace` unprotected — anyone with `--remote claude-remote`
access via your claude.ai account can read it.
