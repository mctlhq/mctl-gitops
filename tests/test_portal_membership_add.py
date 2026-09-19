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
         "updated_tools": [{"name": "send_message", "enabled": True},
                           {"name": "get_my_send_status", "enabled": False}],
         "updated_prompts": [], "tools": [{"name": "send_message"}, {"name": "get_my_send_status"}],
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
    "prompts": [{"name": "projects_prompt_a"}],
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
    # Models an existing member's on_behalf being flipped by hand right
    # after this script's FIRST portal read (the early already-member check)
    # -- everything the donor and the write are derived from must come from
    # a LATER read, or it would copy the value from before the flip.
    if [ "$is_put" = no ] && [ -n "${MUTATE_AFTER_FIRST_GET:-}" ] && [ ! -f "$MUTATED_MARKER" ]; then
      touch "$MUTATED_MARKER"
    elif [ "$is_put" = no ] && [ -n "${MUTATE_AFTER_FIRST_GET:-}" ] && [ -f "$MUTATED_MARKER" ]; then
      # Every existing member together, so they still agree with each other
      # -- isolating "which read was this value taken from" from the
      # separate disagreement/type checks tested elsewhere.
      jq -c '.servers |= map(.on_behalf = false)' "$STATE_FILE" > "$STATE_FILE.m"
      mv "$STATE_FILE.m" "$STATE_FILE"
    fi
    # Counts non-PUT portal reads (early=1, fresh=2, just_before=3) and
    # mutates only once the count reaches $MUTATE_ON_GET_N -- isolating "the
    # write reflects the LAST read (just_before)" from "the write reflects
    # SOME read taken after the first" (already covered above).
    if [ "$is_put" = no ] && [ -n "${MUTATE_ON_GET_N:-}" ]; then
      n=$(( $(cat "$GET_COUNTER" 2>/dev/null || echo 0) + 1 ))
      printf '%s' "$n" > "$GET_COUNTER"
      if [ "$n" -ge "$MUTATE_ON_GET_N" ]; then
        jq -c '.servers |= map(.on_behalf = false)' "$STATE_FILE" > "$STATE_FILE.m"
        mv "$STATE_FILE.m" "$STATE_FILE"
      fi
    fi
    if [ "$is_put" = yes ]; then
      cp "$PUT_BODY_FILE" "$STATE_FILE"
      # Wrap what was sent back in the shape a real GET-after-PUT would have:
      # {"servers": [...]} becomes the new .result, id/hostname preserved.
      jq -c '. + {id:"mcp", hostname:"mcp.mctl.ai"}' "$STATE_FILE" > "$STATE_FILE.w"
      mv "$STATE_FILE.w" "$STATE_FILE"
      # Models the measured API bug the README's re-snapshot recipe diffs
      # against: "this API is on record answering 200 while keeping a field
      # it was told to change." Only active when SPOIL_TG_ENABLED is set, so
      # every other case still gets a faithful store.
      if [ -n "${SPOIL_TG_ENABLED:-}" ]; then
        jq -c '(.servers[] | select(.server_id=="tg") | .updated_tools[0].enabled) |= not' \
          "$STATE_FILE" > "$STATE_FILE.s"
        mv "$STATE_FILE.s" "$STATE_FILE"
      fi
      # Same measured behaviour, but on the just-inserted entry itself: the
      # API accepts the PUT (200) but stores the new member with a tool
      # already enabled that was sent disabled.
      if [ -n "${SPOIL_NEW_ENABLED:-}" ]; then
        jq -c '(.servers[] | select(.server_id=="projects") | .updated_tools[0].enabled) |= true' \
          "$STATE_FILE" > "$STATE_FILE.n"
        mv "$STATE_FILE.n" "$STATE_FILE"
      fi
      # A harmless reordering, content unchanged: the API is free to return
      # array elements in whatever order it stores them internally, and that
      # must not read as a dropped or altered mapping.
      if [ -n "${SHUFFLE_ORDER:-}" ]; then
        jq -c '.servers |= map(.updated_tools |= reverse)' "$STATE_FILE" > "$STATE_FILE.o"
        mv "$STATE_FILE.o" "$STATE_FILE"
      fi
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


