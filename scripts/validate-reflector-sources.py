#!/usr/bin/env python3
"""Reflector source guard (D1): no Git-visible Reflector enabler or mirror marker.

Offline: reads only the checked-out tree. Part of the S-A containment of
mctl-agents#1007 (B4): mirroring of the Secrets in namespace `database` must
stay off. This is the repo half; the live half is scripts/check-live-reflector-drift.py
(manual, needs the cluster, NOT run in CI).

usage: validate-reflector-sources.py [ROOT] [--anchor REL_PATH ...]
  ROOT defaults to the repository root. Exit 0 GREEN, 1 RED, 2 UNKNOWN.

GREEN means only: no Git-visible enabler or mirror marker in the scanned tree.
It NEVER means "no S-A"; the COVERAGE block printed on every run says what is
not seen. Anything the scan could not read or parse is UNKNOWN, never green.

Test seam: the module-level REVERT set disables one rule at a time. Only the
tests set it (to prove each rule is load-bearing); there is deliberately no
environment variable or flag that can weaken the guard from outside.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

ALLOW = {("ConfigMap", "argo-workflows", "mctl-platform-config"):
         "non-secret platform config, reflected to all namespaces by design"}   # (kind, namespace, name)
ANCHOR_ALLOWED = ("ConfigMap", "argo-workflows", "mctl-platform-config")
ALLOW_REFLECTS = {"argo-workflows/mctl-platform-config"}
DEFAULT_ANCHORS = ["platform-gitops/argo-workflows/config/mctl-platform-config.yaml"]
SKIP_DIRS = {".git"}            # node_modules is scanned on purpose (a vendored chart or script can carry an enabler)
TEXT_EXT = (".yaml", ".yml", ".json", ".tf", ".sh", ".tpl")   # NUL byte in one of these is UNKNOWN, never "binary, skipped"
ARCHIVE_EXT = (".tgz", ".tar.gz", ".zip", ".tar", ".gz", ".jar", ".whl")
_R = "reflection" + "-"      # spelled in pieces so this file never contains a literal key
FLAG_KEYS = {_R + "allowed", _R + "auto-enabled"}
NS_KEYS = {_R + "allowed-namespaces", _R + "auto-namespaces",
           _R + "allowed-namespaces-selector", _R + "auto-namespaces-selector"}
MIRROR_KEYS = {"reflects", "auto-reflects", "reflected-version", "reflected-at"}
KNOWN = FLAG_KEYS | NS_KEYS | MIRROR_KEYS
REVERT = set()      # test seam only, see module docstring

COVERAGE = """COVERAGE: D1 reads only text files in the scanned Git tree (all extensions, all kinds, tests/fixtures included).\n  Prose-only mentions in .md are not flagged unless they spell a full key with a value.
NOT SEEN by D1: .git internals; packaged archives (.tgz/.tar.gz/.zip/...) are listed below and are NOT opened; client-side applies (kubectl annotate/apply/patch run by a person or script), Secrets that never
  were in Git (the three S-A database/* sources), objects created by Terraform apply from outside this tree or from
  state only, charts rendered from remote repositories, values pulled at runtime (Vault, ExternalSecret remote data),
  generated indirection (range over annotation maps, printf-built keys), Reflector's own Helm values.
D1 GREEN = "no Git-visible enabler". It is NEVER "no S-A". The live state is D2's job (metadata listing)."""

PFX = r'reflector\\?\.v1\\?\.k8s\\?\.emberstack\\?\.com'
OCC = re.compile(PFX + r'(?P<sep>/|~1|%2[Ff]|\\/)?(?P<suf>[A-Za-z][A-Za-z0-9-]*)')
PFX_ANY = re.compile(PFX)
TOKEN = re.compile(_R + r'(?:allowed|auto-enabled|allowed-namespaces|auto-namespaces)')
VAL = re.compile(r'''^(?:["'`])?\s*[:=]\s*(?P<v>"(?:[^"\\]|\\.)*"|'[^']*'|[^\s,}\]#]*)''')
VALUE_LINE = re.compile(r'''^\s*-?\s*value\s*[:=]\s*(?P<v>"(?:[^"\\]|\\.)*"|'[^']*'|[^\s,}\]#]*)''')
MATCH_ALL = {"", ".*", ".+", ".*?", "[\\s\\S]*", "[^]*"}

def rev(name): return name in REVERT

def decode(b):
    """BOM-aware. Returns text; raises ValueError when the bytes cannot be decoded faithfully."""
    if b.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")): return b.decode("utf-32")
    if b.startswith((b"\xff\xfe", b"\xfe\xff")): return b.decode("utf-16")
    if b.startswith(b"\xef\xbb\xbf"): return b[3:].decode("utf-8", "replace")
    return b.decode("utf-8", "replace")

def unq(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'": v = v[1:-1]
    return v.strip()

def provably_false(raw):
    return unq(raw).lower() == "false"

def enabling(raw):
    if rev("flag_not_provable_false"):          # old behaviour: literal "true" only
        return raw == '"true"'
    return not provably_false(raw)

def match_all(raw):
    for el in unq(raw).split(","):
        e = el.strip().lstrip("^").rstrip("$").strip()
        while e.startswith("(") and e.endswith(")"): e = e[1:-1].strip()
        if e in MATCH_ALL: return True
    return False

def scan_text(path, text):
    """returns list of findings (strings) and list of allow-listed enabling docs [(kind,name)]"""
    bad, allowed_seen = [], []
    lines = text.split("\n")
    docs, cur, start = [], [], 0
    for i, l in enumerate(lines):
        if re.match(r"^---\s*$", l):
            docs.append((start, cur)); cur, start = [], i + 1
        else: cur.append(l)
    docs.append((start, cur))
    for start, dl in docs:
        occ = []   # (lineno, suf, raw or None, removal)
        for j, line in enumerate(dl):
            if "reflect" not in line and "emberstack" not in line: continue
            ln = start + j + 1
            line_c = line.replace('\\"', '"')
            ms = list(OCC.finditer(line_c))
            if not rev("prefix_unrecognised_suffix"):
                covered = {m.start() for m in ms}
                for pm in PFX_ANY.finditer(line_c):
                    if pm.start() in covered: continue
                    tail = line_c[pm.end():pm.end() + 24]
                    if path.endswith(".md") and not re.match(r'^(?:/|~1|%2[Ff]|\\/)(?![A-Za-z])', tail):
                        continue            # prose naming the bare domain; a key-shaped templated tail is still flagged
                    bad.append(f"{path}:{ln}: Reflector annotation prefix followed by an unrecognised/templated suffix {tail!r} (key not statically readable)")
            for k, m in enumerate(ms):
                suf = m.group("suf")
                end = ms[k + 1].start() if k + 1 < len(ms) else len(line_c)
                rest = line_c[m.end():end]
                removal = False
                if suf.endswith("-") and suf.rstrip("-") in KNOWN:   # kubectl annotate key-  (removal)
                    suf, removal = suf.rstrip("-"), True
                if rev("formats") and not re.match(r'^\s*' + PFX, line_c):
                    continue                    # old behaviour: only "key: value" yaml lines
                raw = None
                if not removal:
                    vm = VAL.match(rest)
                    if vm: raw = vm.group("v")
                    else:
                        for nxt in dl[j + 1:j + 4]:
                            nm = VALUE_LINE.match(nxt)
                            if nm: raw = nm.group("v"); break
                occ.append((ln, suf, raw, removal))
            if not rev("unqualified") and not path.endswith(".md"):   # prose in .md may name the keys
                qual = len(ms)
                if len(TOKEN.findall(line_c)) > qual:
                    bad.append(f"{path}:{ln}: unqualified reflection-* token (key built indirectly?)")
        if not occ: continue
        dtext = "\n".join(dl)
        kinds = re.findall(r"^kind:\s*(\S+)", dtext, re.M)
        nm = re.search(r"^  name:\s*(\S+)", dtext, re.M)
        kind, name = (kinds[0] if len(kinds) == 1 else None), (unq(nm.group(1)) if nm else None)
        nsm = re.search(r"^  namespace:\s*(\S+)", dtext, re.M)
        ns = unq(nsm.group(1)) if nsm else None
        if rev("allow_ns"): allow = any(k == kind and n == name for (k, _x, n) in ALLOW)   # old behaviour: name only
        else: allow = (kind, ns, name) in ALLOW
        flags = {}
        en_lines = []
        for ln, suf, raw, removal in occ:
            if removal: continue
            if suf in FLAG_KEYS:
                if raw is None or enabling(raw):
                    en_lines.append((ln, suf, raw))
                else: flags[suf] = True
            elif suf not in KNOWN:
                bad.append(f"{path}:{ln}: unknown reflector.v1 annotation '{suf}' (not interpretable)")
        for ln, suf, raw in en_lines:
            if allow:
                allowed_seen.append((kind, ns, name)); continue
            why = "Secret must never be a reflector source; " if kind == "Secret" else ""
            bad.append(f"{path}:{ln}: {suf}={raw!r} not provably \"false\" in {kind}/{ns}/{name} "
                       f"(not allow-listed). {why}")
        both_false = all(flags.get(k) for k in FLAG_KEYS)
        if not rev("ns_matchall") and not allow and not both_false:
            for ln, suf, raw, removal in occ:
                if suf in NS_KEYS and not removal and (raw is None or match_all(raw)):
                    bad.append(f"{path}:{ln}: {suf}={raw!r} empty/match-all/unreadable and flags not provably false in {kind}/{name}")
        if not rev("reflects_marker"):
            for ln, suf, raw, removal in occ:
                if suf in MIRROR_KEYS and not removal:
                    src = unq(raw) if raw is not None else None
                    if suf == "reflects" and src in ALLOW_REFLECTS: continue
                    bad.append(f"{path}:{ln}: mirror marker {suf}={raw!r} committed in {kind}/{name} (mirror or pull-reflection from non-allow-listed source)")
    return bad, allowed_seen

def scan(root, anchors):
    if not os.path.isdir(root): return None, [f"UNKNOWN: root not a directory: {root}"], []
    errs = []
    bad, seen, allowed_all = [], 0, []
    archives = []
    def onerr(e): errs.append(f"walk error {e.filename}: {e.strerror}")
    for dp, dn, fn in os.walk(root, onerror=onerr):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
        for f in sorted(fn):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root)
            if rev("file_types"):
                if not f.endswith((".yaml", ".yml", ".tpl")) or "/tests/" in p or "/fixtures/" in p: continue
            if os.path.islink(p) and not os.path.exists(p):
                errs.append(f"dangling symlink {rel}"); continue
            try:
                b = open(p, "rb").read()
            except Exception as e:
                errs.append(f"unreadable {rel}: {e}"); continue
            seen += 1
            if f.lower().endswith(ARCHIVE_EXT): archives.append(rel)
            try:
                if b[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff") or b[:2] in (b"\xff\xfe", b"\xfe\xff"):
                    if rev("utf16_bom"): raise ValueError("revert")
                    text = decode(b)
                elif b"\0" in b:
                    if f.lower().endswith(TEXT_EXT) and not rev("nul_text_unknown"):
                        errs.append(f"NUL byte in text-extension file {rel} (undecodable without BOM): not skipped"); continue
                    continue                              # binary of another type
                else: text = decode(b)
            except Exception as e:
                if str(e) == "revert": continue
                errs.append(f"undecodable {rel}: {e}"); continue
            b2, a2 = scan_text(rel, text)
            bad += b2; allowed_all += a2
    scan.archives = archives
    if errs: return None, errs, []
    for a in anchors:
        ap = os.path.join(root, a)
        if not os.path.isfile(ap): return None, [f"UNKNOWN: anchor missing (partial tree?): {a}"], []
    if not rev("anchor") and seen and ANCHOR_ALLOWED not in allowed_all and anchors:
        return None, ["UNKNOWN: anchor file present but its allow-listed enabler was not parsed (parser blind?)"], []
    return seen, bad, allowed_all

def main(argv):
    root, anchors, i = REPO, [], 0
    if argv and not argv[0].startswith("--"): root, i = argv[0], 1
    while i < len(argv):
        if argv[i] == "--anchor" and i + 1 < len(argv): anchors.append(argv[i + 1]); i += 2
        else: print("UNKNOWN: bad arg", argv[i]); return 2
    if not anchors: anchors = DEFAULT_ANCHORS
    seen, bad, allowed = scan(root, anchors)
    print(COVERAGE)
    arch = getattr(scan, "archives", [])
    if not rev("archive_coverage"):
        print(f"COVERAGE archives: {len(arch)} packaged archive(s) in the tree, NOT opened (contents unseen): " + (", ".join(arch[:20]) if arch else "none"))
    if seen is None:
        print("UNKNOWN (exit 2):"); [print("  ", b) for b in bad[:10]]; return 2
    if seen == 0: print("UNKNOWN (exit 2): no files scanned"); return 2
    if bad:
        print(f"RED (exit 1) files={seen} findings={len(bad)}"); [print("  ", b) for b in bad[:25]]; return 1
    print(f"GREEN (exit 0, repo scope only; NOT 'no S-A') files={seen} allow-listed enablers={len(allowed)}")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
