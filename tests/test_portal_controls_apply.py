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
# Models the endpoint as measured, not as its verb suggests: the PUT is a
# merge -- a field the body leaves out keeps its stored value. Verified
# against the live portal for `description` and for `servers` before this
# stub was written to behave that way.
#
# It also records the curl config and argv. Resolving -K is the point: the
# script's header claims the token reaches curl through a config on a file
# descriptor and never through the command line, and only a stub that opens
# that config can hold it to that.
[ -f "$STATE_FILE" ] || printf '%s' "$LIVE_JSON" > "$STATE_FILE"
printf '%s' "$*" > "$ARGV_FILE"
for a in "$@"; do
  if [ "${next:-}" = cfg ]; then cat "$a" > "$AUTH_FILE" 2>/dev/null; next=; continue; fi
  case "$a" in -K) next=cfg; continue ;; esac
done
is_put=no; next=
for a in "$@"; do
  if [ "${next:-}" = data ]; then printf '%s' "$a" > "$PUT_BODY_FILE"; next=; continue; fi
  case "$a" in
    PUT) is_put=yes ;;
    --data) next=data ;;
  esac
done
if [ "$is_put" = yes ]; then
  jq -c --slurpfile patch "$PUT_BODY_FILE" '. * $patch[0]' "$STATE_FILE" > "$STATE_FILE.new"
  mv "$STATE_FILE.new" "$STATE_FILE"
