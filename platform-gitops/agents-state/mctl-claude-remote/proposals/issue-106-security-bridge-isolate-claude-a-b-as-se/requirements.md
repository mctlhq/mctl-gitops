# Bridge slice 4b host isolation: Claude slots A and B as separate macOS users, scenario 8 refused

## Context

Issue #106 asks to finish the host half of slice 4b of the ChatGPT orchestrator bridge
(`docs/chatgpt-orchestrator-bridge.md`, "Slice 4b: security boundary"). The Valkey half
is in code. Each slot has its own `bridge_slot_<name>` user that can only append to
`s:<slot>:out` and read `s:<slot>:resp` and `s:<slot>:inbox`
(`plugin/mctl-bridge/ops/slot.sh`). A single ingester running as `bridge_orch` applies
the requests (`src/ingest.ts`). On the host side, every process still runs under the
operator's macOS UID. The slice 4 trusted-experiment run (scenario 8) found that
`admin.pw`, `orch.pw` and the peer slot's password were readable from a slot, and that
the Codex app-server control socket accepted a connection. `ops/install.sh` and
`ops/slot.sh` both say that host separation "is NOT done here".

This proposal adds the code, the operator runbooks and the probes that move slots A and
B onto two distinct non-admin macOS identities. Valkey, the ingester, the waker and the
Codex daemon stay in the operator's trusted context. The proposal also produces an
evidence bundle that shows the scenario 8 bypasses are now refused. Every privileged
host change is a separate step that the owner runs by hand. Nothing in this proposal
runs sudo, changes accounts, restarts jobs or admits working slots on its own.

## User stories

- AS the bridge owner I WANT a read-only preflight with a no-change plan, blast radius,
  rollback and the exact commands SO THAT I can review the host change before I grant
  privilege.
- AS the bridge owner I WANT slots A and B to run under two distinct non-admin macOS
  users SO THAT neither slot can read the other's credentials, transcripts, worktrees or
  bridge state, or any orchestrator or admin secret.
- AS the orchestrator operator I WANT a trusted launcher that starts, stops and inspects
  a slot under its own UID SO THAT slot processes never hold my UID, my environment or
  my descriptors.
- AS a security reviewer I WANT probes that run inside the actual spawned slot process
  context and produce a sanitized PASS/FAIL/UNOBSERVABLE bundle SO THAT production
  claims rest on observed refusals, not on a simulated ACL role.
- AS the operator I WANT the bridge jobs to recover from SIGKILL without a manual
  kickstart SO THAT scenario 7 recovery does not depend on me.

## Acceptance criteria (EARS)

Preflight and provisioning

- WHEN the operator runs `ops/preflight.sh` THE SYSTEM SHALL change nothing on the host
  and SHALL print the following. Operator UID and groups. Candidate free UIDs for the
  slot users. The bridge process tree. The launchd domains and job states of
  `com.mctl.bridge-*`. The home directory and `~/.codex` permissions. The Codex daemon
  and its socket owner and mode. The current `$H/etc` and `$H/slots` modes. CPU, memory
  and swap. Then a no-change plan, the blast radius, a rollback and the exact sudo
  commands.
- WHEN `ops/provision-slot-users.sh` runs without `--apply` THE SYSTEM SHALL print the
  privileged commands it would run and SHALL perform none of them.
- IF `ops/provision-slot-users.sh --apply` is not running with an effective UID of 0
  from an interactive terminal THEN THE SYSTEM SHALL refuse and exit non-zero. Nothing
  in the repo invokes it.
- WHEN provisioning runs THE SYSTEM SHALL create two distinct hidden, non-admin users,
  each with its own primary group, one for slot A and one for slot B. Neither is a
  member of `admin` or listed in sudoers, and neither owns or can write any trusted
  path. Each home directory
  is mode 0700.
- WHEN provisioning runs THE SYSTEM SHALL install a sudoers drop-in that lets only the
  operator run only `/opt/mctl-bridge/bin/slot-run` as each slot user, and SHALL
  validate the drop-in with `visudo -cf` before installing it.

Trusted launcher and filesystem

- WHILE a slot runs THE SYSTEM SHALL run its `claude` process, its MCP adapter
  (`src/channel.ts`) and its hooks (`hooks/state.py`) under that slot's own UID. HOME,
  `~/.claude`, `~/.mctl-bridge/state`, logs and worktrees are private to that UID.
- WHILE a slot runs THE SYSTEM SHALL keep Valkey, the ingester, the waker and the Codex
  daemon under the operator UID. `admin.pw` and `orch.pw` stay in an operator-only
  directory (0700) and the control socket stays in an operator-only directory.
- WHEN the launcher starts a slot THE SYSTEM SHALL clear the environment, set HOME,
  USER, SHELL and PATH explicitly (PATH never includes the operator's `~/.local/bin` or
  the `mctl-bridge` CLI), pass no credential in argv or environment, and close every
  inherited descriptor above 2.
