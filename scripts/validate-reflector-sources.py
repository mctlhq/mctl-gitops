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

Enforcement: CI runs this in the `validate` job of validate-manifests.yml, which
is a required check, so a RED or UNKNOWN result BLOCKS merging a pull request.
It is not its own required check. Two structural limits:
  * It runs from the pull request's OWN head. A PR that edits this guard, its
    allow-list, its tests or the workflow step is checked by the edited guard;
    only the required human review stands in front of that (the main-protection
    ruleset has require_code_owner_review false).
  * It only gates what reaches a pull request. A push to main that skips PR
    checks (the gitops-bump DeployKey, a bypass actor of main-protection in
    `always` mode) is not gated; on push the same step runs after the fact and
    can only report.

How it reads: line by line (so .tf, scripts, templates and JSON patches are covered
too), after decoding \\xNN / \\uNNNN / \\UNNNNNNNN escapes in the line. A flag value
is "provably false" only when the literal value is false (case-insensitive,
quoted or not); anything else, a templated value included, is an enabler. A
value that is not in the same line is bound to the same YAML list item or
mapping block (never to a neighbouring operation); zero or several candidates
leave it unreadable, which is an enabler. The single allow-listed source is
decided from the PARSED document (PyYAML, duplicate keys refused): kind,
namespace and name must match, and every Reflector key in that document must
sit in its own metadata.annotations. Documents are split on `^---(\\s|$)`.
A document that mentions an allow-listed name but cannot be parsed, or has
duplicate keys, is UNKNOWN.

Archives (.tgz .tar.gz .tar .zip .jar .whl .gz) are opened in memory (never
extracted) with caps on depth, member count, member size and total size, and
their members are scanned with the same rules. Anything unopenable or over a cap
is UNKNOWN. A file holding NUL bytes or invalid UTF-8 is UNKNOWN unless it is a
recognised binary type (magic number or binary extension).

Symlinks: a directory symlink whose target is inside the root is listed in
COVERAGE and not followed (its target is scanned at the real path, so a link
loop cannot recurse). A symlink that points outside the root, or a dangling or
looping one, is UNKNOWN.

