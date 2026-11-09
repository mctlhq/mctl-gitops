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

How it reads, in two layers whose findings are added together:
  1. A line scan of every text file (so .tf, scripts, templates and JSON patches are covered too), after decoding
     \\xNN / \\uNNNN / \\UNNNNNNNN escapes. A flag value is "provably false" only when the literal value is false
     (case-insensitive, quoted or not); anything else, a templated value included, is an enabler. In YAML/JSON files a
     trailing comment is cut off before a value is read.
  2. For every .yaml/.yml/.json document that can spell a Reflector key (the word `emberstack` survives escape and
     line-join decoding, or the document spells a YAML tag: `!!x`, `!<...>`, `!h!x`, `%TAG`, any of which may resolve to
     !!binary and so hide the key in base64; the same applies to a string value that spells tags, and to a file of any
     other extension that parses as YAML), a parse with PyYAML's composer (no object construction, so alias bombs stay linear). The
     RESOLVED keys are read: aliases, merge keys, explicit `? key` entries, multi-line and escaped scalars, and the
     path/value of each JSON-patch operation (also inside a string value such as a kustomize `patch:`). A key defined
     twice in one mapping (duplicate, merge conflict) is UNKNOWN, never read as the first or the last one. A document
     over MAX_DOC_BYTES, more than MAX_NODES nodes or deeper than MAX_YAML_DEPTH is UNKNOWN.
  A document that mentions a key but does not parse (a Helm template) is read by the line scan only, plus a syntax
  tripwire: an anchor, alias, merge key, explicit key or a trailing backslash in it is UNKNOWN.
The single allow-listed source is decided from the parsed document: kind, namespace and name must match, and every
Reflector key in it must sit in its own metadata.annotations, spelled directly (no alias, no multi-line or folded
key). Documents are split on `^---(\\s|$)`. A document that names an allow-listed source but cannot be read as one
YAML document is UNKNOWN.

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
import base64, binascii, gzip, io, os, re, sys, tarfile, zipfile
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
MAX_DOC_BYTES = 1024 * 1024      # a YAML document that mentions a Reflector key is parsed; a larger one is UNKNOWN
MAX_NODES = 100000               # nodes visited per document (alias bombs share nodes, the walk visits each container once)
MAX_YAML_DEPTH = 100
MAX_LINE_BYTES = 64 * 1024       # a line that mentions a key is read only up to this length; a longer one is UNKNOWN
MAX_LINE_KEYS = 200              # ... and only with this many key mentions on it (value lookup is per mention)
MAX_KEY_LINES = 200               # lines mentioning a key per document (each costs a scan of its block)
MAX_DOC_LINES = 20000            # lines of a document that mentions a key (block-scoped value lookup is per mention)
MAX_FINDINGS_PER_FILE = 1000     # more findings than this in one file: UNKNOWN (the file is plainly hostile or generated)
_R = "reflection" + "-"      # spelled in pieces so this file never contains a literal key
FLAG_KEYS = {_R + "allowed", _R + "auto-enabled"}
NS_KEYS = {_R + "allowed-namespaces", _R + "auto-namespaces",
           _R + "allowed-namespaces-selector", _R + "auto-namespaces-selector"}
MIRROR_KEYS = {"reflects", "auto-reflects", "reflected-version", "reflected-at"}
KNOWN = FLAG_KEYS | NS_KEYS | MIRROR_KEYS
REVERT = set()      # test seam only, see module docstring

