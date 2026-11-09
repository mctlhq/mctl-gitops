#!/usr/bin/env python3
"""Structural source pin for platform-gitops/bootstrap (#1033, B4).

This is NOT a semantic check. It does not render the chart and says nothing
about what the generated ApplicationSet, AppProject or Application objects
contain; those are covered by the rendered-output checks. It only answers one
question: did any file that can influence that generation change, appear or
disappear without tests/fixtures/bootstrap-source-pin.json being updated in
the same change?

WHAT CONTROL THIS IS, AND IS NOT (state of main-protection, ruleset 18465404)
  * The pin turns every change to a bootstrap source into a visible diff of
    the fixture. A pin update needs a pull request whose diff shows the
    fixture change; the reviewer of that diff is claude[bot]
    (claude-review.yml).
  * It is NOT an enforced owner review. The ruleset has
    require_code_owner_review=false and required_approving_review_count=1,
    and mashkovd is the only account with write access, so CODEOWNERS for
    these two files is routing only (and is already covered by the `*`
    default).
  * The validate job that runs this test is NOT a required status check
    (required: cloudflare-plan, reserved-hosts). A red pin is visible, not
    blocking, until that is changed in the ruleset (a settings change this
    repository cannot make by itself).
  * An author who changes a source AND regenerates the fixture in the same PR
    passes every check here. The pin cannot judge whether a change is right;
    it only guarantees the change is on the page. Whoever edits the workflow
    step or this file removes the control in the same PR, with the same
    visibility and no more.
  * Independent of CODEOWNERS, the test itself refuses a one-sided update
    in a pull request: the fixture may change if and only if the pinned
    content changed (merge base vs head). A source change with no pin update
    is red. It cannot prevent a deliberate paired edit.

COUPLING: PULL REQUEST CONTEXT, FAIL-CLOSED
  A pull request context is: --base given, or GITHUB_EVENT_NAME is
  pull_request / pull_request_target, or GITHUB_BASE_REF is set. There the
  base must be observable; an unresolvable base ref, a missing GITHUB_BASE_REF,
  no merge base (shallow checkout) or an unreadable base tree is exit 2, never
  "not checked". Outside a pull request (local run, push to main) the
  coupling is not applicable and the test says so
  ("coupling: not applicable (not a pull request)").

COUPLING: REPAIR PATH (fixture-only change)
  If a source change ever reaches main without a pin update, main stays red
  and a source-free PR would be red on the rule above. Rule: a fixture-only
  change (fixture differs from the base's, pinned sources identical) is
  allowed ONLY IF (a) the base commit is itself in drift, i.e. its own pinned
  sources do not match its own fixture, evaluated from the base git tree
  (unreadable base tree or malformed base fixture is exit 2), AND (b) the new
  fixture matches the head tree. Any other one-sided change stays red: a
  fixture-only change on a converged base, a repair whose fixture still does
  not match head, or a source change without a pin update on a drifted base.
  LIMIT: the repair path cannot tell a legitimate repair from an author who
  re-pins a drifted base to whatever the tree now contains; it restores
  consistency, it does not judge the content. The reviewer of the fixture
  diff still decides.

INPUTS COME FROM THE GIT TREE, NOT THE FILESYSTEM
  The file set and file bytes are read from a commit (HEAD by default, or
  --rev) with `git ls-tree -r -z` and `git cat-file --batch`, as bytes. An
  untracked or ignored file, or a dirty worktree, cannot change the result.
  Detached HEAD (the CI checkout) is fine. If git is unavailable, the
  directory is not a repository, an object is missing (shallow or partial
  clone) or a revision does not resolve, the result is exit 2, never "clean".
  Consequence for development: commit the source change first, then run
  --print-pin.

WHAT IS PINNED
  Every file under platform-gitops/bootstrap (Chart.yaml, values.yaml,
  templates/, crds/, files/, charts/ with subcharts, anything a template can
  read through .Files), by repo-relative path and SHA-256 of the exact blob
  bytes. Line endings are NOT normalised: a CRLF change is a byte change.
  Symlinks and submodules in the tree are exit 2.

  One narrow exception, because bots rewrite these files directly on main
  (gitops-bump.yaml, release-deploy.yaml push image tag bumps under the
  ruleset's DeployKey bypass): in templates/mctl-platform/ ONLY (the only
  bootstrap prefix in both workflows' ALLOWED_PREFIXES) the TAG VALUE of the
  forms the workflows write is masked. Derived from both workflows on main:
    1. repository: ghcr.io/mctlhq/<name>\\n<ws>tag: <v>         (Pattern 1)
    2. registry: ghcr.io\\n<ws>repository: mctlhq/<name>\\n<ws>tag: <v>
                                                               (Pattern 2;
       gitops-bump writes ` "<tag>"`, release-deploy writes ` <tag>`)
    3. image: ["']ghcr.io/mctlhq/<name>:<v>                    (Pattern 3)
    4. value: ["']ghcr.io/mctlhq/<name>:<v>                    (Pattern 4)
  <v> is masked only if it has the exact shape both workflows validate:
  ^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$ (forms 1 and 2 also accept it in double
  quotes, which is what the workflows write). The line ending (LF or CRLF)
  is preserved in the masked form, so an EOL change of a masked line is a
  byte change and is drift. Anything else on that line (a Helm action, a
  longer or empty value) is not masked and so is drift. A bot bump of a line
  that a human saved with CRLF rewrites it to LF (the bots eat the CR) and so
  is visible drift too; the real files are LF.
  Two inputs are REJECTED with exit 2 instead of being hashed, because
  hashing them would be ambiguous:
    * a literal "<bump-managed>" anywhere in a file under that prefix (it
      would hash exactly like a masked real tag);
    * ANY `tag:` line that follows a form 1/2 repository line (the line the
      bots rewrite with `tag:)[^\\n]+`) and that the masks do not match
      exactly: non-canonical spacing, a tab, two spaces, trailing
      whitespace, !!str, single quotes, a trailing comment, an invalid or
      empty value, a Helm action. The bots would rewrite such a line to
      `tag: "<v>"` on the first bump, so hashing it would pass now and go red
      on main later. Write tag: "x" or tag: x. (A trailing CR is matched by
      the masks and kept, so it is covered as a byte change, not rejected.)
    The selftest checks
  the regexes in both workflows still read as recorded here.

SCOPE LIMITS (not pinned at all)
  helm-charts/base-service, helm-charts/tenant, services/*/*/values.yaml and
  tenants/*/values.yaml are inputs to what the bootstrap ApplicationSets
  generate or deploy, but they are NOT covered by this pin. The globs the
  ApplicationSets read are recorded in the fixture only so a change to the
  glob list is visible.

CASE-VARIANT PATHS
  Two tree paths (or directories) that differ only in case or Unicode
  normalisation check out differently on case-insensitive and
  case-sensitive platforms. That is exit 2, explicitly.

Coupling exceptions (PR runs): a fixture-only change on a base that is itself in
drift, and a source-only change that brings a drifted base back to the
unchanged fixture ("repair by revert"), are exit 0 when the head matches the
fixture. If the BASE tree cannot be built (for example main holds a rejected
tag form) but the head builds clean and matches the fixture, the result is
exit 0 with "base unobservable, head converged"; if the head is not clean or
not converged it is exit 2.

Exit codes: 0 pin matches; 1 drift (or one-sided pin update); 2 input could
not be observed (git unavailable, bad revision, missing object or directory,
symlink, submodule, case-variant duplicates, unreadable or malformed
fixture, base required but unobservable). Nothing is skipped.

Usage:
  python3 tests/test_bootstrap_source_pin.py             # verify HEAD
  python3 tests/test_bootstrap_source_pin.py --print-pin # regenerate fixture
  python3 tests/test_bootstrap_source_pin.py --selftest  # mutation selftest
  options: --rev REV (default HEAD), --base REV (coupling base; else
  $GITHUB_BASE_REF as origin/<ref>; else origin/main when present)
"""
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHART = "platform-gitops/bootstrap"
FIXTURE = "tests/fixtures/bootstrap-source-pin.json"
BUMP_PREFIX = (CHART + "/templates/mctl-platform/").encode()
PLACEHOLDER = b"<bump-managed>"

