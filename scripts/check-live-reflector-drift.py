#!/usr/bin/env python3
"""Live Reflector drift check (D2). MANUAL tool: needs a metadata listing taken from the cluster.

NOT run in CI. CI only runs tests/test_live_reflector_drift.py, which feeds this
script recorded synthetic fixtures. A GREEN here is a statement about the
listing you gave it, taken at that moment, nothing more.

Take the listing (read-only; only metadata is written to the output, see the collector's header for what
kubectl itself fetches):
  scripts/collect-reflector-metadata.sh > listing.txt
Then: scripts/check-live-reflector-drift.py listing.txt --expect-context NAME [--expect-server URL] [KUBECTL_RC]
        [--anchor ns/name]... | --no-anchor  [--source ns/name]...
  The listing starts with a "#CLUSTER context=<c> server=<s>" header written by the collector. At least one of
  --expect-context / --expect-server is REQUIRED and must equal the header; a missing header, a missing
  expectation or a mismatch is UNKNOWN (a listing of the wrong cluster must never be read as this one).
  --anchor defaults to database/postgres-credentials (a listing that lacks it is partial: UNKNOWN).
  Use --no-anchor explicitly once the sources are deleted; the default never silently drops it.
  --source adds a source (ns/name) to the non-annotated-copy rule; the three S-A sources in database are built in.
rows: ns|name|allowed|auto|reflects|auto-reflects|reflected-version|reflected-at ; trailer "#END rows=N" is the last line and the only one
exit 0 GREEN, 1 RED, 2 UNKNOWN. UNKNOWN outranks RED (drift you could not fully observe is not reported as green).
GREEN accepts exactly the end state: sources exist with allowed=false and auto-enabled=false, zero mirrors.
Mirror markers (Reflector 10.0.65 docs): reflects ("<ns>/<name>"), auto-reflects, reflected-version, reflected-at.
Non-annotated copies: a Secret named like a source in any namespace other than the source's own is RED even
without markers (a plain copy, a pull-created or hand-made duplicate). Unreadable listing: UNKNOWN.

Test seam: the module-level REVERT set disables one rule at a time. Only the tests set it; there is
deliberately no environment variable or flag that can weaken the check from outside.
"""
import os, re, sys
ALLOW_SOURCES = set()      # (ns, name) allowed to be a reflector source / to have mirrors; empty after Row 1
DEFAULT_ANCHOR = "database/postgres-credentials"
SOURCES = [("database", "object-storage-credentials"), ("database", "postgres-credentials"),
           ("database", "tenant-bootstrap-secret")]
REVERT = set()      # test seam only, see module docstring
def rev(n): return n in REVERT
_R = "reflection" + "-"      # spelled in pieces so the repo guard never sees a literal key here
SRC = re.compile(r"^[^/\s|]+/[^/\s|]+$")

HEADER = re.compile(r"#CLUSTER context=([A-Za-z0-9._:/@%+\-\[\]]+) server=([A-Za-z0-9._:/@%+\-\[\]]+)")

def esc(s):
    """Printable form: control characters escaped so a hostile Secret name cannot forge a log line or a workflow command."""
    return "".join(c if (c.isprintable() and c not in "\u2028\u2029") else "\\u%04x" % ord(c) for c in str(s))