def run(root, *args, portal=None, server=None, keep_state=False, spoil_tg=False, spoil_new=False,
        mutate_after_first_get=False, mutate_on_get_n=None, shuffle_order=False):
    put_body = root / "put-body.json"
    put_body.unlink(missing_ok=True)
    if not keep_state:
        (root / "portal-state.json").unlink(missing_ok=True)
    (root / "mutated-marker").unlink(missing_ok=True)
    (root / "get-counter").unlink(missing_ok=True)
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
        SPOIL_TG_ENABLED="1" if spoil_tg else "",
        SPOIL_NEW_ENABLED="1" if spoil_new else "",
        SHUFFLE_ORDER="1" if shuffle_order else "",
        MUTATE_AFTER_FIRST_GET="1" if mutate_after_first_get else "",
        MUTATED_MARKER=str(root / "mutated-marker"),
        MUTATE_ON_GET_N=str(mutate_on_get_n) if mutate_on_get_n is not None else "",
        GET_COUNTER=str(root / "get-counter"),
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
        check("the new entry carries every prompt disabled",
              sent is not None
              and {t["name"]: t["enabled"] for t in
                   [s for s in sent["servers"] if s["server_id"] == "projects"][0]["updated_prompts"]}
              == {"projects_prompt_a": False},
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
        # seerrsense is a live portal member (PORTAL_LIVE) with no Terraform
        # resource at all, by design -- a DCR server registered out-of-band.
        # The Terraform gate must not run for --check, only for a write.
        root = fixture(tmp)
        p, sent = run(root, "seerrsense", "--check")
        check("--check on a live, non-Terraform-declared member succeeds",
              p.returncode == 0 and sent is None and "already a member" in p.stdout,
              f"rc={p.returncode} {(p.stdout + p.stderr)[:200]}")

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
        # Existing members "agree" only because both are missing the keys
        # entirely (the API having stopped projecting them) -- {} projects to
        # {on_behalf: null, default_disabled: null}, which `unique` collapses
        # to a single element, so the agreement check alone would pass this.
        # The type check below it must catch it.
        null_donors = json.loads(json.dumps(PORTAL_LIVE))
        for s in null_donors["servers"]:
            del s["on_behalf"]
            del s["default_disabled"]
        root = fixture(tmp)
        p, sent = run(root, "projects", portal=null_donors)
        check("agreeing but non-boolean (null) donors refuse rather than copy null",
              p.returncode != 0 and sent is None and "not on a boolean value" in p.stderr,
              p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        # The API answers 200 while keeping a field it was told to change --
        # measured behaviour per README.md's re-snapshot section. Here it
        # silently flips tg's first tool back after the write, so what comes
        # back does not match what was sent for a server this script never
        # touched. The id-only check alone would call this a clean apply.
        root = fixture(tmp)
        p, sent = run(root, "projects", spoil_tg=True)
        check("a write that returns something other than what was sent for an untouched member is refused",
              p.returncode != 0 and "does not match what was sent" in p.stderr,
              f"rc={p.returncode} {p.stderr[:300]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "--check")
        check("an omitted server_id (flag lands in $1) is a usage error, not a bogus add",
              p.returncode == 2 and sent is None and "usage:" in p.stderr,
              f"rc={p.returncode} {p.stderr[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "--help")
        check("any leading-dash first argument, not just the two known flags, is a usage error",
              p.returncode == 2 and sent is None and "usage:" in p.stderr,
              f"rc={p.returncode} {p.stderr[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "projects", server={"id": "projects", "tools": [{"name": "projects_list"}, {"name": None}]})
        check("a tool catalogue entry with no name is refused rather than written as {\"name\": null}",
              p.returncode != 0 and sent is None and "a tool with no name" in p.stderr,
              p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        # The API accepts the insert (200) but stores the new member with a
        # tool already enabled that this script asked to be disabled. Id
        # presence alone would call this a clean add.
        root = fixture(tmp)
        p, sent = run(root, "projects", spoil_new=True)
        check("the new entry is verified against what was sent, not just its id's presence",
              p.returncode != 0 and "was not written as sent" in p.stderr,
              f"rc={p.returncode} {p.stderr[:300]}")

    with tempfile.TemporaryDirectory() as tmp:
        # An existing member's on_behalf is flipped (by hand, say) right
        # after this script's first ("early", already-member) read. The
        # donor value used for the new entry must come from a read taken
        # AFTER that flip, not the stale one the early check happened to see.
        root = fixture(tmp)
        p, sent = run(root, "projects", mutate_after_first_get=True)
        check("the donor is derived from a read taken at write-time, not an earlier stale one",
              p.returncode == 0 and sent is not None
              and [s for s in sent["servers"] if s["server_id"] == "projects"][0]["on_behalf"] is False,
              f"rc={p.returncode} {json.dumps(sent)[:300] if sent else p.stderr[:300]}")

    with tempfile.TemporaryDirectory() as tmp:
        # Isolates "the body is built from `just_before`" from "built from
        # SOME read after the first": mutates only on the THIRD portal read
        # (just_before), which the previous case's mutate-after-first-get
        # cannot distinguish from a body still built from the second (fresh).
        root = fixture(tmp)
        p, sent = run(root, "projects", mutate_on_get_n=3)
        check("the write body is built from the just-before-write read, not an earlier fresh one",
              p.returncode == 0 and sent is not None
              and [s for s in sent["servers"] if s["server_id"] == "tg"][0]["on_behalf"] is False,
              f"rc={p.returncode} {json.dumps(sent)[:300] if sent else p.stderr[:300]}")
        check("the NEW entry's own donor value also comes from the just-before-write read",
              p.returncode == 0 and sent is not None
              and [s for s in sent["servers"] if s["server_id"] == "projects"][0]["on_behalf"] is False,
              f"rc={p.returncode} {json.dumps(sent)[:300] if sent else p.stderr[:300]}")

    with tempfile.TemporaryDirectory() as tmp:
        # The API is free to return array elements in a different order than
        # they were sent -- content unchanged. Comparing raw (unsorted)
        # arrays would flag this as a lost or altered mapping; it must not.
        root = fixture(tmp)
        p, sent = run(root, "projects", shuffle_order=True)
        check("a harmless reordering of updated_tools by the API is not mistaken for a lost mapping",
              p.returncode == 0 and "added:" in p.stdout,
              f"rc={p.returncode} {(p.stdout + p.stderr)[:300]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p, sent = run(root, "projects", server={"id": "projects", "tools": [{"name": "projects_list"}, {"name": ""}]})
        check("a tool catalogue entry with an empty-string name is refused, not just a null one",
              p.returncode != 0 and sent is None and "a tool with no name" in p.stderr,
              p.stderr[:200])

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
