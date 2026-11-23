"""release-bump-route.py: pr / direct, and a refusal for everything it cannot read.

Plain script: `python3 tests/test_release_bump_route.py`. Each mutant of the
script must turn a case red; the shipped routes file must name mctl-api.
"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release-bump-route.py"
failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(f"{name}: {detail}")


def run(script, image, routes_text):
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        if routes_text is not None:
            (root / "platform-gitops").mkdir()
            (root / "platform-gitops/release-bump-routes.yaml").write_text(routes_text)
        return subprocess.run([sys.executable, str(script), "--image", image, "--root", str(root)],
                              capture_output=True, text=True)


API = "ghcr.io/mctlhq/mctl-api"
OK = "pr_route_images:\n  - ghcr.io/mctlhq/mctl-api\n"
# (name, routes text, image, expected stdout or None for "exit 2, empty stdout")
CASES = [
    ("listed image routes to pr", OK, API, "pr"),
    ("unlisted image routes to direct", OK, "ghcr.io/mctlhq/mctl-docs", "direct"),
    ("a prefix of a listed image is not listed", OK, "ghcr.io/mctlhq/mctl", "direct"),
    ("empty list routes everything direct", "pr_route_images: []\n", API, "direct"),
    ("missing file is a refusal", None, API, None),
    ("unparseable file is a refusal", "pr_route_images: [\n", API, None),
    ("duplicate key is a refusal", "pr_route_images: []\npr_route_images:\n  - " + API + "\n", API, None),
    ("non-list is a refusal", "pr_route_images: " + API + "\n", API, None),
    ("a mapping whose keys look like images is a refusal", "pr_route_images:\n  " + API + ": x\n", API, None),
    ("non-string entry is a refusal", "pr_route_images:\n  - 5\n", API, None),
    ("null list is a refusal", "pr_route_images:\n", API, None),
    ("extra key is a refusal", OK + "other: 1\n", API, None),
    ("duplicate entry is a refusal", "pr_route_images:\n  - " + API + "\n  - " + API + "\n", API, None),
    ("malformed entry is a refusal", "pr_route_images:\n  - 'Not An Image'\n", API, None),
    ("malformed --image is a refusal", OK, "not an image", None),
    ("empty file is a refusal", "", API, None),
]


def verdict(script):
    res = []
    for name, text, image, want in CASES:
        r = run(script, image, text)
        got_ok = (r.returncode == 0 and r.stdout.strip() == want) if want else (r.returncode == 2 and r.stdout == "")
        res.append((name, got_ok, r))
    return res


for name, ok, r in verdict(SCRIPT):
    check(name, ok, f"rc={r.returncode} out={r.stdout!r} err={r.stderr[-200:]!r}")

real = subprocess.run([sys.executable, str(SCRIPT), "--image", API], cwd=ROOT, capture_output=True, text=True)
check("the shipped routes file sends mctl-api to the PR route", real.stdout.strip() == "pr", real.stderr)
real = subprocess.run([sys.executable, str(SCRIPT), "--image", "ghcr.io/mctlhq/mctl-docs"], cwd=ROOT, capture_output=True, text=True)
check("the shipped routes file leaves other images direct", real.stdout.strip() == "direct", real.stderr)

src = SCRIPT.read_text()
MUT = [
    ("unreadable file is treated as no routes",
     "    data = yaml.load((root / ROUTES).read_text(), Loader=_DupKeyLoader)",
     "    try:\n        data = yaml.load((root / ROUTES).read_text(), Loader=_DupKeyLoader)\n    except Exception:\n        return []"),
    ("duplicate keys accepted", "    for k, _ in node.value:\n        key = loader.construct_object(k, deep=True)\n        if key in seen:\n            raise ValueError(f\"duplicate key {key!r}\")",
     "    for k, _ in node.value:\n        key = loader.construct_object(k, deep=True)\n        if False:\n            raise ValueError(f\"duplicate key {key!r}\")"),
    ("non-list accepted", '    if not isinstance(images, list):\n        raise ValueError("pr_route_images is not a list")', "    if False:\n        raise ValueError('x')"),
    ("non-string entry accepted", "        if not isinstance(i, str) or not IMAGE.fullmatch(i):", "        if False:"),
    ("extra keys accepted", 'set(data) != {"pr_route_images"}', 'False'),
    ("prefix match instead of exact", 'return "pr" if image in pr_route_images(root) else "direct"',
     'return "pr" if any(i.startswith(image) for i in pr_route_images(root)) else "direct"'),
    ("failure exits 0 with direct", '        return 2\n    print(out)', '        print("direct")\n        return 0\n    print(out)'),
    ("duplicate entries accepted", '    if len(set(images)) != len(images):\n        raise ValueError("duplicate image entry")', "    pass"),
]
for name, old, new in MUT:
    check(f"mutant anchor exists: {name}", src.count(old) == 1, f"count={src.count(old)}")
    with tempfile.TemporaryDirectory() as d:
        m = pathlib.Path(d) / "release-bump-route.py"
        m.write_text(src.replace(old, new))
        killed = not all(ok for _, ok, _ in verdict(m))
        check(f"mutant killed: {name}", killed)

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("all release-bump-route checks passed")
