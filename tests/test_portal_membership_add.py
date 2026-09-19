"""Drive scripts/portal-membership-add.sh against a stub Cloudflare API.

The script inserts a new server_id into the same shared `servers[]` array
that scripts/portal-controls-apply.sh's stub (see test_portal_controls_apply.py)
already models -- but unlike that script, this one's whole job is to touch
that array, so the risk shape is different: an existing member's mapping must
never be lost or overwritten by the insert, the new entry's shape must come
from a server_id the committed Terraform actually declares, and a donor
mismatch across existing members must refuse rather than guess.

The Cloudflare API is two stub `curl`s composed on PATH (servers/<id> and
portals/<id>), so nothing reaches the network and the assertions are about
the requests the script would actually send.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_REL = "scripts/portal-membership-add.sh"
TF_REL = "infrastructure/cloudflare/portal/mcp-servers.tf"

TF_FIXTURE = '''resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "tg" {
  account_id = var.account_id
  id         = "tg"
}

resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "projects" {
  account_id = var.account_id
  id         = "projects"
}
'''

# The live portal as the API returns it before the add.
PORTAL_LIVE = {
    "id": "mcp",
    "name": "mcp",
    "hostname": "mcp.mctl.ai",
    "servers": [
        {"server_id": "tg", "on_behalf": True, "default_disabled": False,
         "updated_tools": [{"name": "send_message", "enabled": True}],
         "updated_prompts": [], "tools": [{"name": "send_message"}],
         "authentication_status": "connected", "created_at": "2026-09-10T00:00:00Z"},
        {"server_id": "seerrsense", "on_behalf": True, "default_disabled": False,
         "updated_tools": [{"name": "search_media", "enabled": True}],
         "updated_prompts": [], "tools": [{"name": "search_media"}],
         "authentication_status": "connected", "created_at": "2026-09-10T00:00:00Z"},
    ],
}

# The new server's own resource, independent of any portal membership.
SERVER_LIVE = {
    "id": "projects",
    "tools": [{"name": "projects_list"}, {"name": "projects_status"}],
}

STUB_CURL = r"""#!/bin/sh
# Two GET endpoints (servers/<id> and portals/<id>) and one PUT
# (portals/<id>), told apart by the trailing URL segment. State persists in
# $STATE_FILE across calls within one script run, seeded from $LIVE_JSON.
[ -f "$STATE_FILE" ] || printf '%s' "$LIVE_JSON" > "$STATE_FILE"
url=""
for a in "$@"; do case "$a" in https://*) url="$a" ;; esac; done
is_put=no; next=
for a in "$@"; do
  if [ "${next:-}" = data ]; then printf '%s' "$a" > "$PUT_BODY_FILE"; next=; continue; fi
  case "$a" in
    -X) : ;;
    PUT) is_put=yes ;;
    --data) next=data ;;
  esac
done
next=
for a in "$@"; do
  if [ "${next:-}" = cfg ]; then cat "$a" > "$AUTH_FILE" 2>/dev/null; next=; continue; fi
  case "$a" in -K) next=cfg; continue ;; esac
done
printf '%s' "$*" >> "$ARGV_FILE"
printf '\n' >> "$ARGV_FILE"

case "$url" in
  *"/servers/"*)
    printf '{"success":true,"result":%s}' "$(cat "$SERVER_STATE_FILE")"
    ;;
  *"/portals/"*)
    if [ "$is_put" = yes ]; then
      cp "$PUT_BODY_FILE" "$STATE_FILE"
      # Wrap what was sent back in the shape a real GET-after-PUT would have:
      # {"servers": [...]} becomes the new .result, id/hostname preserved.
      jq -c '. + {id:"mcp", hostname:"mcp.mctl.ai"}' "$STATE_FILE" > "$STATE_FILE.w"
      mv "$STATE_FILE.w" "$STATE_FILE"
    fi
    printf '{"success":true,"result":%s}' "$(cat "$STATE_FILE")"
    ;;
