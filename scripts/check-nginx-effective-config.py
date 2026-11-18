#!/usr/bin/env python3
"""Detect nginx features that the November 2026 advisories make reachable.

Reads the output of `nginx -T` (effective configuration, includes expanded)
from a file or stdin and fails when it enables a feature gated by one of the
ten advisories fixed in nginx 1.31.9 / 1.30.7 (nginx.org, 2026-11-18):

  http2 / http3 / quic     CVE-2026-123007, CVE-2026-123633, CVE-2026-121810
  resolver                 CVE-2026-123634
  ssl listener             CVE-2026-118899 (client body over TLS 1.3)
  mail { }                 CVE-2026-113425
  proxy_protocol listener  CVE-2026-120993
  alias                    CVE-2026-125283 (with try_files)
  stream { }               CVE-2026-120967, CVE-2026-123640
  load_module              can add mail or stream behind our back

Exit codes: 0 = no gated feature found, 1 = at least one found, 2 = the input
could not be read as an nginx configuration. "Could not observe" is never
"clean": empty input, or input with no `listen` directive, exits 2.

Usage:  kubectl exec POD -- nginx -T | scripts/check-nginx-effective-config.py
        scripts/check-nginx-effective-config.py --selftest

This is a config check, not a version check: a patched nginx (>= 1.31.9 or
>= 1.30.7) makes these features safe to enable. Do not write the full `nginx -T`
output to logs or evidence: it can contain secrets.
"""
import re
import sys

LISTEN_FLAGS = ("http2", "quic", "ssl", "proxy_protocol")
DIRECTIVES = {
    "http2": "CVE-2026-123007/123633 (HTTP/2)",
    "http3": "CVE-2026-121810 (HTTP/3)",
    "resolver": "CVE-2026-123634",
    "alias": "CVE-2026-125283 (alias with try_files)",
    "load_module": "can enable mail or stream modules",
}
BLOCKS = {
    "mail": "CVE-2026-113425 (mail proxy)",
    "stream": "CVE-2026-120967, CVE-2026-123640 (stream)",
}


def statements(text):
    """Yield (lineno, tokens) for each statement, with comments removed."""
    cleaned = []
    for n, line in enumerate(text.splitlines(), 1):
        cleaned.append((n, re.sub(r"#.*$", "", line)))
    buf, start = "", 0
    for n, line in cleaned:
        for ch in line:
            if not buf.strip():
                start = n
            if ch in ";{}":
                tokens = buf.split()
                if ch == "{" and tokens:
                    yield start, tokens + ["{"]
                elif tokens:
                    yield start, tokens
                buf = ""
            else:
                buf += ch
        buf += " "


def check(text):
    findings, listens = [], 0
    for n, t in statements(text):
        d = t[0]
        if d == "listen":
            listens += 1
            for flag in LISTEN_FLAGS:
                if any(a == flag or a.startswith(flag + "=") for a in t[2:]):
                    findings.append((n, "listen ... %s" % flag))
        elif d in DIRECTIVES:
            findings.append((n, "%s  [%s]" % (d, DIRECTIVES.get(d, ""))))
        elif d in BLOCKS and t[-1] == "{":
            findings.append((n, "%s block  [%s]" % (d, BLOCKS[d])))
        elif d == "ssl_certificate":
            findings.append((n, "ssl_certificate (TLS terminated in nginx)"))
    return findings, listens


def run(text):
    if not text.strip():
        print("UNVERIFIED: empty input, nothing was observed", file=sys.stderr)
        return 2
    findings, listens = check(text)
    if listens == 0:
        print("UNVERIFIED: no listen directive found; not an nginx -T dump",
              file=sys.stderr)
        return 2
    for n, what in findings:
        print("line %d: %s" % (n, what))
    return 1 if findings else 0


CLEAN = """
# configuration file /etc/nginx/nginx.conf:
events { worker_connections 1024; }
http {
  include /etc/nginx/conf.d/*.conf;
  # configuration file /etc/nginx/conf.d/default.conf:
  server {
    listen 8080;   # no http2 here
    location / { try_files $uri $uri/ =404; }
  }
}
"""


def selftest():
    ok = True

    def expect(name, text, rc):
        nonlocal ok
        got = run(text)
        if got != rc:
            ok = False
            print("SELFTEST FAIL: %s: rc %d, want %d" % (name, got, rc),
                  file=sys.stderr)

    expect("clean", CLEAN, 0)
    expect("empty", "", 2)
    expect("not-nginx", "hello world;", 2)
    expect("comment-only-mentions", CLEAN + "# listen 8443 ssl http2;", 0)
    mutations = {
        "listen-http2": "listen 8080 http2;",
        "listen-quic": "listen 8443 quic reuseport;",
        "listen-ssl": "listen 8443 ssl;",
        "listen-proxy-protocol": "listen 8080 proxy_protocol;",
        "http2-on": "http2 on;",
        "http3-on": "http3 on;",
        "resolver": "resolver 10.0.0.2;",
        "alias": "location /a/ { alias /srv/a/; try_files $uri =404; }",
        "load-module": "load_module modules/ngx_stream_module.so;",
        "ssl-cert": "ssl_certificate /x.pem;",
    }
    for name, line in mutations.items():
        expect("mutation:" + name, CLEAN.replace("listen 8080;", line + " listen 8080;"), 1)
    expect("mail-block", CLEAN + "mail { server { listen 25; } }", 1)
    expect("stream-block", CLEAN + "stream { server { listen 53; } }", 1)
    print("selftest: %s" % ("ok" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    src = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    sys.exit(run(src))
