"""Drive scripts/portal-controls-apply.sh against a stub Cloudflare API.

The script writes to the MCP portal that fronts all three upstreams, and the
body it PUTs is the portal's own body with three switches replaced. Two
things can go wrong there and neither is visible in review:

  * it applies something other than the committed file -- an edit on disk, a
    file that is not tracked at all, or a file naming a different portal;
  * it carries back less than it read. The `servers` array in that body holds
    the tool allowlists owned by mctl-telegram, mctl-api and seerrsense. A
    projection that dropped or flattened it would silently re-expose or hide
    tools across three services, and the API would answer 200.

Both are asserted here against the real script. The Cloudflare API is a stub
`curl` on PATH, so nothing reaches the network and the assertions are about
the request the script would actually send.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_REL = "scripts/portal-controls-apply.sh"
FILE_REL = "infrastructure/cloudflare/portal/mcp-portal-controls.json"

# The live portal as the API returns it: read-only timestamps the script must
# drop, and a servers array with allowlists it must carry back untouched.
LIVE = {
    "id": "mcp",
    "name": "mcp",
    "hostname": "mcp.mctl.ai",
    "secure_web_gateway": False,
    "code_mode": "off",
    "allow_code_mode": False,
    "created_at": "2026-09-10T00:00:00Z",
    "created_by": "someone",
    "modified_at": "2026-09-10T00:00:00Z",
    "modified_by": "someone",
    "servers": [
        {"server_id": "tg", "default_disabled": True,
         "updated_tools": [{"name": "get_my_send_status", "enabled": True},
                           {"name": "send_message", "enabled": False}]},
        {"server_id": "api", "default_disabled": True, "updated_tools": []},
        {"server_id": "seerrsense", "default_disabled": True, "updated_tools": []},
    ],
}

STUB_CURL = r"""#!/bin/sh
# Records the PUT body, answers both calls from LIVE_JSON.
for a in "$@"; do
  if [ "$a" = "-X" ]; then is_put=maybe; continue; fi
  if [ "${is_put:-}" = maybe ] && [ "$a" = "PUT" ]; then is_put=yes; continue; fi
  case "$a" in --data) next=data; continue ;; esac
  if [ "${next:-}" = data ]; then printf '%s' "$a" > "$PUT_BODY_FILE"; next=; fi
done
if [ "${is_put:-}" = yes ]; then
  printf '{"success":true,"result":%s}' "$(cat "$PUT_BODY_FILE")"
else
  printf '{"success":true,"result":%s}' "$LIVE_JSON"