_NAME = rb"[a-z0-9][a-z0-9._-]*"
_TAG = rb"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}(?![A-Za-z0-9._-])"
_EOL = rb"(\r?)(?=\n|\Z)"   # group 2: kept, so an EOL change stays visible
# Tag-line forms 1 and 2: the bot leaves ` "<tag>"` or ` <tag>` after `tag:`.
_VAL = rb'(?: "' + _TAG + rb'"| ' + _TAG + rb")" + _EOL
MASKS = [
    # 1. Pattern 1 (both workflows): combined repository + tag
    (re.compile(rb"(repository:\s*ghcr\.io/mctlhq/" + _NAME + rb"\n\s+tag:)" + _VAL),
     rb"\1 " + PLACEHOLDER + rb"\2"),
    # 2. Pattern 2: split registry / repository / tag
    (re.compile(rb"(registry:\s*ghcr\.io\n\s+repository:\s*mctlhq/" + _NAME + rb"\n\s+tag:)" + _VAL),
     rb"\1 " + PLACEHOLDER + rb"\2"),
    # 3. Pattern 3: inline image: <image>:<tag>
    (re.compile(rb"(image:\s*[\"']?ghcr\.io/mctlhq/" + _NAME + rb")[\"']?:" + _TAG),
     rb"\1:" + PLACEHOLDER),
    # 4. Pattern 4: workflow-parameter value: <image>:<tag>
    (re.compile(rb"(value:\s*[\"']?ghcr\.io/mctlhq/" + _NAME + rb")[\"']?:" + _TAG),
     rb"\1:" + PLACEHOLDER),
]
# Every `tag:` line the bots would rewrite (their regex is `tag:)[^\n]+` after
# a form 1/2 repository line). After masking, such a line must read exactly
# ` <bump-managed>` (plus an optional kept CR); anything else is a form the
# masks did not match exactly and is rejected, never hashed.
_CTX_TAG = re.compile(rb"(?:repository:\s*ghcr\.io/mctlhq/" + _NAME
                      + rb"|registry:\s*ghcr\.io\n\s+repository:\s*mctlhq/" + _NAME
                      + rb")\n\s+tag:([^\n]*)")
_MASKED_TAIL = re.compile(rb" " + PLACEHOLDER + rb"\r?")
GLOB_RE = re.compile(rb"^\s*-\s*path:\s*(\S+)\s*$")
# Regex-defining lines the selftest requires verbatim (whitespace-stripped)
# in the bump workflows, so a changed bot pattern fails the selftest instead
# of silently turning main red or letting a new form through unmasked.
BOT_SOURCES = {
    ".github/workflows/gitops-bump.yaml": [
        "p1=re.compile(r'(repository:\\s*'+re.escape(image_name)+r'\\n\\s+tag:)[^\\n]+')",
        "r'(registry:\\s*'+re.escape(registry)+",
        "r'\\n\\s+repository:\\s*'+re.escape(repo)+",
        "r'\\n\\s+tag:)[^\\n]+'",
        "p3=re.compile(r'(image:\\s*[\"\\']?'+re.escape(image_name)+r')[\"\\']?:[\\w.\\-]+')",
        "p4=re.compile(r'(value:\\s*[\"\\']?'+re.escape(image_name)+r')[\"\\']?:[\\w.\\-]+')",
        "re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9._-]{0,127}',new_tag)",
    ],
    ".github/workflows/release-deploy.yaml": [
        "p1=re.compile(r'(repository:\\s*'+re.escape(image_name)+r'\\n\\s+tag:)[^\\n]+')",
        "r'(registry:\\s*'+re.escape(registry)+",
        "r'\\n\\s+repository:\\s*'+re.escape(repo)+",
        "r'\\n\\s+tag:)[^\\n]+'",
        "p2=re.compile(r'(image:\\s*[\"\\']?'+re.escape(image_name)+r')[\"\\']?:[\\w.\\-]+')",
        "p4=re.compile(r'(value:\\s*[\"\\']?'+re.escape(image_name)+r')[\"\\']?:[\\w.\\-]+')",
        "re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9._-]{0,127}',new_tag)",
    ],
}


class Unobservable(Exception):
    pass


def show(s):
    """Printable form of a str or bytes path; never raises on odd bytes."""
    if isinstance(s, bytes):
        return s.decode("utf-8", "backslashreplace")
    return s.encode("utf-8", "backslashreplace").decode("utf-8")


def pstr(b):
    return b.decode("utf-8", "surrogateescape")


# ---------------------------------------------------------------- git input

