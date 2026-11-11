"""Bootstrap-aware version hold of release-gate.py (mctlhq/mctl-gitops#2528).

mctl-api keeps its Helm values in a `values: |` block scalar of a Helm template,
so the plain `image.tag` reader cannot see it. These cases run the real script
against copies of the real bootstrap file. Plain script like the other release
gate tests: `python3 tests/test_release_gate_bootstrap_hold.py`.

Every negative case is mutation-verified: MUTANTS lists one deliberate break of
the script per rule, and each must turn at least one named case red.
"""
import atexit
import copy
import itertools
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release-gate.py"
GATE = "platform-gitops/release-gates.yaml"
API = "platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml"
REAL_POLICY = yaml.safe_load((ROOT / GATE).read_text())
REAL_API = (ROOT / API).read_text()
# The live tag moves with every allowed mctl-api release: derive it, never pin it.
_m = re.search(r"repository: ghcr\.io/mctlhq/mctl-api\n\s+(tag: [^\n]+)", REAL_API)
assert _m, "no mctl-api image tag in the bootstrap file"
OLD_TAG = _m.group(1)
_WORK = pathlib.Path(tempfile.mkdtemp(prefix="hold-test-"))
atexit.register(shutil.rmtree, _WORK, ignore_errors=True)  # every tree lives under _WORK
_N = itertools.count()
GOOD = {"version": "4.155.0", "grant": "mctlhq/mctl-gitops#9999", "approved_by": "mashkovd",
        "expires": "2099-01-01"}
REFUSED = 6


def tree(api_text=REAL_API, allow=(), policy=None, drop_api=False):
    d = _WORK / f"t{next(_N)}"
    d.mkdir()
    pol = copy.deepcopy(policy if policy is not None else REAL_POLICY)
    if isinstance(pol, dict) and pol.get("version_holds"):
        pol["version_holds"][0]["allow"] = [dict(a, expires=_date(a["expires"])) for a in allow]
    for rel in [GATE] + [p for g in REAL_POLICY["gates"] for p in g["paths"]]:
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        if rel != GATE:
            (d / rel).symlink_to(ROOT / rel)  # read-only inputs: no copy per tree
    (d / GATE).write_text(yaml.safe_dump(pol))
    if not drop_api:
        (d / API).parent.mkdir(parents=True, exist_ok=True)
        (d / API).write_text(api_text)
    return d


def _date(v):
    import datetime
    return datetime.date.fromisoformat(v) if isinstance(v, str) and re.fullmatch(r"\d{4}-\d\d-\d\d", v) else v


def gate(script, d, *args, marker=None):
    """Exit code; with `marker`, -1 unless that text is in the script's stderr (the reason matters)."""
    r = subprocess.run([sys.executable, str(script), "--root", str(d), *args], capture_output=True, text=True)
    return r.returncode if marker is None or marker in r.stderr else -1


def bump(script, d, new_tag, *extra):
    return gate(script, d, "check", "--files", API, "--new-tag", new_tag, *extra)


def verify(script, d):
    return gate(script, d, "verify")


def with_tag(tag_line):
    assert REAL_API.count(OLD_TAG) == 1
    return REAL_API.replace(OLD_TAG, tag_line)


def diff_rc(script, mutate, parent_policy=None, marker=None):
    """Parent commit = real policy + real bootstrap file; head = parent + mutate(dir). Exit code of `diff`."""
    d = _WORK / f"d{next(_N)}"
    d.mkdir()
    for rel in [GATE, API] + [p for g in REAL_POLICY["gates"] for p in g["paths"]]:
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, d / rel)
    if parent_policy is not None:
        (d / GATE).write_text(yaml.safe_dump(parent_policy))

    def git(*a):
        subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                       check=True, capture_output=True)
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base", "--no-gpg-sign")
    mutate(d)
    git("add", "-A")
    git("commit", "-qm", "head", "--no-gpg-sign", "--allow-empty")
    return gate(script, d, "diff", "--base", "HEAD~1", "--head", "HEAD", marker=marker)


def set_tag(d, tag):
    (d / API).write_text(with_tag(f'tag: "{tag}"'))


