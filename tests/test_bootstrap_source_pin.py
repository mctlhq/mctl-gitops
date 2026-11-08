#!/usr/bin/env python3
"""Structural source pin for platform-gitops/bootstrap (#1033, B4).

This is NOT a semantic check. It does not render the chart and says nothing
about what the generated ApplicationSet, AppProject or Application objects
contain; those are covered by the rendered-output checks. It only answers one
question: did any file that can influence that generation change, appear or
disappear without tests/fixtures/bootstrap-source-pin.json being updated in
the same change? Together with CODEOWNERS routing, that makes every such
change visible as a pin diff in review.

Sources are derived from the chart directory itself, not from a hand list:
every file under platform-gitops/bootstrap (Chart.yaml, values.yaml,
templates/, crds/, files/, charts/ with subcharts, requirements, anything a
template could read through .Files) is pinned by repo-relative path and the
SHA-256 of its bytes. Line endings are normalised (CRLF -> LF). One further,
narrow normalisation exists because a bot legitimately edits these files: in
templates/mctl-platform/ only, the value of a `tag:` line that directly follows
a `repository: ghcr.io/mctlhq/...` line is masked, because gitops-bump.yaml
rewrites exactly that line straight on main. Without it the pin would go red
after every release bump. Everything else in those files stays pinned.

Intentionally NOT pinned by content: the repository inputs the ApplicationSets
glob (platform-gitops/services/*/* and platform-gitops/tenants/*). Their
globs are recorded in the fixture for visibility; the directory contents are
expected to change routinely.

Exit codes: 0 pin matches; 1 drift; 2 input could not be observed (missing
directory, symlink, non-regular file, unreadable file, unreadable or
malformed fixture). Nothing is skipped.

Usage:
  python3 tests/test_bootstrap_source_pin.py             # verify
  python3 tests/test_bootstrap_source_pin.py --print-pin # regenerate fixture
  python3 tests/test_bootstrap_source_pin.py --selftest  # mutation selftest
"""
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHART = "platform-gitops/bootstrap"
FIXTURE = "tests/fixtures/bootstrap-source-pin.json"
BUMP_PREFIX = CHART + "/templates/mctl-platform/"
TAG_RE = re.compile(rb'(?m)^(\s*repository:[ \t]*ghcr\.io/mctlhq/\S+[ \t]*\n\s*tag:[ \t]*)\S+([ \t]*)$')
GLOB_RE = re.compile(r"^\s*-\s*path:\s*(\S+)\s*$")


class Unobservable(Exception):
    pass


def _digest(path, rel=""):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise Unobservable("unreadable %s: %s" % (path, e.strerror))
    data = data.replace(b"\r\n", b"\n")
    if rel.startswith(BUMP_PREFIX):
        data = TAG_RE.sub(rb"\1<bump-managed>\2", data)
    return hashlib.sha256(data).hexdigest()


def collect(root):
    base = os.path.join(root, CHART)
    if not os.path.isdir(base) or os.path.islink(base):
        raise Unobservable("missing or non-directory %s" % CHART)
    files, errors = {}, []

    def onerror(e):
        errors.append("cannot list %s: %s" % (e.filename, e.strerror))

    for dirpath, dirnames, filenames in os.walk(base, onerror=onerror, followlinks=False):
        dirnames.sort()
        for name in dirnames:
            if os.path.islink(os.path.join(dirpath, name)):
                raise Unobservable("symlink %s" % os.path.relpath(os.path.join(dirpath, name), root))
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            try:
                mode = os.lstat(p).st_mode
            except OSError as e:
                raise Unobservable("cannot stat %s: %s" % (rel, e.strerror))
            if not stat.S_ISREG(mode):
                raise Unobservable("not a regular file: %s" % rel)
            files[rel] = _digest(p, rel)
    if errors:
        raise Unobservable("; ".join(errors))
    if not files:
        raise Unobservable("no files found under %s" % CHART)
    return files


def globs(root):
    out = set()
    tdir = os.path.join(root, CHART, "templates", "bootstrap")
    if not os.path.isdir(tdir):
        raise Unobservable("missing %s/templates/bootstrap" % CHART)
    for name in sorted(os.listdir(tdir)):
        if not name.startswith("applicationset-"):
            continue
        with open(os.path.join(tdir, name), encoding="utf-8") as f:
            for line in f:
                m = GLOB_RE.match(line)
                if m and "*" in m.group(1):
                    out.add(m.group(1))
    return sorted(out)


def build(root):
    return {
        "_comment": "Structural pin, not a semantic check. Regenerate with "
                    "python3 tests/test_bootstrap_source_pin.py --print-pin",
        "chart": CHART,
        "sources": collect(root),
        "excluded_unpinned_glob_inputs": globs(root),
    }


def render(pin):
    return json.dumps(pin, indent=2, sort_keys=True) + "\n"