COVERAGE = """COVERAGE: D1 reads the text files of the scanned Git tree (all extensions and kinds, tests/fixtures included)
  and the members of archives it can open.
  Prose-only mentions in .md are not flagged unless they spell a full key with a value.
  In .yaml/.yml/.json documents that parse, the RESOLVED keys are read: aliases, merge keys, explicit keys, multi-line and
  escaped scalars, JSON-patch path/value (also inside kustomize patch strings); duplicate keys, merge conflicts, oversized
  or too deeply nested documents are UNKNOWN.
NOT SEEN by D1: .git internals; files of a recognised binary type; client-side applies (kubectl annotate/apply/patch run by
  a person or script), Secrets that never were in Git (the three S-A database/* sources), objects created by Terraform apply
  from outside this tree or from state only, charts rendered from remote repositories, values pulled at runtime (Vault,
  ExternalSecret remote data), Reflector's own Helm values, generated indirection (range over annotation maps, printf-built
  keys, keys assembled by a template engine or a script at run time), and, in a document that does NOT parse as YAML (Helm
  templates) or in a file that is not .yaml/.yml/.json, anchors, merge keys, explicit keys and folded or multi-line scalars:
  there only the line scan and a syntax tripwire run (the tripwire makes a document that mentions a key and uses such syntax
  UNKNOWN, but a script or .tf that assembles a key across lines is not seen).
D1 runs from the pull request's own head: a PR that edits this guard, its allow-list, its tests or the workflow step is
  checked by the edited guard.
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
PROBES = ("a", "default", "database", "kube-system", "x1-y2", "0", "zzzzzzzzzz")   # realistic namespace names
BROAD = 5                        # a regex that fully matches at least this many probes is treated as match-all

def rev(name): return name in REVERT

def esc(s):
    """Printable form of a path or label: control characters and line separators escaped, so a hostile file
    name cannot start a workflow command (`::error::`) or forge a log line."""
    return "".join(c if (c.isprintable() and c not in "\u2028\u2029") else "\\u%04x" % ord(c) for c in str(s))

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

def broad_regex(raw):
    """True when a namespace-list entry would match (nearly) every namespace, or cannot be read as a regex."""
    whole = unq(raw)
    for el in [whole] + whole.split(","):       # the whole value too: a quantifier such as {0,} holds a comma
        e = el.strip().lstrip("^").rstrip("$").strip()
        while e.startswith("(") and e.endswith(")"): e = e[1:-1].strip()
        if e in MATCH_ALL: return True
        for cand in (el.strip(), e):
            if len(cand) > 200: return True               # not worth interpreting: refuse
            try:
                rx = re.compile(cand)
            except (re.error, RecursionError, OverflowError):
                return True                               # unreadable regex is never "narrow"
            if sum(1 for p in PROBES if rx.fullmatch(p)) >= BROAD: return True
    return False

def match_all(raw):
    return broad_regex(raw)

_JOIN = re.compile(r"\\\r?\n[ \t]*")

# A `!!binary` scalar spells its text in base64, so a key can be hidden from every textual check.
BINARY_TAG = re.compile(r"!!binary|yaml\.org,2002:binary", re.I)
# Any way a tag can be written: `!!x` (also percent-escaped, `!!bin%61ry`), a verbatim `!<...>`, a named handle `!e!x`,
# or a `%TAG` directive that redefines a handle. A scalar tagged !!binary spells its text in base64, and PyYAML resolves
# all of these spellings to the same tag, so the text `emberstack` need not appear anywhere in the file.
TAGHINT = re.compile(r"%TAG|!!|!<|![\w-]*![\w%]")

_B64RUN = re.compile(r"[A-Za-z0-9+/]{16,}")

def b64_hides_key(text):
    """Whether any base64 run in text (whitespace removed, any of the four alignments) decodes to something that
    contains the word `emberstack`. Used for text the YAML parser cannot read, where a tag cannot be resolved but a
    base64 key can still be recognised."""
    flat = re.sub(r"\s+", "", text)
    for m in _B64RUN.finditer(flat):
        run = m.group(0)
        for o in range(4):
            part = run[o:]; part = part[:len(part) // 4 * 4]
            if not part: continue
            try:
                if "emberstack" in base64.b64decode(part).decode("latin-1").lower(): return True
            except (binascii.Error, ValueError):
                continue
    return False

def mentions(dtext):
    """Whether a document can spell a Reflector key at all. Every key contains the whole word `emberstack` once the
    transformations a YAML scalar may apply (escapes, `\\`-newline joins) are undone; case-insensitive on purpose.
    A miss here would skip the structural parse."""
    t = normalise(_JOIN.sub("", dtext)).lower()
    return "emberstack" in t

def strip_comment(line):
    """Drops a YAML comment (a `#` at the start or after whitespace, outside quotes) from one line."""
    q = None
    i = 0
    while i < len(line):
        c = line[i]
        if q == '"':
            if c == "\\": i += 2; continue
            if c == '"': q = None
        elif q == "'":
            if c == "'": q = None
        elif c in "\"'" and (i == 0 or line[i - 1] in " \t[{,:-"): q = c
        elif c == "#" and (i == 0 or line[i - 1] in " \t"): return line[:i]
        i += 1
    return line

TRICKS = [re.compile(p) for p in (r"(?m)(?:^|[\s\[{,:-])&[\w-]", r"(?m)(?:^|[\s\[{,:-])\*[\w-]", r"<<\s*:",
                                  r"(?m)^\s*\?(?:\s|$)", r"(?m)\\[ \t]*$",
                                  r"!!binary|yaml\.org,2002:binary", r"(?m)(?:^|[\s\[{,:-])![A-Za-z<]")]

def has_tricks(dtext):
    t = "\n".join(strip_comment(l) for l in dtext.split("\n"))      # a comment may say anything
    return not rev("tricks") and any(p.search(t) for p in TRICKS)

SCALAR, MAPPING, SEQUENCE = (yaml.ScalarNode, yaml.MappingNode, yaml.SequenceNode) if yaml else (None, None, None)
MERGE_TAG = "tag:yaml.org,2002:merge"

def structural(dtext, start, level=0, strict=False, textual=True):
    """Parses one document part with PyYAML's composer (no object construction, so an alias bomb stays linear) and
    walks the RESOLVED keys and values. Returns None when the text is not parseable YAML, otherwise
    (occurrences, reasons, roots, own_only). Occurrences are (line, suffix, raw value or None, False) like the line scan's.
    `reasons` are UNKNOWN reasons: duplicate keys, merge conflicts, caps, keys the walk cannot interpret."""
    try:
        roots = [n for n in yaml.compose_all(dtext, Loader=yaml.SafeLoader) if n is not None]
    except Exception:
        return None
    occ, reasons, hits = [], [], []
    binary_ids = set()           # scalars written as !!binary: .value now holds the DECODED text
    # Tags that change what a scalar resolves to. !!binary is decoded; the other tag:yaml.org,2002:* tags keep the
    # text (judged as written: a value that is not provably "false" is RED anyway); any other tag (custom, local)
    # may be rewritten by a constructor we cannot see, so it is UNKNOWN.
    stack, vis = list(roots), set()
    tag_reasons, binary_hit, tag_strs = [], False, []
    while stack:
        n = stack.pop()
        if id(n) in vis: continue
        vis.add(id(n))
        if len(vis) > MAX_NODES: tag_reasons.append(f"more than {MAX_NODES} YAML nodes"); break
        tag = n.tag or ""
        if tag == "tag:yaml.org,2002:binary" and isinstance(n, SCALAR):
            try:
                n.value = base64.b64decode("".join(n.value.split()), validate=True).decode("utf-8", "replace")
                binary_ids.add(id(n))
                if "emberstack" in normalise(n.value).lower(): binary_hit = True
            except (binascii.Error, ValueError):
                tag_reasons.append(f"line {start + n.start_mark.line + 1}: !!binary scalar that is not valid base64: cannot be read")
        elif not tag.startswith("tag:yaml.org,2002:") and not rev("tags"):
            tag_reasons.append(f"line {start + n.start_mark.line + 1}: non-standard YAML tag {esc(tag)[:40]!r}: "
                               "the resolved value cannot be known")
        if isinstance(n, SCALAR) and tag == "tag:yaml.org,2002:str" and TAGHINT.search(n.value):
            t_ = n.value.strip()
            if "\n" in t_ or t_[:1] in "[{" or t_.startswith("- "): tag_strs.append(n)     # a YAML/JSON string that spells tags
        if isinstance(n, MAPPING): stack.extend(x for kv in n.value for x in kv)
        elif isinstance(n, SEQUENCE): stack.extend(n.value)

    def read_tag_strings(known_hidden):
        """Reads every string value that spells YAML tags one level down: its text may resolve to a key although the
        outer string never contains the word `emberstack` (a kustomize patch whose path is !!binary)."""
        o, r = [], []
        for n in tag_strs:
            if level >= 3:
                r.append(f"line {start + n.start_mark.line + 1}: tagged YAML text inside strings nested more than 3 levels deep"); continue
            sub = structural(n.value, start + n.start_mark.line + (0 if n.style in ("|", ">") else -1) + 1, level + 1,
                             textual=mentions(n.value)) if len(n.value) <= MAX_DOC_BYTES else None
            if sub is None:
                if b64_hides_key(n.value):
                    r.append(f"line {start + n.start_mark.line + 1}: a string value spells YAML tags, holds base64 of the Reflector key "
                             "and is not YAML the guard can read")
            else:
                o += sub[0]; r += sub[1]
        return o, r
    if not textual and not binary_hit and not rev("tag_gate"):
        # nothing here spells the key and no binary scalar decodes to it: the tag findings above are not about this guard
        o, r = read_tag_strings(False)
        return o, r, roots, False
    reasons += tag_reasons
    seen = {}                    # id(container node) -> subtree hit count, so an alias bomb is walked once
    scal = set()                 # id of scalar nodes already used once: a second use is an alias
    consumed = set()             # scalar nodes read as a key or an operation path
    val_hits = []                # (scalar node, hidden) for string values that carry key text
    nodes = [0]
    state = {"reuse": False, "hidden": False}

    def ln_of(n): return start + n.start_mark.line + 1

    def literal(n):
        """True when the scalar's own source text, as the line scan reads it, spells the same key text."""
        src = dtext[n.start_mark.index:n.end_mark.index]
        if "\n" in src and n.style != "|": return False
        return len(PFX_ANY.findall(normalise(src.replace('\\"', '"')))) == len(PFX_ANY.findall(n.value))

    def pairs(m, depth):
        """The mapping's resolved (key node, value node) pairs; merge keys flattened. Duplicates are reasons."""
        explicit, merged = [], []
        for kn, vn in m.value:
            if isinstance(kn, SCALAR) and kn.tag == MERGE_TAG:
                srcs = vn.value if isinstance(vn, SEQUENCE) else [vn]
                for sm in srcs:
                    if not isinstance(sm, MAPPING):
                        reasons.append(f"line {ln_of(kn)}: merge key `<<` with a value that is not a mapping"); continue
                    merged.extend(pairs(sm, depth + 1))
            else:
                explicit.append((kn, vn))
        out, keys = [], {}
        for kn, vn in explicit + merged:
            if not isinstance(kn, SCALAR) and strict:
                reasons.append(f"line {ln_of(kn)}: mapping key that is not a scalar "
                               "(a templated placeholder?): not interpretable")
            kid = ("s", kn.value) if isinstance(kn, SCALAR) else ("c", id(kn))
            if kid in keys:
                shown = esc(kn.value) if isinstance(kn, SCALAR) else "<complex>"
                reasons.append(f"line {ln_of(kn)}: key {shown!r} defined more than once in one mapping "
                               "(duplicate or merge conflict: parsers disagree on which wins)")
                continue
            keys[kid] = (kn, vn)
            out.append((kn, vn))
        return out

    def judge_pair(kn, vn):
        if not isinstance(kn, SCALAR): return
        hits_in_key = len(PFX_ANY.findall(kn.value))
        if not hits_in_key: return
        consumed.add(id(kn))
        if literal(kn) and id(kn) not in scal and not rev("hidden_keys_all"):
            return                      # the line scan reads this key exactly as written; do not count it twice
        state["hidden"] = True
        m = OCC.search(kn.value)
        if hits_in_key != 1 or not m or m.end() != len(kn.value) or kn.value[:m.start()]:
            occ.append((ln_of(kn), "<unparsed key " + esc(kn.value)[:60] + ">", None, False)); return
        raw = vn.value if isinstance(vn, SCALAR) and id(vn) not in binary_ids else None
        occ.append((ln_of(kn), m.group("suf"), raw, False))

    def judge_op(items):
        d = {kn.value: vn for kn, vn in items if isinstance(kn, SCALAR)}
        pn = d.get("path")
        if not isinstance(pn, SCALAR) or not PFX_ANY.search(pn.value): return
        consumed.add(id(pn))
        if id(pn) in scal: state["hidden"] = True
        ms = list(OCC.finditer(pn.value))
        vn = d.get("value")
        raw = vn.value if isinstance(vn, SCALAR) and id(vn) not in binary_ids else None
        if len(PFX_ANY.findall(pn.value)) != len(ms):
            occ.append((ln_of(pn), "<unparsed path " + esc(pn.value)[:60] + ">", None, False)); return
        for m in ms: occ.append((ln_of(pn), m.group("suf"), raw, False))

    def walk(n, path, depth):
        nodes[0] += 1
        if nodes[0] > MAX_NODES: raise Unreadable(f"more than {MAX_NODES} YAML nodes")
        if depth > MAX_YAML_DEPTH: raise Unreadable(f"YAML nested deeper than {MAX_YAML_DEPTH}")
        if isinstance(n, SCALAR):
            c = len(PFX_ANY.findall(n.value))
            if c:
                hits.append(path + ("<value>",))
                val_hits.append((n, id(n) in scal or not literal(n)))
            scal.add(id(n))
            return c
        if id(n) in seen:
            if seen[id(n)]: state["reuse"] = True
            return seen[id(n)]
        seen[id(n)] = 0
        total = 0
        if isinstance(n, MAPPING):
            ps = pairs(n, depth)
            for kn, vn in ps:
                if isinstance(kn, SCALAR):
                    if PFX_ANY.search(kn.value):
                        hits.append(path)
                        judge_pair(kn, vn)
                        total += 1
                    kp = path + (kn.value,)
                    scal.add(id(kn))
                else:
                    total += walk(kn, path + ("<complex-key>",), depth + 1)
                    kp = path + ("<complex-key>",)
                total += walk(vn, kp, depth + 1)
            judge_op(ps)
        else:
            for v in n.value: total += walk(v, path + ("[]",), depth + 1)
        seen[id(n)] = total
        return total

    try:
        for r in roots: walk(r, (), 0)
    except Unreadable as e:
        reasons.append(str(e))
    except RecursionError:
        reasons.append("YAML nested too deeply to walk")
    sub_own = True
    for n, hid in val_hits:
        if id(n) in consumed: continue
        t = n.value.strip()
        if not (hid or "\n" in t or t[:1] in "[{" or t.startswith("- ")): continue
        # a string value that itself holds YAML/JSON (a kustomize `patch:` string, a JSON patch in a ConfigMap):
        # read it with the same rules, one level down
        if level >= 3:
            reasons.append(f"line {ln_of(n)}: Reflector key text inside strings nested more than 3 levels deep"); continue
        base = ln_of(n) if n.style in ("|", ">") else ln_of(n) - 1     # block scalars start on the line AFTER their header
        sub = structural(n.value, base, level + 1) if len(n.value) <= MAX_DOC_BYTES else None
        if sub is None or all(isinstance(r, SCALAR) for r in sub[2]):
            if hid:
                reasons.append(f"line {ln_of(n)}: Reflector key text reaches a value by alias, escape or folded scalar "
                               "and the value is not YAML or JSON the guard can read")
            continue
        occ += sub[0]; reasons += sub[1]; sub_own = False
    if tag_strs:
        o, r = read_tag_strings(True)
        occ += o; reasons += r
        if o or r: sub_own = False
    if not sub_own: state["hidden"] = True
    own_only = all(h == ("metadata", "annotations") for h in hits) and not state["reuse"] and not state["hidden"]
    return occ, reasons, roots, own_only

