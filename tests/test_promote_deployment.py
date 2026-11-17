"""wft-promote-deployment verify-image and pin-image steps (mctlhq/mctl-api#1049).

Both scripts are extracted from the template and run against a real local
bare repository (git is stubbed only to redirect `clone` there). Every refusal
must leave origin untouched; the happy path must pin image.tag together with
image.digest and nothing else. Mutants at the end remove each guard in turn
and require the matching scenario to stop holding.
"""
import os, re, pathlib, shutil, stat, subprocess, tempfile
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TPL = ROOT / "platform-gitops/argo-workflows/cluster-templates/wft-promote-deployment.yaml"
REAL_GIT = shutil.which("git")
TEMPLATES = {t["name"]: t for t in yaml.safe_load(TPL.read_text())["spec"]["templates"]}
VERIFY = TEMPLATES["verify-image"]["script"]["source"]
PIN = TEMPLATES["pin-image"]["script"]["source"]
VAL = "platform-gitops/services/labs/app/values.yaml"
REPO = "ghcr.io/mctlhq/app"
OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64
TAG = "rev-" + "1" * 40
failures = []


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


def values(tag="1.0.0", digest=OLD, repo=REPO, extra=""):
    return (f"# the service\nimage:\n  repository: {repo}\n  tag: \"{tag}\"\n"
            + (f"  digest: {digest}\n" if digest else "") + extra)


class Box:
    def __init__(self, d):
        self.tmp = pathlib.Path(d)
        self.origin = self.tmp / "origin.git"
        self.env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        self.g("init", "-q", "--bare", "-b", "main", str(self.origin))
        self.w = self.tmp / "seed"
        shutil.copytree(ROOT / "platform-gitops/argo-workflows/scripts", self.w / "platform-gitops/argo-workflows/scripts")
        gate = ROOT / "platform-gitops/release-gates.yaml"
        if gate.exists():
            shutil.copy(gate, self.w / "platform-gitops/release-gates.yaml")
        self.g("init", "-q", "-b", "main", cwd=self.w)
        self.commit(values(extra="resources:\n  limits:\n    cpu: 100m\n"))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        stub = self.bin / "git"
        stub.write_text(f"#!/bin/sh\nif [ \"$1\" = clone ]; then shift\n"
                        f"  while [ \"${{1#-}}\" != \"$1\" ]; do shift; done\n"
                        f"  exec '{REAL_GIT}' clone -q 'file://{self.origin}' \"$2\"\nfi\nexec '{REAL_GIT}' \"$@\"\n")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        # origin/HEAD in a clone of a bare repo whose HEAD is main
        resolver = self.tmp / "resolve.sh"
        # The registry: the tag and the digest both resolve to NEW, unless a
        # test rewrites the table.
        self.table = self.tmp / "registry"
        self.registry({f"{REPO}@{NEW}": NEW, f"{REPO}:{TAG}": NEW})
        resolver.write_text(f"#!/bin/sh\ngrep \"^$1 \" '{self.table}' | cut -d' ' -f2 | grep .\n")
        resolver.chmod(resolver.stat().st_mode | stat.S_IEXEC)
        self.resolver = resolver
        (self.tmp / "key").write_text("k\n")
        (self.tmp / "home").mkdir()

    def registry(self, rows):
        self.table.write_text("".join(f"{k} {v}\n" for k, v in rows.items()))

    def g(self, *a, cwd=None):
        return subprocess.run([REAL_GIT, *a], cwd=cwd, env=self.env, check=True, capture_output=True, text=True).stdout

    def commit(self, text, rel=VAL):
        p = self.w / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.g("add", "-A", cwd=self.w)
        self.g("commit", "-q", "-m", "c", cwd=self.w)
        self.g("push", "-q", str(self.origin), "main", cwd=self.w)

    def head(self):
        return self.g("--git-dir", str(self.origin), "rev-parse", "main").strip()

    def show(self):
        return self.g("--git-dir", str(self.origin), "show", f"main:{VAL}")

    def run(self, src, mutate=None, **p):
        src = mutate(src) if mutate else src
        src = src.replace("/tmp/", str(self.tmp) + "/w-").replace("/secrets/deploy-key/ssh-privatekey", str(self.tmp / "key"))
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.tmp / "home"),
               "GITOPS_ORG": "mctlhq", "GITOPS_REPO": "mctl-gitops", "PROMOTE_RESOLVE": str(self.resolver),
               "PARAM_TEAM_NAME": "labs", "PARAM_COMPONENT_NAME": "app",
               "PARAM_IMAGE_TAG": TAG, "PARAM_IMAGE_DIGEST": NEW, "PARAM_IMAGE_REPOSITORY": REPO}
        env.update({f"PARAM_{k.upper()}": v for k, v in p.items()})
        f = self.tmp / "s.sh"
        f.write_text(src)
        r = subprocess.run(["bash", str(f)], env=env, capture_output=True, text=True, cwd=self.tmp, timeout=120)
        return r.returncode, r.stdout + r.stderr


def boxed(fn):
    with tempfile.TemporaryDirectory() as d:
        return fn(Box(d))


def verify_refused(**p):
    return boxed(lambda b: b.run(VERIFY, **p)[0] != 0)


def pin_refused(**p):
    def body(b):
        before = b.head()
        return b.run(PIN, **p)[0] != 0 and b.head() == before
    return boxed(body)


def verify_ok(b):
    rc, out = b.run(VERIFY)
    return rc == 0 and (b.tmp / "w-image_repository").read_text() == REPO