def verify(root):
    """Return 0, 1 or 2."""
    try:
        actual = build(root)
        with open(os.path.join(root, FIXTURE), encoding="utf-8") as f:
            pinned = json.load(f)
        if not isinstance(pinned, dict) or not isinstance(pinned.get("sources"), dict):
            raise Unobservable("malformed fixture")
    except Unobservable as e:
        print("UNOBSERVABLE: %s" % e)
        return 2
    except (OSError, ValueError) as e:
        print("UNOBSERVABLE: fixture unreadable or malformed: %s" % e)
        return 2
    a, p = actual["sources"], pinned["sources"]
    drift = ["added: " + k for k in sorted(set(a) - set(p))]
    drift += ["removed: " + k for k in sorted(set(p) - set(a))]
    drift += ["changed: " + k for k in sorted(set(a) & set(p)) if a[k] != p[k]]
    if pinned.get("excluded_unpinned_glob_inputs") != actual["excluded_unpinned_glob_inputs"]:
        drift.append("glob inputs differ from the recorded list")
    if drift:
        print("DRIFT: bootstrap sources differ from %s:" % FIXTURE)
        for d in drift:
            print("  " + d)
        print("Review the change, then regenerate: python3 tests/test_bootstrap_source_pin.py --print-pin")
        return 1
    print("ok: %d bootstrap sources match the pin" % len(a))
    return 0


def selftest():
    """Each mutation must be red; the unmutated copy must be green."""
    tmp = tempfile.mkdtemp(prefix="bsp-")
    failures = []

    def fresh():
        dst = os.path.join(tmp, "r")
        shutil.rmtree(dst, ignore_errors=True)
        for rel in (CHART, "tests/fixtures"):
            shutil.copytree(os.path.join(REPO, rel), os.path.join(dst, rel), symlinks=True)
        return dst

    def b(root, rel):
        return os.path.join(root, CHART, rel)

    def touch(path, data=b"x\n"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def append(path):
        with open(path, "ab") as f:
            f.write(b"# m\n")

    def _bump(path):
        with open(path, "rb") as f:
            d = f.read()
        n = TAG_RE.sub(rb"\1\"0.0.0-bump\"\2", d)
        if n == d:
            raise SystemExit("selftest: no bump-managed tag line in %s" % path)
        with open(path, "wb") as f:
            f.write(n)

    first_tpl = sorted(k for k in collect(REPO) if "/templates/" in k)[0]
    tpl_rel = first_tpl[len(CHART) + 1:]
    cases = [
        ("real tree", lambda r: None, 0),
        ("modify template", lambda r: append(b(r, tpl_rel)), 1),
        ("bump-bot tag edit stays green", lambda r: _bump(b(r, "templates/mctl-platform/mctl-api.yaml")), 0),
        ("non-tag edit in mctl-platform", lambda r: append(b(r, "templates/mctl-platform/mctl-api.yaml")), 1),
        ("modify values.yaml", lambda r: append(b(r, "values.yaml")), 1),
        ("modify files/ file", lambda r: append(b(r, "files/usage-pricing/claude-firstparty.json")), 1),
        ("add template", lambda r: touch(b(r, "templates/system/new.yaml")), 1),
        ("add crds file", lambda r: touch(b(r, "crds/new.yaml")), 1),
        ("add subchart file", lambda r: touch(b(r, "charts/sub/templates/x.yaml")), 1),
        ("add subchart Chart.yaml", lambda r: touch(b(r, "charts/sub/Chart.yaml")), 1),
        ("remove template", lambda r: os.remove(b(r, tpl_rel)), 1),
        ("rename template", lambda r: os.rename(b(r, tpl_rel), b(r, tpl_rel + ".bak")), 1),
        ("symlink file", lambda r: os.symlink(b(r, "values.yaml"), b(r, "templates/link.yaml")), 2),
        ("symlink dir", lambda r: os.symlink(b(r, "files"), b(r, "charts-link")), 2),
        ("missing chart dir", lambda r: shutil.rmtree(b(r, "")), 2),
        ("missing fixture", lambda r: os.remove(os.path.join(r, FIXTURE)), 2),
        ("unreadable file", lambda r: os.chmod(b(r, "values.yaml"), 0), 2),
    ]
    for name, mutate, want in cases:
        root = fresh()
        mutate(root)
        if name == "unreadable file" and os.geteuid() == 0:
            continue  # root reads mode-0 files; cannot be simulated
        got = verify(root)
        if got != want:
            failures.append("%s: want exit %d, got %d" % (name, want, got))
    shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print("SELFTEST FAILED:\n  " + "\n  ".join(failures))
        return 1
    print("selftest ok: %d cases" % len(cases))
    return 0


def main(argv):
    if "--print-pin" in argv:
        try:
            sys.stdout.write(render(build(REPO)))
        except Unobservable as e:
            print("UNOBSERVABLE: %s" % e, file=sys.stderr)
            return 2
        return 0
    if "--selftest" in argv:
        return selftest()
    rc = verify(REPO)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
