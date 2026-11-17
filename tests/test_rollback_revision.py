"""wft-rollback-revision restore-values step (mctlhq/mctl-api#1048).

The script is extracted from the template and run against a real local bare
repository (git is stubbed only to redirect `clone` there with full history).
Every refusal must leave origin untouched; the happy path must restore the
whole values.yaml and report the new commit. Mutants at the end remove each
guard in turn and require the matching scenario to stop holding.
"""
import os, pathlib, shutil, stat, subprocess, tempfile
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TPL = ROOT / "platform-gitops/argo-workflows/cluster-templates/wft-rollback-revision.yaml"
GUARD_REL = "platform-gitops/argo-workflows/scripts/release-gate-guard.sh"
GATE_REL = "platform-gitops/release-gates.yaml"
REAL_GIT = shutil.which("git")
SRC = [t for t in yaml.safe_load(TPL.read_text())["spec"]["templates"] if t["name"] == "restore-values"][0]["script"]["source"]
VAL = "platform-gitops/services/labs/app/values.yaml"
D1 = "sha256:" + "a" * 64
D2 = "sha256:" + "b" * 64
failures = []


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


def values(digest, extra=""):
    return ("image:\n  repository: ghcr.io/mctlhq/app\n  tag: \"1.0.0\"\n"
            f"  digest: {digest}\n{extra}")


class Box:
    def __init__(self, d):
        self.tmp = pathlib.Path(d)
        self.origin = self.tmp / "origin.git"
        self.env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        self.g("init", "-q", "--bare", "-b", "main", str(self.origin))
        self.w = self.tmp / "seed"
        for rel in ("platform-gitops/argo-workflows/scripts",):
            shutil.copytree(ROOT / rel, self.w / rel)
        shutil.copy(ROOT / GATE_REL, self.w / GATE_REL) if (ROOT / GATE_REL).exists() else None
        self.g("init", "-q", "-b", "main", cwd=self.w)
        self.commit(values(D1, "  # old\nresources:\n  limits:\n    cpu: 100m\n"))
        self.target = self.sha()
        self.commit(values(D2, "resources:\n  limits:\n    cpu: 500m\n"))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        stub = self.bin / "git"
        stub.write_text(f"#!/bin/sh\nif [ \"$1\" = clone ]; then shift\n"
                        f"  while [ \"${{1#-}}\" != \"$1\" ]; do shift; done\n"
                        f"  exec '{REAL_GIT}' clone -q 'file://{self.origin}' \"$2\"\nfi\nexec '{REAL_GIT}' \"$@\"\n")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        (self.tmp / "key").write_text("k\n")
        (self.tmp / "home").mkdir()

    def g(self, *a, cwd=None):
        return subprocess.run([REAL_GIT, *a], cwd=cwd, env=self.env, check=True, capture_output=True, text=True).stdout

    def commit(self, text, rel=VAL):
        p = self.w / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.g("add", "-A", cwd=self.w)
        self.g("commit", "-q", "-m", "c", cwd=self.w)
        self.g("push", "-q", str(self.origin), "main", cwd=self.w)

    def sha(self):
        return self.g("rev-parse", "HEAD", cwd=self.w).strip()

    def head(self):
        return self.g("--git-dir", str(self.origin), "rev-parse", "main").strip()

    def show(self, rev="main"):
        return self.g("--git-dir", str(self.origin), "show", f"{rev}:{VAL}")

    def run(self, mutate=None, **p):
        src = SRC if not mutate else mutate(SRC)
        src = src.replace("/tmp/", str(self.tmp) + "/w-").replace("/secrets/deploy-key/ssh-privatekey", str(self.tmp / "key"))
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.tmp / "home"),
               "GITOPS_ORG": "mctlhq", "GITOPS_REPO": "mctl-gitops",
               "PARAM_TEAM_NAME": "labs", "PARAM_COMPONENT_NAME": "app",
               "PARAM_TARGET_COMMIT": self.target, "PARAM_EXPECTED_DIGEST": D1}
        env.update({f"PARAM_{k.upper()}": v for k, v in p.items()})
        f = self.tmp / "s.sh"
        f.write_text(src)
        r = subprocess.run(["bash", str(f)], env=env, capture_output=True, text=True, cwd=self.tmp, timeout=120)
        return r.returncode, r.stdout + r.stderr