def root_identity(roots):
    """(kind, namespace, name) of the single mapping root, or raises Unreadable."""
    if len(roots) != 1 or not isinstance(roots[0], MAPPING):
        raise Unreadable("expected exactly one mapping document, got %d" % len(roots))
    def get(m, k):
        for kn, vn in m.value:
            if isinstance(kn, SCALAR) and kn.value == k: return vn
        return None
    s = lambda n: n.value if isinstance(n, SCALAR) else None
    md = get(roots[0], "metadata")
    md = md if isinstance(md, MAPPING) else None
    return (s(get(roots[0], "kind")), s(get(md, "namespace")) if md else None, s(get(md, "name")) if md else None)

def line_occurrences(dl, start, ext, label, is_md, bad, unk):
    occ = []   # (lineno, suf, raw or None, removal)
    yaml_ext = ext in YAML_EXT
    dln = [normalise(l) for l in dl]
    if not rev("line_cap"):
        mentioning = sum(1 for l in dl if "emberstack" in l.lower() or "reflect" in l)
        if mentioning > MAX_KEY_LINES or (mentioning and len(dl) > MAX_DOC_LINES):
            unk.append(f"{label}:{start + 1}: document mentions a Reflector key on more than {MAX_KEY_LINES} lines or has more "
                       f"than {MAX_DOC_LINES} lines: not read")
            return occ
    for j, line in enumerate(dl):
        line_c = normalise(line.replace('\\"', '"'))
        if "reflect" not in line_c and "emberstack" not in line_c: continue
        ln = start + j + 1
        if not rev("line_cap") and (len(line_c) > MAX_LINE_BYTES or line_c.count("emberstack") > MAX_LINE_KEYS):
            unk.append(f"{label}:{ln}: a line that mentions a Reflector key is longer than {MAX_LINE_BYTES} bytes or "
                       f"repeats it more than {MAX_LINE_KEYS} times: not read")
            continue
        line_v = strip_comment(line_c) if yaml_ext and not rev("comments") else line_c
        ms = list(OCC.finditer(line_c))
        if not rev("prefix_unrecognised_suffix"):
            covered = {m.start() for m in ms}
            for pm in PFX_ANY.finditer(line_c):
                if pm.start() in covered: continue
                tail = line_c[pm.end():pm.end() + 24]
                if is_md and not re.match(r'^(?:/|~1|%2[Ff]|\\/)(?![A-Za-z])', tail):
                    continue            # prose naming the bare domain; a key-shaped templated tail is still flagged
                bad.append(f"{label}:{ln}: Reflector annotation prefix followed by an unrecognised/templated suffix "
                           f"{tail!r} (key not statically readable)")
        for k, m in enumerate(ms):
            suf = m.group("suf")
            end = ms[k + 1].start() if k + 1 < len(ms) else len(line_c)
            rest = line_v[m.end():end]
            removal = False
            if suf.endswith("-") and suf.rstrip("-") in KNOWN:   # kubectl annotate key-  (removal)
                suf, removal = suf.rstrip("-"), True
            if rev("formats") and not re.match(r'^\s*' + PFX, line_c):
                continue                    # old behaviour: only "key: value" yaml lines
            raw = None
            if not removal:
                raw = find_value(dln, j, line_v, rest)
            occ.append((ln, suf, raw, removal))
        if not rev("unqualified") and not is_md:   # prose in .md may name the keys
            if len(TOKEN.findall(line_c)) > len(ms):
                bad.append(f"{label}:{ln}: unqualified reflection-* token (key built indirectly?)")
    return occ

