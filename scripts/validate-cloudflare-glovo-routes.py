#!/usr/bin/env python3
"""Pin the Worker routes of glovo.mctl.ai (infrastructure/cloudflare/zones/mctl-ai/workers.tf).

Cloudflare matches a route pattern against the whole request URL including the
query string, supports only the `*` wildcard (zero or more of any character),
rejects query parameters inside a pattern, and lets the most specific matching
pattern win; a route without a script bypasses Workers. See
https://developers.cloudflare.com/workers/configuration/routing/routes/

Checks, by simulating that matching over the declared routes:
  - the root, with or without a query string, is served by glovo-landing;
  - /mcp and /.well-known/* are never served by a Worker (they stay on the
    tunnel origin);
  - no pattern contains a query parameter (the API rejects it).

  validate-cloudflare-glovo-routes.py            check the repository tree
  validate-cloudflare-glovo-routes.py --selftest prove each refusal fires
"""
import re
import sys
from pathlib import Path

WORKERS_TF = "infrastructure/cloudflare/zones/mctl-ai/workers.tf"
HOST = "glovo.mctl.ai"
WORKER = "glovo-landing"

# (path+query, expected script or None for "no Worker")
CASES = [
    ("/", WORKER),
    ("/?lang=en", WORKER),
    ("/?lang=ru", WORKER),
    ("/?x=1", WORKER),
    ("/mcp", None),
    ("/mcp?x=1", None),
    ("/mcp/", None),
    ("/.well-known/oauth-protected-resource", None),
    ("/.well-known/oauth-protected-resource/mcp", None),
    ("/.well-known/oauth-protected-resource?x=1", None),
]

RESOURCE = re.compile(r'resource\s+"cloudflare_workers_route"\s+"[^"]+"\s*\{(.*?)\n\}', re.S)
PATTERN = re.compile(r'^\s*pattern\s*=\s*"([^"]*)"', re.M)
SCRIPT = re.compile(r'^\s*script\s*=\s*"([^"]*)"', re.M)


def routes(text):
    out = []
    for body in RESOURCE.findall(text):
        m = PATTERN.search(body)
        if m:
            s = SCRIPT.search(body)
            out.append((m.group(1), s.group(1) if s else None))
    return out


def matches(pattern, url):
    rx = "".join(".*" if c == "*" else re.escape(c) for c in pattern)
    return re.fullmatch(rx, url) is not None


def serving(rs, path):
    """Script serving https://HOST<path>, or None: most specific pattern wins
    (more literal characters), and a scriptless route yields None."""
    url = HOST + path
    hit = [(len(p.replace("*", "")), s) for p, s in rs if matches(p, url)]
    if not hit:
        return None
    top = max(h[0] for h in hit)
    scripts = {s for n, s in hit if n == top}
    # Equally specific patterns with different outcomes: Cloudflare gives no
    # documented order, so refuse rather than guess.
    return scripts.pop() if len(scripts) == 1 else "AMBIGUOUS"


def check(text):
    rs = [(p, s) for p, s in routes(text) if p.startswith(HOST)]
    errs = []
    for p, _ in rs:
        if "?" in p:
            errs.append(f"pattern {p!r} contains a query parameter; the API rejects it")
    for path, want in CASES:
        got = serving(rs, path)
        if got != want:
            errs.append(f"{path}: served by {got!r}, expected {want!r}")
    return errs


def selftest():
    good = (Path(__file__).resolve().parent.parent / WORKERS_TF).read_text()
    assert not check(good), check(good)

    def drop(name, text):
        return re.sub(r'resource\s+"cloudflare_workers_route"\s+"%s"\s*\{.*?\n\}\n' % name, "", text, flags=re.S)

    for name in ("glovo_landing_query", "glovo_origin_mcp", "glovo_origin_well_known"):
        assert check(drop(name, good)), f"removing {name} must fail"
    assert check(good.replace('"glovo.mctl.ai/*"', '"glovo.mctl.ai/?*"')), "query pattern must fail"
    wide = good + '\nresource "cloudflare_workers_route" "w" {\n  pattern = "glovo.mctl.ai/*mcp*"\n  script  = "glovo-landing"\n}\n'
    assert check(wide), "a wider pattern capturing /mcp must fail"
    print("selftest ok")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0
    root = Path(__file__).resolve().parent.parent
    errs = check((root / WORKERS_TF).read_text())
    for e in errs:
        print("REFUSED:", e)
    if not errs:
        print("glovo routes ok")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
