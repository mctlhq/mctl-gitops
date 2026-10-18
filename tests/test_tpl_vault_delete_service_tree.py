#!/usr/bin/env python3
"""Run delete-service-secrets' Vault program against a fake KV v2 tree.

retire-service used to DELETE secret/metadata/teams/<t>/<s> and .../repo-pat
only. KV v2 deletes metadata per path, so every secret below the service
(database, preview, preview/database) survived the retire: labs/psa-smoke
kept its DB credentials and preview secrets in Vault after a Succeeded
retire on 2026-10-18. A non-204 answer was also only a warning, so the step
reported a clean retire it had not observed.

This extracts the program from the template rather than restating it,
serves secret/metadata from a local HTTP server and asserts on what is left.
"""
import http.server
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import urllib.parse

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL = ROOT / "platform-gitops/argo-workflows/cluster-templates/tpl-vault-write.yaml"
doc = yaml.safe_load(TPL.read_text())
SOURCE = [t for t in doc["spec"]["templates"]
          if t["name"] == "delete-service-secrets"][0]["script"]["source"]
m = re.search(r"^python3 - <<'PY'\n(.*?)\n^PY$", SOURCE, re.S | re.M)
if not m:
    sys.exit("FAIL  could not extract the python program from delete-service-secrets")
PROGRAM = m.group(1)

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


class Vault(http.server.BaseHTTPRequestHandler):
    secrets = set()        # leaf paths under secret/metadata/, e.g. teams/labs/a/database
    list_status = {}       # path -> forced LIST status
    delete_status = {}     # path -> forced DELETE status
    malformed = set()      # paths whose LIST body is not JSON
    ignore_deletes = False
    requests = []

    def log_message(self, *args):
        pass

    def _path(self):
        u = urllib.parse.urlparse(self.path)
        prefix = "/v1/secret/metadata/"
        assert u.path.startswith(prefix), u.path
        return urllib.parse.unquote(u.path[len(prefix):]).rstrip("/"), u.query

    def _send(self, status, body=b""):
        self.send_response(status)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        cls = type(self)
        path, query = self._path()
        listing = "list=true" in query
        cls.requests.append(("LIST" if listing else "GET", path))
        if not listing:
            # A read of one path's own metadata, not of its children.
            return self._send(200 if path in cls.secrets else 404, b"{}")
        if path in cls.list_status:
            return self._send(cls.list_status[path])
        if path in cls.malformed:
            return self._send(200, b"<html>proxy error</html>")
        keys = set()
        for s in cls.secrets:
            if s.startswith(path + "/"):
                rest = s[len(path) + 1:]
                keys.add(rest.split("/", 1)[0] + ("/" if "/" in rest else ""))
        if not keys:
            return self._send(404, b'{"errors":[]}')
        self._send(200, json.dumps({"data": {"keys": sorted(keys)}}).encode())

    def do_DELETE(self):
        cls = type(self)
        path, _ = self._path()
        cls.requests.append(("DELETE", path))
        if path in cls.delete_status:
            return self._send(cls.delete_status[path])
        if not cls.ignore_deletes:
            cls.secrets.discard(path)
        self._send(204)


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Vault)
threading.Thread(target=server.serve_forever, daemon=True).start()
ADDR = f"http://127.0.0.1:{server.server_address[1]}"

OTHERS = {"teams/labs/other", "teams/labs/other/database",
          "teams/labs/svc-2", "teams/labs/svc-2/database",   # name-prefix sibling
          "teams/karabu/svc", "teams/karabu/svc/database"}   # same name, other team


def run(secrets, team="labs", service="svc", token="t", **knobs):
    Vault.secrets = set(secrets) | OTHERS
    Vault.list_status = knobs.get("list_status", {})
    Vault.delete_status = knobs.get("delete_status", {})
    Vault.malformed = knobs.get("malformed", set())
    Vault.ignore_deletes = knobs.get("ignore_deletes", False)
    Vault.requests = []
    env = {"PATH": os.environ["PATH"], "VAULT_ADDR": ADDR, "VAULT_TOKEN": token,
           "PARAM_TEAM_NAME": team, "PARAM_COMPONENT_NAME": service}
    return subprocess.run([sys.executable, "-c", PROGRAM], env=env,
                          capture_output=True, text=True, timeout=60)


FULL = {"teams/labs/svc", "teams/labs/svc/repo-pat", "teams/labs/svc/database",
        "teams/labs/svc/preview", "teams/labs/svc/preview/database",
        "teams/labs/svc/a/b/c/deep"}

# 1. The whole tree goes, nothing else does.
r = run(FULL)
check("full tree: exit 0", r.returncode == 0, r.stdout + r.stderr)
check("full tree: nothing left under teams/labs/svc",
      not {s for s in Vault.secrets if s == "teams/labs/svc" or s.startswith("teams/labs/svc/")},
      sorted(Vault.secrets))