def git(root, args, stdin=None, ok=(0,)):
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        p = subprocess.run(["git", "-C", root] + args, input=stdin,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    except OSError as e:
        raise Unobservable("git unavailable: %s" % (e.strerror or e))
    if p.returncode not in ok:
        raise Unobservable("git %s failed (%d): %s" % (
            show(args[0].encode() if isinstance(args[0], str) else args[0]),
            p.returncode, show(p.stderr.strip()[:200])))
    return p


def resolve(root, rev):
    p = git(root, ["rev-parse", "--verify", "--quiet", "--end-of-options", rev + "^{commit}"], ok=(0, 1))
    sha = p.stdout.decode().strip()
    if p.returncode != 0 or not sha:
        raise Unobservable("revision does not resolve to a commit: %s" % show(rev))
    return sha


def tree_entries(root, sha, prefix):
    out = git(root, ["ls-tree", "-r", "-z", "--full-tree", sha, "--", prefix]).stdout
    entries = []
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, sep, path = rec.partition(b"\t")
        parts = meta.split(b" ")
        if not sep or len(parts) != 3:
            raise Unobservable("unparsable ls-tree record")
        entries.append((parts[0], parts[1], parts[2], path))
    return entries


def read_blobs(root, shas):
    uniq = sorted(set(shas))
    if not uniq:
        return {}
    out = git(root, ["cat-file", "--batch"], stdin=b"".join(s + b"\n" for s in uniq)).stdout
    blobs, pos = {}, 0
    for s in uniq:
        nl = out.find(b"\n", pos)
        if nl < 0:
            raise Unobservable("truncated cat-file output")
        head = out[pos:nl].split(b" ")
        if len(head) != 3 or head[0] != s or head[1] != b"blob":
            raise Unobservable("object not readable (missing or not a blob): %s" % show(s))
        size = int(head[2])
        blobs[s] = out[nl + 1:nl + 1 + size]
        if len(blobs[s]) != size:
            raise Unobservable("truncated blob %s" % show(s))
        pos = nl + 1 + size + 1
    return blobs


def read_path_at(root, sha, path):
    """Bytes of `path` in commit `sha`, or None if the path is absent from it."""
    ents = tree_entries(root, sha, path)
    ents = [e for e in ents if e[3] == path.encode()]
    if not ents:
        return None
    mode, typ, osha, _ = ents[0]
    if typ != b"blob" or mode not in (b"100644", b"100755"):
        raise Unobservable("%s is not a regular file in the tree" % show(path))
    return read_blobs(root, [osha])[osha]


def mask(data):
    for rx, rep in MASKS:
        data = rx.sub(rep, data)
    return data


def digest(rel, data):
    if rel.startswith(BUMP_PREFIX):
        if PLACEHOLDER in data:
            raise Unobservable(
                "literal %s in a bump-managed file would hash like a masked tag: %s"
                % (show(PLACEHOLDER), show(rel)))
        data = mask(data)
        for m in _CTX_TAG.finditer(data):
            if not _MASKED_TAIL.fullmatch(m.group(1)):
                raise Unobservable(
                    "bump-managed tag line that the masks do not match exactly (spacing, tab, "
                    "!!str, quotes, comment, invalid value); the bots would rewrite it. "
                    "Write it as tag: \"<tag>\" or tag: <tag>: %s" % show(rel))
    return hashlib.sha256(data).hexdigest()


def fold(s):
    return unicodedata.normalize("NFC", pstr(s)).casefold()


def check_case_variants(paths):
    seen = {}
    for p in paths:
        comps = p.split(b"/")
        for i in range(1, len(comps) + 1):
            raw = b"/".join(comps[:i])
            k = fold(raw)
            if seen.setdefault(k, raw) != raw:
                raise Unobservable("case/normalisation-variant paths: %s vs %s"
                                   % (show(seen[k]), show(raw)))


def collect(root, sha):
    ents = tree_entries(root, sha, CHART + "/")
    if not ents:
        raise Unobservable("no files found under %s in %s" % (CHART, sha[:12]))
    for mode, typ, _, path in ents:
        if mode == b"120000":
            raise Unobservable("symlink in tree: %s" % show(path))
        if typ != b"blob" or mode not in (b"100644", b"100755"):
            raise Unobservable("not a regular file in tree (%s %s): %s"
                               % (show(mode), show(typ), show(path)))
    check_case_variants([e[3] for e in ents])
    blobs = read_blobs(root, [e[2] for e in ents])
    files = {pstr(path): digest(path, blobs[osha]) for _, _, osha, path in ents}
    raw = {path: blobs[osha] for _, _, osha, path in ents}
    return files, raw


def globs(raw):
    out, seen = set(), False
    pre = (CHART + "/templates/bootstrap/").encode()
    for path, data in raw.items():
        if not path.startswith(pre):
            continue
        seen = True
        if not path[len(pre):].startswith(b"applicationset-"):
            continue
        for line in data.split(b"\n"):
            m = GLOB_RE.match(line.rstrip(b"\r"))
            if m and b"*" in m.group(1):
                out.add(pstr(m.group(1)))
    if not seen:
        raise Unobservable("missing %s/templates/bootstrap" % CHART)
    return sorted(out)


def build(root, sha):
    files, raw = collect(root, sha)
    return {
        "_comment": "Structural pin, not a semantic check. Regenerate (after "
                    "committing the source change) with "
                    "python3 tests/test_bootstrap_source_pin.py --print-pin",
        "chart": CHART,
        "sources": files,
        "excluded_unpinned_glob_inputs": globs(raw),
    }


def render(pin):
    return json.dumps(pin, indent=2, sort_keys=True) + "\n"


def load_fixture(root, sha):
    data = read_path_at(root, sha, FIXTURE)
    if data is None:
        return None
    try:
        pinned = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Unobservable("fixture malformed: %s" % e)
    if not isinstance(pinned, dict) or not isinstance(pinned.get("sources"), dict):
        raise Unobservable("malformed fixture")
    return pinned


# ------------------------------------------------------------ pin vs. tree

def drift_of(actual, pinned):
    a, p = actual["sources"], pinned["sources"]
    drift = ["added: " + show(k) for k in sorted(set(a) - set(p))]
    drift += ["removed: " + show(k) for k in sorted(set(p) - set(a))]
    drift += ["changed: " + show(k) for k in sorted(set(a) & set(p)) if a[k] != p[k]]
    if pinned.get("excluded_unpinned_glob_inputs") != actual["excluded_unpinned_glob_inputs"]:
        drift.append("glob inputs differ from the recorded list")
    return drift


def resolve_base(root, head, explicit):
    """Merge base commit for the coupling check. None only when this is not a
    pull request run (no --base, no pull_request event, no GITHUB_BASE_REF):
    the coupling is then not applicable. In a pull request context an
    unresolvable base is Unobservable (exit 2), never "not checked"."""
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    strict = bool(explicit) or event in ("pull_request", "pull_request_target") or bool(ref)
    if not strict:
        return None          # not a pull request: coupling is not applicable
    if explicit:
        cands = [explicit]
    elif ref:
        cands = ["origin/" + ref, ref]
    else:
        raise Unobservable("pull_request run without GITHUB_BASE_REF: base unknown")
    tip = None
    for c in cands:
        p = git(root, ["rev-parse", "--verify", "--quiet", "--end-of-options", c + "^{commit}"], ok=(0, 1))
        if p.returncode == 0 and p.stdout.strip():
            tip = p.stdout.decode().strip()
            break
    if tip is None:
        raise Unobservable("base revision not observable (tried %s)" % ", ".join(cands))
    p = git(root, ["merge-base", head, tip], ok=(0, 1))
    if p.returncode == 0 and p.stdout.strip():
        return p.stdout.decode().strip()
    # No common history: accept only the first parent of a merge head (the
    # refs/pull/N/merge checkout), which is the base tip itself.
    p = git(root, ["rev-parse", "--verify", "--quiet", head + "^1"], ok=(0, 1))
    if p.returncode == 0 and p.stdout.decode().strip() == tip:
        return tip
    raise Unobservable("no merge base between HEAD and %s (shallow checkout?)" % cands[0])


def coupling(root, head, explicit_base):
    """Return (exit_code, lines). 0/1/2; pin fixture and pinned content must
    change together."""
    base = resolve_base(root, head, explicit_base)
    if base is None:
        return 0, ["coupling: not applicable (not a pull request)"]
    fix_b = load_fixture(root, base)
    if fix_b is None:
        return 0, ["coupling: not applicable (the fixture does not exist at the base: introduction)"]
    fix_h = load_fixture(root, head)
    if fix_h is None:
        raise Unobservable("fixture missing at head")
    src_h = build(root, head)        # an unobservable head is exit 2
    try:
        src_b = build(root, base)
    except Unobservable as e:
        # The base tree cannot be read (for example main already holds a form
        # that is rejected). The fix PR must not be blocked for that, but only
        # a head that builds clean AND matches its own fixture is let through.
        if drift_of(src_h, fix_h):
            raise Unobservable("base unobservable (%s) and the head is not converged "
                               "with the fixture" % show(str(e)))
        return 0, ["coupling: base unobservable, head converged (base %s: %s); "
                   "the base cannot be compared, the head matches the fixture"
                   % (base[:12], show(str(e)))]
    fix_changed = fix_b != fix_h
    src_changed = (src_b["sources"], src_b["excluded_unpinned_glob_inputs"]) != \
                  (src_h["sources"], src_h["excluded_unpinned_glob_inputs"])
    if fix_changed and not src_changed:
        # Repair path: allowed only if the base commit is itself in drift
        # (evaluated from the base tree; unreadable base tree is exit 2 above)
        # AND the new fixture matches the head tree.
        if not drift_of(src_b, fix_b):
            return 1, ["COUPLING: the pin fixture changed but no pinned bootstrap source changed "
                       "since the merge base (%s), and the base is not in drift (not a repair)"
                       % base[:12]]
        if drift_of(src_h, fix_h):
            return 1, ["COUPLING: repair attempt, but the new fixture does not match the head tree "
                       "(base %s is in drift)" % base[:12]]
        return 0, ["coupling: repair ok (base %s was in drift; the fixture now matches the head tree)"
                   % base[:12]]
    if src_changed and not fix_changed:
        # Repair by revert: the base is in drift (a source reached it without a
        # pin update), the sources changed back and the head matches the
        # unchanged fixture.
        if drift_of(src_b, fix_b) and not drift_of(src_h, fix_h):
            return 0, ["coupling: repair by revert ok (base %s was in drift; the sources "
                       "changed and the head matches the unchanged fixture)" % base[:12]]
        return 1, ["COUPLING: pinned bootstrap sources changed since the merge base (%s) "
                   "but the pin fixture did not" % base[:12]]
    return 0, ["coupling: ok (base %s; fixture changed: %s, pinned sources changed: %s)"
               % (base[:12], fix_changed, src_changed)]


def verify(root, rev="HEAD", base=None):
    """Return 0, 1 or 2."""
    try:
        sha = resolve(root, rev)
        actual = build(root, sha)
        pinned = load_fixture(root, sha)
        if pinned is None:
            raise Unobservable("fixture %s missing from %s" % (FIXTURE, rev))
        crc, clines = coupling(root, sha, base)
    except Unobservable as e:
        print("UNOBSERVABLE: %s" % show(str(e)))
        return 2
    drift = drift_of(actual, pinned)
    if drift:
        print("DRIFT: bootstrap sources differ from %s:" % FIXTURE)
        for d in drift:
            print("  " + d)
        print("Review the change, commit it, then regenerate: "
              "python3 tests/test_bootstrap_source_pin.py --print-pin")
    for line in clines:
        print(show(line))
    if drift or crc:
        return 1
    print("ok: %d bootstrap sources match the pin" % len(actual["sources"]))
    return 0


# ------------------------------------------------------------------ selftest

def bot_gitops_bump(content, image_name, new_tag):
    """Copy of gitops-bump.yaml's patterns 1-4 (the selftest asserts the
    regex source lines still exist in the workflow)."""
    p1 = re.compile(r'(repository:\s*' + re.escape(image_name) + r'\n\s+tag:)[^\n]+')
    out, _ = p1.subn(lambda m: m.group(1) + ' "' + new_tag + '"', content)
    registry, repo = image_name.split('/', 1)
    p_split = re.compile(r'(registry:\s*' + re.escape(registry) +
                         r'\n\s+repository:\s*' + re.escape(repo) + r'\n\s+tag:)[^\n]+')
    out, _ = p_split.subn(lambda m: m.group(1) + ' "' + new_tag + '"', out)
    p3 = re.compile(r'(image:\s*["\']?' + re.escape(image_name) + r')["\']?:[\w.\-]+')
    out, _ = p3.subn(lambda m: m.group(1) + ':' + new_tag, out)
    p4 = re.compile(r'(value:\s*["\']?' + re.escape(image_name) + r')["\']?:[\w.\-]+')
    out, _ = p4.subn(lambda m: m.group(1) + ':' + new_tag, out)
    return out


def bot_release_deploy(content, image_name, new_tag):
    """Copy of release-deploy.yaml's patterns (Pattern 2 writes the tag unquoted)."""
    p1 = re.compile(r'(repository:\s*' + re.escape(image_name) + r'\n\s+tag:)[^\n]+')
    out, _ = p1.subn(lambda m: m.group(1) + ' "' + new_tag + '"', content)
    registry, repo = image_name.split('/', 1)
    p3 = re.compile(r'(registry:\s*' + re.escape(registry) +
                    r'\n\s+repository:\s*' + re.escape(repo) + r'\n\s+tag:)[^\n]+')
    out, _ = p3.subn(lambda m: m.group(1) + ' ' + new_tag, out)
    p2 = re.compile(r'(image:\s*["\']?' + re.escape(image_name) + r')["\']?:[\w.\-]+')
    out, _ = p2.subn(lambda m: m.group(1) + ':' + new_tag, out)
    p4 = re.compile(r'(value:\s*["\']?' + re.escape(image_name) + r')["\']?:[\w.\-]+')
    out, _ = p4.subn(lambda m: m.group(1) + ':' + new_tag, out)
    return out


def selftest():
    """Each mutation must be red; the unmutated copy must be green."""
    tmp = tempfile.mkdtemp(prefix="bsp-")
    failures = []
    saved_env = {k: os.environ.pop(k) for k in ("GITHUB_EVENT_NAME", "GITHUB_BASE_REF") if k in os.environ}
    ident = ["-c", "user.name=selftest", "-c", "user.email=selftest@invalid",
             "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false"]
    sources = [CHART, FIXTURE]

    def g(root, *args, stdin=None):
        return git(root, list(args), stdin=stdin).stdout

    def commit(root, msg):
        g(root, *ident, "commit", "-q", "--allow-empty", "-m", msg)

    def fresh():
        dst = os.path.join(tmp, "r")
        shutil.rmtree(dst, ignore_errors=True)
        os.makedirs(dst)
        tracked = g(REPO, "ls-files", "-z", "--", *sources).split(b"\0")
        for rel in tracked:
            if not rel:
                continue
            s = os.path.join(REPO.encode(), rel)
            d = os.path.join(dst.encode(), rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if os.path.islink(s):
                os.symlink(os.readlink(s), d)
            else:
                shutil.copyfile(s, d)
        g(dst, "init", "-q")
        g(dst, "add", "-A")
        commit(dst, "base")
        return dst

    def b(root, rel):
        return os.path.join(root, CHART, rel)

    def rd(path):
        with open(path, "rb") as f:
            return f.read()

    def wr(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def append(path, data=b"# m\n"):
        wr(path, rd(path) + data)

    def repin(root):
        """Commit the worktree, regenerate the fixture from it, commit again."""
        g(root, "add", "-A")
        commit(root, "src")
        pin = build(root, resolve(root, "HEAD"))
        wr(os.path.join(root, FIXTURE), render(pin).encode())
        g(root, "add", "-A")
        commit(root, "pin")

    def plumb(root, path, data=b"x\n", mode="100644"):
        """Add a tree entry without touching the filesystem (non-UTF-8 and
        case-variant names cannot exist on every host filesystem)."""
        h = g(root, "hash-object", "-w", "--stdin", stdin=data).strip()
        subprocess.run(["git", "-C", root, "update-index", "--add", "--cacheinfo",
                        mode.encode() + b"," + h + b"," + path], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return "plumbed"

    def bump_with(fn, rel, image, tag):
        def m(root):
            p = b(root, rel)
            old = rd(p).decode()
            new = fn(old, image, tag)
            if new == old:
                raise SystemExit("selftest: bot replica changed nothing in %s for %s" % (rel, image))
            wr(p, new.encode())
        return m

    def set_tag_line(rel, old_re, new_line):
        def m(root):
            p = b(root, rel)
            d = rd(p)
            n, k = re.subn(old_re, new_line, d, count=1)
            if k != 1:
                raise SystemExit("selftest: no tag line to mutate in %s" % rel)
            wr(p, n)
        return m

    mp = "templates/mctl-platform/mctl-api.yaml"
    pt = "templates/mctl-platform/mctl-portal.yaml"
    api_tag = rb'(?m)^(\s*tag:) "[^"]*"$'
    first_tpl = sorted(k for k in collect(REPO, resolve(REPO, "HEAD"))[0] if "/templates/" in k)[0]
    tpl_rel = first_tpl[len(CHART) + 1:]
    synth = (b"      image: ghcr.io/mctlhq/synth-img:1.0.0\n"
             b"      value: \"ghcr.io/mctlhq/synth-img:1.0.0\"\n")

    def synth_then_bump(fn):
        def m(root):
            append(b(root, "templates/mctl-platform/mctl-agent.yaml"), synth)
            repin(root)
            p = b(root, "templates/mctl-platform/mctl-agent.yaml")
            old = rd(p).decode()
            new = fn(old, "ghcr.io/mctlhq/synth-img", "7.7.7")
            if new == old:
                raise SystemExit("selftest: synthetic bump changed nothing")
            wr(p, new.encode())
        return m

    def outside_prefix_tag_edit(root):
        wr(b(root, "templates/system/zz-synth.yaml"),
           b"image:\n  repository: ghcr.io/mctlhq/zz\n  tag: \"1.0.0\"\n")
        repin(root)
        append(b(root, "templates/system/zz-synth.yaml"), b"")
        wr(b(root, "templates/system/zz-synth.yaml"),
           b"image:\n  repository: ghcr.io/mctlhq/zz\n  tag: \"2.0.0\"\n")

    def crlf_values(root):
        p = b(root, "values.yaml")
        wr(p, rd(p).replace(b"\n", b"\r\n"))

    def after_dirty(root):
        append(b(root, "values.yaml"))

    def after_untracked(root):
        wr(b(root, "templates/untracked-extra.yaml"), b"x\n")
        wr(os.path.join(root, ".gitignore"), b"*.ign\n")
        wr(b(root, "templates/ignored.ign"), b"x\n")

    def after_remove_git(root):
        shutil.rmtree(os.path.join(root, ".git"))

    # (name, mutate-before-commit, after-commit-worktree-change, want, kwargs)
    # mutate returns "plumbed" when it already staged its own entries.
    cases = [
        ("real tree", lambda r: None, None, 0, {}),
        ("modify template", lambda r: append(b(r, tpl_rel)), None, 1, {}),
        ("modify values.yaml", lambda r: append(b(r, "values.yaml")), None, 1, {}),
        ("modify files/ file", lambda r: append(b(r, "files/usage-pricing/claude-firstparty.json")), None, 1, {}),
        ("add template", lambda r: wr(b(r, "templates/system/new.yaml"), b"x\n"), None, 1, {}),
        ("add crds file", lambda r: wr(b(r, "crds/new.yaml"), b"x\n"), None, 1, {}),
        ("add subchart file", lambda r: wr(b(r, "charts/sub/templates/x.yaml"), b"x\n"), None, 1, {}),
        ("add subchart Chart.yaml", lambda r: wr(b(r, "charts/sub/Chart.yaml"), b"x\n"), None, 1, {}),
        ("remove template", lambda r: os.remove(b(r, tpl_rel)), None, 1, {}),
        ("rename template", lambda r: os.rename(b(r, tpl_rel), b(r, tpl_rel + ".bak")), None, 1, {}),
        ("symlink file", lambda r: os.symlink(b(r, "values.yaml"), b(r, "templates/link.yaml")), None, 2, {}),
        ("symlink dir", lambda r: os.symlink(b(r, "files"), b(r, "charts-link")), None, 2, {}),
        ("missing chart dir", lambda r: shutil.rmtree(b(r, "")), None, 2, {}),
        ("missing fixture", lambda r: os.remove(os.path.join(r, FIXTURE)), None, 2, {}),
        ("malformed fixture", lambda r: wr(os.path.join(r, FIXTURE), b"{not json"), None, 2, {}),

        # P1: every bump form the workflows write stays green
        ("gitops-bump P1 combined, quoted", bump_with(bot_gitops_bump, mp, "ghcr.io/mctlhq/mctl-api", "9.9.9"), None, 0, {}),
        ("gitops-bump P2 split (portal)", bump_with(bot_gitops_bump, pt, "ghcr.io/mctlhq/mctl-portal", "9.9.9"), None, 0, {}),
        ("release-deploy P1 combined", bump_with(bot_release_deploy, mp, "ghcr.io/mctlhq/mctl-api", "9.9.9"), None, 0, {}),
        ("release-deploy P2 split, unquoted (portal)", bump_with(bot_release_deploy, pt, "ghcr.io/mctlhq/mctl-portal", "9.9.9"), None, 0, {}),
        ("gitops-bump P3+P4 inline image/value", synth_then_bump(bot_gitops_bump), None, 0, {}),
        ("release-deploy P3+P4 inline image/value", synth_then_bump(bot_release_deploy), None, 0, {}),
        ("tag edit outside templates/mctl-platform is drift", outside_prefix_tag_edit, None, 1, {}),
        ("non-tag edit in mctl-platform", lambda r: append(b(r, mp)), None, 1, {}),
        ("repository edit in mctl-platform", lambda r: wr(b(r, mp), rd(b(r, mp)).replace(b"ghcr.io/mctlhq/mctl-api", b"ghcr.io/evil/mctl-api", 1)), None, 1, {}),

        # P2: tag value shape
        ("tag is a Helm action is rejected (unmatched tag line)", set_tag_line(mp, api_tag, rb'\1 {{ .Values.evil }}'), None, 2, {}),
        # Forms a human may commit but the bots would rewrite: rejected with a
        # clear message (exit 2), never silently left unmasked.
        ("tag with trailing comment is rejected", set_tag_line(mp, api_tag, rb'\1 "1.0.0" # x'), None, 2, {}),
        ("tag unquoted with trailing comment is rejected", set_tag_line(mp, api_tag, rb'\1 1.0.0 # x'), None, 2, {}),
        ("split form (portal) single-quoted tag is rejected",
         set_tag_line(pt, rb'(?m)^(\s*tag:) [^\n]*$', rb"\1 '1.0.0'"), None, 2, {}),
        ("tag with comment and invalid value is rejected", set_tag_line(mp, api_tag, rb'\1 "a b" # x'), None, 2, {}),
        # P3: masked line keeps its line ending; placeholder text cannot collide
        ("LF to CRLF on a masked tag line is a byte change", set_tag_line(mp, rb'(?m)^(\s*tag: "[^"]*")$', rb'\1\r'), None, 1, {}),
        ("bot bump of a CRLF tag line is visible drift (bot strips the CR)",
         lambda r: (set_tag_line(mp, rb'(?m)^(\s*tag: "[^"]*")$', rb'\1\r')(r), repin(r),
                    bump_with(bot_gitops_bump, mp, "ghcr.io/mctlhq/mctl-api", "9.9.9")(r))[-1], None, 1, {}),
        ("literal placeholder as tag value", set_tag_line(mp, api_tag, rb'\1 <bump-managed>'), None, 2, {}),
        ("literal placeholder in a comment", lambda r: append(b(r, mp), b"# <bump-managed>\n"), None, 2, {}),
        ("placeholder text outside the bump prefix is plain content", lambda r: append(b(r, "values.yaml"), b"# <bump-managed>\n"), None, 1, {}),
        ("tag longer than 128 is rejected", set_tag_line(mp, api_tag, rb'\1 "' + b"a" * 129 + b'"'), None, 2, {}),
        ("tag with a space is rejected", set_tag_line(mp, api_tag, rb'\1 "1.0 0"'), None, 2, {}),
        ("tag empty is rejected", set_tag_line(mp, api_tag, rb'\1 '), None, 2, {}),
        ("tag leading dash is rejected", set_tag_line(mp, api_tag, rb'\1 "-1.0"'), None, 2, {}),
        # Finding 1: every tag line shape the masks do not match exactly (the
        # bots would rewrite it to `tag: "<v>"`) is rejected, split form included.
        ("tag no space after colon is rejected", set_tag_line(mp, api_tag, rb'\1"1.0.0"'), None, 2, {}),
        ("tag two spaces is rejected", set_tag_line(mp, api_tag, rb'\1  "1.0.0"'), None, 2, {}),
        ("tag tab after colon is rejected", set_tag_line(mp, api_tag, rb'\1\t"1.0.0"'), None, 2, {}),
        ("tag trailing space after quotes is rejected", set_tag_line(mp, api_tag, rb'\1 "1.0.0" '), None, 2, {}),
        ("tag trailing tab after quotes is rejected", set_tag_line(mp, api_tag, rb'\1 "1.0.0"\t'), None, 2, {}),
        ("tag !!str is rejected", set_tag_line(mp, api_tag, rb'\1 !!str "1.0.0"'), None, 2, {}),
        ("split form: two spaces is rejected",
         set_tag_line(pt, rb'(?m)^(\s*tag:) [^\n]*$', rb'\1  1.0.0'), None, 2, {}),
        ("split form: unquoted with trailing space is rejected",
         set_tag_line(pt, rb'(?m)^(\s*tag:) [^\n]*$', rb'\1 1.0.0 '), None, 2, {}),
        ("split form: !!str is rejected",
         set_tag_line(pt, rb'(?m)^(\s*tag:) [^\n]*$', rb'\1 !!str 1.0.0'), None, 2, {}),
        ("split form: tab is rejected",
         set_tag_line(pt, rb'(?m)^(\s*tag:) [^\n]*$', rb'\1\t1.0.0'), None, 2, {}),
        # EOL mask (finding 6): the CR of a masked line is kept. A value change
        # that keeps the CR is masked (green); LF<->CRLF (above) is drift.
        ("EOL mask: CRLF tag line, value change keeps the CR, is masked",
         lambda r: (set_tag_line(mp, rb'(?m)^(\s*tag: "[^"]*")$', rb'\1\r')(r), repin(r),
                    set_tag_line(mp, rb'(?m)^(\s*tag: )"[^"]*"\r$', rb'\1"8.8.8"\r')(r))[-1], None, 0, {}),
        ("tag single-quoted is rejected", set_tag_line(mp, api_tag, rb"\1 '1.0.0'"), None, 2, {}),
        ("tag valid shape 128 chars stays green", set_tag_line(mp, api_tag, rb'\1 "' + b"a" * 128 + b'"'), None, 0, {}),

        # P2: case variants
        ("case-variant file paths", lambda r: (plumb(r, (CHART + "/templates/Zcase.yaml").encode()),
                                              plumb(r, (CHART + "/templates/zcase.yaml").encode()))[0], None, 2, {"noadd": True}),
        ("case-variant directories", lambda r: (plumb(r, (CHART + "/templates/ZDir/a.yaml").encode()),
                                                plumb(r, (CHART + "/templates/zdir/b.yaml").encode()))[0], None, 2, {"noadd": True}),

        # P2: inputs come from the tree
        ("dirty tracked file is ignored", lambda r: None, after_dirty, 0, {}),
        ("untracked and ignored files are ignored", lambda r: None, after_untracked, 0, {}),
        ("git metadata missing", lambda r: None, after_remove_git, 2, {}),
        ("git unavailable", lambda r: None, None, 2, {"nogit": True}),
        ("bad revision", lambda r: None, None, 2, {"rev": "no-such-rev"}),

        # P3: bytes
        ("CRLF is a byte change", crlf_values, None, 1, {}),
        ("non-UTF-8 file name does not crash", lambda r: plumb(r, (CHART + "/templates/").encode() + b"bad\xff\xfename.yaml"), None, 1, {"noadd": True}),
    ]

    def coupling_cases():
        """Cases that need a base commit: build a base repo, then a 'PR'."""
        out = []

        def run(name, setup_base, pr, want, base_arg="BASE", env=None, direct=False, say=None):
            root = fresh()
            setup_base(root)
            base = resolve(root, "HEAD")
            pr(root)
            if base_arg == "BASE":
                base_arg = base
            elif base_arg == "NONE":
                base_arg = None
            for k in ("GITHUB_EVENT_NAME", "GITHUB_BASE_REF"):
                os.environ.pop(k, None)
            os.environ.update(env or {})
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    if direct:       # coupling() alone, bypassing verify()'s own drift check
                        try:
                            got, lines = coupling(root, resolve(root, "HEAD"), base_arg)
                            for line in lines:
                                print(show(line))
                        except Unobservable as e:
                            print("UNOBSERVABLE: %s" % show(str(e)))
                            got = 2
                    else:
                        got = verify(root, base=base_arg)
            finally:
                for k in ("GITHUB_EVENT_NAME", "GITHUB_BASE_REF"):
                    os.environ.pop(k, None)
            if got != want:
                failures.append("%s: want exit %d, got %d" % (name, want, got))
            if say and say not in buf.getvalue():
                failures.append("%s: output lacks %r" % (name, say))
            if say is None and "NOT CHECKED" in buf.getvalue():
                failures.append("%s: printed NOT CHECKED" % name)
            out.append(name)

        def stale_fixture(root):
            p = os.path.join(root, FIXTURE)
            d = json.loads(rd(p))
            k = sorted(d["sources"])[0]
            d["sources"][k] = "0" * 64
            wr(p, render(d).encode())
            g(root, "add", "-A")
            commit(root, "stale pin")

        def fix_fixture_only(root):
            wr(os.path.join(root, FIXTURE), render(build(root, resolve(root, "HEAD"))).encode())
            g(root, "add", "-A")
            commit(root, "fix pin only")

        def src_and_pin(root):
            append(b(root, "values.yaml"))
            repin(root)

        def src_only(root):
            append(b(root, "values.yaml"))
            g(root, "add", "-A")
            commit(root, "src only")

        def bump_only(root):
            bump_with(bot_gitops_bump, mp, "ghcr.io/mctlhq/mctl-api", "9.9.9")(root)
            g(root, "add", "-A")
            commit(root, "bump")

        def no_fixture_at_base(root):
            g(root, "rm", "-q", FIXTURE)
            commit(root, "base without pin")

        def drifted_base(root):          # a source change reached main without a pin update
            append(b(root, "values.yaml"))
            g(root, "add", "-A")
            commit(root, "drifted base")

        def pin_comment_only(root):      # fixture-only change on a converged base
            p = os.path.join(root, FIXTURE)
            d = json.loads(rd(p))
            d["_comment"] += " (edited)"
            wr(p, render(d).encode())
            g(root, "add", "-A")
            commit(root, "fixture only")

        def wrong_repair(root):          # fixture-only change that still does not match head
            p = os.path.join(root, FIXTURE)
            d = json.loads(rd(p))
            d["sources"][sorted(d["sources"])[1]] = "1" * 64
            wr(p, render(d).encode())
            g(root, "add", "-A")
            commit(root, "wrong repair")

        def base_without_chart(root):    # unreadable base tree: no bootstrap chart at base
            g(root, "rm", "-rq", CHART)
            commit(root, "base without chart")

        def base_bad_fixture(root):
            wr(os.path.join(root, FIXTURE), b"{nope")
            g(root, "add", "-A")
            commit(root, "base with malformed fixture")

        def restore_chart(root):
            tracked = g(REPO, "ls-files", "-z", "--", CHART).split(b"\0")
            for rel in tracked:
                if rel:
                    d = os.path.join(root.encode(), rel)
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    shutil.copyfile(os.path.join(REPO.encode(), rel), d)
            g(root, "add", "-A")
            commit(root, "chart back")

        def shallow_pr(root):
            """Replace root by a depth-1 clone of the head whose origin/main
            is fetched at depth 1 too: no common history, base unobservable."""
            tag = os.path.join(tmp, "shallow")
            shutil.rmtree(tag, ignore_errors=True)
            g(root, "branch", "-f", "main", "HEAD~1")
            subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "pr",
                            "file://" + root, tag], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            g(tag, "fetch", "-q", "--depth", "1", "origin", "main:refs/remotes/origin/main")
            shutil.rmtree(root)
            shutil.move(tag, root)

        def intro(root):
            pass

        st = {}

        def break_tag(root):             # main holds a rejected single-quoted tag
            st["orig"] = rd(b(root, mp))
            set_tag_line(mp, api_tag, rb"\1 '1.0.0'")(root)
            g(root, "add", "-A")
            commit(root, "base with a rejected tag form")

        def fix_tag(root):
            wr(b(root, mp), st["orig"])
            g(root, "add", "-A")
            commit(root, "tag form fixed")

        def fix_tag_but_drift(root):
            wr(b(root, mp), st["orig"])
            append(b(root, "values.yaml"))
            g(root, "add", "-A")
            commit(root, "tag form fixed, other source changed, no pin")

        def other_change_only(root):
            append(b(root, "values.yaml"))
            g(root, "add", "-A")
            commit(root, "other change")

        def revert_values(root):         # undo drifted_base's appended line, fixture untouched
            p = b(root, "values.yaml")
            d = rd(p)
            assert d.endswith(b"# m\n")
            wr(p, d[:-len(b"# m\n")])
            g(root, "add", "-A")
            commit(root, "revert the drift")

        def pr_branch_with_refs(root):
            """Base tip as origin/main (no local main) and a pr branch."""
            g(root, "update-ref", "refs/remotes/origin/main", "HEAD")
            g(root, "checkout", "-q", "-b", "pr")

        def pr_branch_with_local_main(root):
            """Base tip only as a LOCAL main branch: the GITHUB_BASE_REF fallback."""
            g(root, "checkout", "-q", "-b", "pr")
            g(root, "update-ref", "refs/heads/main", "HEAD")

        PR = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_BASE_REF": "main"}

        run("coupling: source change with pin update", lambda r: None, src_and_pin, 0)
        run("coupling: source change without pin update", lambda r: None, src_only, 1)
        # repair path: a fixture-only change is allowed ONLY on a drifted base
        run("repair: fixture-only PR on a drifted base is green", drifted_base, fix_fixture_only, 0)
        run("repair: fixture-only change on a converged base is red", lambda r: None, pin_comment_only, 1)
        run("repair: fixture that does not match head is red (verify)", drifted_base, wrong_repair, 1)
        run("repair: fixture that does not match head is red (coupling alone)", drifted_base, wrong_repair, 1, direct=True)
        run("repair: drifted base, source change without pin stays red", drifted_base, src_only, 1)
        # Finding 2: repair by revert (sources back to the pinned state, fixture untouched)
        run("repair by revert: base in drift, head converged, fixture untouched is green",
            drifted_base, revert_values, 0, say="repair by revert ok")
        run("repair by revert: same, coupling alone", drifted_base, revert_values, 0, direct=True, say="repair by revert ok")
        run("repair by revert: head still in drift is red", drifted_base, other_change_only, 1)
        run("repair by revert: head still in drift is red (coupling alone)", drifted_base, other_change_only, 1, direct=True)
        run("repair by revert: converged base, source change without pin is red", lambda r: None, other_change_only, 1)
        # Finding 3: base unobservable. Head converged -> exit 0 with its own message;
        # head not clean or not converged -> exit 2.
        run("base unobservable, head converged: fix PR is green and says so", break_tag, fix_tag, 0,
            say="base unobservable, head converged")
        run("base unobservable, head converged: coupling alone", break_tag, fix_tag, 0, direct=True,
            say="base unobservable, head converged")
        run("base unobservable, head converged: base without the chart", base_without_chart, restore_chart, 0,
            say="base unobservable, head converged")
        run("base unobservable, head still rejected is exit 2", break_tag, other_change_only, 2)
        run("base unobservable, head builds but drifts is exit 2", break_tag, fix_tag_but_drift, 2)
        run("base unobservable, head drifts: coupling alone is exit 2", break_tag, fix_tag_but_drift, 2, direct=True)
        run("repair: base with malformed fixture is unobservable", base_bad_fixture, fix_fixture_only, 2)
        run("coupling: stale base fixture fixed by fixture-only PR is a repair", stale_fixture, fix_fixture_only, 0)
        run("coupling: bump-only change, no pin change", lambda r: None, bump_only, 0)
        run("coupling: no change at all", lambda r: None, lambda r: None, 0)
        run("coupling: base missing a fixture (introduction)", no_fixture_at_base,
            lambda r: (wr(os.path.join(r, FIXTURE), render(build(r, resolve(r, "HEAD"))).encode()),
                       g(r, "add", "-A"), commit(r, "introduce"))[0], 0)
        run("coupling: explicit base does not resolve", lambda r: None, lambda r: None, 2, base_arg="no-such-base")
        # fail-closed base: a PR run that cannot resolve its base is exit 2
        run("pr run: base ref does not resolve", lambda r: None, src_only, 2, base_arg="NONE",
            env={"GITHUB_EVENT_NAME": "pull_request", "GITHUB_BASE_REF": "no-such-branch"})
        run("pr run: GITHUB_BASE_REF alone (no event) is still strict", lambda r: None, src_only, 2, base_arg="NONE",
            env={"GITHUB_BASE_REF": "no-such-branch"})
        run("pr run: no GITHUB_BASE_REF at all", lambda r: None, src_only, 2, base_arg="NONE",
            env={"GITHUB_EVENT_NAME": "pull_request"})
        run("pr run: shallow checkout without the base", lambda r: (g(r, "checkout", "-q", "-b", "pr"), None)[1],
            lambda r: (src_and_pin(r), shallow_pr(r))[1], 2, base_arg="NONE", env=PR)
        # pull_request path simulated through the environment (real CI is not run here)
        run("pr path: origin/<GITHUB_BASE_REF> + event, source change without pin is red",
            pr_branch_with_refs, src_only, 1, base_arg="NONE", env=PR)
        run("pr path: origin/<GITHUB_BASE_REF> + event, source change with pin is green",
            pr_branch_with_refs, src_and_pin, 0, base_arg="NONE", env=PR, say="coupling: ok")
        run("pr path: GITHUB_BASE_REF resolved through the local-branch fallback, red",
            pr_branch_with_local_main, src_only, 1, base_arg="NONE", env=PR)
        run("pr path: GITHUB_BASE_REF resolved through the local-branch fallback, green",
            pr_branch_with_local_main, src_and_pin, 0, base_arg="NONE", env=PR, say="coupling: ok")
        run("pr path: --base fallback when the event has no GITHUB_BASE_REF, red",
            lambda r: None, src_only, 1, env={"GITHUB_EVENT_NAME": "pull_request"})
        run("pr path: --base wins over an unresolvable GITHUB_BASE_REF, red",
            lambda r: None, src_only, 1, env={"GITHUB_EVENT_NAME": "pull_request", "GITHUB_BASE_REF": "no-such-branch"})
        # outside a PR the coupling is explicitly not applicable
        run("non-pr run: coupling not applicable, says so", lambda r: None, src_only, 1, base_arg="NONE",
            say="coupling: not applicable (not a pull request)")
        run("non-pr run (push to main): converged tree is green and says so", lambda r: None, lambda r: None, 0,
            base_arg="NONE", say="coupling: not applicable (not a pull request)")
        return out

    n = 0
    for name, mutate, after, want, kw in cases:
        root = fresh()
        res = mutate(root)
        if kw.get("noadd") or res == "plumbed":
            commit(root, "mut")
        else:
            g(root, "add", "-A")
            commit(root, "mut")
        # The fixture is committed in the base commit; mutations that change
        # sources are therefore expected to differ from it.
        if after:
            after(root)
        old_path = os.environ.get("PATH", "")
        try:
            if kw.get("nogit"):
                empty = os.path.join(tmp, "empty")
                os.makedirs(empty, exist_ok=True)
                os.environ["PATH"] = empty
            got = verify(root, rev=kw.get("rev", "HEAD"), base=None)
        finally:
            os.environ["PATH"] = old_path
        n += 1
        if got != want:
            failures.append("%s: want exit %d, got %d" % (name, want, got))
    n += len(coupling_cases())

    # Bot parity: the regex source lines recorded in BOT_SOURCES must still
    # be present in the workflows on this tree.
    head = resolve(REPO, "HEAD")
    for wf, lines in BOT_SOURCES.items():
        try:
            text = read_path_at(REPO, head, wf)
        except Unobservable as e:
            failures.append("bot parity %s: %s" % (wf, e))
            continue
        if text is None:
            failures.append("bot parity: %s missing from the tree" % wf)
            continue
        flat = re.sub(r"\s+", "", text.decode("utf-8", "replace"))
        for line in lines:
            if re.sub(r"\s+", "", line) not in flat:
                failures.append("bot parity: %s no longer contains %s" % (wf, line))
        n += 1

    os.environ.update(saved_env)
    shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print("SELFTEST FAILED:\n  " + "\n  ".join(failures))
        return 1
    print("selftest ok: %d cases" % n)
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
        sys.stderr.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass

    def opt(name, default=None):
        if name in argv:
            i = argv.index(name)
            if i + 1 >= len(argv):
                print("usage: %s needs a value" % name, file=sys.stderr)
                sys.exit(2)
            return argv[i + 1]
        return default

    rev = opt("--rev", "HEAD")
    if "--print-pin" in argv:
        try:
            sys.stdout.write(render(build(REPO, resolve(REPO, rev))))
        except Unobservable as e:
            print("UNOBSERVABLE: %s" % show(str(e)), file=sys.stderr)
            return 2
        return 0
    if "--selftest" in argv:
        return selftest()
    return verify(REPO, rev=rev, base=opt("--base"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
