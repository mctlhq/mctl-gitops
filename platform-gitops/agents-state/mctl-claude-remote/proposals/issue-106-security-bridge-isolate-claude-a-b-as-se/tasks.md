# Tasks: issue-106-security-bridge-isolate-claude-a-b-as-se

Code and CI only. No task runs sudo, changes host accounts, installs or restarts the
bridge, enables working slots, or merges or deploys. Host steps are operator runbook
entries.

- [ ] 1. Add `plugin/mctl-bridge/ops/preflight.sh`. It is read-only, needs no sudo, and
  covers the following:
  - UIDs and groups, and free-UID and name checks through `dscl`.
  - The bridge, Codex and Claude process tree, and the `launchctl print` state of
    `com.mctl.bridge-*` in `gui/` and `user/`.
  - `stat` of `$HOME`, `~/.codex`, the socket, `$H/etc` and `$H/slots`.
  - CPU, memory and swap.
  - A respawn probe on a scratch `sleep` label only.
  - The no-change plan, the blast radius, the rollback and the exact owner sudo
    commands.
  - Output to `$H/evidence/preflight-<ts>.txt`, with no secret values.
  - DoD: shellcheck clean. A CI test runs it with `dscl`, `launchctl`, `sysctl` and
    `vm_stat` stubbed on PATH and asserts two things: no command outside a read-only
    allowlist is invoked, and the output contains every section.
- [ ] 2. Add `ops/provision-slot-users.sh` (depends on 1). It is dry-run by default.
  `--apply` requires `EUID==0` and a TTY. `--remove` is the rollback.
  - Creates two hidden non-admin users with distinct UIDs and primary groups, and home
    mode 0700.
  - Creates `/opt/mctl-bridge/{code,bin,etc,slots/<s>}` with the owners and modes from
    the design.
  - Installs `/etc/sudoers.d/mctl-bridge` (0440, `visudo -cf` checked) that limits the
    operator to `/opt/mctl-bridge/bin/slot-run` as each slot user.
  - Prints the per-user Claude login step.
  - DoD: a dry-run snapshot test asserts the exact command list. It asserts that no
    command adds a slot user to `admin`. It asserts that the sudoers line targets only
    the slot users and only `slot-run`. It asserts that `--apply` refuses when not root
    or not on a TTY.
- [ ] 3. Add `ops/slot-run`, the trusted launcher (depends on 2 and on PR #105's
  argument quoting).
  - Verbs: `install-cred`, `start`, `stop`, `show`, `keys`, `probe`, `check`.
  - Every invocation validates the slot map and UID (refusing 0, the operator UID,
    `admin` members and duplicate mappings). It checks that no trusted path ancestor is
    writable by a slot or is an escaping symlink, and that the repo `realpath` is under
    `$HOME/work/`.
  - It rebuilds the environment with `env -i` (PATH without the operator's
    `~/.local/bin`), closes descriptors above 2, and refuses bypass modes in user
    Claude settings.
  - It builds the `claude` argv as an array with `--permission-mode default`.
  - `install-cred` reads stdin and writes `~/.mctl-bridge/slot.pw` (0400).
  - DoD: unit tests cover each refusal. A test asserts that the launcher text never
    contains `--dangerously-skip-permissions`.
- [ ] 4. Rework `ops/slot.sh` to delegate to `slot-run` through `sudo -u <slot user>`
  (depends on 3).
  - Keeps `ACL SETUSER` on the operator side and pipes the password into
    `install-cred`.
  - Removes `$H/etc/slot-<s>.pw` after a successful install.
  - Renders `mcp.json` and `settings.json` into `/opt/mctl-bridge/slots/<s>/` (0640,
    slot group).
  - Keeps `MCTL_BRIDGE_ISOLATION=trusted-experiment` as an explicit legacy mode,
    refused when `slots.conf` has `working=1`.
  - DoD: the ACL rule string is unchanged (`isolation.test.ts` still passes), and the
    legacy mode prints a warning.
- [ ] 5. Update `ops/install.sh` (depends on 3).
  - Copies the code to `/opt/mctl-bridge/code/<version>` and switches `current`.
  - Installs `slot-run` and `slots.conf` only when `/opt/mctl-bridge` exists and is
    operator-owned. It never calls sudo.
  - Asserts that `$H`, `$H/etc` and `~/.codex/app-server-control` are 0700.
  - Selects the launchd domain recorded by preflight.
  - DoD: a test asserts `install.sh` contains no `sudo` and that the mode assertions are
    present.
- [ ] 6. Add supervision (depends on 1): `ops/com.mctl.bridge-supervisor.plist`
  (`StartInterval` 30) and `ops/supervise.sh`, which kickstarts any stopped bridge
  label and logs it. The supervisor is installed only if the preflight respawn probe
  shows KeepAlive does not respawn.
  - DoD: a stubbed `launchctl` test shows that a stopped label gets exactly one
    kickstart and a running label gets none.
- [ ] 7. Add `src/probe-isolation.ts`, run through `slot-run probe` (depends on 3). It
  runs the cross-slot file, socket and Valkey matrix from the design and one permitted
  `status` round trip. It writes sanitized JSONL.
  - DoD: unit tests assert that no output line contains a value read from a
    password-file fixture. They also assert that a successful forbidden operation
    yields `FAIL` and a missing check yields `UNOBSERVABLE`.