def policy_with(allow):
    pol = copy.deepcopy(REAL_POLICY)
    pol["version_holds"][0]["allow"] = [dict(a, expires=_date(a["expires"])) for a in allow]
    return pol


def cases(script):
    """(name, got, want) triples; a case is green when got == want."""
    out = []

    def add(name, got, want):
        out.append((name, got, want))

    # --- positive controls: ordinary releases still pass ---------------------
    add("positive: real tree verifies", verify(script, tree()), 0)
    add("positive: mctl-api 4.154.1 bump passes", bump(script, tree(), "4.154.1"), 0)
    add("positive: mctl-api 4.99.0 (older) bump passes", bump(script, tree(), "4.99.0"), 0)
    add("positive: other service plain image.tag bump passes",
        gate(script, tree(), "check", "--files", "platform-gitops/services/labs/x/values.yaml", "--new-tag", "9.9.9"), 0)
    add("positive: 4.155.0 with a valid allow passes (bump)", bump(script, tree(allow=[GOOD]), "4.155.0"), 0)
    add("positive: 4.155.0 in tree with a valid allow passes (verify)",
        verify(script, tree(with_tag('tag: "4.155.0"'), allow=[GOOD])), 0)

    # --- negative: held version -------------------------------------------------
    add("neg: bump to 4.155.0 without an allow record", bump(script, tree(), "4.155.0"), REFUSED)
    add("neg: bump to 4.200.0 (any version above the hold) without an allow", bump(script, tree(), "4.200.0"), REFUSED)
    add("neg: 4.155.0 already in the tree without an allow (verify)", verify(script, tree(with_tag('tag: "4.155.0"'))), REFUSED)
    add("neg: allow record for a different version", bump(script, tree(allow=[dict(GOOD, version="4.155.1")]), "4.155.0"), REFUSED)
    add("neg: allow record expired", bump(script, tree(allow=[dict(GOOD, expires="2000-01-01")]), "4.155.0"), REFUSED)
    add("neg: allow record without approved_by (unsigned)",
        bump(script, tree(allow=[{k: v for k, v in GOOD.items() if k != "approved_by"}]), "4.155.0"), REFUSED)
    add("neg: allow record without grant",
        bump(script, tree(allow=[{k: v for k, v in GOOD.items() if k != "grant"}]), "4.155.0"), REFUSED)
    add("neg: allow record with a non-date expiry", bump(script, tree(allow=[dict(GOOD, expires="soon")]), "4.155.0"), REFUSED)
    add("neg: two allow records for one version", bump(script, tree(allow=[GOOD, GOOD]), "4.155.0"), REFUSED)
    add("neg: non-semver new tag", bump(script, tree(), "latest"), REFUSED)
    add("neg: prerelease new tag", bump(script, tree(), "4.155.0-rc.1"), REFUSED)

    # --- negative: could not observe the bootstrap tag ------------------------------
    add("neg: bootstrap file missing", bump(script, tree(drop_api=True), "4.154.1"), REFUSED)
    add("neg: bootstrap file missing (verify)", verify(script, tree(drop_api=True)), REFUSED)
    add("neg: no values block scalar", bump(script, tree(REAL_API.replace("values: |", "values: x", 1)), "4.154.1"), REFUSED)
    add("neg: two values block scalars",
        bump(script, tree(REAL_API.replace("  ignoreDifferences:", "  x:\n    values: |\n      a: 1\n  ignoreDifferences:", 1)), "4.154.1"), REFUSED)
    add("neg: malformed block scalar (broken YAML inside)",
        bump(script, tree(with_tag(OLD_TAG + '\n            bad: [unclosed')), "4.154.1"), REFUSED)
    add("neg: duplicate image.tag line",
        bump(script, tree(with_tag(OLD_TAG + '\n            tag: "4.155.0"')), "4.154.1"), REFUSED)
    add("neg: duplicate image.tag line, verify",
        verify(script, tree(with_tag(OLD_TAG + '\n            tag: "4.155.0"'))), REFUSED)
    second_ref = REAL_API.replace(
        "          ingress:\n",
        "          sidecar:\n            repository: ghcr.io/mctlhq/mctl-api\n            tag: \"4.155.0\"\n          ingress:\n", 1)
    add("neg: second image reference with its own tag", bump(script, tree(second_ref), "4.154.1"), REFUSED)
    add("neg: tag is an unquoted number", bump(script, tree(with_tag("tag: 4.155")), "4.154.1"), REFUSED)
    add("neg: tag is empty", bump(script, tree(with_tag("tag:")), "4.154.1"), REFUSED)
    # The text pair the bump rewrites sits under another key, while `image` names a different repository.
    moved = REAL_API.replace("          image:\n            repository: ghcr.io/mctlhq/mctl-api\n",
                             "          image:\n            repository: ghcr.io/other/img\n            tag: \"1.0.0\"\n"
                             "          sidecar:\n            repository: ghcr.io/mctlhq/mctl-api\n", 1)
    assert moved != REAL_API
    add("neg: image.repository is another image", bump(script, tree(moved), "4.154.1"), REFUSED)

    # --- negative: the policy itself -------------------------------------------------
    nohold = copy.deepcopy(REAL_POLICY)
    del nohold["version_holds"]
    add("neg: policy without a version_holds section", bump(script, tree(policy=nohold), "4.154.1"), REFUSED)
    badhold = copy.deepcopy(REAL_POLICY)
    badhold["version_holds"][0]["held_from"] = "later"
    add("neg: malformed hold (held_from not X.Y.Z)", bump(script, tree(policy=badhold), "4.154.1"), REFUSED)

    # --- the policy is read from a trusted revision, not the tree --------------------
    d = tree()
    git = lambda *a: subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True)  # noqa: E731
    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base", "--no-gpg-sign")
    git("branch", "-M", "trusted")
    pol = yaml.safe_load((d / GATE).read_text())
    pol["version_holds"][0]["allow"] = [dict(GOOD, expires=_date(GOOD["expires"]))]
    (d / GATE).write_text(yaml.safe_dump(pol))  # a pending commit grants itself an allow
    add("neg: self-granted allow in the tree, trusted rev has none",
        gate(script, d, "check", "--files", API, "--new-tag", "4.155.0", "--policy-rev", "trusted"), REFUSED)
    add("pos: same tree without --policy-rev trusts the tree", gate(script, d, "check", "--files", API, "--new-tag", "4.155.0"), 0)
    add("neg: policy rev does not exist",
        gate(script, d, "check", "--files", API, "--new-tag", "4.154.1", "--policy-rev", "nosuchrev"), REFUSED)
    (d / API).write_text(with_tag('tag: "4.155.0"'))
    add("neg: verify of 4.155.0 with --policy-rev trusted", gate(script, d, "verify", "--policy-rev", "trusted"), REFUSED)
    (d / API).write_text(REAL_API)
    add("pos: verify of 4.154.0 with --policy-rev trusted", gate(script, d, "verify", "--policy-rev", "trusted"), 0)
    # --- expiry gates new writes only; the deployed state stays verifiable ---------------
    expired = dict(GOOD, expires="2000-01-01")
    deployed = with_tag('tag: "4.155.0"')
    add("pos: expired allow, 4.155.0 already deployed: verify stays green",
        verify(script, tree(deployed, allow=[expired])), 0)
    add("neg: expired allow, a new bump to 4.155.0 is refused", bump(script, tree(allow=[expired]), "4.155.0"), REFUSED)
    add("neg: expired allow, bump to 4.155.0 when 4.155.0 is already deployed is refused",
        bump(script, tree(deployed, allow=[expired]), "4.155.0"), REFUSED)
    add("neg: expired allow for 4.155.0 does not cover a deployed 4.155.1",
        verify(script, tree(with_tag('tag: "4.155.1"'), allow=[expired])), REFUSED)

    # --- bump mode judges only the image being bumped --------------------------------------
    add("pos: bump of another image through a glob over the held file is not judged",
        bump(script, tree(), "4.155.0", "--image", "ghcr.io/mctlhq/mctl-portal"), 0)
    add("neg: bump of the held image (named) is judged", bump(script, tree(), "4.155.0", "--image", "ghcr.io/mctlhq/mctl-api"), REFUSED)
    add("neg: image not named: judged (fail closed)", bump(script, tree(), "4.155.0"), REFUSED)

    # --- the post-push watcher (`diff`): the parent policy judges the pushed content -------
    add("diff pos: no change", diff_rc(script, lambda d: None), 0)
    add("diff pos: push of 4.154.1", diff_rc(script, lambda d: set_tag(d, "4.154.1")), 0)
    add("diff neg: push of 4.155.0, no allow in the parent policy", diff_rc(script, lambda d: set_tag(d, "4.155.0")), REFUSED)
    add("diff pos: push of 4.155.0, valid allow already in the parent policy",
        diff_rc(script, lambda d: set_tag(d, "4.155.0"), policy_with([GOOD])), 0)
    add("diff neg: push of 4.155.0, allow expired in the parent policy",
        diff_rc(script, lambda d: set_tag(d, "4.155.0"), policy_with([expired])), REFUSED)

    def grant_and_bump(d):  # one commit grants itself the allow and ships the version
        (d / GATE).write_text(yaml.safe_dump(policy_with([GOOD])))
        set_tag(d, "4.155.0")
    add("diff neg: one push adds the allow and bumps the tag", diff_rc(script, grant_and_bump), REFUSED)

    def remove_file(d):
        (d / API).unlink()
    add("diff neg: push removes the held file (violation, not unknown)", diff_rc(script, remove_file, marker="held file was removed"), REFUSED)

    def file_to_dir(d):  # the path becomes a directory: the read itself fails
        (d / API).unlink()
        (d / API).mkdir()
        (d / API / "x").write_text("x")
    add("diff unknown: held file unreadable in the pushed tree", diff_rc(script, file_to_dir, marker="is not a regular file"), 7)

    nohold = copy.deepcopy(REAL_POLICY)
    del nohold["version_holds"]
    add("diff unknown: parent policy without version_holds", diff_rc(script, lambda d: None, nohold, marker="parent gate policy unreadable"), 7)
    add("diff unknown: pushed block no longer parses", diff_rc(script, lambda d: (d / API).write_text(with_tag("tag: ["))), 7)
    return out