def scan_text(label, text, ext):
    """Returns (findings, allow-listed enabling docs [(kind, ns, name)], unreadable reasons, notes)."""
    bad, allowed_seen, unreadable, notes = [], [], [], []
    is_md = ext == ".md"
    lines = text.split("\n")
    docs, cur, start = [], [], 0
    for i, l in enumerate(lines):
        if DOC_SPLIT.match(l):
            docs.append((start, cur)); cur, start = [l[3:]], i
        else: cur.append(l)
    docs.append((start, cur))
    for di, (start, dl) in enumerate(docs):
        occ = line_occurrences(dl, start, ext, label, is_md, bad, unreadable)
        dtext = "\n".join(dl)
        if di > 0 and not is_md:
            # `%TAG` / `%YAML` directives sit BEFORE the `---` that starts the document they govern, so the split above
            # left them at the tail of the previous part. Carry them over, or `!binary` under a redefined handle is
            # read as an unknown local tag (the line numbers of such a document shift by the directive lines).
            tail = []
            for l in reversed(docs[di - 1][1]):
                if l.startswith("%"): tail.append(l)
                elif l.strip() and not l.lstrip().startswith("#"): break
            if tail: dtext = "\n".join(reversed(tail)) + "\n---\n" + dtext
        ident, allow = (None, None, None), False
        names = any(n in dtext for (_k, _ns, n) in ALLOW)
        textual = mentions(dtext)
        tg = bool(TAGHINT.search(dtext)) and not is_md and not rev("tag_gate")
        if (ext in YAML_EXT and (occ or textual or tg)) or (tg and ext not in YAML_EXT):
            if len(dtext) > MAX_DOC_BYTES and not rev("doc_cap"):
                unreadable.append(f"{label}: document near line {start + 1} mentions a Reflector key and is larger than "
                                  f"{MAX_DOC_BYTES} bytes: not parsed")
            else:
                sres = None if rev("structural") else structural(dtext, start, strict=bool(occ and names), textual=textual)
                if sres is None:
                    if ext in YAML_EXT and (textual or (tg and b64_hides_key(dtext))):
                        notes.append(f"{label}:{start + 1}")
                        if has_tricks(dtext) or not textual:
                            unreadable.append(f"{label}: document near line {start + 1} mentions a Reflector key, is not "
                                              "parseable YAML and uses anchors, aliases, merge or explicit keys, or a "
                                              "trailing backslash: cannot be read")
                    if occ and names:
                        unreadable.append(f"{label}: document near line {start + 1} names an allow-listed source but "
                                          "cannot be read as one YAML document (parse error)")
                else:
                    s_occ, reasons, roots, own_only = sres
                    unreadable += [f"{label}: {r}" for r in reasons]
                    occ = occ + s_occ
                    if occ and names:
                        try:
                            ident = root_identity(roots)
                            allow = ident in ALLOW and own_only and not reasons
                        except Unreadable as e:
                            unreadable.append(f"{label}: document near line {start + 1} names an allow-listed source but "
                                              f"cannot be read as one YAML document ({e})")
        if not occ: continue
        kind, ns, name = ident
        judge(label, occ, ident, allow, bad, allowed_seen)
    if len(unreadable) > 100 and not rev("finding_cap"):
        unreadable[100:] = [f"{label}: {len(unreadable) - 100} further reasons not listed"]
    if len(bad) > MAX_FINDINGS_PER_FILE and not rev("finding_cap"):
        unreadable.append(f"{label}: more than {MAX_FINDINGS_PER_FILE} findings in one file: not listed, not read further")
        del bad[MAX_FINDINGS_PER_FILE:]
    return bad, allowed_seen, unreadable, notes