def boxed(fn):
    with tempfile.TemporaryDirectory() as d:
        return fn(Box(d))


def refused(**p):
    def body(b):
        before = b.head()
        rc, out = b.run(**p)
        return rc != 0 and b.head() == before
    return boxed(body)


def happy(b):
    rc, out = b.run()
    new = pathlib.Path(b.tmp / "w-commit_sha").read_text().strip() if (b.tmp / "w-commit_sha").exists() else ""
    return rc == 0 and b.head() == new != "" and D1 in b.show() and "100m" in b.show() and D2 not in b.show()


check("restores the whole values.yaml of the target commit", boxed(happy))
check("a no-op restore succeeds without a new commit",
      boxed(lambda b: (b.commit(b.g("--git-dir", str(b.origin), "show", f"{b.target}:{VAL}")), (lambda h: b.run()[0] == 0 and b.head() == h)(b.head()))[1]))
check("refuses a non-hex target", refused(target_commit="main"))
check("refuses a short target", refused(target_commit="abc123"))
check("refuses a bad digest shape", refused(expected_digest="sha256:zz"))
check("refuses a digest the commit does not pin", refused(expected_digest=D2))
check("refuses a team that is not a DNS label", refused(team_name="../x"))
check("refuses an unknown service", refused(component_name="nope"))
check("refuses a commit that is not on main",
      boxed(lambda b: (b.g("checkout", "-q", "-b", "side", cwd=b.w), b.commit(values(D1), rel=VAL), b.g("push", "-q", str(b.origin), "side", cwd=b.w),
                       (lambda s, h: b.run(target_commit=s)[0] != 0 and b.head() == h)(b.sha(), b.head()))[3]))
check("refuses when the image repository changed since",
      boxed(lambda b: (b.commit(values(D2).replace("ghcr.io/mctlhq/app", "ghcr.io/evil/app")), (lambda h: b.run()[0] != 0 and b.head() == h)(b.head()))[1]))

MUT = {
    "no digest check": (lambda s: s.replace('[ "$got" = "$DIGEST" ]', "true"), dict(expected_digest=D2)),
    "no main ancestry check": (lambda s: s.replace('git merge-base --is-ancestor "${TARGET}" origin/main', "true"), None),
    "no immutable keys check": (lambda s: s.replace("'.image.repository' ", ""), None),
}


def mutant_goes_red(name):
    mut, params = MUT[name]
    if name == "no main ancestry check":
        def body(b):
            b.g("checkout", "-q", "-b", "side", cwd=b.w)
            b.commit(values(D1, "x: 1\n"))
            b.g("push", "-q", str(b.origin), "side", cwd=b.w)
            before = b.head()
            rc, _ = b.run(mutate=mut, target_commit=b.sha())
            return not (rc != 0 and b.head() == before)
        return boxed(body)
    if name == "no immutable keys check":
        def body(b):
            b.commit(values(D2).replace("ghcr.io/mctlhq/app", "ghcr.io/evil/app"))
            before = b.head()
            rc, _ = b.run(mutate=mut)
            return not (rc != 0 and b.head() == before)
        return boxed(body)
    def body(b):
        before = b.head()
        rc, _ = b.run(mutate=mut, **params)
        return not (rc != 0 and b.head() == before)
    return boxed(body)


for n in MUT:
    check(f"mutant: {n} is caught", mutant_goes_red(n))

if failures:
    raise SystemExit(f"{len(failures)} failed: {failures}")
print("all checks passed")