def wiring():
    """Both bump workflows: check from the trusted policy, verify right before git push."""
    out = []
    for label, name in (("gitops-bump", "gitops-bump.yaml"), ("release-deploy", "release-deploy.yaml")):
        wf = (ROOT / ".github/workflows" / name).read_text()
        chk = re.search(r'"scripts/release-gate\.py", "check",\s*\n\s*"--files", \*\[os\.path\.normpath\(f\) for f in files\], '
                        r'"--new-tag", new_tag,\s*"--policy-rev", "origin/main", "--image", image_name\]', wf)
        out.append((f"wiring: {label} check reads the policy from origin/main and names the image", bool(chk), True))
        pushes = [m.start() for m in re.finditer(r"^\s+(?:if )?git push\b", wf, re.M)]
        vers = [m.start() for m in re.finditer(r"release-gate\.py verify --policy-rev origin/main", wf)]
        out.append((f"wiring: {label} verify reads the policy from origin/main", len(vers) == 1, True))
        out.append((f"wiring: {label} verify precedes the push",
                    len(pushes) == 1 and len(vers) == 1 and vers[0] < pushes[0], True))
        out.append((f"wiring: {label} no unpinned verify left", "release-gate.py verify\n" not in wf and "release-gate.py verify |" not in wf, True))
    return out


