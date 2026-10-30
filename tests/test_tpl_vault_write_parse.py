#!/usr/bin/env python3
"""Run write-service-secrets' parse/merge/write program against a fake Vault.

The step used to be shell: values went through `echo | xargs` (an unbalanced
quote failed the step, inner quotes and backslashes were silently dropped) and
the merge pasted both JSON documents into a `python3 -c '...'` string, so a
value containing a single quote broke the program and the `|| echo` fallback
wrote only the new keys, deleting every secret already stored at the path.

This extracts the program from the template rather than restating it, serves
the KV v2 endpoint from a local HTTP server, and asserts on what was POSTed.
"""
import http.server
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL = ROOT / "platform-gitops/argo-workflows/cluster-templates/tpl-vault-write.yaml"
doc = yaml.safe_load(TPL.read_text())
SOURCE = [t for t in doc["spec"]["templates"]
          if t["name"] == "write-service-secrets"][0]["script"]["source"]
m = re.search(r"^python3 - <<'PY'\n(.*?)\n^PY$", SOURCE, re.S | re.M)
assert m, "could not extract the python program from write-service-secrets"
PROGRAM = m.group(1)

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


class Vault(http.server.BaseHTTPRequestHandler):
    get_status = 200
    existing = {}
    post_status = 200
    posts = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        cls = type(self)
        body = json.dumps({"data": {"data": cls.existing}}).encode() if cls.get_status == 200 else b""
        self.send_response(cls.get_status)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        cls = type(self)
        n = int(self.headers.get("Content-Length", 0))
        cls.posts.append((self.path, self.headers.get("X-Vault-Token"),
                          json.loads(self.rfile.read(n))))
        self.send_response(cls.post_status)
        self.end_headers()


server = http.server.HTTPServer(("127.0.0.1", 0), Vault)
threading.Thread(target=server.serve_forever, daemon=True).start()
ADDR = f"http://127.0.0.1:{server.server_port}"
PATH = "secret/data/teams/t/s"


def run(text, get_status=200, existing=None, post_status=200, cwd=None):
    Vault.get_status, Vault.existing, Vault.post_status = get_status, existing or {}, post_status
    Vault.posts = []
    proc = subprocess.run(
        [sys.executable, "-I", "-"], input=PROGRAM, capture_output=True, text=True, cwd=cwd,
        env={"PATH": os.environ["PATH"], "VAULT_ADDR": ADDR, "VAULT_PATH": PATH,
             "VAULT_TOKEN": "tok", "PARAM_SECRET_ENV_VARS": text})
    return proc, list(Vault.posts)


with tempfile.TemporaryDirectory() as d:
    canary = pathlib.Path(d) / "canary"
    hostile = f"'); __import__('os').system('touch {canary}'); ('"
    FIDELITY = [
        ("Q1", "a\"b'c", "a\"b'c"),
        ("BS", r"C:\path\n", r"C:\path\n"),
        ("SP", "two  spaces", "two  spaces"),
        ("PAD", "  padded\t", "padded"),
        ("DQ", '"quoted"', "quoted"),
        ("SQ", "'single'", "single"),
        ("B64", "YWJj==", "YWJj=="),
        ("HOSTILE", hostile, hostile[1:-1]),
    ]
    text = "\n".join(f"{k}={raw}" for k, raw, _ in FIDELITY) + "\n# c\n\n  K2 = v \n"
    proc, posts = run(text, existing={"OLD": "keep", "Q1": "old"}, cwd=d)
    check("a payload with quotes, backslashes and code is accepted",
          proc.returncode == 0, proc.stderr)
    check("exactly one write", len(posts) == 1, posts)
    data = posts[0][2].get("data", {}) if posts else {}
    check("the write goes to the service path with the token",
          bool(posts) and posts[0][0] == f"/v1/{PATH}" and posts[0][1] == "tok", posts[:1])
    for k, raw, want in FIDELITY:
        if want is not None:
            check(f"value {raw!r} is stored as {want!r}", data.get(k) == want, repr(data.get(k)))
    check("existing keys survive the merge", data.get("OLD") == "keep", data)
    check("new values win over existing ones", data.get("Q1") == "a\"b'c", data)
    check("a key is trimmed", data.get("K2") == "v", data)
    check("a value never becomes program text", not canary.exists())

    # The program is a quoted here-document; a value line equal to its
    # terminator is still only a (key-only) line of data.
    proc, posts = run("A=1\nPY\nB=2", cwd=d)
    data = posts[0][2].get("data", {}) if posts else {}
    check("a line equal to the here-document terminator is data",
          proc.returncode == 0 and data == {"A": "1", "PY": "", "B": "2"}, (proc.stderr, data))

# A KV v2 write replaces the whole secret: an unreadable current version must
# stop the step. The old shell logged "will write fresh" and did exactly that.
for status in (403, 500, 503):
    proc, posts = run("A=1", get_status=status)
    check(f"GET {status}: step fails", proc.returncode != 0)
    check(f"GET {status}: nothing is written", posts == [], posts)

proc, posts = run("A=1", get_status=404)
check("GET 404: a new path is created with only the new keys",
      proc.returncode == 0 and posts and posts[0][2] == {"data": {"A": "1"}}, (proc.stderr, posts))

proc, posts = run("A=1", post_status=500)
check("a failed write fails the step", proc.returncode != 0)

for bad in ("a.b=1", "1A=1", "A B=1", "x | y=1"):
    proc, posts = run(f"OK=1\n{bad}")
    check(f"invalid key {bad!r} fails before any write", proc.returncode != 0 and posts == [],
          (proc.returncode, posts))

proc, posts = run("# only a comment\n\n")
check("no KEY=value lines fails rather than writing an empty merge",
      proc.returncode != 0 and posts == [], (proc.returncode, posts))

server.shutdown()
if failures:
    print("\nFAILURES:\n" + "\n".join(failures), file=sys.stderr)
    sys.exit(1)
print("\nAll checks passed.")