def judge(label, occ, ident, allow, bad, allowed_seen):
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
                bad.append(f"{label}:{ln}: {suf}={raw!r} empty/match-all/unreadable and flags not provably false "
                           f"in {kind}/{name}")
    if not rev("reflects_marker"):
        for ln, suf, raw, removal in occ:
            if suf in MIRROR_KEYS and not removal:
                src = unq(raw) if raw is not None else None
                if suf == "reflects" and src in ALLOW_REFLECTS: continue
                bad.append(f"{label}:{ln}: mirror marker {suf}={raw!r} committed in {kind}/{name} "
                           "(mirror or pull-reflection from non-allow-listed source)")

def inside(real_root, real_path):
    return real_path == real_root or real_path.startswith(real_root.rstrip(os.sep) + os.sep)

def is_known_binary(name, b):
    n = name
    if n.lower().endswith(YAML_EXT) and not rev("yaml_never_binary"): return False    # named as text: a magic number does not make it a picture
    if any(b.startswith(m) for m in BINARY_MAGIC): return True
    return n.endswith(BINARY_EXT)

class Ctx:
    def __init__(self):
        self.seen, self.bad, self.allowed, self.errs = 0, [], [], []
        self.archives, self.total, self.notes = [], 0, []

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
            ctx.errs.append(f"NUL byte in {esc(label)} (not a recognised binary type, undecodable without BOM): "
                            "not skipped"); return
        else:
            text = decode(b)
    except UnicodeError as e:
        if is_known_binary(name, b): return
        ctx.errs.append(f"undecodable {esc(label)}: {e}"); return
    b2, a2, u2, n2 = scan_text(esc(label), text, os.path.splitext(ln)[1])
    ctx.bad += b2; ctx.allowed += a2; ctx.errs += u2; ctx.notes += n2