def pin_happy(b):
    rc, out = b.run(PIN)
    sha = (b.tmp / "w-commit_sha").read_text().strip() if (b.tmp / "w-commit_sha").exists() else ""
    s = b.show()
    return (rc == 0 and b.head() == sha != "" and TAG in s and NEW in s and OLD not in s
            and "cpu: 100m" in s and "# the service" in s)


# verify-image
check("verify: the tag and the digest resolve to the digest", boxed(verify_ok))
check("verify: refuses when the tag now points at another digest",
      boxed(lambda b: (b.registry({f"{REPO}@{NEW}": NEW, f"{REPO}:{TAG}": OLD}), b.run(VERIFY)[0] != 0)[1]))
check("verify: refuses a digest that is not in the registry",
      boxed(lambda b: (b.registry({f"{REPO}:{TAG}": NEW}), b.run(VERIFY)[0] != 0)[1]))
check("verify: refuses a tag that is not in the registry",
      boxed(lambda b: (b.registry({f"{REPO}@{NEW}": NEW}), b.run(VERIFY)[0] != 0)[1]))
check("verify: refuses a repository outside the platform namespace",
      boxed(lambda b: (b.commit(values(repo="ghcr.io/evil/app")), b.run(VERIFY)[0] != 0)[1]))
check("verify: refuses an unknown service", verify_refused(component_name="nope"))
check("verify: refuses a team that is not a DNS label", verify_refused(team_name="../x"))
check("verify: refuses a malformed digest", verify_refused(image_digest="sha256:zz"))
check("verify: refuses a malformed tag", verify_refused(image_tag="-rf"))

# pin-image
check("pin: writes image.tag and image.digest and nothing else", boxed(pin_happy))
check("pin: a no-op pin succeeds without a new commit",
      boxed(lambda b: (b.commit(values(tag=TAG, digest=NEW, extra="resources:\n  limits:\n    cpu: 100m\n")),
                       (lambda h: b.run(PIN)[0] == 0 and b.head() == h)(b.head()))[1]))
check("pin: pins a digest on a service that had none",
      boxed(lambda b: (b.commit(values(digest="")), b.run(PIN)[0] == 0 and NEW in b.show())[1]))
check("pin: refuses when the repository is not the verified one", pin_refused(image_repository="ghcr.io/mctlhq/other"))
check("pin: refuses when image.repository changed since it was verified",
      boxed(lambda b: (b.commit(values(repo="ghcr.io/evil/app")), (lambda h: b.run(PIN)[0] != 0 and b.head() == h)(b.head()))[1]))
check("pin: refuses an unknown service", pin_refused(component_name="nope"))
check("pin: refuses a malformed digest", pin_refused(image_digest="sha256:zz"))
check("pin: refuses a malformed tag", pin_refused(image_tag="a b"))

# The tag is re-pushed after the preview ran (mctl-api#1049): production must
# still run the digest the preview ran. Before verify the tag no longer
# describes the preview (refused above); after verify, pin must not look at
# the tag at all.
def repushed_pin_keeps_the_preview_digest(mutate=None):
    def body(b):
        b.registry({f"{REPO}@{NEW}": NEW, f"{REPO}:{TAG}": OLD})  # the tag now points at the old image
        rc, _ = b.run(PIN, mutate=mutate)
        s = b.show()
        return rc == 0 and NEW in s and OLD not in s
    return boxed(body)


check("repush: after the tag moves, pin still writes the preview's digest", repushed_pin_keeps_the_preview_digest())

MUT = {
    "verify: no tag-still-points-here check": lambda s: re.sub(r'(got=\$\(\$RESOLVE "\$\{REPO\}:\$\{TAG\}"\).*\n)\s*\[ "\$got" = "\$DIGEST" \]', r'\1          true', s),
    "verify: no namespace check": lambda s: s.replace('case "$REPO" in "ghcr.io/${GITOPS_ORG}/${COMPONENT}") ;;', 'case "$REPO" in *) ;;'),
    "pin: digest taken from the tag (promote by tag)": lambda s: s.replace('DIGEST="$PARAM_IMAGE_DIGEST"', 'DIGEST=$("$PROMOTE_RESOLVE" "${PARAM_IMAGE_REPOSITORY}:${PARAM_IMAGE_TAG}")'),
    "pin: no repository recheck": lambda s: s.replace('[ "$(yq \'.image.repository // ""\' "${VALUES}")" = "$REPO_EXPECTED" ]', 'true'),
}


def caught(name):
    mut = MUT[name]
    if name.startswith("verify: no tag"):
        return boxed(lambda b: (b.registry({f"{REPO}@{NEW}": NEW, f"{REPO}:{TAG}": OLD}), b.run(VERIFY, mutate=mut)[0] == 0)[1])
    if name.startswith("pin: digest taken from the tag"):
        return not repushed_pin_keeps_the_preview_digest(mutate=mut)
    if name.startswith("verify"):
        return boxed(lambda b: (b.commit(values(repo="ghcr.io/evil/app")), b.registry({"ghcr.io/evil/app@" + NEW: NEW, "ghcr.io/evil/app:" + TAG: NEW}),
                                b.run(VERIFY, mutate=mut)[0] == 0)[2])
    return boxed(lambda b: (b.commit(values(repo="ghcr.io/evil/app")), (lambda h: b.run(PIN, mutate=mut)[0] == 0 or b.head() != h)(b.head()))[1])


for n in MUT:
    check(f"mutant: {n} is caught", caught(n))

if failures:
    raise SystemExit(f"{len(failures)} failed: {failures}")
print("all checks passed")
