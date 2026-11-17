"""Ledger mode of the mctl-api version hold (mctlhq/mctl-api#1022 S4).

Runs the real release-gate.py against copies of the real bootstrap file:
`python3 tests/test_release_gate_ledger_hold.py`.

shadow:  the YAML allow records still decide (unchanged behaviour).
enforce: a bump needs the approved ledger digest equal to the digest written,
         the allow records are ignored, verify accepts the held tag, the
         offline diff no longer judges the tag by allow records, and a pull
         request may change the tag only as the release bot's bump PR, judged
         by the policy at the base.

Every negative case is mutation-verified: MUTANTS lists one deliberate break
of the script per rule, and each must turn at least one case red.
"""
import atexit
import copy
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
LIVE_API = (ROOT / API).read_text()
_m = re.search(r"repository: ghcr\.io/mctlhq/mctl-api\n\s+(tag: [^\n]+)", LIVE_API)
assert _m, "no mctl-api image tag in the bootstrap file"
BASE_API = LIVE_API.replace(_m.group(1), 'tag: "4.154.0"')
NEW_API = LIVE_API.replace(_m.group(1), 'tag: "4.200.0"')
D1, D2 = "sha256:" + "a" * 64, "sha256:" + "b" * 64
BOT, PREFIX = "mctl-gitops-pr[bot]", "release-bump/"
REFUSED, UNKNOWN = 6, 7
_WORK = pathlib.Path(tempfile.mkdtemp(prefix="ledger-hold-test-"))
atexit.register(shutil.rmtree, _WORK, ignore_errors=True)
_n = [0]


def policy(mode="enforce", allow=(), ledger=None):
    pol = copy.deepcopy(yaml.safe_load((ROOT / GATE).read_text()))
    h = pol["version_holds"][0]
    h["allow"] = [dict(a) for a in allow]
    if mode is None:
        h.pop("ledger", None)
    else:
        h["ledger"] = {"mode": mode, "wait_minutes": 60, "bump_pr_author": BOT, "bump_pr_branch_prefix": PREFIX,
                       **(ledger or {})}
    return pol


def tree(pol, api=BASE_API):
    _n[0] += 1
    d = _WORK / f"t{_n[0]}"
    for rel in [p for g in pol["gates"] for p in g["paths"]]:
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, d / rel)  # real files: the git-based modes reject symlinks
    (d / GATE).parent.mkdir(parents=True, exist_ok=True)
    (d / GATE).write_text(yaml.safe_dump(pol))
    (d / API).parent.mkdir(parents=True, exist_ok=True)
    (d / API).write_text(api)
    return d


def git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})


def repo(base_pol, head_pol, head_api=NEW_API):
    """A git repo with a base commit and a head commit; returns (dir, base, head)."""
    d = tree(base_pol)
    git(d, "init", "-q")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (d / GATE).write_text(yaml.safe_dump(head_pol))
    (d / API).write_text(head_api)
    git(d, "add", "-A")
    git(d, "commit", "-qm", "head", "--allow-empty")
    head = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return d, base, head