def zip_entry_cap(b):
    """Refuses a zip whose end-of-central-directory record announces more than MAX_MEMBERS entries, BEFORE
    zipfile reads (and allocates) the whole central directory."""
    if rev("archive_caps"): return
    i = b.rfind(b"PK\x05\x06", max(0, len(b) - 65557))
    if i < 0 or len(b) < i + 22: return              # no EOCD: zipfile reports it as corrupt (UNKNOWN)
    total = int.from_bytes(b[i + 10:i + 12], "little")
    if total == 0xFFFF or total > MAX_MEMBERS:       # 0xFFFF: zip64 or at least that many
        raise Unreadable(f"zip central directory announces {total if total != 0xFFFF else 'zip64 / 65535 or more'} entries")

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
                listed = 0
                for m in tf:
                    listed += 1
                    if listed > MAX_MEMBERS and not rev("archive_caps"):
                        raise Unreadable(f"more than {MAX_MEMBERS} entries")
                    if not m.isreg(): continue
                    if m.size > MAX_MEMBER_BYTES and not rev("archive_caps"):
                        raise Unreadable(f"member {esc(m.name)} declares {m.size} bytes")
                    take(m.name, tf.extractfile(m).read)
        elif ln.endswith(ARCHIVE_ZIP):
            zip_entry_cap(b)
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
    """Returns (seen, bad, allowed, archives, dirlinks, notes). seen is None when the tree could not be observed
    (bad then holds the UNKNOWN reasons). archives/dirlinks are returned on every path, early returns included."""
    if not os.path.isdir(root): return None, [f"UNKNOWN: root not a directory: {esc(root)}"], [], [], [], []
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
    if ctx.errs: return None, ctx.errs, [], ctx.archives, dirlinks, ctx.notes
    for a in anchors:
        ap = os.path.join(root, a)
        if not os.path.isfile(ap) and not rev("anchor_file"):
            return None, [f"UNKNOWN: anchor missing (partial tree?): {esc(a)}"], [], ctx.archives, dirlinks, ctx.notes
    if not rev("anchor") and ctx.seen and ANCHOR_ALLOWED not in ctx.allowed and anchors:
        return (None, ["UNKNOWN: anchor file present but its allow-listed enabler was not parsed (parser blind?)"], [],
                ctx.archives, dirlinks, ctx.notes)
    return ctx.seen, ctx.bad, ctx.allowed, ctx.archives, dirlinks, ctx.notes