fi
"""


def fixture(tmp, controls=None, live=None):
    """A throwaway checkout holding the real script and a committed file."""
    controls = controls if controls is not None else {
        "portal": "mcp", "hostname": "mcp.mctl.ai",
        "secure_web_gateway": False, "code_mode": "off", "allow_code_mode": False,
    }
    root = pathlib.Path(tmp)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / pathlib.Path(FILE_REL).parent).mkdir(parents=True, exist_ok=True)
    (root / "stub").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / SCRIPT_REL, root / SCRIPT_REL)
    (root / FILE_REL).write_text(json.dumps(controls, indent=2) + "\n")
    stub = root / "stub" / "curl"
    stub.write_text(STUB_CURL)
    stub.chmod(0o755)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "fixture@example.test")
    git(root, "config", "user.name", "fixture")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")
    return root


def git(root, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env,
                   capture_output=True)


def run(root, *args, live=None):
    put_body = root / "put-body.json"
    env = dict(
        os.environ,
        PATH=f"{root / 'stub'}{os.pathsep}{os.environ['PATH']}",
        CLOUDFLARE_API_TOKEN="stub-token",
        CLOUDFLARE_ACCOUNT_ID="stub-account",
        LIVE_JSON=json.dumps(live if live is not None else LIVE),
        PUT_BODY_FILE=str(put_body),
    )
    p = subprocess.run(["bash", str(root / SCRIPT_REL), *args],
                       capture_output=True, text=True, env=env)
    sent = json.loads(put_body.read_text()) if put_body.exists() else None
    return p, sent


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name} {detail}")
        FAILURES.append(name)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        # Committed state matches live: an apply is a no-op that still proves
        # the round trip, and the allowlists must come back untouched.
        p, sent = run(root)
        check("a matching file applies", p.returncode == 0, p.stderr)
        check("the servers array is carried back verbatim",
              sent is not None and sent.get("servers") == LIVE["servers"],
              json.dumps(sent.get("servers") if sent else None)[:200])
        check("read-only timestamps are dropped",
              sent is not None and not ({"created_at", "created_by", "modified_at",
                                         "modified_by"} & set(sent)),
              str(sorted(sent)) if sent else "")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        # The switch the whole of Phase 2 turns.
        (root / FILE_REL).write_text(json.dumps(
            {"portal": "mcp", "hostname": "mcp.mctl.ai", "secure_web_gateway": True,
             "code_mode": "off", "allow_code_mode": False}, indent=2) + "\n")
        git(root, "commit", "-qam", "gateway on")
        p, sent = run(root)
        check("turning the gateway on sends it",
              p.returncode == 0 and sent and sent["secure_web_gateway"] is True, p.stderr)
        p, _ = run(root, "--check")
        check("--check reports drift against live", p.returncode != 0
              and "secure_web_gateway" in p.stderr, p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        (root / FILE_REL).write_text('{"portal":"mcp","hostname":"mcp.mctl.ai",'
                                     '"secure_web_gateway":false,"code_mode":"off",'
                                     '"allow_code_mode":false,"gateway":true}\n')
        git(root, "commit", "-qam", "unknown key")
        p, _ = run(root)
        # A key this script does not implement is a decision nobody applied.
        check("an unknown key is refused",
              p.returncode != 0 and "expected shape" in p.stderr, p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        (root / FILE_REL).write_text(json.dumps(
            {"portal": "other", "hostname": "mcp.mctl.ai", "secure_web_gateway": False,
             "code_mode": "off", "allow_code_mode": False}, indent=2) + "\n")
        git(root, "commit", "-qam", "retarget")
        p, _ = run(root)
        check("a file naming another portal is refused",
              p.returncode != 0 and "expected mcp/mcp.mctl.ai" in p.stderr, p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        # The id is what the API routes on; a portal moved to another
        # hostname is not the portal this file was written for.
        moved = dict(LIVE, hostname="something-else.mctl.ai")
        p, _ = run(root, live=moved)
        check("a portal serving another hostname is refused",
              p.returncode != 0 and "refusing" in p.stderr, p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        (root / FILE_REL).write_text('{"portal":"mcp","hostname":"mcp.mctl.ai",'
                                     '"secure_web_gateway":true,"code_mode":"off",'
                                     '"allow_code_mode":false}\n')
        p, _ = run(root)
        check("an uncommitted edit is refused",
              p.returncode != 0 and "differs from HEAD" in p.stderr, p.stderr[:200])
        git(root, "add", FILE_REL)
        p, _ = run(root)
        # Index-relative `git diff` passes this one; HEAD-relative does not.
        check("a staged but uncommitted edit is refused",
              p.returncode != 0 and "differs from HEAD" in p.stderr, p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        git(root, "rm", "--cached", "-q", "--", FILE_REL)
        git(root, "commit", "-qm", "untrack")
        (root / FILE_REL).write_text('{"portal":"mcp","hostname":"mcp.mctl.ai",'
                                     '"secure_web_gateway":true,"code_mode":"off",'
                                     '"allow_code_mode":false}\n')
        p, _ = run(root)
        # `git diff HEAD -- <path>` exits 0 for a path HEAD does not have,
        # whatever is on disk, so tracking is checked before content.
        check("a file left on disk but removed from the repository is refused",
              p.returncode != 0 and "is not tracked" in p.stderr, p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        shutil.rmtree(root / ".git")
        p, _ = run(root)
        check("a copy outside a checkout is refused",
              p.returncode != 0 and "not a git checkout" in p.stderr, p.stderr[:200])

    if FAILURES:
        print(f"\n{len(FAILURES)} case(s) failed: {', '.join(FAILURES)}")
        return 1
    print("\nall cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
