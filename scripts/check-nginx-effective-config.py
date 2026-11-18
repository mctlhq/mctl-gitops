#!/usr/bin/env python3
"""Detect nginx features that the November 2026 advisories make reachable.

Analyses the effective configuration printed by `nginx -T` and fails when it
enables a feature gated by one of the ten advisories fixed in nginx 1.31.9 /
1.30.7 (nginx.org, 2026-11-18):

  http2 / http3 / quic     CVE-2026-123007, CVE-2026-123633, CVE-2026-121810
  resolver                 CVE-2026-123634
  ssl listener             CVE-2026-118899 (client body over TLS 1.3)
  mail { }                 CVE-2026-113425
  proxy_protocol listener  CVE-2026-120993
  alias                    CVE-2026-125283 (with try_files)
  stream { }               CVE-2026-120967, CVE-2026-123640
  load_module              can add mail or stream behind our back

Exit codes: 0 = clean, 1 = a gated feature found, 2 = UNVERIFIED (could not
observe a complete configuration). "Could not observe" is never "clean".

Preferred, the command itself is checked (exit 0 and "test is successful" on
stderr are required, so the dump is nginx's own and complete):

    check-nginx-effective-config.py -- kubectl exec POD -- nginx -T

File or stdin input cannot prove the dump is complete (a dump cut after the
last closing brace looks whole), so without --assume-complete it never reports
clean: it exits 1 on a finding and 2 otherwise. Pass --assume-complete only
for a dump you captured yourself from a successful `nginx -T`.

Parsing follows nginx: a `#` starts a comment only at the start of a token,
quotes group a token and are removed, `;` `{` `}` inside quotes are text, and
`${name}` braces belong to the token. A truncated input (open quote, open
block, last statement without a terminator, no `events` or `http` block, no
`listen`, a missing chunk for a non-glob `include`) is UNVERIFIED. A glob
`include` that matched no file prints no chunk, which is legitimate, so the
detector cannot tell it from a missing one: this is why file mode is never clean.

Do not store the full `nginx -T` output: it can contain secrets.
"""
import re
import subprocess
import sys

LISTEN_FLAGS = ("http2", "quic", "ssl", "proxy_protocol")
DIRECTIVES = {
    "resolver": "CVE-2026-123634",
    "alias": "CVE-2026-125283 (alias with try_files)",
    "load_module": "can enable mail or stream modules",
    "ssl_certificate": "TLS terminated in nginx (CVE-2026-118899)",
}
SWITCHES = {"http2": "CVE-2026-123007/123633 (HTTP/2)", "http3": "CVE-2026-121810 (HTTP/3)"}
PREFIXES = ("http3_", "quic_")
BLOCKS = {
    "mail": "CVE-2026-113425 (mail proxy)",
    "stream": "CVE-2026-120967, CVE-2026-123640 (stream)",
}
CHUNK = re.compile(r"^# configuration file (.+?):\s*$", re.M)


class Unreadable(Exception):
    pass


def statements(text):
    """Return [(line, tokens, terminator)] following nginx's tokenizer.

    terminator is ';' for a directive, '{' for a block start, '}' for a block
    end. Raises Unreadable on an open quote, an open block or a last statement
    without a terminator.
    """
    out, toks, cur = [], [], []
    line, start, depth = 1, 1, 0
    in_tok = quoted = var_brace = comment = False
    quote = ""
    i, n = 0, len(text)

    def end_token():
        nonlocal in_tok, quoted, cur
        if in_tok:
            toks.append("".join(cur))
        cur, in_tok, quoted = [], False, False

    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
        if comment:
            if ch == "\n":
                comment = False
            i += 1
            continue
        if quote:
            if ch == "\\" and i + 1 < n:
                cur.append(text[i + 1])
                if text[i + 1] == "\n":
                    line += 1
                i += 2
                continue
            if ch == quote:
                quote = ""
                end_token()
            else:
                cur.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            # Outside quotes nginx also takes the next character literally,
            # including whitespace, ';', '{', '#' and quotes.
            if not in_tok:
                if not toks:
                    start = line
                in_tok = True
            nxt = text[i + 1]
            cur.append(nxt if nxt in "\"'\\" else ch + nxt)
            if nxt == "\n":
                line += 1
            i += 2
            continue
        if ch in " \t\r\n":
            end_token()
        elif ch == "#" and not in_tok:
            comment = True
        elif ch in "\"'" and not in_tok:
            if not toks:
                start = line
            quote, in_tok, quoted = ch, True, True
        elif ch == "{" and in_tok and cur and cur[-1] == "$":
            cur.append(ch)
            var_brace = True
        elif ch == "}" and var_brace:
            cur.append(ch)
            var_brace = False
        elif ch in ";{}":
            end_token()
            if ch == "}":
                if toks:
                    raise Unreadable("line %d: '}' after a statement without ';'" % line)
                depth -= 1
                if depth < 0:
                    raise Unreadable("line %d: unbalanced '}'" % line)
                out.append((line, [], "}"))
            else:
                if not toks and ch == ";":
                    pass
                else:
                    if ch == "{":
                        depth += 1
                    out.append((start, toks, ch))
                toks = []
        else:
            if not in_tok:
                if not toks:
                    start = line
                in_tok = True
            cur.append(ch)
        i += 1
    if quote:
        raise Unreadable("unterminated quote")
    end_token()
    if toks:
        raise Unreadable("last statement has no terminator: truncated input")
    if depth != 0:
        raise Unreadable("%d block(s) left open: truncated input" % depth)
    return out