MUTANTS = {
    # name: (old, new, a case that must go red)
    "hold ignored": ('if v < _semver(h["held_from"]):  # type: ignore[operator]\n            continue',
                     "if True:\n            continue", "neg: bump to 4.155.0 without an allow record"),
    "bump judged on the current tag, not the new one": ("version = current if files is None else new_tag", "version = current",
                                                        "neg: bump to 4.155.0 without an allow record"),
    "allow matches any version": ('if a["version"] == version]', "if True]", "neg: allow record for a different version"),
    "expiry ignored": ('elif files is not None and rec[0]["expires"] < today:', "elif False:", "neg: allow record expired"),
    "unsigned allow accepted": ('all(isinstance(a.get(k), str) and a[k].strip() for k in ("grant", "approved_by"))', "True",
                                "neg: allow record without approved_by (unsigned)"),
    "duplicate allow accepted": ('if a["version"] in seen:', "if False:", "neg: two allow records for one version"),
    "unreadable tag skipped": ('''out.append(f"UNKNOWN: {h['file']} image.tag unreadable for hold {h['name']}: {type(exc).__name__}: {exc}")
            continue''', "continue", "neg: bootstrap file missing"),
    "duplicate key accepted": ("if key in seen:\n            raise", "if False:\n            raise", "neg: duplicate image.tag line"),
    "second image reference accepted": ('if len(pat.findall(text)) != 1 or text.count(hold["repository"]) != 1:', "if False:",
                                        "neg: second image reference with its own tag"),
    "repository not compared": ('img.get("repository") != hold["repository"]', "False", "neg: image.repository is another image"),
    "non-string tag accepted": ("if not isinstance(tag, str):", "if False:", "neg: tag is an unquoted number"),
    "missing version_holds tolerated": ('holds = doc.get("version_holds") if isinstance(doc, dict) else None',
                                        'holds = (doc.get("version_holds") if isinstance(doc, dict) else None) or []',
                                        "neg: policy without a version_holds section"),
    "policy rev ignored": ("    if rev is None:\n        return _load(root, GATE)", "    if True:\n        return _load(root, GATE)",
                           "neg: self-granted allow in the tree, trusted rev has none"),
    "expiry applied to the deployed state": ("elif files is not None and rec[0]", "elif rec[0]", "pos: expired allow, 4.155.0 already deployed: verify stays green"),
    "expiry ignored for new writes of an already-deployed version": ('elif files is not None and rec[0]["expires"] < today:',
        "elif False:", "neg: expired allow, bump to 4.155.0 when 4.155.0 is already deployed is refused"),
    "every bump judged whatever the image": ('(image is not None and image != h["repository"])', "False",
                                             "pos: bump of another image through a glob over the held file is not judged"),
    "an unnamed image is skipped": ('image is not None and image != h["repository"]', "image != h[\"repository\"]",
                                    "neg: image not named: judged (fail closed)"),
    "diff: held file not copied into the scratch tree": ("            (tmp / p).write_bytes(h)\n            # A push that changes",
        "            # A push that changes", "diff neg: push of 4.155.0, no allow in the parent policy"),
    "diff: removed held file not reported": ('viol.append(f"{p}: held file was removed")\n                continue\n            (tmp / p).parent',
        'continue\n            (tmp / p).parent', "diff neg: push removes the held file (violation, not unknown)"),
    "diff: failed read of the held file skipped": ('unk.append(f"{p}: {exc}")\n                continue\n            if h is None:',
        'continue\n            if h is None:', "diff unknown: held file unreadable in the pushed tree"),
    "diff: a changed held tag is not a write": ("            if new_t != old_tag:", "            if False:",
                                                  "diff neg: push of 4.155.0, allow expired in the parent policy"),
    "diff: parent policy not required to hold version_holds": ('holds = _holds(base_policy)', 'holds = (base_policy.get("version_holds") or []) if isinstance(base_policy, dict) else []',
                                                              "diff unknown: parent policy without version_holds"),
    "several values blocks accepted": ("if len(starts) != 1:", "if len(starts) < 1:", "neg: two values block scalars"),
}


def main():
    failures = []

    def report(name, ok, detail=""):
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            failures.append(f"{name}: {detail}")

    for name, got, want in cases(SCRIPT) + wiring():
        report(name, got == want, f"got {got}, want {want}")

    src = SCRIPT.read_text()
    for name, (old, new, red) in MUTANTS.items():
        report(f"mutant anchor exists: {name}", src.count(old) == 1, f"count={src.count(old)}")
        with tempfile.TemporaryDirectory() as t:
            m = pathlib.Path(t) / "release-gate.py"
            m.write_text(src.replace(old, new))
            red_cases = [n for n, g, w in cases(m) if g != w]
        report(f"mutant killed: {name} (red: {red!r})", red in red_cases, f"red cases: {red_cases}")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
