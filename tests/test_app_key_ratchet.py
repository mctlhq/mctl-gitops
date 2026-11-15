"""Proof both ways for scripts/app-key-ratchet.py (#1033).

Green on a converged input AND red on each deliberate mutation. A failed,
partial or malformed read must end in UNKNOWN (20), never in clean, and
UNKNOWN outranks a finding.
"""
import base64
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

spec = importlib.util.spec_from_file_location(
    "ratchet", pathlib.Path("scripts/app-key-ratchet.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def b64(s):
    return {"encoding": "base64", "content": base64.b64encode(s.encode()).decode()}


WF_OK = "steps:\n  - with:\n      private-key: ${{ secrets.AGENTS_APP_PRIVATE_KEY }}\n"
WF_PLAIN = "steps:\n  - run: echo hi\n"
ALLOW = {"repos": {"alpha": {".github/workflows/rp.yml": ["AGENTS_APP_PRIVATE_KEY"]}}}


class World:
    """A fake org. fail=(path-substring, exception) makes that read fail."""

    def __init__(self, files=None, truncated=False, pages=None, fail=None,
                 repos=None, tree_override=None):
        self.files = files if files is not None else {
            "alpha": {".github/workflows/rp.yml": WF_OK, ".github/workflows/ci.yml": WF_PLAIN},
            "beta": {".github/workflows/ci.yml": WF_PLAIN},
        }
        self.truncated, self.fail, self.tree_override = truncated, fail, tree_override
        self.repos = repos if repos is not None else [
            {"name": "alpha", "archived": False, "default_branch": "main"},
            {"name": "beta", "archived": False, "default_branch": "main"},
            {"name": "old", "archived": True, "default_branch": "main"},
        ]
        self.pages = pages

    def __call__(self, path, token):
        # The real client follows absolute "next" links from the Link header.
        path = path.removeprefix("https://api.github.com")
        if self.fail and self.fail in path:
            raise R.ReadError(f"{path}: injected failure")
        if path.startswith("/orgs/"):
            if self.pages:
                return self.pages(path)
            return self.repos, ""
        parts = path.split("/")
        repo = parts[3]
        if "/git/trees/" in path:
            if self.tree_override is not None:
                return self.tree_override, ""
            tree = [{"type": "blob", "path": p, "sha": f"{repo}:{p}"} for p in self.files.get(repo, {})]
            tree.append({"type": "blob", "path": "README.md", "sha": "x"})
            return {"tree": tree, "truncated": self.truncated}, ""
        if "/git/blobs/" in path:
            key = path.split("/git/blobs/")[1]
            r, p = key.split(":", 1)
            return b64(self.files[r][p]), ""
        raise AssertionError(path)


def run(world, allow=ALLOW):
    f, u, s, o = R.scan("t", allow, world)
    return R.verdict(f, u), f, u, s, o


# 1. Converged input is clean.
code, f, u, s, o = run(World())
check("converged input is clean", code == 0 and not f and not u, f"{code} {f} {u}")
check("archived repos are not read", "old" not in o, str(o))

# 2. Mutations: each must be red.
w = World(files={"alpha": {".github/workflows/rp.yml": WF_OK, ".github/workflows/new.yml": WF_OK}, "beta": {}})
code, f, u, *_ = run(w)
check("MUTATION new file referencing the key -> findings", code == 10 and len(f) == 1 and "new.yml" in f[0], f"{code} {f}")

w = World(files={"alpha": {".github/workflows/rp.yml": WF_OK}, "beta": {".github/workflows/x.yml": WF_OK}})
code, f, *_ = run(w)
check("MUTATION unlisted repo referencing the key -> findings", code == 10 and "beta" in f[0], f"{code} {f}")

w = World(files={"alpha": {".github/workflows/rp.yml": WF_OK + "      k: ${{ secrets.APP_PRIVATE_KEY }}\n"}, "beta": {}})
code, f, *_ = run(w)
check("MUTATION second key added to an allowed file -> findings", code == 10 and "APP_PRIVATE_KEY" in f[0], f"{code} {f}")

w = World(files={"alpha": {".github/workflows/rp.yml": WF_OK, ".github/workflows/c.yml": "jobs:\n  a:\n    uses: o/r/.github/workflows/w.yml@x\n    secrets: inherit\n"}, "beta": {}})
code, f, *_ = run(w)
check("MUTATION `secrets: inherit` -> findings", code == 10 and "inherit" in f[0], f"{code} {f}")

w = World(files={"alpha": {".github/workflows/rp.yml": WF_OK, ".github/workflows/b.yml": "x: ${{ secrets['AGENTS_APP_PRIVATE_KEY'] }}\n"}, "beta": {}})
code, f, *_ = run(w)
check("MUTATION bracket-form reference -> findings", code == 10 and "b.yml" in f[0], f"{code} {f}")

w = World(files={"alpha": {".github/workflows/rp.yml": WF_OK, ".github/workflows/l.yml": "x: ${{ secrets.agents_app_private_key }}\ny: ${{ secrets['App_Private_Key'] }}\n"}, "beta": {}})
code, f, *_ = run(w)
check("MUTATION lower/mixed-case reference -> findings", code == 10 and len(f) == 2, f"{code} {f}")

for variant in ("secrets: inherit  # why", 'secrets: "inherit"', "secrets: 'inherit'"):
    w = World(files={"alpha": {".github/workflows/rp.yml": WF_OK, ".github/workflows/c.yml": "jobs:\n  a:\n    " + variant + "\n"}, "beta": {}})
    code, f, *_ = run(w)
    check(f"MUTATION inherit variant {variant!r} -> findings", code == 10 and "inherit" in f[0], f"{code} {f}")

# 3. Unreadable is unknown, never clean.
code, f, u, *_ = run(World(truncated=True))
check("truncated tree -> unknown", code == 20 and any("truncated" in x for x in u), f"{code} {u}")

code, f, u, *_ = run(World(tree_override={"tree": "nope", "truncated": False}))
check("malformed tree body -> unknown", code == 20, f"{code} {u}")

code, f, u, *_ = run(World(fail="/git/blobs/"))
check("blob read failure -> unknown", code == 20, f"{code} {u}")

code, f, u, *_ = run(World(fail="/git/trees/"))
check("tree read failure -> unknown, not an empty repo", code == 20 and not f, f"{code} {f} {u}")

code, f, u, *_ = run(World(fail="/orgs/"))
check("repo listing failure -> unknown", code == 20 and u, f"{code} {u}")

code, f, u, *_ = run(World(repos={"message": "boom"}))
check("repo listing that is not a list -> unknown", code == 20, f"{code} {u}")

code, f, u, *_ = run(World(repos=[{"name": "alpha"}]))
check("malformed repo entry -> unknown", code == 20, f"{code} {u}")

# 4. A later page failing after earlier pages succeeded is a failed read.
def pages(path):
    if "page=2" in path:
        raise R.ReadError("page 2 failed")
    return [{"name": "alpha", "archived": False, "default_branch": "main"}], '<https://api.github.com/orgs/mctlhq/repos?page=2>; rel="next"'
w = World(pages=pages)
code, f, u, *_ = run(w)
check("second page failing -> unknown, not a shorter list", code == 20 and u, f"{code} {u}")

# ... and a healthy two-page listing is joined.
calls = []
def two_pages(url, token):
    calls.append(url)
    if "page=2" in url:
        return [{"n": 2}], ""
    return [{"n": 1}], '<https://x/y?page=2>; rel="next"'
check("two pages are joined", R.fetch_list("/p", "t", two_pages) == [{"n": 1}, {"n": 2}], str(calls))

# 5. A repo the allowlist names but the token cannot see is unknown.
w = World(repos=[{"name": "beta", "archived": False, "default_branch": "main"}])
code, f, u, *_ = run(w)
check("allowlisted repo invisible to the token -> unknown", code == 20 and any("alpha" in x for x in u), f"{code} {u}")

# 6. Unknown outranks a finding.
w = World(files={"alpha": {".github/workflows/rp.yml": WF_OK, ".github/workflows/n.yml": WF_OK}, "beta": {}}, fail="/repos/mctlhq/beta/git/trees/")
code, f, u, *_ = run(w)
check("unknown outranks a finding", code == 20 and f and u, f"{code} {f} {u}")

# 7. A stale allowlist entry is reported but is not a failure.
w = World(files={"alpha": {".github/workflows/rp.yml": WF_PLAIN}, "beta": {}})
code, f, u, s, o = run(w)
check("stale allowlist entry is reported, not failed", code == 0 and s, f"{code} {s}")

# 8. main(): no token and an unreadable allowlist are unknown, not clean.
os.environ.pop("GH_TOKEN", None)
check("no token -> unknown", R.main([]) == 20)
os.environ["GH_TOKEN"] = "x"
orig_open = open
real = R.__file__ if hasattr(R, "__file__") else None
with tempfile.TemporaryDirectory() as d:
    R.__file__ = os.path.join(d, "app-key-ratchet.py")
    check("missing allowlist -> unknown", R.main([]) == 20)
    pathlib.Path(d, "app-key-allowlist.json").write_text("{not json")
    check("malformed allowlist -> unknown", R.main([]) == 20)
    pathlib.Path(d, "app-key-allowlist.json").write_text(json.dumps({"repos": []}))
    check("allowlist without a repos map -> unknown", R.main([]) == 20)

# 9. The committed allowlist is well formed.
al = json.loads(pathlib.Path("scripts/app-key-allowlist.json").read_text())
keys = set(al["keys"])
bad = [(r, p, k) for r, fs in al["repos"].items() for p, ks in fs.items() for k in ks if k not in keys | {"inherit"}]
check("committed allowlist is well formed", not bad and al["repos"], str(bad))
check("APP_PRIVATE_KEY is allowed only in mctl-gitops",
      all(r == "mctl-gitops" for r, fs in al["repos"].items() for ks in fs.values() if "APP_PRIVATE_KEY" in ks),
      "APP_PRIVATE_KEY outside mctl-gitops")

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for x in failures:
        print(" -", x)
    sys.exit(1)
print("all checks passed")