def analyse(text):
    """Return (findings, error). error is a reason string or None."""
    try:
        stmts = statements(text)
    except Unreadable as e:
        return [], str(e)
    findings, listens, blocks = [], 0, set()
    for n, t, term in stmts:
        if term == "}":
            continue
        d, args = t[0], t[1:]
        if term == "{":
            blocks.add(d)
            if d in BLOCKS:
                findings.append((n, "%s block  [%s]" % (d, BLOCKS[d])))
            continue
        if d == "listen":
            listens += 1
            for flag in LISTEN_FLAGS:
                if any(a == flag or a.startswith(flag + "=") for a in args[1:]):
                    findings.append((n, "listen ... %s" % flag))
        elif d in SWITCHES:
            if args[:1] != ["off"]:
                findings.append((n, "%s  [%s]" % (d, SWITCHES[d])))
        elif d in DIRECTIVES:
            findings.append((n, "%s  [%s]" % (d, DIRECTIVES[d])))
        elif d.startswith(PREFIXES):
            findings.append((n, "%s  [HTTP/3 / QUIC]" % d))
    if listens == 0:
        return findings, "no listen directive found: not an nginx -T dump"
    for need in ("events", "http"):
        if need not in blocks:
            return findings, "no %s block: not a complete nginx -T dump" % need
    chunks = CHUNK.findall(text)
    if not chunks or not chunks[0].endswith("nginx.conf"):
        return findings, "no '# configuration file ...nginx.conf:' header: not an nginx -T dump"
    base = chunks[0].rsplit("/", 1)[0]
    for n, t, term in stmts:
        if term == ";" and t[0] == "include" and len(t) == 2 and not re.search(r"[*?\[]", t[1]):
            path = t[1] if t[1].startswith("/") else base + "/" + t[1]
            if path not in chunks:
                return findings, "line %d: include %s has no chunk in the dump" % (n, t[1])
    return findings, None


def report(findings):
    for n, what in findings:
        print("line %d: %s" % (n, what))


def run(text, complete):
    """complete: True when the producer is known to have succeeded."""
    if not text.strip():
        print("UNVERIFIED: empty input, nothing was observed", file=sys.stderr)
        return 2
    findings, err = analyse(text)
    if findings:
        report(findings)
        return 1
    if err:
        print("UNVERIFIED: " + err, file=sys.stderr)
        return 2
    if not complete:
        print("UNVERIFIED: file or stdin input cannot prove the dump is complete; "
              "use `-- <command>` or pass --assume-complete", file=sys.stderr)
        return 2
    return 0


def run_command(cmd):
    if not cmd:
        print("UNVERIFIED: no command after --", file=sys.stderr)
        return 2
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        print("UNVERIFIED: command failed to run: %s" % e, file=sys.stderr)
        return 2
    if r.returncode != 0:
        print("UNVERIFIED: command exited %d" % r.returncode, file=sys.stderr)
        return 2
    if b"test is successful" not in r.stderr:
        print("UNVERIFIED: no 'test is successful' on stderr", file=sys.stderr)
        return 2
    return run(r.stdout.decode("utf-8", "replace"), True)


CLEAN = """# configuration file /etc/nginx/nginx.conf:
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  include /etc/nginx/conf.d/*.conf;
}
# configuration file /etc/nginx/mime.types:
types { text/html html; }
# configuration file /etc/nginx/conf.d/default.conf:
server {
  listen 8080;   # no http2 here
  location / { try_files $uri $uri/ =404; }
}
"""


def with_listen(extra):
    return CLEAN.replace("  listen 8080;", "  " + extra + "\n  listen 8080;")