fi
printf '{"success":true,"result":%s}' "$(cat "$STATE_FILE")"
"""


def fixture(tmp, controls=None):
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


def run(root, *args, live=None, keep_state=False):
    put_body = root / "put-body.json"
    # Cleared per run: otherwise a later invocation that exits before the PUT
    # returns the previous body, and `sent is not None` stops meaning "a PUT
    # happened" -- which would let a refusal case pass without asserting one.
    put_body.unlink(missing_ok=True)
    if not keep_state:
        (root / "portal-state.json").unlink(missing_ok=True)
    auth = root / "curl-auth.txt"
    argv = root / "curl-argv.txt"
    auth.unlink(missing_ok=True)
    argv.unlink(missing_ok=True)
    env = dict(
        os.environ,
        PATH=f"{root / 'stub'}{os.pathsep}{os.environ['PATH']}",
        CLOUDFLARE_API_TOKEN="stub-token",
        CLOUDFLARE_ACCOUNT_ID="stub-account",
        LIVE_JSON=json.dumps(live if live is not None else LIVE),
        PUT_BODY_FILE=str(put_body),
        AUTH_FILE=str(auth),
        ARGV_FILE=str(argv),
        STATE_FILE=str(root / "portal-state.json"),
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
        # Committed state matches live: an apply is a no-op that still proves
        # the round trip, and the allowlists must come back untouched.
        p, sent = run(root)
        check("a matching file applies", p.returncode == 0, p.stderr)
        # The write carries only the fields this file owns. `servers` holds
        # the tool allowlists of three other repositories; a body that sent
        # them back would be a read-modify-write over somebody else's state.
        check("the write carries only the fields the file owns",
              sent is not None and set(sent) == {"secure_web_gateway", "code_mode",
                                                 "allow_code_mode"},
              json.dumps(sent)[:200])
        # The quiet direction of a two-valued signal. It is missing from a
        # suite that only ever asserts refusals, and its absence is what let
        # the drift expression report the baseline as drifted against itself.
        q, _ = run(root, "--check")
        check("--check is quiet when live matches the committed file",
              q.returncode == 0 and "in sync" in q.stdout,
              f"rc={q.returncode} {(q.stdout + q.stderr)[:200]}")
        d, _ = run(root, "--dry-run")
        check("--dry-run says so when there is nothing to change",
              d.returncode == 0 and "no change" in d.stdout,
              f"rc={d.returncode} {(d.stdout + d.stderr)[:200]}")
        # The header claims the token reaches curl through a config on a file
        # descriptor and never through the command line. Asserted both ways.
        a, _ = run(root)
        check("the token reaches curl through the config",
              "Authorization: Bearer stub-token" in a.curl_config,
              repr(a.curl_config)[:200])
        check("the token is nowhere in curl's arguments",
              a.curl_argv != "" and "stub-token" not in a.curl_argv,
              repr(a.curl_argv)[:200])

        # The same statement from the other side: not sending the field and
        # the field still being there are different claims, and the second
        # one is what the upstream repositories actually need.
        state = json.loads((root / "portal-state.json").read_text())
        check("the mappings are untouched by the write",
              state.get("servers") == LIVE["servers"],
              json.dumps(state.get("servers"))[:200])

    with tempfile.TemporaryDirectory() as tmp:
        # An allowlist apply in mctl-telegram, mctl-api or seerrsense can land
        # between this script's read and its write. A body that carried the
        # mappings back would revert it and be answered 200. Here the stub
        # rewrites tg's allowlist after the read, and the write must leave
        # that new value standing.
        root = fixture(tmp)
        stub = root / "stub" / "curl"
        concurrent = json.dumps([{"name": "get_my_send_status", "enabled": True},
                                 {"name": "send_message", "enabled": False},
                                 {"name": "list_dialogs", "enabled": True}])
        # Injected only on the PUT invocation: the GET has already answered
        # with the old state by then, which is exactly the window.
        stub.write_text(stub.read_text().replace(
            'if [ "$is_put" = yes ]; then\n  jq -c',
            'if [ "$is_put" = yes ]; then\n'
            "  jq -c --argjson t '" + concurrent + "' "
            "'(.servers[] | select(.server_id==\"tg\") | .updated_tools) |= $t' "
            '"$STATE_FILE" > "$STATE_FILE.c" && mv "$STATE_FILE.c" "$STATE_FILE"\n'
            '  jq -c', 1))
        stub.chmod(0o755)
        p, _ = run(root)
        state = json.loads((root / "portal-state.json").read_text())
        tg = [x for x in state["servers"] if x["server_id"] == "tg"][0]
        check("an allowlist applied during the write is not reverted",
              p.returncode == 0 and len(tg["updated_tools"]) == 3,
              f"rc={p.returncode} {json.dumps(tg)[:200]} {p.stderr[:150]}")

    with tempfile.TemporaryDirectory() as tmp:
        # Someone turned Code Mode on in the dashboard. The apply has to
        # bring both fields back, and then agree that it did: a write naming
        # only code_mode would leave the stored allow_code_mode true under
        # this endpoint's merge semantics, the response check would reject
        # its own successful write, and --check would stay red forever.
        root = fixture(tmp)
        drifted = dict(LIVE, code_mode="opt_in", allow_code_mode=True)
        p, sent = run(root, live=drifted)
        state = json.loads((root / "portal-state.json").read_text())
        check("an apply converges on a portal left at opt_in",
              p.returncode == 0 and state["code_mode"] == "off"
              and state["allow_code_mode"] is False,
              f"rc={p.returncode} {json.dumps({k: state.get(k) for k in ('code_mode', 'allow_code_mode')})} {p.stderr[:150]}")
        q, _ = run(root, "--check", live=drifted, keep_state=True)
        check("--check is quiet once the apply has converged",
              q.returncode == 0 and "in sync" in q.stdout,
              f"rc={q.returncode} {(q.stdout + q.stderr)[:200]}")

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
        # The apply must not be able to print success over a portal that came
        # back missing a mapping. Nothing observed does this -- it is the
        # failure the response check exists for, so it is given a portal that
        # does it.
        root = fixture(tmp)
        stub = root / "stub" / "curl"
        stub.write_text(stub.read_text().replace(
            'if [ "$is_put" = yes ]; then\n  jq -c',
            'if [ "$is_put" = yes ]; then\n'
            '  jq -c \'.servers |= map(select(.server_id != "seerrsense"))\' '
            '"$STATE_FILE" > "$STATE_FILE.d" && mv "$STATE_FILE.d" "$STATE_FILE"\n'
            '  jq -c', 1))
        stub.chmod(0o755)
        p, _ = run(root)
        check("a portal that came back missing a mapping is not reported as applied",
              p.returncode != 0 and "mapping was lost" in p.stderr, p.stderr[:200])

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
        # `type == "string"` does not constrain this field the way
        # `type == "boolean"` constrains a flag. A typo would be PUT to the
        # portal and then reported as drift forever, noise shaped exactly
        # like the signal this file exists to carry.
        (root / FILE_REL).write_text(json.dumps(
            {"portal": "mcp", "hostname": "mcp.mctl.ai", "secure_web_gateway": False,
             "code_mode": "of", "allow_code_mode": False}, indent=2) + "\n")
        git(root, "commit", "-qam", "typo in code_mode")
        p, _ = run(root)
        check("a code_mode outside the documented set is refused",
              p.returncode != 0 and "expected shape" in p.stderr, p.stderr[:200])

    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        # The API answers 400 when code_mode and allow_code_mode disagree, so
        # the file is refused here rather than sent to be rejected there.
        (root / FILE_REL).write_text(json.dumps(
            {"portal": "mcp", "hostname": "mcp.mctl.ai", "secure_web_gateway": False,
             "code_mode": "off", "allow_code_mode": True}, indent=2) + "\n")
        git(root, "commit", "-qam", "inconsistent code mode fields")
        p, _ = run(root)
        check("code_mode and allow_code_mode must agree",
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