def run(script, d, *args):
    r = subprocess.run([sys.executable, str(script), "--root", str(d), *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def bump(script, d, *extra):
    return run(script, d, "check", "--files", API, "--new-tag", "4.200.0", *extra)[0]


REC = {"version": "4.200.0", "grant": "mctlhq/mctl-gitops#1", "approved_by": "mashkovd"}


def rec():
    import datetime
    return dict(REC, expires=datetime.date(2099, 1, 1))


def cases(script):
    """(name, actual, expected) for every rule."""
    out = []
    t = tree(policy("shadow"))
    out.append(("shadow: no allow record refuses", bump(script, t, "--new-digest", D1, "--ledger-approved-digest", D1),
                REFUSED))
    t = tree(policy("shadow", allow=[rec()]))
    out.append(("shadow: allow record passes", bump(script, t, "--new-digest", D1), 0))
    t = tree(policy("enforce"))
    out.append(("enforce: matching ledger digest passes without a record",
                bump(script, t, "--new-digest", D1, "--ledger-approved-digest", D1), 0))
    out.append(("enforce: no ledger digest refuses", bump(script, t, "--new-digest", D1), REFUSED))
    out.append(("enforce: ledger digest for another image refuses",
                bump(script, t, "--new-digest", D1, "--ledger-approved-digest", D2), REFUSED))
    out.append(("enforce: unknown written digest refuses", bump(script, t, "--ledger-approved-digest", D1), REFUSED))
    out.append(("enforce: malformed digests refuse",
                bump(script, t, "--new-digest", "sha256:x", "--ledger-approved-digest", "sha256:x"), REFUSED))
    t = tree(policy("enforce", allow=[rec()]))
    out.append(("enforce: an allow record alone no longer passes", bump(script, t, "--new-digest", D1), REFUSED))
    t = tree(policy("enforce"), api=NEW_API)
    out.append(("enforce: verify accepts the held tag without a record", run(script, t, "verify")[0], 0))
    t = tree(policy("shadow"), api=NEW_API)
    out.append(("shadow: verify still needs a record", run(script, t, "verify")[0], REFUSED))
    for name, bad in (("mode", {"mode": "on"}), ("wait 0", {"wait_minutes": 0}), ("wait bool", {"wait_minutes": True}),
                      ("no author", {"bump_pr_author": ""}), ("no prefix", {"bump_pr_branch_prefix": None})):
        # An allow record is present, so a block silently treated as "no
        # ledger" would pass through the YAML; it must refuse instead.
        t = tree(policy("enforce", allow=[rec()], ledger=bad))
        out.append((f"malformed ledger block ({name}) refuses",
                    bump(script, t, "--new-digest", D1, "--ledger-approved-digest", D1), REFUSED))
    t = tree(policy("enforce"))
    code, text = run(script, t, "ledger-holds")
    out.append(("ledger-holds lists the enforced hold",
                0 if code == 0 and text.strip() == "enforce ghcr.io/mctlhq/mctl-api 4.154.0" else 1, 0))
    t = tree(policy(None))
    code, text = run(script, t, "ledger-holds")
    out.append(("ledger-holds lists nothing without a ledger block", 0 if code == 0 and not text.strip() else 1, 0))

    d, b, h = repo(policy("enforce"), policy("enforce"))
    pi = lambda a, br: run(script, d, "pr-identity", "--base", b, "--head", h, "--author", a, "--branch", br)[0]  # noqa: E731
    out.append(("pr-identity: release bot bump PR passes", pi(BOT, "release-bump/mctl-api-4.200.0"), 0))
    out.append(("pr-identity: a person may not change the tag", pi("mashkovd", "release-bump/mctl-api-4.200.0"),
                REFUSED))
    out.append(("pr-identity: the bot from another branch may not", pi(BOT, "feat/x"), REFUSED))
    out.append(("diff: enforced tag change is not judged by records",
                run(script, d, "diff", "--base", b, "--head", h)[0], 0))
    d, b, h = repo(policy("enforce"), policy("shadow"))
    out.append(("pr-identity: policy is read from the base, not the PR",
                run(script, d, "pr-identity", "--base", b, "--head", h, "--author", "mashkovd", "--branch", "x")[0],
                REFUSED))
    d, b, h = repo(policy("shadow"), policy("shadow"))
    out.append(("pr-identity: shadow mode does not judge authors",
                run(script, d, "pr-identity", "--base", b, "--head", h, "--author", "mashkovd", "--branch", "x")[0], 0))
    out.append(("diff: shadow tag change without a record is a violation",
                run(script, d, "diff", "--base", b, "--head", h)[0], REFUSED))
    d, b, h = repo(policy("enforce"), policy("enforce"), head_api=BASE_API)
    out.append(("pr-identity: a PR that leaves the tag alone passes",
                run(script, d, "pr-identity", "--base", b, "--head", h, "--author", "mashkovd", "--branch", "x")[0], 0))
    d, b, h = repo(policy("enforce"), policy("enforce"), head_api="not yaml: [")
    out.append(("pr-identity: unreadable head tag is unknown",
                run(script, d, "pr-identity", "--base", b, "--head", h, "--author", BOT, "--branch", PREFIX + "x")[0],
                UNKNOWN))
    return out


MUTANTS = {
    "enforce ignores the digest match": ("            elif ledger_digest != new_digest:", "            elif False:"),
    "enforce falls back to allow records": ("        if _enforced(h):\n            if files is None:",
                                            "        if False:\n            if files is None:"),
    "unknown written digest accepted": ("            if not (isinstance(new_digest, str) and DIGEST.fullmatch(new_digest)):",
                                        "            if False:"),
    "mode not validated": ('    if not isinstance(led, dict) or led.get("mode") not in LEDGER_MODES:',
                           "    if not isinstance(led, dict):"),
    "author not checked": ('            if author != led["bump_pr_author"] or not branch.startswith(led["bump_pr_branch_prefix"]):',
                           '            if not branch.startswith(led["bump_pr_branch_prefix"]):'),
    "branch not checked": ('            if author != led["bump_pr_author"] or not branch.startswith(led["bump_pr_branch_prefix"]):',
                           '            if author != led["bump_pr_author"]:'),
    "policy read from head": ('        raw = _blob(repo, base, GATE)\n        if raw is None:\n            return [f"{GATE} absent at {base}"]',
                              '        raw = _blob(repo, head, GATE)\n        if raw is None:\n            return [f"{GATE} absent at {base}"]'),
    "diff judges enforced tag by records": ("            if new_t != old_tag and not _enforced(hold):",
                                            "            if new_t != old_tag:"),
}


def main() -> int:
    bad = [(n, a, e) for n, a, e in cases(SCRIPT) if a != e]
    for n, a, e in bad:
        print(f"FAIL {n}: got {a}, want {e}")
    src = SCRIPT.read_text()
    missed = []
    for name, (old, new) in MUTANTS.items():
        assert src.count(old) == 1, f"mutant {name!r} does not apply"
        m = _WORK / f"mutant{abs(hash(name))}.py"
        m.write_text(src.replace(old, new))
        if all(a == e for _, a, e in cases(m)):
            missed.append(name)
    for name in missed:
        print(f"FAIL mutant survived: {name}")
    total = len(cases(SCRIPT))
    print(f"ledger hold: {total - len(bad)}/{total} cases, {len(MUTANTS) - len(missed)}/{len(MUTANTS)} mutants caught")
    return 1 if bad or missed else 0


if __name__ == "__main__":
    sys.exit(main())