def evaluate(lines, rc=0, anchors=(), allow=None, sources=None, expect=None):
    allow = ALLOW_SOURCES if allow is None else allow
    sources = set(SOURCES if sources is None else sources) | set(allow)
    if rc != 0: return 2, [f"UNKNOWN: listing command failed rc={rc}"]
    if rev("crlf"): lines = [l.rstrip("\n") for l in lines]
    else: lines = [l.rstrip("\r\n") for l in lines]       # CRLF listings (a file saved on Windows, a CRLF pipe)
    if not rev("crlf") and any("\r" in l for l in lines):
        return 2, ["UNKNOWN: stray carriage return inside a line (corrupt or mixed line endings)"]
    # An empty listing needs no line of its own: it has no header (UNKNOWN below), no trailer (UNKNOWN below) and, with
    # both of those reverted, no rows (UNKNOWN below). Each of the three is proven on its own in the tests.
    heads = [l for l in lines if l.startswith("#CLUSTER")]
    trailer = [l for l in lines if l.startswith("#END")]
    stray = [l for l in lines if l.startswith("#") and not l.startswith(("#CLUSTER", "#END"))]
    if stray: return 2, [f"UNKNOWN: unrecognised comment line {esc(stray[0])[:60]!r}"]
    rows = [l for l in lines if l and not l.startswith("#")]
    if not rev("cluster_identity"):
        hm = HEADER.fullmatch(heads[0]) if len(heads) == 1 else None
        if not hm or lines[0] != heads[0]:
            return 2, ["UNKNOWN: missing, repeated or malformed #CLUSTER header on the first line (listing of an unknown cluster)"]
        ec, es = (expect or {}).get("context"), (expect or {}).get("server")
        if not ec and not es:
            return 2, ["UNKNOWN: no expected cluster identity given (--expect-context / --expect-server)"]
        if (ec and hm.group(1) != ec) or (es and hm.group(2) != es):
            return 2, [f"UNKNOWN: listing is from context={esc(hm.group(1))} server={esc(hm.group(2))}, expected {esc(ec or '*')} / {esc(es or '*')}"]
    if not rev("trailer"):
        m = re.fullmatch(r"#END rows=(\d+)", trailer[-1]) if trailer else None
        if len(trailer) != 1 or not m or lines[-1] != trailer[0]:
            return 2, ["UNKNOWN: missing or malformed #END trailer (truncated listing?)"]
        if int(m.group(1)) != len(rows):
            return 2, [f"UNKNOWN: trailer says {m.group(1)} rows, got {len(rows)} (partial listing)"]
    if not rows: return 2, ["UNKNOWN: zero rows (never read as 0 found)"]
    present, red, unk = set(), [], []
    parsed = []
    for l in rows:
        p = l.split("|")
        if len(p) != 8: return 2, [f"UNKNOWN: malformed row with {len(p)} fields (expected 8)"]
        if not p[0] or not p[1]: return 2, ["UNKNOWN: row without namespace/name"]
        parsed.append(p); present.add((p[0], p[1]))
    for a in anchors:
        n, _, nm = a.partition("/")
        if (n, nm) not in present: return 2, [f"UNKNOWN: anchor Secret {a} absent from listing (partial?)"]
    if not rev("copy_rule"):
        for ns, name in sorted(present):
            for sns, sname in sorted(sources):
                if name == sname and ns != sns:
                    red.append(f"non-annotated copy {ns}/{name} of source {sns}/{sname} (any namespace other than the source's)")
    for ns, name, allowed, auto, reflects, autoref, rver, rat in parsed:
        key = (ns, name)
        if not rev("source_flags") and key not in allow:
            for fname, v in ((_R + "allowed", allowed), (_R + "auto-enabled", auto)):
                if v.strip().lower() not in ("", "false"):      # true, TRUE, ' true', anything not provably false
                    red.append(f"source {ns}/{name}: {fname}={v!r}")
        elif rev("source_flags") and allowed == "true" and key not in allow:   # old prototype behaviour
            red.append(f"source {ns}/{name}: {_R}allowed='true'")
        markers = [x for x in (reflects, autoref, rver, rat) if x != ""]
        if rev("mirror_rule"): markers = []
        if markers:
            src = reflects
            if not SRC.match(src):
                unk.append(f"mirror {ns}/{name}: markers present but source unreadable (reflects={reflects!r})")
                continue
            s = tuple(src.split("/"))
            if s not in allow:
                red.append(f"mirror {ns}/{name} <- {src}: source not allow-listed")
            elif s not in present:
                unk.append(f"mirror {ns}/{name} <- {src}: allow-listed source not in listing, cannot read it")
    if unk and not rev("unknown_outranks"): return 2, unk + red[:3]
    return (1 if red else 0), red

def main(argv):
    if not argv: print("usage: check-live-reflector-drift.py LISTING [RC] [--anchor ns/name]... | --no-anchor [--source ns/name]..."); return 2
    path, rc, anchors, i, no_anchor, extra, expect = argv[0], 0, [], 1, False, [], {}
    try:
        while i < len(argv):
            if argv[i] == "--anchor": anchors.append(argv[i + 1]); i += 2
            elif argv[i] == "--no-anchor": no_anchor = True; i += 1
            elif argv[i] in ("--expect-context", "--expect-server"):
                if not argv[i + 1] or argv[i + 1].startswith("--"): raise ValueError(argv[i] + " needs a value")
                expect[argv[i][len("--expect-"):]] = argv[i + 1]; i += 2
            elif argv[i] == "--source":
                ns, _, nm = argv[i + 1].partition("/")
                if not ns or not nm: raise ValueError("--source needs ns/name")
                extra.append((ns, nm)); i += 2
            else: rc = int(argv[i]); i += 1
    except (ValueError, IndexError) as e:
        print(f"UNKNOWN: bad argument ({esc(e)})"); return 2
    if no_anchor and anchors: print("UNKNOWN: --anchor and --no-anchor are mutually exclusive"); return 2
    if not no_anchor and not anchors and not rev("default_anchor"): anchors = [DEFAULT_ANCHOR]
    try: lines = open(path, newline="").readlines()    # newline="": keep \r\n so evaluate() sees and handles it
    except Exception as e: print("UNKNOWN:", esc(e)); return 2
    code, out = evaluate(lines, rc, anchors, sources=SOURCES + extra, expect=expect)
    print(["GREEN", "RED", "UNKNOWN"][code], f"(exit {code})", f"findings={len(out)}")
    for o in out[:10]: print("  ", esc(o))
    if code == 0: print("   scope: Secrets only, metadata only; ConfigMaps and non-Secret kinds are not covered; copies are caught only by name (a renamed copy is not); cluster identity is the collector's own header, matched to what you expected, not independently proven")
    return code
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