esac
"""


def fixture(tmp, tf=TF_FIXTURE):
    root = pathlib.Path(tmp)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / pathlib.Path(TF_REL).parent).mkdir(parents=True, exist_ok=True)
    (root / "stub").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / SCRIPT_REL, root / SCRIPT_REL)
    (root / TF_REL).write_text(tf)
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


def run(root, *args, portal=None, server=None, keep_state=False):
    put_body = root / "put-body.json"
    put_body.unlink(missing_ok=True)
    if not keep_state:
        (root / "portal-state.json").unlink(missing_ok=True)
    server_state = root / "server-state.json"
    server_state.write_text(json.dumps(server if server is not None else SERVER_LIVE))
    auth = root / "curl-auth.txt"
    argv = root / "curl-argv.txt"
    auth.unlink(missing_ok=True)
    argv.unlink(missing_ok=True)
    env = dict(
        os.environ,
        PATH=f"{root / 'stub'}{os.pathsep}{os.environ['PATH']}",
        CLOUDFLARE_API_TOKEN="stub-token",
        CLOUDFLARE_ACCOUNT_ID="stub-account",
        LIVE_JSON=json.dumps(portal if portal is not None else PORTAL_LIVE),
        PUT_BODY_FILE=str(put_body),
        AUTH_FILE=str(auth),
        ARGV_FILE=str(argv),
        STATE_FILE=str(root / "portal-state.json"),
        SERVER_STATE_FILE=str(server_state),
    )
    p = subprocess.run(["bash", str(root / SCRIPT_REL), *args],
                       capture_output=True, text=True, env=env)
    sent = json.loads(put_body.read_text()) if put_body.exists() else None
    p.curl_config = auth.read_text() if auth.exists() else ""
    p.curl_argv = argv.read_text() if argv.exists() else ""
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
        p, sent = run(root, "projects")
        check("adding a new, Terraform-declared server succeeds",
              p.returncode == 0, p.stdout + p.stderr)
        check("the new entry carries every tool disabled",
              sent is not None
              and {t["name"]: t["enabled"] for t in
                   [s for s in sent["servers"] if s["server_id"] == "projects"][0]["updated_tools"]}
              == {"projects_list": False, "projects_status": False},
              json.dumps(sent)[:300])
        check("the new entry copies on_behalf/default_disabled from the agreeing existing members",
              sent is not None
              and [s for s in sent["servers"] if s["server_id"] == "projects"][0]["on_behalf"] is True
              and [s for s in sent["servers"] if s["server_id"] == "projects"][0]["default_disabled"] is False,
              json.dumps(sent)[:300])
        # The existing members' mappings must survive verbatim -- this is the
        # read-modify-write this script cannot avoid, unlike its sibling.
        state = json.loads((root / "portal-state.json").read_text())
        after_ids = {s["server_id"] for s in state["servers"]}
        check("no existing mapping is lost", after_ids == {"tg", "seerrsense", "projects"},
              json.dumps(sorted(after_ids)))
        tg = [s for s in state["servers"] if s["server_id"] == "tg"][0]
        check("an existing member's allowlist is untouched",
              tg["updated_tools"] == PORTAL_LIVE["servers"][0]["updated_tools"],
              json.dumps(tg))
        check("the token reaches curl through the config, never the argv",
              "Authorization: Bearer stub-token" in p.curl_config
              and "stub-token" not in p.curl_argv,
              repr(p.curl_config)[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "projects", "--check")
        check("--check reports a non-member as absent and does not write",
              p.returncode != 0 and sent is None and "NOT a member" in p.stderr,
              f"rc={p.returncode} {p.stderr[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        # Add it once for real, then ask again.
        run(root, "projects")
        p, sent = run(root, "projects", "--check", keep_state=True)
        check("--check is quiet once the server is already a member",
              p.returncode == 0 and sent is None and "already a member" in p.stdout,
              f"rc={p.returncode} {p.stdout[:200]}")
        p2, sent2 = run(root, "projects", keep_state=True)
        check("re-running apply on an existing member is a no-op, not an error",
              p2.returncode == 0 and sent2 is None and "already a member" in p2.stdout,
              f"rc={p2.returncode} {p2.stdout[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "projects", "--dry-run")
        check("--dry-run shows the body and does not write",
              p.returncode == 0 and sent is None and "would add" in p.stdout,
              f"rc={p.returncode} {p.stdout[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "not-a-declared-server")
        check("a server_id absent from Terraform is refused",
              p.returncode != 0 and sent is None
              and "no cloudflare_zero_trust_access_ai_controls_mcp_server resource" in p.stderr,
              p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        # A server_id containing ERE metacharacters must not match loosely
        # against an unrelated resource name.
        root = fixture(tmp, tf=TF_FIXTURE + '\nresource "cloudflare_zero_trust_access_ai_controls_mcp_server" "fooXbar" {\n}\n')
        p, sent = run(root, "foo.bar")
        check("a server_id with regex metacharacters does not loosely match a sibling resource",
              p.returncode != 0 and sent is None, p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "projects", server={"id": "projects", "tools": []})
        check("a server with an empty tool catalogue is refused rather than added blank",
              p.returncode != 0 and sent is None and "no tools in its catalogue" in p.stderr,
              p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        # Existing members disagree on on_behalf -- there is no single
        # representative donor, so the script must refuse rather than guess.
        mixed = json.loads(json.dumps(PORTAL_LIVE))
        mixed["servers"][1]["on_behalf"] = False
        root = fixture(tmp)
        p, sent = run(root, "projects", portal=mixed)
        check("disagreeing existing donors refuse rather than guess",
              p.returncode != 0 and sent is None and "do not agree" in p.stderr,
              p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "--check")
        check("an omitted server_id (flag lands in $1) is a usage error, not a bogus add",
              p.returncode == 2 and sent is None and "usage:" in p.stderr,
              f"rc={p.returncode} {p.stderr[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "projects", portal={"id": "mcp", "hostname": "mcp.mctl.ai", "servers": []})
        check("a portal with no existing members refuses rather than invent a shape",
              p.returncode != 0 and sent is None and "no existing members" in p.stderr,
              p.stderr[:200])

    if FAILURES:
        print(f"\n{len(FAILURES)} case(s) failed: {', '.join(FAILURES)}")
        return 1
    print("\nall cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