check("full tree: siblings and other teams untouched", OTHERS <= Vault.secrets,
      sorted(OTHERS - Vault.secrets))
deleted = [p for v, p in Vault.requests if v == "DELETE"]
check("full tree: every DELETE stays inside the service",
      all(p == "teams/labs/svc" or p.startswith("teams/labs/svc/") for p in deleted), deleted)
check("full tree: the service path itself is deleted last",
      deleted and deleted[-1] == "teams/labs/svc", deleted)

# 2. A secret only below the service, no secret at the service path itself.
r = run({"teams/labs/svc/database"})
check("children only: exit 0 and removed",
      r.returncode == 0 and "teams/labs/svc/database" not in Vault.secrets, r.stderr)

# 3. Nothing stored: documented absence (404) is a clean retire.
r = run(set())
check("absent service: exit 0", r.returncode == 0, r.stderr)

# 4. A LIST that is not 200/404 is a failed read, not an empty tree.
for status in (403, 500, 503):
    r = run(FULL, list_status={"teams/labs/svc": status})
    check(f"LIST {status} on the service: step fails", r.returncode != 0, r.stdout)
    check(f"LIST {status} on the service: no DELETE issued",
          not [1 for v, _ in Vault.requests if v == "DELETE"], Vault.requests)
r = run(FULL, list_status={"teams/labs/svc/preview": 403})
check("LIST 403 on a subtree: step fails", r.returncode != 0, r.stdout)
r = run(FULL, malformed={"teams/labs/svc"})
check("malformed LIST body: step fails", r.returncode != 0, r.stdout)

# 5. A failed DELETE fails the step instead of warning.
r = run(FULL, delete_status={"teams/labs/svc/database": 403})
check("DELETE 403: step fails", r.returncode != 0, r.stdout)
# Asserted on the DELETE branch's own message: the final LIST would also
# fail the step here, and must not be what this case relies on.
check("DELETE 403: reported as a failed delete, path named",
      "were not deleted" in r.stderr and "teams/labs/svc/database" in r.stderr, r.stderr)

# 6. Vault answered 204 but the tree is still there: not a clean retire.
r = run(FULL, ignore_deletes=True)
check("deletes not applied: step fails", r.returncode != 0, r.stdout)

# 6b. Same for a service with no subtree: LIST is empty either way, so only
# a read of the service's own metadata can tell (claude P2 on #1974).
r = run({"teams/labs/svc"}, ignore_deletes=True)
check("root-only tree, deletes not applied: step fails",
      r.returncode != 0 and "want 404" in r.stderr, r.stdout + r.stderr)
r = run({"teams/labs/svc"})
check("root-only tree: exit 0 and removed",
      r.returncode == 0 and "teams/labs/svc" not in Vault.secrets, r.stderr)

# 6c. mctl-api allows a trailing hyphen in team and component names, so a
# retire of such a service must not be refused (agy P2 on #1974).
r = run({"teams/labs/svc-", "teams/labs/svc-/database"}, service="svc-")
check("name with a trailing hyphen: retired",
      r.returncode == 0 and not {s for s in Vault.secrets if s.startswith("teams/labs/svc-/")
                                 or s == "teams/labs/svc-"}, r.stdout + r.stderr)

# 7. Names that would widen the recursive walk are refused before any request.
for team, service in (("labs", ""), ("", "svc"), ("labs", "a/b"), ("labs", ".."),
                      ("labs", "svc/"), ("labs", "Svc"), ("labs", "-svc"), ("labs", "svc\n")):
    r = run(FULL, team=team, service=service)
    check(f"name {team!r}/{service!r}: refused with no request",
          r.returncode != 0 and not Vault.requests and FULL <= Vault.secrets,
          f"rc={r.returncode} requests={Vault.requests}")

# 8. No token from the login: fail before touching Vault.
r = run(FULL, token="")
check("empty token: refused with no request",
      r.returncode != 0 and not Vault.requests, r.stdout)

# 9. Same guard class in write-service-secrets-from-secret: `$` in a Python
# regex also matches before a trailing newline, so `re.match(r"^...$")`
# accepted "svc\n". Both name checks use fullmatch now.
WRITE_SRC = [t for t in doc["spec"]["templates"]
             if t["name"] == "write-service-secrets-from-secret"][0]["script"]["source"]
for team, service in (("labs", "svc\n"), ("labs\n", "svc"), ("labs", "")):
    Vault.requests = []
    r = subprocess.run([sys.executable, "-I", "-c", WRITE_SRC],
                       env={"PATH": os.environ["PATH"], "VAULT_ADDR": ADDR,
                            "PARAM_TEAM_NAME": team, "PARAM_COMPONENT_NAME": service},
                       capture_output=True, text=True, timeout=60)
    check(f"write-from-secret name {team!r}/{service!r}: refused with no request",
          r.returncode != 0 and "invalid team_name or component_name" in r.stderr
          and not Vault.requests, (r.returncode, r.stderr[-200:]))

server.shutdown()
if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