def selftest():
    ok = True
    py = sys.executable

    fails = []

    def expect(name, got, want):
        nonlocal ok
        if got != want:
            ok = False
            fails.append("SELFTEST FAIL: %s: rc %s, want %s" % (name, got, want))

    quiet = open("/dev/null", "w")
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = quiet
    try:
        def f(text, complete=True):
            return run(text, complete)

        def cmd(out, err, rc):
            code = ("import sys;sys.stdout.write(%r);sys.stderr.write(%r);sys.exit(%d)"
                    % (out, err, rc))
            return run_command([py, "-c", code])

        expect("clean", f(CLEAN), 0)
        expect("clean-file-mode-never-clean", f(CLEAN, False), 2)
        expect("empty", f(""), 2)
        expect("not-nginx", f("hello world;"), 2)
        expect("only-listen", f("listen 8080;"), 2)
        expect("no-http", f(CLEAN.replace("http {", "other {")), 2)
        expect("no-events", f(CLEAN.replace("events { worker_connections 1024; }", "")), 2)
        expect("no-listen", f(CLEAN.replace("  listen 8080;", "")), 2)
        expect("no-main-chunk-header", f(CLEAN.replace("# configuration file /etc/nginx/nginx.conf:", "")), 2)
        expect("missing-include-chunk", f(CLEAN.replace("# configuration file /etc/nginx/mime.types:\ntypes { text/html html; }\n", "")), 2)
        expect("truncated-mid-block", f(CLEAN.rstrip().rstrip("}")), 2)
        expect("truncated-no-terminator", f(CLEAN + "server_name"), 2)
        expect("open-quote", f(CLEAN + 'add_header X "abc;'), 2)
        expect("comment-mentions-gated", f(CLEAN + "# listen 8443 ssl http2;"), 0)
        expect("escaped-semicolon-stays-in-token", f(CLEAN.replace("listen 8080;", "listen 8080; add_header X a\\;b;")), 0)
        expect("hash-inside-token-not-comment", f(CLEAN.replace("listen 8080;", "listen 8080; error_page 404 /a#b;")), 0)
        expect("http2-off-is-clean", f(CLEAN.replace("  listen 8080;", "  http2 off;\n  listen 8080;")), 0)
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dump.conf")
            for name, body, want in (
                ("non-utf8-in-comment", CLEAN.encode() + b"# \xff\xfe bytes\n", 0),
                ("non-utf8-with-finding", with_listen("listen 8443 ssl;").encode() + b"# \xff\n", 1),
            ):
                with open(path, "wb") as fh:
                    fh.write(body)
                expect(name, main([path, "--assume-complete"]), want)
            expect("missing-file", main([os.path.join(d, "nope")]), 2)
        mutations = {
            "listen-http2": "listen 8443 http2;",
            "listen-quic": "listen 8443 quic reuseport;",
            "listen-ssl": "listen 8443 ssl;",
            "listen-proxy-protocol": "listen 8080 proxy_protocol;",
            "http2-on": "http2 on;",
            "http3-on": "http3 on;",
            "http3-prefix": "http3_hq on;",
            "quic-prefix": "quic_bpf on;",
            "resolver": "resolver 10.0.0.2;",
            "alias": "location /a/ { alias /srv/a/; try_files $uri =404; }",
            "load-module": "load_module modules/ngx_stream_module.so;",
            "ssl-cert": "ssl_certificate /x.pem;",
            "mail-block": "mail { server { listen 25; } }",
            "stream-block": "stream { server { listen 53; } }",
            "mail-compact": "mail{server{listen 25;}}",
            "quoted-flag": 'listen 8443 "ssl";',
            "quoted-directive": '"resolver" 10.0.0.2;',
            "quoted-block": '"stream" { server { listen 53; } }',
            "after-hash-in-quotes": 'add_header X "a#b"; listen 8443 ssl http2;',
            "after-hash-in-rewrite": "rewrite ^/a#b /c; listen 8443 quic;",
            "after-brace-in-quotes": 'add_header X "a{b"; resolver 1.1.1.1;',
            "variable-brace": "set $x ${y}; resolver 1.1.1.1;",
            "backslash-semicolon-then-hash": "add_header X a\\;#; listen 8443 ssl;",
            "backslash-space-then-quote": 'add_header X a\\ "b; listen 8443 ssl;',
            "backslash-brace": "add_header X a\\{; resolver 1.1.1.1;",
            "crlf": "listen 8443 ssl;",
        }
        for name, line in mutations.items():
            text = with_listen(line)
            if name == "crlf":
                text = text.replace("\n", "\r\n")
            expect("mutation:" + name, f(text), 1)
        expect("cmd-ok", cmd(CLEAN, "test is successful", 0), 0)
        expect("cmd-finding", cmd(with_listen("listen 8443 ssl;"), "test is successful", 0), 1)
        expect("cmd-nonzero", cmd(CLEAN, "test is successful", 1), 2)
        expect("cmd-no-success-line", cmd(CLEAN, "", 0), 2)
        expect("cmd-no-output", cmd("", "test is successful", 0), 2)
        expect("cmd-missing", run_command(["/nonexistent/nginx-binary"]), 2)
        expect("cmd-none", run_command([]), 2)
        big = CLEAN + " " * 3_000_000 + "\n"
        expect("long-whitespace-linear", f(big), 0)
    finally:
        sys.stdout, sys.stderr = real_out, real_err
    for line in fails:
        print(line, file=sys.stderr)
    print("selftest: %s" % ("ok" if ok else "FAILED"))
    return 0 if ok else 1


def _main(argv):
    if "--selftest" in argv:
        return selftest()
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 2
    if "--" in argv:
        return run_command(argv[argv.index("--") + 1:])
    assume = "--assume-complete" in argv
    files = [a for a in argv if not a.startswith("--")]
    if len(files) > 1:
        print("UNVERIFIED: expected at most one input file", file=sys.stderr)
        return 2
    data = open(files[0], "rb").read() if files else sys.stdin.buffer.read()
    return run(data.decode("utf-8", "replace"), assume)


def main(argv):
    try:
        return _main(argv)
    except Exception as e:  # never let a crash read as "found" (1) or "clean" (0)
        print("UNVERIFIED: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
