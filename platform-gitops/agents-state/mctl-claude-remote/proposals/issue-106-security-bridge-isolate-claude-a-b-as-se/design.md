# Design: issue-106-security-bridge-isolate-claude-a-b-as-se

## Current state

Files read in the clone (HEAD `92ea97f`, the merge of PR #104):

- `plugin/mctl-bridge/ops/install.sh`
  - Runs entirely as the operator. `H=$HOME/mctl-bridge`, with `umask 077`.
  - Creates `$H/etc/admin.pw` and `$H/etc/orch.pw`, then writes `users.acl` with
    `bridge_admin` and `bridge_orch` and keeps the `bridge_slot_*` lines.
  - Writes `valkey.conf`: `bind 127.0.0.1`, port 6390, `appendfsync always`, request
    and memory limits.
  - Rsyncs the code to `$H/plugin` and symlinks the CLI into `~/.local/bin/mctl-bridge`.
  - Installs `~/.codex/rules/mctl-bridge.rules`.
  - Bootstraps `com.mctl.bridge-{valkey,ingest,waker}` into `gui/$(id -u)` and
    kickstarts them.
  - Its header says: "Host-level separation of slots from the operator's uid is a
    separate operator step and is NOT done here".
- `plugin/mctl-bridge/ops/slot.sh` (`start|stop|show|keys|list`)
  - Creates `$H/etc/slot-<s>.pw` next to `admin.pw` and `orch.pw`, all operator-owned
    0600.
  - Runs `ACL SETUSER bridge_slot_<s> ... -@all +xadd +xread +xrevrange +ping`
    `%W~…out %R~…resp %R~…inbox` with the admin password.
  - Writes `$H/slots/<s>/{mcp.json,settings.json,run.sh}`. In `run.sh`, PATH begins
    with the operator's `$HOME/.local/bin`, which is where the `mctl-bridge` CLI lives.
    stderr goes to the operator-owned `$H/log/slot-<s>.err`.
  - Starts `screen -dmS bridge-slot-<s>` under the operator UID.
  - Uses `--permission-mode default` and only the bridge tools are pre-allowed.
  - Its header says "Slots still run under the operator's uid until the host boundary
    step is done".
  - Interpolates `$repo` and paths into a heredoc'd zsh script. PR #105 fixes this
    quoting, but #105 is not in this clone.
- `plugin/mctl-bridge/ops/com.mctl.bridge-waker.plist`: runs as the operator, with
  `MCTL_BRIDGE_CODEX_SOCKET=@HOME@/.codex/app-server-control/app-server-control.sock`
  and `KeepAlive` true. The Valkey and ingest plists follow the same pattern.
- `plugin/mctl-bridge/ops/mctl-bridge`: the orchestrator CLI wrapper with
  `MCTL_BRIDGE_VALKEY_PASSWORD_FILE=$H/etc/orch.pw`.
- `plugin/mctl-bridge/src/channel.ts` (the slot adapter)
  - Reads its password from `MCTL_BRIDGE_VALKEY_PASSWORD_FILE` (line ~469).
  - Takes its state dir from `os.homedir()/.mctl-bridge/state` and its Claude PID from
    `process.ppid` (lines ~493–494).
  - Because both depend on the UID and HOME of the process that runs it, they move to
    the slot user with no code change, provided the launcher sets HOME.
- `plugin/mctl-bridge/hooks/state.py`: writes `~/.mctl-bridge/state/<pid>.json` (mode
  0700 dir) and holds no credentials.
- `plugin/mctl-bridge/src/waker.ts`: connects to the Codex control socket from the
  operator context (line ~391).
- `plugin/mctl-bridge/src/ingest.ts`, `src/slotlink.ts`, `src/bridge.lua`: the slice 4b
  request-stream protocol. `test/isolation.test.ts` covers it against a real Valkey
  through `bridge_slot_*` credentials: own-stream-only access, unchanged state on
  refusal, identity from the stream, replay, epoch and trim cases. CI runs `bun test`
  in `.github/workflows/pr-checks.yml` (ubuntu, Bun 1.3.14). `isolation.test.ts`
  already asserts that `install.sh` writes the server limits.
- `docs/chatgpt-orchestrator-bridge.md`
  - "Permission boundary" names the target: a separate macOS user, with the control
    socket and orchestrator credentials out of reach.
  - "Slice 4 results" records the scenario 8 bypasses and the finding that launchd did
    not respawn SIGKILLed Valkey and waker despite `KeepAlive` ("pended nondemand
    spawn = inefficient").
  - "Slice 4b" lists the host acceptance checks this proposal addresses.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/claude-remote/values.yaml`: this is the cluster
  `claude-remote` pod (image 0.14.1, `replicaCount: 0`, paused 2026-10-29 because of
  the Claude account hold). It is not the Mac mini bridge. Its Valkey env points at the
  cluster `platform-events` Valkey, which belongs to slice 5 and is not touched here.
- No gitops service or tenant describes the Mac mini bridge. The bridge is installed by
  hand with `ops/install.sh` on the host, which this run cannot observe. The real UIDs,
  launchd domains, home permissions, Codex daemon, socket mode and resources are
  therefore not observed. Collecting them is task 1 (preflight), and they are listed
  under Open questions.
- The mctl MCP tools were not used. The bridge host is not a platform workload, so
  tenant and service reads would not describe it.

## Proposed solution

### Trust zones

| Zone | UID | Holds | Slot access |
|---|---|---|---|
| Operator (trusted) | operator | `$H/etc/{admin,orch}.pw`, `users.acl`, `valkey.conf`, Valkey data, ingester, waker, `~/.codex` and the control socket, the `mctl-bridge` CLI | none (dirs 0700) |
| Trusted code | operator-owned, slot read and execute | `/opt/mctl-bridge/code/<version>/` (plugin `src/`, `hooks/`), `/opt/mctl-bridge/bin/slot-run`, `/opt/mctl-bridge/etc/slots.conf` | read and execute, never write |
| Slot A config | operator-owned, group `mctlslota`, 0640 in a 0750 dir | `/opt/mctl-bridge/slots/a/{mcp.json,settings.json}` (no secrets) | A only |
| Slot A private | `mctlslota` | `/Users/mctlslota` (0700): `.claude/`, `.mctl-bridge/state`, `.mctl-bridge/slot.pw` (0400), `log/`, `work/<repo>` | A only |
| Slot B | `mctlslotb` | the same layout for B | B only |

The user names `mctlslota` and `mctlslotb`, the UIDs and `/opt/mctl-bridge` are
defaults that preflight confirms. Two users are required. A single shared `mctl-slot`
user would not separate A from B on the filesystem. Valkey stays on TCP 127.0.0.1. Any
local UID can reach the port, so per-slot passwords and ACLs are what separate the
slots there. The `default` user stays `off`.

### New and changed files (all under `plugin/mctl-bridge/ops/`)

1. **`preflight.sh`** (new, read-only, runs as the operator, no sudo)
   - Inventories `id`, `dscl . -list /Users UniqueID` (to find free UIDs and check for
     name collisions), `dscl . -read /Groups/admin`, and the process tree
     (`ps -axo user,pid,ppid,command` filtered to bridge, Codex and Claude).
   - Runs `launchctl print gui/<uid>` and `user/<uid>` for each `com.mctl.bridge-*`
     job, and lists other jobs in those domains so the blast radius is visible.
   - Runs `stat` on `$HOME`, `~/.codex`, the socket dir and socket, `$H/etc/*` and
     `$H/slots/*`.
   - Records the `claude --version` login method, and `sysctl hw.memsize`, `vm_stat`,
     `sysctl vm.swapusage` and `uptime`.
   - Prints a no-change plan, the blast radius (which jobs and users are touched; no
     production jobs are restarted), a rollback, and the exact commands that the owner
     runs by hand with sudo.
   - Writes everything to `$H/evidence/preflight-<ts>.txt` with no secret values. It
     only checks that password files exist and records their mode and owner.
2. **`provision-slot-users.sh`** (new)
   - Dry-run by default: prints the commands.
   - `--apply` refuses unless `EUID==0` and stdin is a TTY. Nothing in the repo calls
     it, and no sudo credential is passed in.
   - Creates each user with `sysadminctl -addUser <name> -UID <uid> -home /Users/<name>
     -shell /bin/zsh` plus `dscl . -create /Users/<name> IsHidden 1`. The user is not
     added to `admin`. Home mode is set to 0700.
   - Creates `/opt/mctl-bridge/{code,bin,etc,slots/a,slots/b}`: operator-owned, 0755,
     and `slots/<s>` 0750 with group `<slot user>`.
   - Installs `/etc/sudoers.d/mctl-bridge`, mode 0440 and checked with `visudo -cf`:
     `<operator> ALL=(mctlslota) NOPASSWD: /opt/mctl-bridge/bin/slot-run` and the same
     line for B. The target is the slot user, never root. `env_reset` and `closefrom`
     stay at the sudo defaults.
   - Prints the per-user Claude login step for the owner to run by hand
     (`sudo -u mctlslota -H claude` and then `/login`). Nothing is copied from the
     operator's keychain or `~/.claude`.
   - `--remove` reverses all of this (see Rollback in tasks.md).
3. **`slot-run`** (new, installed to `/opt/mctl-bridge/bin/`)
   - A zsh launcher that runs as the slot UID through `sudo -u <slot user>`. It takes
     a fixed verb set: `install-cred`, `start`, `stop`, `show`, `keys`, `probe`,
     `check`.
   - Every invocation does the following:
     - Validates the slot name against `^[a-z0-9][a-z0-9-]{0,30}$` and looks it up in
       `slots.conf`.
     - Checks that the slot's `id -u` equals the mapped UID, and that it is not 0, not
       the operator UID, not in `admin`, and not mapped twice.
     - Checks every ancestor of the code, launcher and config paths: none may be
       writable or owned by a slot UID, and none may be a symlink whose target leaves
       the trusted root.
     - Rebuilds the environment from nothing (`env -i HOME=… USER=… LOGNAME=…
       SHELL=/bin/zsh PATH=/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin
       ENABLE_CLAUDEAI_MCP_SERVERS=false`). The operator's `~/.local/bin` is never
       included.
     - Closes descriptors above 2 before `exec`.
   - `install-cred` reads the password from stdin and writes
     `$HOME/.mctl-bridge/slot.pw` with mode 0400, atomically.
   - `start <repo>` resolves the repo with `realpath` and requires it to be under
     `$HOME/work/`. It refuses if `~/.claude/settings.json` (or `settings.local.json`)
     sets `defaultMode: bypassPermissions` or `skipDangerousModePermissionPrompt`. It
     then starts `screen -dmS bridge-slot-<s>` with `claude` and an argv array:
     `--mcp-config /opt/mctl-bridge/slots/<s>/mcp.json --strict-mcp-config --settings
     … --allowedTools <bridge tools> --permission-mode default`. No
     `--dangerously-skip-permissions` is passed. stderr goes to `$HOME/log/slot.err`.
   - `show` and `keys` act on the slot's own screen session, which lives under the slot
     UID's `/tmp/uscreens/S-<user>`.
   - `probe` runs `probe-isolation.ts` (below).
4. **`slot.sh`** (changed)
   - Keeps its CLI. The operator side still generates the password and runs
     `ACL SETUSER` as admin, exactly as today.
   - Then pipes the password through `sudo -u <user> /opt/mctl-bridge/bin/slot-run <s>
     install-cred`, removes any `$H/etc/slot-<s>.pw` left over from the trusted
     experiment, renders `mcp.json` and `settings.json` into `/opt/mctl-bridge/slots/<s>/`
     (pointing `MCTL_BRIDGE_VALKEY_PASSWORD_FILE` at the slot-owned file and the code at
     `/opt/mctl-bridge/code/current`), and calls `slot-run start|stop|show|keys`.
   - `list` asks each mapped slot.
   - `MCTL_BRIDGE_ISOLATION=trusted-experiment` keeps the old same-UID behaviour for
     tests only. It prints a warning and is refused when `slots.conf` declares
     `working=1`.
5. **`install.sh`** (changed)
   - Additionally rsyncs the code to `/opt/mctl-bridge/code/<version>` and switches the
     `current` symlink (operator-owned) to it.
   - Installs `slot-run` and `slots.conf` only if `/opt/mctl-bridge` already exists and
     is operator-owned. If it does not, it prints the provisioning step and does not
     use sudo itself.
   - Valkey, ingest and waker stay operator jobs.
   - Asserts `$H`, `$H/etc` and `~/.codex/app-server-control` are 0700, and fails if
     they are not.
6. **Supervision**
   - `preflight.sh` tests respawn in a scratch label (`com.mctl.bridge-respawn-probe`,
     a `sleep` job) in both `gui/<uid>` and `user/<uid>`, without touching production
     jobs.
   - If neither domain respawns after `kill -9`, the new job
     `com.mctl.bridge-supervisor.plist` takes over: a `StartInterval` 30 job running
     `ops/supervise.sh`. The script runs `launchctl print` for each bridge label and
     `launchctl kickstart` for any that is not running, and logs each action to
     `$H/log/supervisor.log`. Timer-driven starts do not depend on KeepAlive demand.
   - The chosen domain is written into `install.sh`, `UID_` domain selection.
7. **`probe-isolation.ts`** (new, in `src/`)
   - Runs inside the actual slot process context, through `slot-run probe`. It uses the
     plugin's own RESP client (`src/valkey.ts`), so it needs no `valkey-cli` from the
     operator tree.
   - Files: attempts `open` of the peer's `slot.pw`, `~/.claude`, transcript dir,
     state dir, `work/` and `/opt/mctl-bridge/slots/<peer>/mcp.json`, plus
     `$H/etc/{admin,orch}.pw`, `users.acl` and `valkey.conf`. Attempts writes to the
     trusted code, launcher and config. Attempts symlink tricks: creating
     `$HOME/work/x -> /Users/<peer>` and asking `slot-run start` to use it.
   - Codex socket: attempts `connect()` to the control socket.
   - Valkey, using its own credential: `HSET` and `DEL` on any `mctl:bridge:*` key,
     `XADD` to the peer's `out`, `XREAD` on the peer's `inbox` and `resp`, `FCALL`,
     `EVAL`, `CONFIG SET`, `ACL LIST`, `FUNCTION LOAD`, `AUTH bridge_orch <wrong>`, and
     a spoofed `slot` field in its own outbox.
   - Also runs one permitted round trip (`status`) to prove the slot still works.
   - Emits JSONL `{check, uid_hash, valkey_user, op, target_class, outcome, detail}`.
     `detail` is an errno name or a Valkey error prefix such as `NOPERM`, never a value
     or secret.
8. **`evidence.sh`** (new, operator)
   - Before and after a probe run, dumps canonical state (`slot`, `msg`, `claim`,
     `audit` keys) with `bridge_admin` and records sha256 hashes only.
   - Hashes the trusted files (`users.acl` hashed as a file; passwords are never read
     into output).
   - Runs both slots' probes.
   - Replays forged, stale and duplicate events through the existing ingester path
     (reusing the scenarios in `test/isolation.test.ts` as live checks).
   - Writes `$H/evidence/4b-<ts>/{summary.md,matrix.json,probes-a.jsonl,probes-b.jsonl,hashes.txt,rollback.md}`.
   - The verdict is PASS only if every required check is PASS. A missing probe line is
     UNOBSERVABLE. Any success on a forbidden operation is FAIL.
9. **Docs**
   - `docs/chatgpt-orchestrator-bridge.md`: change "Permission boundary" from one
     `mctl-slot` user to two per-slot users, add a "Slice 4b host results" placeholder
     that the operator fills from the bundle, and record the supervision decision.
   - `plugin/mctl-bridge/README.md`: add an operator runbook (preflight, review,
     owner-run sudo, per-user login, install, probe, evidence, rollback).

### Why this shape

- The slot boundary is a different UID that the operator cannot accidentally give a
  shell to. sudo with a fixed target user and a fixed command, and the launcher
  re-validating argv, keeps privilege out of model processes. No root process runs
  model code.
- Credentials move by stdin into a file the slot owns. That avoids argv and env
  exposure, which a `ps -E` or a child process could otherwise read.
- The adapter and hooks already derive state from HOME and ppid. Moving UID needs no
  protocol change, and the Valkey half from #103 and #104 stays as it is.

## Alternatives

1. **One shared `mctl-slot` user**, as the doc currently suggests. Rejected: it
   protects the operator from the slots but not A from B (`slot-b.pw`, transcripts and
   worktrees would be mutually readable). The issue says this explicitly.
2. **LaunchDaemons in the `system` domain with `UserName=<slot user>`** instead of
   sudo. Each slot would be a root-installed daemon. This gives clean descriptors and
   environment, but every config change needs root, it does not fit interactive
   `screen` sessions with `show` and `keys`, and preflight has not yet shown that
   respawn works in that domain. Kept as a fallback for supervision only.
3. **macOS sandbox profiles (`sandbox-exec`) under the operator UID.** Rejected:
   `sandbox-exec` is deprecated, Claude Code's tools spawn arbitrary children, and the
   Keychain and socket remain the same UID. This is a weaker boundary than separate
   UIDs.
4. **Containers or VMs per slot.** Rejected for this host: Docker Desktop does not fit
   in 8 GB (doc, "Slice 4"), and each Claude slot is already about 300 MB.

## Platform impact

- **Migration:** existing `$H/etc/slot-*.pw` and `bridge_slot_*` users stay valid.
  `slot.sh start` rotates the password into the slot home on first isolated start and
  deletes the operator-side copy. Running trusted-experiment slots must be stopped
  first. That is an operator action and is not done automatically.
- **Backward compatibility:** the CLI, the Valkey protocol, the plists' environment and
  the Codex rules are unchanged. The trusted-experiment mode remains behind an explicit
  env var for CI and dev, and is refused when working slots are enabled.
- **Resources:** two more macOS users and home directories, plus duplicated `~/.claude`
  per user (tens of MB). No extra resident processes, except the optional supervisor
  timer.
- **Risks and mitigations:**
  - Claude login may not work for a non-GUI user. Preflight probes it, and it is listed
    as an open question with a token-file fallback.
  - The sudoers rule is an escalation path from the operator to the slots, never the
    reverse. It is limited to one binary that is not slot-writable, and verified with
    `visudo -cf`.
  - A slot can still edit its own `~/.claude` settings. The launcher refuses bypass
    modes at start. Changes made mid-session still require a permission prompt in
    default mode. The residual risk is documented.
  - Localhost Valkey is reachable by any UID, so the ACL is the boundary. The probes
    cover it from the real slot context.
  - `/opt` creation and sudoers changes are host-wide. Dry-run, rollback, and no
    restart of unrelated jobs keep the blast radius small.
  - The launchd respawn defect is mitigated by a probe-chosen domain or the supervisor.
    A reboot remains a separate operator test.
