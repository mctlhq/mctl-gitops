#!/usr/bin/env python3
"""Run delete-vault-policy's Vault program against a fake Vault.

delete-tenant-safe (and the removed legacy delete-tenant) used to probe each policy and ESO role
with `vault policy read ... >/dev/null 2>&1` / `vault read ...` and delete only
when the probe succeeded, so a denied or unreachable Vault printed "not
found (already deleted). Skipping." and the step went green with every
object still in place. The KV cleanup turned a failed LIST into `[]` and
ignored failed deletes with `|| true`, and it walked only two levels, so
teams/<t>/<s>/preview/database survived even a clean run.

This extracts the program from the template rather than restating it,
serves the three Vault path families from a local HTTP server and asserts on
what is left.

Run: python3 tests/test_wft_delete_tenant_vault.py
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
T = ROOT / "platform-gitops/argo-workflows/cluster-templates"
FILES = ("wft-delete-tenant-safe.yaml",)

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def program(fname):
    doc = yaml.safe_load((T / fname).read_text())
    src = [t for t in doc["spec"]["templates"]
           if t["name"] == "delete-vault-policy"][0]["script"]["source"]
    m = re.search(r"^python3 - <<'PY'\n(.*?)\n^PY$", src, re.S | re.M)
    if not m:
        sys.exit(f"FAIL  could not extract the python program from {fname}")
    return src, m.group(1)


SOURCES = {f: program(f) for f in FILES}
for f, (src, _) in SOURCES.items():
    # The old probes: a read whose failure is indistinguishable from absence.
    check(f"{f}: no `vault policy read`/`vault read` probe left",
          not re.search(r"vault (policy )?read\b", src), src)
    check(f"{f}: no failure swallowed into an empty listing",
          '|| echo "[]"' not in src and "|| true" not in src, src)


class Vault(http.server.BaseHTTPRequestHandler):
    objects = set()        # e.g. sys/policies/acl/tenant-acme, secret/metadata/teams/acme/svc
    read_status = {}       # path -> forced GET/LIST status
    delete_status = {}     # path -> forced DELETE status
    error_but_applied = {} # path -> DELETE status sent after really deleting
    appear_on_delete = set()  # written by someone else at the first KV DELETE
    malformed = set()
    ignore_deletes = False
    requests = []

    def log_message(self, *args):
        pass

    def _path(self):
        u = urllib.parse.urlparse(self.path)
        assert u.path.startswith("/v1/"), u.path
        return urllib.parse.unquote(u.path[len("/v1/"):]).rstrip("/"), u.query

    def _send(self, status, body=b""):
        self.send_response(status)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        cls = type(self)
        path, query = self._path()
        listing = "list=true" in query
        cls.requests.append(("LIST" if listing else "GET", path))
        if path in cls.read_status:
            return self._send(cls.read_status[path])
        if not listing:
            return self._send(200 if path in cls.objects else 404, b"{}")
        if path in cls.malformed:
            return self._send(200, b"<html>proxy error</html>")
        keys = set()
        for s in cls.objects:
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
        if cls.appear_on_delete and path.startswith("secret/"):
            cls.objects |= cls.appear_on_delete
            cls.appear_on_delete = set()
        if path in cls.delete_status:
            return self._send(cls.delete_status[path])
        if path in cls.error_but_applied:
            cls.objects.discard(path)
            return self._send(cls.error_but_applied[path])
        if not cls.ignore_deletes:
            cls.objects.discard(path)
        # Vault answers 204 whether or not the object existed.
        self._send(204)


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Vault)
threading.Thread(target=server.serve_forever, daemon=True).start()
ADDR = f"http://127.0.0.1:{server.server_address[1]}"

ACL = "sys/policies/acl/"
ROLE = "auth/kubernetes/role/"
KV = "secret/metadata/teams/"
TENANT_OBJECTS = {
    ROLE + "argo-workflow-tenant-acme", ROLE + "eso-tenant-acme", ROLE + "eso-tenant-acme-preview",
    ACL + "tenant-acme", ACL + "eso-tenant-acme", ACL + "eso-tenant-acme-preview",
    KV + "acme/svc", KV + "acme/svc/repo-pat", KV + "acme/svc/database",
    KV + "acme/svc/preview", KV + "acme/svc/preview/database", KV + "acme/a/b/c/deep",
}
# Name-prefix siblings and the platform objects must survive.
OTHERS = {
    ROLE + "argo-workflow", ROLE + "argo-workflow-tenant-acme2", ROLE + "eso-tenant-acmex",
    ACL + "tenant-acme2", ACL + "argo-workflow-provisioner", ACL + "eso-tenant-acme-previewx",
    KV + "acme2/svc", KV + "acme2/svc/database", KV + "labs/svc",
}


def mine(objs):
    return {o for o in objs if o in TENANT_OBJECTS or o.startswith(KV + "acme/")}


for fname, (_, prog) in SOURCES.items():
    short = fname.removeprefix("wft-").removesuffix(".yaml")

    def run(objects, tenant="acme", token="t", **knobs):
        Vault.objects = set(objects) | OTHERS
        Vault.read_status = knobs.get("read_status", {})
        Vault.delete_status = knobs.get("delete_status", {})
        Vault.error_but_applied = knobs.get("error_but_applied", {})
        Vault.appear_on_delete = set(knobs.get("appear_on_delete", ()))
        Vault.malformed = knobs.get("malformed", set())
        Vault.ignore_deletes = knobs.get("ignore_deletes", False)
        Vault.requests = []
        env = {"PATH": os.environ["PATH"], "VAULT_ADDR": ADDR, "VAULT_TOKEN": token,
               "PARAM_TENANT_NAME": tenant}
        return subprocess.run([sys.executable, "-I", "-c", prog], env=env,
                              capture_output=True, text=True, timeout=60)

    # 1. Everything of the tenant goes, nothing else does.
    r = run(TENANT_OBJECTS)
    check(f"{short}: full tenant: exit 0", r.returncode == 0, r.stdout + r.stderr)
    check(f"{short}: full tenant: nothing of acme left", not mine(Vault.objects),
          sorted(mine(Vault.objects)))
    check(f"{short}: full tenant: siblings and platform objects untouched",
          OTHERS <= Vault.objects, sorted(OTHERS - Vault.objects))
    deleted = [p for v, p in Vault.requests if v == "DELETE"]
    check(f"{short}: full tenant: every DELETE names an acme object",
          all(p in TENANT_OBJECTS or p == KV + "acme" or p.startswith(KV + "acme/")
              for p in deleted), deleted)

    # 2. Nothing there at all: documented absence (204/404 then 404) is clean.
    r = run(set())
    check(f"{short}: absent tenant: exit 0", r.returncode == 0, r.stdout + r.stderr)

    # 3. A read that is neither 200 nor 404 is not absence (the old probe bug).
    for path in (ACL + "tenant-acme", ROLE + "eso-tenant-acme"):
        for status in (403, 500):
            r = run(TENANT_OBJECTS, read_status={path: status})
            check(f"{short}: GET {status} on {path}: step fails",
                  r.returncode != 0 and path in r.stdout, r.stdout + r.stderr)

    # 4. A failed DELETE fails the step instead of skipping.
    for path in (ACL + "tenant-acme", ROLE + "argo-workflow-tenant-acme",
                 KV + "acme/svc/database"):
        r = run(TENANT_OBJECTS, delete_status={path: 403})
        check(f"{short}: DELETE 403 on {path}: step fails, path named",
              r.returncode != 0 and "were not deleted" in r.stderr and path in r.stderr,
              r.stdout + r.stderr)

    # 4b. An error answer is not trusted even when the object is gone.
    r = run(TENANT_OBJECTS, error_but_applied={ACL + "tenant-acme": 500})
    check(f"{short}: DELETE 500 that still deleted: step fails",
          r.returncode != 0 and "DELETE returned HTTP 500" in r.stdout, r.stdout + r.stderr)

    # 5. Vault said 204 but nothing went: not a clean delete.
    r = run(TENANT_OBJECTS, ignore_deletes=True)
    check(f"{short}: deletes not applied: step fails", r.returncode != 0, r.stdout)

    # 5b. A secret written under the tenant while the delete runs is caught
    # by the final LIST, not reported as a clean delete.
    r = run(TENANT_OBJECTS, appear_on_delete={KV + "acme/late/x"})
    check(f"{short}: secret written during the delete: step fails",
          r.returncode != 0 and "still lists" in r.stderr, r.stdout + r.stderr)

    # 6. A LIST that is not 200/404 is a failed read, not an empty tree.
    for status in (403, 503):
        r = run(TENANT_OBJECTS, read_status={KV + "acme": status})
        check(f"{short}: LIST {status} on teams/acme: step fails",
              r.returncode != 0 and not [p for v, p in Vault.requests
                                         if v == "DELETE" and p.startswith("secret/")],
              r.stdout + r.stderr)
    r = run(TENANT_OBJECTS, read_status={KV + "acme/svc/preview": 403})
    check(f"{short}: LIST 403 on a subtree: step fails", r.returncode != 0, r.stdout)
    r = run(TENANT_OBJECTS, malformed={KV + "acme"})
    check(f"{short}: malformed LIST body: step fails", r.returncode != 0, r.stdout)

    # 7. Names that would widen the walk are refused before any request.
    for tenant in ("", "a", "acme/svc", "..", "acme/", "Acme", "-acme", "acme\n"):
        r = run(TENANT_OBJECTS, tenant=tenant)
        check(f"{short}: tenant {tenant!r}: refused with no request",
              r.returncode != 0 and not Vault.requests and TENANT_OBJECTS <= Vault.objects,
              f"rc={r.returncode} requests={Vault.requests}")

    # 8. No token from the login: fail before touching Vault.
    r = run(TENANT_OBJECTS, token="")
    check(f"{short}: empty token: refused with no request",
          r.returncode != 0 and not Vault.requests, r.stdout)

server.shutdown()
if failures:
    print("\nFAILURES:\n" + "\n".join(failures), file=sys.stderr)
    sys.exit(1)
print("\nAll checks passed.")
