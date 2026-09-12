"""Drive scripts/portal-server-auth-apply.sh against a stub Cloudflare API.

The script rewrites the OAuth registration of a live portal upstream. What it
writes is `auth_credentials`, a write-only blob echoed back only as the
read-only `auth_config_summary` projection, and the shape of that blob is
mirrored from the projection rather than published in a schema. Three things
can go wrong there and none is visible in review:

  * it applies something other than the committed file -- an edit on disk, a
    file that is not tracked, or one naming a different portal or upstream;
  * it writes a field it does not own. The endpoint accepts `updated_tools`
    and `updated_prompts` -- the capability overrides owned by mctl-telegram,
    mctl-api and seerrsense -- and a separate write-only `client_secret`.
    Naming any of them would make every apply a read-modify-write over
    somebody else's state. The script sends only the blob, which is safe
    because the endpoint merges rather than replaces -- measured against the
    live `tg` server before the script relied on it, so the stub below merges
    too;
  * the write is accepted and stores something else. Because the field is
    write-only, the only way to know is to read the projection back, and a
    stub that lets a write land differently is what holds the script to
    doing that.

The Cloudflare API is a stub `curl` on PATH, so nothing reaches the network
and the assertions are about the request the script would actually send.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_REL = "scripts/portal-server-auth-apply.sh"
FILE_REL = "infrastructure/cloudflare/portal/mcp-portal-server-auth.json"

WIDE = ("telegram:dialogs:read telegram:messages:read telegram:messages:send "
        "telegram:messages:pin account:manage")
NARROW = "telegram:dialogs:read telegram:messages:read"

CONFIG = {
    "issuer": "https://tg.mctl.ai",
    "authorization_endpoint": "https://tg.mctl.ai/oauth/authorize",
    "token_endpoint": "https://tg.mctl.ai/oauth/token",
    "revocation_endpoint": "https://tg.mctl.ai/oauth/revoke",
}

COMMITTED = {
    "portal": "mcp",
    "servers": [{
        "server_id": "tg",
        "hostname": "https://tg.mctl.ai/mcp",
        "auth_mode": "manual",
        "config": dict(CONFIG),
        "registration_info": {
            "client_id": "cloudflare-portal-mcp",
            "redirect_uris": ["https://mcp.mctl.ai/servers-callback"],
            "token_endpoint_auth_method": "none",
            "scope": WIDE,
        },
    }],
}


def live(scope=WIDE, **over):
    """The server object as the API returns it, narrow or wide."""
    s = {
        "id": "tg",
        "name": "mctl Telegram (tg.mctl.ai)",
        "hostname": "https://tg.mctl.ai/mcp",
        "auth_type": "oauth",
        "status": "ready",
        "tools": [{"name": f"tool{i}", "enabled": True} for i in range(30)],
        "auth_config_summary": {
            "auth_mode": "manual",
            "has_client_secret": True,
            "client_secret_version": 1,
            "config": dict(CONFIG),
            "registration_info": {
                "client_id": "cloudflare-portal-mcp",
                "redirect_uris": ["https://mcp.mctl.ai/servers-callback"],
                "token_endpoint_auth_method": "none",
                "scope": scope,
            },
        },
        # Measured on the live server: a real write does NOT move this. It is
        # here so a test that started trusting it would have something to
        # trust, and the script never reads it.
        "modified_at": "2026-09-10 07:21:28",
    }
    s.update(over)
    return s


# Models the endpoint as measured, not as its verb suggests: the PUT merges,
# so a field the body leaves out keeps its stored value. Writing
# `auth_credentials` replaces the projection's auth_mode/config/
# registration_info and leaves has_client_secret and the tool list alone --
# which is the behaviour the script's post-write checks are written against.
#
# $MUTATE is a jq filter applied to the state after a write, so a case can
# model a server that accepted the call and stored something else.
STUB_CURL = r"""#!/bin/sh
[ -f "$STATE_FILE" ] || printf '%s' "$LIVE_JSON" > "$STATE_FILE"
printf '%s' "$*" > "$ARGV_FILE"
next=
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
  jq -c --slurpfile patch "$PUT_BODY_FILE" '
    . as $cur
    | ($patch[0] | del(.auth_credentials)) as $plain
    | ($cur * $plain)
    | if ($patch[0].auth_credentials // null) != null
      then ($patch[0].auth_credentials | fromjson) as $c
        | .auth_config_summary = (.auth_config_summary * {
            auth_mode: $c.auth_mode, config: $c.config,
            registration_info: $c.registration_info })
      else . end
  ' "$STATE_FILE" > "$STATE_FILE.new"
  mv "$STATE_FILE.new" "$STATE_FILE"
  if [ -n "${MUTATE:-}" ]; then
    jq -c "$MUTATE" "$STATE_FILE" > "$STATE_FILE.m" && mv "$STATE_FILE.m" "$STATE_FILE"
  fi
fi
printf '{"success":true,"result":%s}' "$(cat "$STATE_FILE")"
"""


def git(root, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env,
                   capture_output=True)


def fixture(tmp, committed=None):
    """A throwaway checkout holding the real script and a committed file."""
    committed = COMMITTED if committed is None else committed
    root = pathlib.Path(tmp)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / pathlib.Path(FILE_REL).parent).mkdir(parents=True, exist_ok=True)
    (root / "stub").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / SCRIPT_REL, root / SCRIPT_REL)
    (root / FILE_REL).write_text(json.dumps(committed, indent=2) + "\n")
    stub = root / "stub" / "curl"
    stub.write_text(STUB_CURL)
    stub.chmod(0o755)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "fixture@example.test")
    git(root, "config", "user.name", "fixture")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")
    return root


def run(root, *args, state=None, mutate=""):
    put_body = root / "put-body.json"
    # Cleared per run: otherwise a later invocation that exits before the PUT
    # returns the previous body, and `sent is not None` stops meaning "a PUT
    # happened" -- which would let a refusal case pass without asserting one.
    put_body.unlink(missing_ok=True)
    state_file = root / "server-state.json"
    state_file.unlink(missing_ok=True)
    auth = root / "curl-auth.txt"
    argv = root / "curl-argv.txt"
    auth.unlink(missing_ok=True)
    argv.unlink(missing_ok=True)
    env = dict(
        os.environ,
        PATH=f"{root / 'stub'}{os.pathsep}{os.environ['PATH']}",
        CLOUDFLARE_API_TOKEN="stub-token",
        CLOUDFLARE_ACCOUNT_ID="stub-account",
        LIVE_JSON=json.dumps(state if state is not None else live()),
        PUT_BODY_FILE=str(put_body),
        AUTH_FILE=str(auth),
        ARGV_FILE=str(argv),
        STATE_FILE=str(state_file),
        MUTATE=mutate,
    )
    p = subprocess.run(["bash", str(root / SCRIPT_REL), *args],
                       capture_output=True, text=True, env=env)
    p.sent = json.loads(put_body.read_text()) if put_body.exists() else None
    p.curl_config = auth.read_text() if auth.exists() else ""
    p.curl_argv = argv.read_text() if argv.exists() else ""
    p.state = json.loads(state_file.read_text()) if state_file.exists() else None
    return p


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

        # The narrow-to-wide apply: the case the file was written for.
        p = run(root, state=live(scope=NARROW))
        check("a narrow upstream is widened", p.returncode == 0, p.stderr[:300])
        check("the write carries only the blob",
              p.sent is not None and set(p.sent) == {"auth_credentials"},
              json.dumps(p.sent)[:200])
        blob = json.loads(p.sent["auth_credentials"]) if p.sent else {}
        check("the blob is exactly the three owned fields",
              set(blob) == {"auth_mode", "config", "registration_info"},
              json.dumps(blob)[:200])
        check("the scope sent is the committed one",
              blob.get("registration_info", {}).get("scope") == WIDE,
              json.dumps(blob.get("registration_info"))[:200])
        check("the stored scope is the committed one after the write",
              p.state["auth_config_summary"]["registration_info"]["scope"] == WIDE,
              json.dumps(p.state["auth_config_summary"])[:200])
        # Not sending a field and the field surviving are different claims,
        # and the second is the one the upstream repositories need.
        check("the capability catalogue survives the write",
              len(p.state.get("tools", [])) == 30,
              json.dumps(p.state.get("tools"))[:120])
        check("the client_secret survives the write",
              p.state["auth_config_summary"]["has_client_secret"] is True
              and p.state["auth_config_summary"]["client_secret_version"] == 1,
              json.dumps(p.state["auth_config_summary"])[:200])
        check("the apply says the upstream must be re-authorised",
              "sign the upstream out" in p.stdout, p.stdout[-200:])

        # The quiet direction of a two-valued signal, missing from a suite
        # that only ever asserts refusals.
        q = run(root, "--check")
        check("--check is quiet when live matches the committed file",
              q.returncode == 0 and "in sync" in q.stdout and q.sent is None,
              f"rc={q.returncode} {(q.stdout + q.stderr)[:200]}")
        d = run(root, "--dry-run")
        check("--dry-run says so when there is nothing to change",
              d.returncode == 0 and "no change" in d.stdout and d.sent is None,
              f"rc={d.returncode} {(d.stdout + d.stderr)[:200]}")

        # The loud direction, naming the field. A detector that cannot say
        # what drifted sends the operator back to the dashboard.
        c = run(root, "--check", state=live(scope=NARROW))
        check("--check is red on a narrowed scope, and names it",
              c.returncode != 0 and "registration_info.scope" in c.stderr
              and c.sent is None,
              f"rc={c.returncode} {(c.stdout + c.stderr)[:300]}")

        # Scope is compared as a set: the API stores it space-separated and
        # the order it comes back in is not something anyone measured.
        shuffled = " ".join(reversed(WIDE.split()))
        r = run(root, "--check", state=live(scope=shuffled))
        check("scope order is not drift",
              r.returncode == 0 and "in sync" in r.stdout,
              f"rc={r.returncode} {(r.stdout + r.stderr)[:200]}")

        # The header claims the token reaches curl through a config on a file
        # descriptor and never the command line. Asserted both ways.
        a = run(root)
        check("the token reaches curl through the config",
              "Authorization: Bearer stub-token" in a.curl_config,
              repr(a.curl_config)[:200])
        check("the token is nowhere in curl's arguments",
              a.curl_argv != "" and "stub-token" not in a.curl_argv,
              repr(a.curl_argv)[:200])

        # `updated_tools` and `updated_prompts` are writable inputs on this
        # endpoint even though the read does not echo them back. Naming
        # either would make the apply a read-modify-write over the allowlists
        # owned by mctl-telegram, mctl-api and seerrsense.
        check("the write names no capability override",
              p.sent is not None
              and "updated_tools" not in p.sent and "updated_prompts" not in p.sent,
              json.dumps(p.sent)[:200])

        # The tool guard is one-sided. Server-level `tools` is the synced
        # capability catalogue -- measured: name/description/schemas, no
        # enabled flag, and no `updated_tools` key in the response at all, so
        # the allowlist that does carry those flags lives on the portal
        # object and is out of this script's reach. A sync landing in the
        # same window can legitimately add a capability, and that must not
        # read as a failed apply.
        m = run(root, state=live(scope=NARROW),
                mutate='.tools += [{"name":"freshly_synced"}]')
        check("a capability gained across the write is not a failure",
              m.returncode == 0 and len(m.state["tools"]) == 31,
              f"rc={m.returncode} {(m.stdout + m.stderr)[:200]}")

        # The write is to a write-only field whose shape is mirrored, not
        # published. A server that stores something else must fail loudly.
        w = run(root, state=live(scope=NARROW),
                mutate='.auth_config_summary.registration_info.scope = "telegram:dialogs:read"')
        check("a write stored differently is a failure, not a clean apply",
              w.returncode != 0 and "does not match what was sent" in w.stderr,
              f"rc={w.returncode} {(w.stdout + w.stderr)[:300]}")
        check("the failure prints the restore point",
              "restore point" in w.stdout or "restore" in w.stderr,
              (w.stdout + w.stderr)[:300])

        # The blob is not supposed to carry the secret. If a write drops it
        # anyway, that is the write doing more than it was asked to.
        s = run(root, state=live(scope=NARROW),
                mutate='.auth_config_summary.has_client_secret = false')
        check("a dropped client_secret is a failure",
              s.returncode != 0 and "client_secret" in s.stderr,
              f"rc={s.returncode} {(s.stdout + s.stderr)[:300]}")

        # Losing tools across the write is one-sided: gaining is legitimate.
        t = run(root, state=live(scope=NARROW), mutate='.tools = []')
        check("losing tools across the write is a failure",
              t.returncode != 0 and "lost tools" in t.stderr,
              f"rc={t.returncode} {(t.stdout + t.stderr)[:300]}")

        # The id is what the API routes on. An id pointed at another upstream
        # is a server this record was not written for.
        h = run(root, state=live(hostname="https://elsewhere.example.test/mcp"))
        check("a retargeted upstream is refused",
              h.returncode != 0 and "refusing" in h.stderr and h.sent is None,
              f"rc={h.returncode} {h.stderr[:200]}")
        # Writing a manual blob over a DCR upstream would convert it.
        dcr = live()
        dcr["auth_config_summary"]["auth_mode"] = "dcr"
        g = run(root, state=dcr)
        check("a DCR upstream is not converted implicitly",
              g.returncode != 0 and "dcr" in g.stderr and g.sent is None,
              f"rc={g.returncode} {g.stderr[:200]}")
        b = run(root, state=live(auth_type="bearer"))
        check("a non-oauth upstream is refused",
              b.returncode != 0 and "auth_type" in b.stderr and b.sent is None,
              f"rc={b.returncode} {b.stderr[:200]}")

        # What is applied is the committed blob, never the copy on disk.
        (root / FILE_REL).write_text(json.dumps(
            {**COMMITTED, "servers": [{**COMMITTED["servers"][0],
                                       "registration_info": {
                                           **COMMITTED["servers"][0]["registration_info"],
                                           "scope": "telegram:messages:send"}}]},
            indent=2) + "\n")
        e = run(root)
        check("an uncommitted edit is refused",
              e.returncode != 0 and "differs from HEAD" in e.stderr and e.sent is None,
              f"rc={e.returncode} {e.stderr[:200]}")
        git(root, "checkout", "--", FILE_REL)

    with tempfile.TemporaryDirectory() as tmp:
        # A file removed from the index and left on disk: `git diff HEAD` says
        # nothing about a path HEAD does not have, so tracking is checked
        # first and separately.
        root = fixture(tmp)
        git(root, "rm", "-q", "--cached", FILE_REL)
        git(root, "commit", "-qm", "untrack")
        u = run(root)
        check("an untracked file is refused",
              u.returncode != 0 and "not tracked" in u.stderr and u.sent is None,
              f"rc={u.returncode} {u.stderr[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        # This script writes to a shared surface. A file naming another
        # portal would rewrite upstreams this repository does not own.
        root = fixture(tmp, committed={**COMMITTED, "portal": "someone-else"})
        o = run(root)
        check("a file naming another portal is refused",
              o.returncode != 0 and "expected mcp" in o.stderr and o.sent is None,
              f"rc={o.returncode} {o.stderr[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        # An unknown key is a decision nobody reviewed under a name the
        # script does not implement.
        bad = json.loads(json.dumps(COMMITTED))
        bad["servers"][0]["client_secret"] = "hunter2"
        root = fixture(tmp, committed=bad)
        k = run(root)
        check("an unknown key in the file is refused",
              k.returncode != 0 and "expected shape" in k.stderr and k.sent is None,
              f"rc={k.returncode} {k.stderr[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        # An empty scope would be applied as "ask for nothing", which reads
        # at every other layer exactly like the bug this file fixes.
        bad = json.loads(json.dumps(COMMITTED))
        bad["servers"][0]["registration_info"]["scope"] = "   "
        root = fixture(tmp, committed=bad)
        z = run(root)
        check("an empty scope is refused",
              z.returncode != 0 and "expected shape" in z.stderr and z.sent is None,
              f"rc={z.returncode} {z.stderr[:200]}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing: {', '.join(FAILURES)}")
        sys.exit(1)
    print("all ok")


if __name__ == "__main__":
    main()