Test seam: the module-level REVERT set disables one rule at a time. Only the
tests set it (to prove each rule is load-bearing); there is deliberately no
environment variable or flag that can weaken the guard from outside.
"""
import gzip, io, os, re, sys, tarfile, zipfile
try:
    import yaml
except ImportError:                      # reported as UNKNOWN by main(), never as GREEN
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

ALLOW = {("ConfigMap", "argo-workflows", "mctl-platform-config"):
         "non-secret platform config, reflected to all namespaces by design"}   # (kind, namespace, name)
ANCHOR_ALLOWED = ("ConfigMap", "argo-workflows", "mctl-platform-config")
ALLOW_REFLECTS = {"argo-workflows/mctl-platform-config"}
DEFAULT_ANCHORS = ["platform-gitops/argo-workflows/config/mctl-platform-config.yaml"]
SKIP_DIRS = {".git"}            # node_modules is scanned on purpose (a vendored chart or script can carry an enabler)
YAML_EXT = (".yaml", ".yml", ".json")
ARCHIVE_TAR = (".tgz", ".tar.gz", ".tar")
ARCHIVE_ZIP = (".zip", ".jar", ".whl")
ARCHIVE_GZ = (".gz",)
BINARY_EXT = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf", ".pyc", ".woff", ".woff2", ".ttf", ".otf",
              ".eot", ".so", ".dylib", ".exe", ".class", ".wasm", ".mp3", ".mp4", ".mov", ".sqlite", ".db")
BINARY_MAGIC = (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\x89PNG\r\n\x1a\n",
                b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"%PDF-", b"wOFF", b"wOF2", b"\x00\x00\x01\x00", b"MZ")
MAX_DEPTH = 2                    # archive inside archive inside archive: deeper is UNKNOWN
MAX_MEMBERS = 20000
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_R = "reflection" + "-"      # spelled in pieces so this file never contains a literal key
FLAG_KEYS = {_R + "allowed", _R + "auto-enabled"}
NS_KEYS = {_R + "allowed-namespaces", _R + "auto-namespaces",
           _R + "allowed-namespaces-selector", _R + "auto-namespaces-selector"}
MIRROR_KEYS = {"reflects", "auto-reflects", "reflected-version", "reflected-at"}
KNOWN = FLAG_KEYS | NS_KEYS | MIRROR_KEYS
REVERT = set()      # test seam only, see module docstring

COVERAGE = """COVERAGE: D1 reads the text files of the scanned Git tree (all extensions, all kinds, tests/fixtures included) and the members of archives it can open.\n  Prose-only mentions in .md are not flagged unless they spell a full key with a value.
NOT SEEN by D1: .git internals; files of a recognised binary type; client-side applies (kubectl annotate/apply/patch run by a person or script), Secrets that never
  were in Git (the three S-A database/* sources), objects created by Terraform apply from outside this tree or from
  state only, charts rendered from remote repositories, values pulled at runtime (Vault, ExternalSecret remote data),
  generated indirection (range over annotation maps, printf-built keys, YAML anchors/merges or folded scalars that
  assemble a key across lines in a file that is not parseable YAML), Reflector's own Helm values.
D1 runs from the pull request's own head: a PR that edits this guard, its allow-list, its tests or the workflow step is checked by the edited guard.
D1 GREEN = "no Git-visible enabler". It is NEVER "no S-A". The live state is D2's job (metadata listing)."""

PFX = r'reflector\\?\.v1\\?\.k8s\\?\.emberstack\\?\.com'
OCC = re.compile(PFX + r'(?P<sep>/|~1|%2[Ff]|\\/)?(?P<suf>[A-Za-z][A-Za-z0-9-]*)')
PFX_ANY = re.compile(PFX)
TOKEN = re.compile(_R + r'(?:allowed|auto-enabled|allowed-namespaces|auto-namespaces)')
_V = r'''(?P<v>"(?:[^"\\]|\\.)*"|'[^']*'|[^\s,}\]#]*)'''
VAL = re.compile(r'''^(?:["'`])?\s*[:=]\s*''' + _V)
VALUE_KEY = re.compile(r'''^\s*(?:-\s+)?["']?value["']?\s*:\s*''' + _V)
VALUE_ANY = re.compile(r'''["']?\bvalue["']?\s*[:=]\s*''' + _V)
ESCAPE = re.compile(r'\\(?:x([0-9a-fA-F]{2})|u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8}))')
DOC_SPLIT = re.compile(r"^---(?:\s|$)")
MATCH_ALL = {"", ".*", ".+", ".*?", "[\\s\\S]*", "[^]*"}

def rev(name): return name in REVERT

def esc(s):
    """Printable form of a path or label: control characters and line separators escaped, so a hostile file
    name cannot start a workflow command (`::error::`) or forge a log line."""
    return "".join(c if (c.isprintable() and c not in "  ") else "\\u%04x" % ord(c) for c in str(s))

class Unreadable(Exception):
    pass

def decode(b):
    """BOM-aware, strict. Raises UnicodeError when the bytes cannot be decoded faithfully."""
    if b.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")): return b.decode("utf-32")
    if b.startswith((b"\xff\xfe", b"\xfe\xff")): return b.decode("utf-16")
    if b.startswith(b"\xef\xbb\xbf"): return b[3:].decode("utf-8")
    return b.decode("utf-8")

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

def normalise(line):
    """Decode the escapes a YAML/JSON/Go string may use to spell a key, so r\\x65flector matches like reflector."""
    if rev("escape_decode"): return line
    def one(m):
        h = m.group(1) or m.group(2) or m.group(3)
        try: return chr(int(h, 16))
        except (ValueError, OverflowError): return m.group(0)
    return ESCAPE.sub(one, line)

def _indent(l): return len(l) - len(l.lstrip(" "))

def block_values(dl, j):
    """Values of the `value` key that belongs to the same YAML list item / mapping block as line j.
    Never reaches into a neighbouring list item (the next JSON-patch operation)."""
    line = dl[j]
    dm = re.match(r"\s*-\s+", line)
    keyind = len(dm.group(0)) if dm else _indent(line)
    start = j
    if not dm:
        start = 0
        for i in range(j - 1, -1, -1):
            li = dl[i]
            if not li.strip(): continue
            if _indent(li) < keyind:
                start = i if li.lstrip().startswith("-") else i + 1
                break
    end = len(dl)
    for k in range(j + 1, len(dl)):
        lk = dl[k]
        if lk.strip() and _indent(lk) < keyind:
            end = k; break
    vals = []
    for k in range(start, end):
        lk = dl[k]
        vm = VALUE_KEY.match(lk)
        if not vm: continue
        dk = re.match(r"\s*-\s+", lk)
        kind_ind = len(dk.group(0)) if dk else _indent(lk)
        if kind_ind == keyind: vals.append(vm.group("v"))
    return vals

def find_value(dl, j, line_c, rest):
    """The value of the annotation key found on line j. None when absent or ambiguous."""
    vm = VAL.match(rest)
    if vm: return vm.group("v")
    same = [m.group("v") for m in VALUE_ANY.finditer(line_c)]
    if same: return same[0] if len(same) == 1 else None
    vals = block_values(dl, j)
    return vals[0] if len(vals) == 1 else None

class DupKeyLoader(yaml.SafeLoader if yaml else object):
    pass
if yaml:
    def _construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        seen = set()
        for knode, _v in node.value:
            k = self.construct_object(knode, deep=True)
            try: dup = k in seen
            except TypeError: raise yaml.constructor.ConstructorError(None, None, "unhashable key", knode.start_mark)
            if dup: raise yaml.constructor.ConstructorError(None, None, "duplicate key %r" % (k,), knode.start_mark)
            seen.add(k)
        return yaml.SafeLoader.construct_mapping(self, node, deep=deep)
    DupKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)

def identity(doc_text):
    """(kind, namespace, name) and whether every Reflector key sits in the object's own metadata.annotations.
    Raises Unreadable on a parse failure, several documents, a non-mapping root or duplicate keys."""
    try:
        objs = [o for o in yaml.load_all(doc_text, Loader=DupKeyLoader) if o is not None]
    except Exception as e:
        raise Unreadable(str(e).replace("\n", " ")[:120])
    if len(objs) != 1 or not isinstance(objs[0], dict):
        raise Unreadable("expected exactly one mapping document, got %d" % len(objs))
    o = objs[0]
    md = o.get("metadata") if isinstance(o.get("metadata"), dict) else {}
    s = lambda x: x if isinstance(x, str) else None
    ident = (s(o.get("kind")), s(md.get("namespace")), s(md.get("name")))
    hits = []
    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(k, str) and PFX_ANY.search(k): hits.append(path)
                walk(v, path + (k,))
        elif isinstance(x, list):
            for v in x: walk(v, path + ("[]",))
        elif isinstance(x, str) and PFX_ANY.search(x): hits.append(path + ("<value>",))
    walk(o, ())
    return ident, all(h == ("metadata", "annotations") for h in hits)

def scan_text(label, text, ext):
    """Returns (findings, allow-listed enabling docs [(kind, ns, name)], unreadable reasons)."""
    bad, allowed_seen, unreadable = [], [], []
    is_md = ext == ".md"
    lines = text.split("\n")
    docs, cur, start = [], [], 0
    for i, l in enumerate(lines):
        if DOC_SPLIT.match(l):
            docs.append((start, cur)); cur, start = [l[3:]], i
        else: cur.append(l)
    docs.append((start, cur))
    for start, dl in docs:
        occ = []   # (lineno, suf, raw or None, removal)
        for j, line in enumerate(dl):
            line_c = normalise(line.replace('\\"', '"'))
            if "reflect" not in line_c and "emberstack" not in line_c: continue
            ln = start + j + 1
            ms = list(OCC.finditer(line_c))
            if not rev("prefix_unrecognised_suffix"):
                covered = {m.start() for m in ms}
                for pm in PFX_ANY.finditer(line_c):
                    if pm.start() in covered: continue
                    tail = line_c[pm.end():pm.end() + 24]
                    if is_md and not re.match(r'^(?:/|~1|%2[Ff]|\\/)(?![A-Za-z])', tail):
                        continue            # prose naming the bare domain; a key-shaped templated tail is still flagged
                    bad.append(f"{label}:{ln}: Reflector annotation prefix followed by an unrecognised/templated suffix {tail!r} (key not statically readable)")
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
                    raw = find_value(dl, j, line_c, rest)
                occ.append((ln, suf, raw, removal))
            if not rev("unqualified") and not is_md:   # prose in .md may name the keys
                if len(TOKEN.findall(line_c)) > len(ms):
                    bad.append(f"{label}:{ln}: unqualified reflection-* token (key built indirectly?)")
        if not occ: continue
        dtext = "\n".join(dl)
        ident, allow = (None, None, None), False
        if ext in YAML_EXT and any(n in dtext for (_k, _ns, n) in ALLOW):
            try:
                ident, own_only = identity(dtext)
                allow = ident in ALLOW and own_only
            except Unreadable as e:
                unreadable.append(f"{label}: document near line {start + 1} names an allow-listed source but cannot be read as one YAML document ({e})")
        kind, ns, name = ident
        flags = {}
        en_lines = []
        for ln, suf, raw, removal in occ:
            if removal: continue
            if suf in FLAG_KEYS:
                if raw is None or enabling(raw):
                    en_lines.append((ln, suf, raw))
                else: flags[suf] = True
            elif suf not in KNOWN:
                bad.append(f"{label}:{ln}: unknown reflector.v1 annotation '{suf}' (not interpretable)")
        for ln, suf, raw in en_lines:
            if allow:
                allowed_seen.append(ident); continue
            why = "Secret must never be a reflector source; " if kind == "Secret" else ""
            bad.append(f"{label}:{ln}: {suf}={raw!r} not provably \"false\" in {kind}/{ns}/{name} "
                       f"(not allow-listed). {why}")
        both_false = all(flags.get(k) for k in FLAG_KEYS)
        if not rev("ns_matchall") and not allow and not both_false:
            for ln, suf, raw, removal in occ:
                if suf in NS_KEYS and not removal and (raw is None or match_all(raw)):
                    bad.append(f"{label}:{ln}: {suf}={raw!r} empty/match-all/unreadable and flags not provably false in {kind}/{name}")
        if not rev("reflects_marker"):
            for ln, suf, raw, removal in occ:
                if suf in MIRROR_KEYS and not removal:
                    src = unq(raw) if raw is not None else None
                    if suf == "reflects" and src in ALLOW_REFLECTS: continue
                    bad.append(f"{label}:{ln}: mirror marker {suf}={raw!r} committed in {kind}/{name} (mirror or pull-reflection from non-allow-listed source)")
    return bad, allowed_seen, unreadable

def inside(real_root, real_path):
    return real_path == real_root or real_path.startswith(real_root.rstrip(os.sep) + os.sep)

def is_known_binary(name, b):
    n = name
    if any(b.startswith(m) for m in BINARY_MAGIC): return True
    return n.endswith(BINARY_EXT)

class Ctx:
    def __init__(self):
        self.seen, self.bad, self.allowed, self.errs = 0, [], [], []
        self.archives, self.total = [], 0

def process(ctx, label, name, b, depth=0):
    """Scans one file (or archive member): bytes b under the display label and member/file name."""
    ln = name.lower()
    ctx.seen += 1
    if ln.endswith(ARCHIVE_TAR + ARCHIVE_ZIP + ARCHIVE_GZ) and not rev("open_archives"):
        return open_archive(ctx, label, ln, b, depth)
    try:
        if b[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff") or b[:2] in (b"\xff\xfe", b"\xfe\xff"):
            if rev("utf16_bom"): return
            text = decode(b)
        elif b"\0" in b:
            if is_known_binary(name, b): return          # a recognised binary type
            ctx.errs.append(f"NUL byte in {esc(label)} (not a recognised binary type, undecodable without BOM): not skipped"); return
        else:
            text = decode(b)
    except UnicodeError as e:
        if is_known_binary(name, b): return
        ctx.errs.append(f"undecodable {esc(label)}: {e}"); return
    b2, a2, u2 = scan_text(esc(label), text, os.path.splitext(ln)[1])
    ctx.bad += b2; ctx.allowed += a2; ctx.errs += u2

def open_archive(ctx, label, ln, b, depth):
    L = esc(label)
    if depth >= MAX_DEPTH:
        ctx.errs.append(f"archive {L} nested deeper than {MAX_DEPTH} levels: contents unseen"); return
    members = 0
    def take(mname, read):
        nonlocal members
        members += 1
        if members > MAX_MEMBERS:
            raise Unreadable(f"more than {MAX_MEMBERS} members")
        data = read(MAX_MEMBER_BYTES + 1)
        if len(data) > MAX_MEMBER_BYTES:
            raise Unreadable(f"member {esc(mname)} larger than {MAX_MEMBER_BYTES} bytes")
        ctx.total += len(data)
        if ctx.total > MAX_TOTAL_BYTES:
            raise Unreadable(f"more than {MAX_TOTAL_BYTES} bytes in total")
        process(ctx, f"{label}!{mname}", mname, data, depth + 1)
    try:
        if ln.endswith(ARCHIVE_TAR):
            with tarfile.open(fileobj=io.BytesIO(b), mode="r:*") as tf:
                for m in tf:
                    if not m.isreg(): continue
                    if m.size > MAX_MEMBER_BYTES and not rev("archive_caps"):
                        raise Unreadable(f"member {esc(m.name)} declares {m.size} bytes")
                    take(m.name, tf.extractfile(m).read)
        elif ln.endswith(ARCHIVE_ZIP):
            with zipfile.ZipFile(io.BytesIO(b)) as zf:
                for zi in zf.infolist():
                    if zi.is_dir(): continue
                    with zf.open(zi) as fh: take(zi.filename, fh.read)
        else:
            with gzip.GzipFile(fileobj=io.BytesIO(b)) as g:
                take(os.path.basename(label)[:-3] or "gunzipped", g.read)
    except Unreadable as e:
        ctx.errs.append(f"archive {L}: {e} (cap exceeded, contents not fully seen)"); return
    except Exception as e:                       # corrupt, encrypted, truncated, unsupported
        ctx.errs.append(f"archive {L} could not be opened: {type(e).__name__}: {str(e)[:100]}"); return
    ctx.archives.append(f"{L} ({members} members)")

def scan(root, anchors):
    """Returns (seen, bad, allowed, archives, dirlinks). seen is None when the tree could not be observed
    (bad then holds the UNKNOWN reasons). archives/dirlinks are returned on every path, early returns included."""
    if not os.path.isdir(root): return None, [f"UNKNOWN: root not a directory: {esc(root)}"], [], [], []
    ctx = Ctx()
    dirlinks = []
    real_root = os.path.realpath(root)
    def onerr(e):
        if not rev("walk_errors"): ctx.errs.append(f"walk error {esc(e.filename)}: {e.strerror}")
    for dp, dn, fn in os.walk(root, onerror=onerr):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
        if not rev("dir_symlinks"):
            # os.walk never descends into directory symlinks. One whose target is inside the root is scanned at
            # its real path (listed, not followed: so a loop cannot recurse); one that leaves the root hides
            # content from the scan, which is UNKNOWN, never "clean".
            for d in dn:
                lp = os.path.join(dp, d)
                if not os.path.islink(lp): continue
                rel = os.path.relpath(lp, root)
                real = os.path.realpath(lp)
                if inside(real_root, real): dirlinks.append(esc(rel))
                else: ctx.errs.append(f"directory symlink {esc(rel)} points outside the root (contents unseen)")
        for f in sorted(fn):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root)
            if os.path.islink(p) and not os.path.exists(p):
                ctx.errs.append(f"dangling symlink {esc(rel)}"); continue
            if not rev("dir_symlinks") and os.path.islink(p) and not inside(real_root, os.path.realpath(p)):
                ctx.errs.append(f"symlink {esc(rel)} points outside the root"); continue
            try:
                with open(p, "rb") as fh: b = fh.read()
            except Exception as e:
                ctx.errs.append(f"unreadable {esc(rel)}: {e}"); continue
            process(ctx, rel, f, b)
    if ctx.errs: return None, ctx.errs, [], ctx.archives, dirlinks
    for a in anchors:
        ap = os.path.join(root, a)
        if not os.path.isfile(ap) and not rev("anchor_file"): return None, [f"UNKNOWN: anchor missing (partial tree?): {esc(a)}"], [], ctx.archives, dirlinks
    if not rev("anchor") and ctx.seen and ANCHOR_ALLOWED not in ctx.allowed and anchors:
        return None, ["UNKNOWN: anchor file present but its allow-listed enabler was not parsed (parser blind?)"], [], ctx.archives, dirlinks
    return ctx.seen, ctx.bad, ctx.allowed, ctx.archives, dirlinks

def main(argv):
    if yaml is None:
        print("UNKNOWN (exit 2): PyYAML is not installed; the allow-list cannot be decided"); return 2
    root, anchors, i = REPO, [], 0
    if argv and not argv[0].startswith("--"): root, i = argv[0], 1
    while i < len(argv):
        if argv[i] == "--anchor" and i + 1 < len(argv): anchors.append(argv[i + 1]); i += 2
        else: print("UNKNOWN: bad arg", esc(argv[i])); return 2
    if not anchors: anchors = DEFAULT_ANCHORS
    seen, bad, allowed, arch, links = scan(root, anchors)
    print(COVERAGE)
    if not rev("archive_coverage"):
        print(f"COVERAGE archives opened in memory and scanned: {len(arch)}" + (": " + ", ".join(arch[:20]) if arch else ": none"))
    if not rev("dir_symlinks"):
        print(f"COVERAGE directory symlinks: {len(links)} with a target inside the root (not followed; the target is scanned at its real path): " + (", ".join(links[:20]) if links else "none"))
    if seen is None:
        print("UNKNOWN (exit 2):"); [print("  ", b) for b in bad[:10]]; return 2
    if seen == 0: print("UNKNOWN (exit 2): no files scanned"); return 2
    if bad:
        print(f"RED (exit 1) files={seen} findings={len(bad)}"); [print("  ", b) for b in bad[:25]]; return 1
    print(f"GREEN (exit 0, repo scope only; NOT 'no S-A') files={seen} allow-listed enablers={len(allowed)}")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