- [ ] 8. Add `ops/evidence.sh` (depends on 7).
  - Takes before and after sha256 of canonical Valkey state and of trusted files.
  - Runs both probes.
  - Runs a live replay of forged, stale and duplicate events and of a spoofed identity
    through the ingester.
  - Writes the bundle (summary, ACL matrix, probes, hashes, rollback). The verdict is
    PASS only if every check is PASS.
  - DoD: a CI run against a real Valkey with two Linux test users (`useradd` on the
    ubuntu runner) produces a bundle with verdict PASS, and with one ACL deliberately
    widened, verdict FAIL.
- [ ] 9. Update docs (depends on 1–8).
  - `docs/chatgpt-orchestrator-bridge.md`: two per-slot users instead of one
    `mctl-slot` user, an empty "Slice 4b host results" table, and the supervision
    decision.
  - `plugin/mctl-bridge/README.md`: the operator runbook (preflight, review, owner
    sudo, per-user login, install, probe, evidence, rollback). It states that working
    slots need a separate owner gate.
  - DoD: the runbook commands match the scripts' dry-run output.
- [ ] 10. Operator-only runbook steps, listed and not executed by the implementer.
  - Run preflight and review it.
  - Run `sudo provision-slot-users.sh --apply`.
  - Log in to Claude under each user.
  - Run `install.sh`.
  - Run `evidence.sh` and the following scenarios:
    - Scenarios 2 and 7, including waker and Valkey SIGKILL recovery and launcher paths
      with metacharacters.
    - Scenario 8 from each slot.
  - Attach the bundle to #106.
  - DoD: a bundle with verdict PASS is posted. Any FAIL or UNOBSERVABLE keeps working
    slots blocked.

## Tests

- [ ] T1. Preflight stub test: only read-only commands run, and every section is
  printed.
- [ ] T2. Provisioning dry-run snapshot: the exact commands, no `admin` membership, the
  sudoers line scope, and `--apply` refused unless root on a TTY.
- [ ] T3. Launcher refusals: an unknown slot, UID 0, the operator UID, an admin-member
  UID, a duplicate mapping, a slot-writable ancestor, a repo symlink escaping to the
  peer home, a repo outside `work/`, and a bypass mode in user settings.
- [ ] T4. Launcher argv and environment: a repo path with spaces, `'`, `$(touch
  marker)`, `;` and a newline arrives as one argument. The marker file is never
  created. The environment has no `MCTL_BRIDGE_VALKEY_PASSWORD` and no operator PATH.
  Only fds 0–2 are open in the child (checked through `/dev/fd` or `lsof -p`).
- [ ] T5. Credential delivery: `install-cred` reads stdin. The password never appears
  in `ps` argv or in the environment. The file is 0400 and owned by the slot UID.
- [ ] T6. Multi-user isolation on the CI runner, with two Linux users and real Valkey.
  From A's process: reading B's `slot.pw`, B's home, `orch.pw` and `admin.pw` fails
  with `EACCES`. Writes to the trusted code fail. A Unix socket owned by the operator
  in a 0700 dir refuses `connect`. The same holds for B against A.
- [ ] T7. Valkey from the real slot process: cross-slot `XADD`/`XREAD`, `HSET`/`DEL`
  on any key, `FCALL`, `EVAL`, `CONFIG SET`, `ACL LIST`, `FUNCTION LOAD` and a spoofed
  `slot` field are all refused or rejected. Canonical state hashes are equal before and
  after. The permitted `status` call succeeds.
- [ ] T8. Forged, stale and replayed events: the existing `isolation.test.ts` scenarios
  plus an evidence-mode run. No change to the other slot's task, admission, epoch,
  reply or audit beyond one recorded rejection.
- [ ] T9. Supervisor: a stopped label gets one kickstart, a running label gets none.
- [ ] T10. Evidence verdict: all PASS gives PASS. One forbidden success gives FAIL. A
  missing probe line gives UNOBSERVABLE, and the overall verdict is not PASS.
- [ ] T11. Regression: no file under `ops/` contains `--dangerously-skip-permissions`,
  and `install.sh` and `slot.sh` contain no bare `sudo` other than
  `sudo -u <slot user> /opt/mctl-bridge/bin/slot-run`.
- [ ] T12. Host (operator, manual): scenarios 2, 7 and 8 re-run on the Mac mini.
  SIGKILL of Valkey, ingester and waker recovers without a manual kickstart. The
  results are recorded in the bundle.

## Rollback

- Code: revert the PR. `MCTL_BRIDGE_ISOLATION=trusted-experiment` restores the previous
  same-UID `slot.sh` behaviour for test slots only. Working slots stay blocked.
- Host (operator, with sudo, by hand):
  1. `slot.sh stop a` and `slot.sh stop b`.
  2. `sudo provision-slot-users.sh --remove`. This deletes `/etc/sudoers.d/mctl-bridge`
     (re-checked with `visudo -c`) and removes the users with `sysadminctl -deleteUser`,
     after archiving their homes if the owner wants to keep transcripts. It also removes
     `/opt/mctl-bridge`.
  3. Re-run the previous `install.sh` from the old checkout. That restores
     `$H/plugin`, and the operator-side `slot-<s>.pw` is regenerated by `slot.sh`.
  4. Run `ACL DELUSER bridge_slot_<s>` if the slot users should go too.
- Unaffected by rollback: Valkey data, the ingester, the waker, the Codex daemon and
  unrelated launchd jobs are never restarted by these scripts. The supervisor plist,
  if installed, is removed with `launchctl bootout` of its own label only.