- WHEN the launcher starts a slot THE SYSTEM SHALL start Claude Code with
  `--permission-mode default` and SHALL NOT pass `--dangerously-skip-permissions`.
- IF the slot's user-level Claude settings set `bypassPermissions` or
  `dangerously-skip-permissions` THEN THE SYSTEM SHALL refuse to start that slot.
- IF the slot name is not in the trusted slot map, OR maps to UID 0, the operator UID,
  an admin-group member, or a UID already mapped to another slot, THEN THE SYSTEM SHALL
  refuse to start it.
- IF the repo path is not under that slot's permitted worktree root after symlinks are
  resolved, or a component of the trusted launcher, code or config path is writable by
  a slot UID, THEN THE SYSTEM SHALL refuse to start the slot.
- WHEN the launcher receives repo or config paths containing spaces or shell
  metacharacters THE SYSTEM SHALL pass them to the target process as single arguments,
  without splitting or evaluating them.
- WHEN a slot password is created or rotated THE SYSTEM SHALL deliver it to the slot UID
  over stdin into a file in the slot's home that the slot UID owns (0400). The slot
  password never stays in an operator-readable path that the peer can reach.

Valkey and bridge control plane

- WHILE slot users exist THE SYSTEM SHALL keep `bridge_slot_a` and `bridge_slot_b`
  limited to `+xadd +xread +xrevrange +ping` on their own `out`, `resp` and `inbox`
  keys, with no FCALL, scripting, admin or dangerous commands.
- IF a slot UID attempts a cross-slot read or write, FCALL, a privileged command or a
  spoofed slot identity THEN THE SYSTEM SHALL refuse it. Canonical state (registration,
  epoch, inflight, task, claim, reply, audit) is byte-identical before and after.
- IF a forged, stale or replayed request arrives THEN THE SYSTEM SHALL NOT change
  another slot's task, admission, epoch, reply or audit beyond a recorded rejection.

Supervision

- WHEN Valkey, the ingester or the waker is killed with SIGKILL THE SYSTEM SHALL bring
  it back without a manual `launchctl kickstart`. Either the chosen launchd domain
  respawns it, or `com.mctl.bridge-supervisor` detects the stopped job and kickstarts
  it within 60 seconds, and logs that it did.

Evidence

- WHEN the operator runs the isolation probe through `slot-run <slot> probe` THE SYSTEM
  SHALL attempt every scenario 8 bypass and every cross-slot file, socket and Valkey
  access from the real slot process context. It SHALL record the sanitized UID, the
  Valkey role, the operation, the target class, the outcome and the errno or Valkey
  error, and SHALL never print secret values.
- WHEN `ops/evidence.sh` completes THE SYSTEM SHALL write a bundle with the following.
  Sanitized user IDs. The ACL matrix. Every negative outcome. Before and after hashes of
  canonical Valkey state and of trusted files. A PASS, FAIL or UNOBSERVABLE result per
  check. The rollback procedure.
- IF any required control is missing, bypassed or could not be observed THEN THE SYSTEM
  SHALL report FAIL or UNOBSERVABLE for that check, never PASS, and the overall verdict
  SHALL NOT be PASS.

## Out of scope

- Running sudo, creating or changing host accounts, installing or restarting the
  bridge, enabling working slots, rebooting the Mac mini, or merging or deploying
  anything without the operator. This proposal ships code and runbooks only.
- The second owner gate that admits real working repositories.
- A full host reboot test. It is scheduled separately by the operator.
- Slice 5 (cluster Valkey ACLs in mctl-gitops) and the cluster `labs/claude-remote`
  service.
- Context isolation between slots (prompt content, shared orchestrator thread) and
  bidirectional context. These are follow-on issues.
- Git push credentials for slot worktrees.
- A default question TTL.

## Open questions

- Claude Code authentication per slot user: does an interactive `claude` login under
  `sudo -u <slot user> -H` work on this host? On macOS it stores the token in the login
  keychain, which may be unavailable for a user without a GUI session. If it does not
  work, is a per-user `claude setup-token` token stored 0400 in the slot's home (passed
  through a file, not env) acceptable? Preflight must confirm this before
  provisioning. The proposal assumes interactive login per user and no copying of the
  operator's session.
- Is a NOPASSWD sudoers rule, limited to `slot-run` as the two slot users,
  acceptable? The alternative is that the owner types a password on every
  start/stop/keys. The proposal assumes NOPASSWD scoped to the launcher only, installed
  by hand by the owner.
- The issue lists "trusted launcher/config" among things the peer must not read. The
  launcher script itself has to be readable and executable by every slot UID. The
  proposal reads the requirement as "not writable by any slot". Per-slot config is
  0640 with the owning slot's group, so the peer cannot read it.
- User names, UIDs and the trusted root (`/opt/mctl-bridge`) are placeholders until
  preflight confirms they are free on the host.
- PR #105 (shell-safe replies and launcher paths) is not in this clone (HEAD is the
  #104 merge). The launcher work assumes #105 lands first, or reimplements its quoting.