def main(argv):
    if yaml is None:
        print("UNKNOWN (exit 2): PyYAML is not installed; the allow-list cannot be decided"); return 2
    root, anchors, i = REPO, [], 0
    if argv and not argv[0].startswith("--"): root, i = argv[0], 1
    while i < len(argv):
        if argv[i] == "--anchor" and i + 1 < len(argv): anchors.append(argv[i + 1]); i += 2
        else: print("UNKNOWN: bad arg", esc(argv[i])); return 2
    if not anchors: anchors = DEFAULT_ANCHORS
    seen, bad, allowed, arch, links, notes = scan(root, anchors)
    print(COVERAGE)
    if not rev("archive_coverage"):
        print(f"COVERAGE archives opened in memory and scanned: {len(arch)}"
              + (": " + ", ".join(arch[:20]) if arch else ": none"))
    if not rev("dir_symlinks"):
        print(f"COVERAGE directory symlinks: {len(links)} with a target inside the root (not followed; the target is "
              "scanned at its real path): " + (", ".join(links[:20]) if links else "none"))
    print(f"COVERAGE documents that mention a key but do not parse as YAML (line scan + syntax tripwire only): {len(notes)}"
          + (": " + ", ".join(notes[:10]) if notes else ""))
    if seen is None:
        print("UNKNOWN (exit 2):"); [print("  ", b) for b in bad[:10]]; return 2
    if seen == 0: print("UNKNOWN (exit 2): no files scanned"); return 2
    if bad:
        print(f"RED (exit 1) files={seen} findings={len(bad)}"); [print("  ", b) for b in bad[:25]]; return 1
    print(f"GREEN (exit 0, repo scope only; NOT 'no S-A') files={seen} allow-listed enablers={len(allowed)}")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
