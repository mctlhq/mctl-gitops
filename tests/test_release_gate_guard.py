"""release-gate-guard.sh and the shared templates that call it (mctlhq/mctl-agents#1007).

The scripts are extracted from the templates rather than restated, because a
restated copy would keep passing after a template changed. git is a stub only
for `clone` (redirected to a local bare repository) and for logging; every
commit, rebase and push is real, against that repository. No network, no key.

A check is accepted only when it is proven both ways: MUTANTS at the end remove
each guard layer in turn and require the matching scenario to stop holding.
"""
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TPL = ROOT / "platform-gitops/argo-workflows/cluster-templates"
GUARD_REL = "platform-gitops/argo-workflows/scripts/release-gate-guard.sh"
GATE_REL = "platform-gitops/release-gates.yaml"
GUARD_TEXT = (ROOT / GUARD_REL).read_text()
GATE_TEXT = (ROOT / GATE_REL).read_text()
REAL_GIT = shutil.which("git")
SVC = "platform-gitops/services"
WORKERS = ["mctl-agents-worker", "mctl-agents-worker-exec", "mctl-agents-worker-implement"]
READ_ONLY = ("validate", "preview")
TARGET_CALL = "sh " + GUARD_REL + " target"
OUTGOING_CALL = "sh " + GUARD_REL + " outgoing origin/main || exit 1"

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def template(file, name):
    doc = yaml.safe_load((TPL / file).read_text())
    return [t for t in doc["spec"]["templates"] if t["name"] == name][0]


TEMPLATES = {
    "commit": template("tpl-git-commit.yaml", "commit-service"),
    "delete": template("tpl-git-commit.yaml", "delete-service"),
    "validate": template("tpl-validate-tenant.yaml", "validate"),
    "preview": template("tpl-validate-tenant.yaml", "image-name"),
    "autoscale": template("wft-deploy-service.yaml", "patch-autoscaling-values"),
    "add-domain": template("wft-add-custom-domain.yaml", "do-add-domain"),
    "remove-domain": template("wft-remove-custom-domain.yaml", "do-remove-domain"),
    "database": template("wft-provision-database.yaml", "do-provision"),
}


def drop_lines(source, needle):
    kept = [ln for ln in source.split("\n") if needle not in ln]
    assert len(kept) < source.count("\n") + 1, f"mutation found nothing to remove: {needle}"
    return "\n".join(kept)


class Box:
    """A bare origin, a stubbed git, and one template run at a time."""

    def __init__(self, tmp, gate=GATE_TEXT, guard=GUARD_TEXT, seed=None):
        self.tmp = pathlib.Path(tmp)
        self.origin = self.tmp / "origin.git"
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.log = self.tmp / "git.log"
        self.log.touch()
        self.gitenv = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }
        self._git("init", "-q", "--bare", "-b", "main", str(self.origin))
        work = self.tmp / "seed"
        work.mkdir()
        for rel in ("platform-gitops/argo-workflows/scripts",
                    "platform-gitops/argo-workflows/config",
                    "platform-gitops/argo-workflows/file-templates",
                    "platform-gitops/argo-workflows/service-templates",
                    "platform-gitops/helm-charts/base-service"):
            shutil.copytree(ROOT / rel, work / rel)
        (work / GUARD_REL).write_text(guard)
        if gate is not None:
            (work / GATE_REL).write_text(gate)
        for w in WORKERS:
            self._values(work, "admins", w, "ghcr.io/mctlhq/mctl-agents", "1.117.0")
        self._values(work, "labs", "app", "ghcr.io/mctlhq/app", "1.0.0")
        for team in ("admins", "labs"):
            d = work / "platform-gitops/tenants" / team
            d.mkdir(parents=True)
            (d / "values.yaml").write_text("tenant: {}\n")
        if seed:
            seed(work)
        self._git("init", "-q", "-b", "main", cwd=work)
        self._git("add", "-A", cwd=work)
        self._git("commit", "-q", "-m", "seed", cwd=work)
        self._git("push", "-q", str(self.origin), "main", cwd=work)
        self._stub()
        self._service_stubs()
        self.key = self.tmp / "key"
        self.key.write_text("fake\n")

    @staticmethod
    def _values(work, team, service, repo, tag):
        d = work / SVC / team / service
        d.mkdir(parents=True)
        (d / "values.yaml").write_text(
            f'image:\n  repository: {repo}\n  tag: "{tag}"\n')
        (d / "catalog-info.yaml").write_text("metadata:\n  name: x\n")

    def _git(self, *args, cwd=None):
        subprocess.run([REAL_GIT, *args], cwd=cwd, env=self.gitenv, check=True,
                       capture_output=True, text=True)

    def _stub(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "git"
        stub.write_text(f"""#!/bin/sh
printf '%s\\n' "$*" >> '{self.log}'
if [ "$1" = clone ]; then
  shift
  while [ "${{1#-}}" != "$1" ]; do shift; done
  exec '{REAL_GIT}' clone -q --depth=1 'file://{self.origin}' "$2"
fi
if [ "$1" = push ] && [ -n "${{RACE_HOOK:-}}" ] && [ ! -e "$RACE_HOOK.done" ]; then
  : > "$RACE_HOOK.done"
  sh "$RACE_HOOK" >/dev/null 2>&1
fi
exec '{REAL_GIT}' "$@"
""")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.bin = bin_dir

    def _service_stubs(self):
        """apk and the platform's HTTP APIs, for templates that call them before cloning."""
        curl = self.bin / "curl"
        curl.write_text(r"""#!/bin/sh
out=""; w=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift ;; -w) w="$2"; shift ;; esac
  shift
done
J='{"auth":{"client_token":"t"},"verified":true,"method":"txt","domains":[{"domain":"a.example.org","id":"1"},{"domain":"b.example.org","id":"2"}]}'
if [ -n "$out" ]; then printf '%s' "$J" > "$out"; else printf '%s' "$J"; fi
[ -n "$w" ] && printf 200
exit 0
""")
        apk = self.bin / "apk"
        apk.write_text("#!/bin/sh\nexit 0\n")
        openssl = self.bin / "openssl"  # not in every test image; the template only wants random text
        openssl.write_text("#!/bin/sh\necho fixture-password\n")
        for p in (curl, apk, openssl):
            p.chmod(0o755)

    def race(self, rel, text):
        """Before the template's first push, someone else lands this commit."""
        hook = self.tmp / "race.sh"
        other = self.tmp / "other"
        hook.write_text(f"""set -e
'{REAL_GIT}' clone -q 'file://{self.origin}' '{other}'
cd '{other}'
mkdir -p "$(dirname '{rel}')"
cat > '{rel}' <<'RACE_EOF'
{text}
RACE_EOF
'{REAL_GIT}' add -A
'{REAL_GIT}' -c user.name=t -c user.email=t@t commit -q -m race
'{REAL_GIT}' push -q origin main
""")
        return str(hook)

    def head(self):
        return subprocess.run([REAL_GIT, "--git-dir", str(self.origin), "rev-parse", "main"],
                              capture_output=True, text=True, check=True).stdout.strip()

    def read(self, rel):
        r = subprocess.run([REAL_GIT, "--git-dir", str(self.origin), "show", f"main:{rel}"],
                           capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def gitlog(self):
        return self.log.read_text()

    def run(self, name, params, mutate=None, race=None):
        t = TEMPLATES[name]
        src = t["script"]["source"]
        if mutate:
            src = mutate(src)
        # validate and preview clone anonymously, so they have no key to redirect.
        assert src.count("/secrets/deploy-key/ssh-privatekey") == (0 if name in READ_ONLY else 1)
        # /tmp first: on Linux the temporary directory itself lives under /tmp.
        src = src.replace("/tmp/", str(self.tmp) + "/w-")
        src = src.replace("/secrets/deploy-key/ssh-privatekey", str(self.key))
        sa = self.tmp / "sa"
        sa.mkdir(exist_ok=True)
        (sa / "namespace").write_text("admins\n")
        (sa / "token").write_text("t\n")
        src = src.replace("/var/run/secrets/kubernetes.io/serviceaccount", str(sa))
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.home),
               "GITOPS_ORG": "mctlhq", "GITOPS_REPO": "mctl-gitops", "PLATFORM_DOMAIN": "mctl.ai"}
        for e in t["script"].get("env", []):
            if e["name"] != "HOME":
                env[e["name"]] = ""
        env.update(params)
        if race:
            env["RACE_HOOK"] = race
        script = self.tmp / f"{name}.sh"
        script.write_text(src)
        # These run under busybox ash in production and use its ${x//a/b} and
        # pipefail; dash, sh on Ubuntu, has neither. The guard they call still
        # runs under plain sh.
        shell = "bash" if name in ("add-domain", "remove-domain", "autoscale") else "sh"
        r = subprocess.run([shell, str(script)], env=env, capture_output=True, text=True,
                           cwd=self.tmp, timeout=120)
        return r.returncode, r.stdout + r.stderr


def commit_params(team, service, action="deploy", tag="1.200.0"):
    return {"PARAM_TEAM_NAME": team, "PARAM_COMPONENT_NAME": service,
            "PARAM_COMPONENT_TYPE": "worker-service", "PARAM_ACTION": action,
            "PARAM_IMAGE_TAG": tag, "PARAM_PORT": "8080", "PARAM_HOST": "none",
            "PARAM_CLEAR_ENV": "false", "PARAM_CLEAR_SECRETS": "false",
            "PARAM_SERVICE_TEMPLATE": "default", "PARAM_PROVISION_DATABASE": "false",
            "PARAM_SKIP_HEALTH_CHECK": "true"}


def delete_params(team, service):
    return {"PARAM_TEAM_NAME": team, "PARAM_COMPONENT_NAME": service,
            "PARAM_COMPONENT_TYPE": "base-service"}


def scale_params(team, service):
    return {"PARAM_TEAM_NAME": team, "PARAM_COMPONENT_NAME": service,
            "PARAM_MIN_REPLICAS": "1", "PARAM_MAX_REPLICAS": "3", "PARAM_CPU_THRESHOLD": "80"}


def validate_params(team, service):
    return {"PARAM_TEAM_NAME": team, "PARAM_COMPONENT_NAME": service, "PARAM_ACTION": "deploy",
            "PARAM_COMPONENT_TYPE": "worker-service", "PARAM_IMAGE_TAG": "1.200.0",
            "PARAM_DOCKERFILE_REPO": "", "PARAM_GIT_TAG": "", "PARAM_HOST": "",
            "PARAM_SERVICE_TEMPLATE": "default", "PARAM_CONTAINER_REGISTRY": "ghcr.io/mctlhq"}


def boxed(fn, **box_kw):
    with tempfile.TemporaryDirectory() as d:
        return fn(Box(d, **box_kw))


def refused(box, before, rc, out, wrote_nothing=True):
    ok = rc != 0 and box.head() == before and "release gate" in out
    if wrote_nothing:
        ok = ok and "commit" not in box.gitlog().replace("commit-service", "")
    return ok


# ── Scenarios: each returns True when the behaviour holds ────────────────────
def deploy_gated(service, action="deploy", mutate=None, guard=GUARD_TEXT, gate=GATE_TEXT,
                 wrote_nothing=True):
    def body(b):
        before = b.head()
        rc, out = b.run("commit", commit_params("admins", service, action), mutate)
        return refused(b, before, rc, out, wrote_nothing)
    return boxed(body, guard=guard, gate=gate)


def deploy_other(mutate=None, guard=GUARD_TEXT, action="deploy"):
    def body(b):
        before = b.head()
        rc, out = b.run("commit", commit_params("labs", "app", action), mutate)
        return rc == 0 and b.head() != before and '1.200.0' in b.read(f"{SVC}/labs/app/values.yaml")
    return boxed(body, guard=guard)


def retire_gated(service, mutate=None, wrote_nothing=True):
    def body(b):
        before = b.head()
        rc, out = b.run("delete", delete_params("admins", service), mutate)
        return refused(b, before, rc, out, wrote_nothing)
    return boxed(body)


def retire_gated_dir_gone(mutate=None):
    """A gated directory already missing is a broken group, not an earlier retire."""
    def seed(work):
        shutil.rmtree(work / SVC / "admins" / WORKERS[1])
    def body(b):
        before = b.head()
        rc, out = b.run("delete", delete_params("admins", WORKERS[1]), mutate)
        return refused(b, before, rc, out)
    return boxed(body, seed=seed)


def retire_other(mutate=None):
    def body(b):
        rc, out = b.run("delete", delete_params("labs", "app"), mutate)
        return rc == 0 and b.read(f"{SVC}/labs/app/values.yaml") is None
    return boxed(body)


GATE_PLUS_APP = GATE_TEXT.replace(
    f"      - {SVC}/admins/mctl-agents-worker/values.yaml\n",
    f"      - {SVC}/admins/mctl-agents-worker/values.yaml\n      - {SVC}/labs/app/values.yaml\n", 1)
assert GATE_PLUS_APP != GATE_TEXT


def race_gate_grows(tmpl, params, mutate=None):
    """The service becomes gated while this run works: the rebase must re-decide."""
    def body(b):
        hook = b.race(GATE_REL, GATE_PLUS_APP)
        rc, out = b.run(tmpl, params, mutate, race=hook)
        log = subprocess.run([REAL_GIT, "--git-dir", str(b.origin), "log", "--format=%s", "main"],
                             capture_output=True, text=True).stdout
        return rc != 0 and "release gate" in out and log.startswith("race\n")
    return boxed(body)


def race_unrelated(mutate=None):
    """A concurrent worker bump must not make another service's deploy refuse."""
    def body(b):
        hook = b.race(f"{SVC}/admins/{WORKERS[0]}/values.yaml", 'image:\n  tag: "1.118.0"')
        rc, out = b.run("commit", commit_params("labs", "app"), mutate, race=hook)
        return rc == 0 and "1.200.0" in b.read(f"{SVC}/labs/app/values.yaml") \
            and "1.118.0" in b.read(f"{SVC}/admins/{WORKERS[0]}/values.yaml")
    return boxed(body)


def scale_gated(mutate=None, wrote_nothing=True):
    def body(b):
        before = b.head()
        rc, out = b.run("autoscale", scale_params("admins", WORKERS[0]), mutate)
        return refused(b, before, rc, out, wrote_nothing)
    return boxed(body)


def scale_other():
    def body(b):
        rc, out = b.run("autoscale", scale_params("labs", "app"))
        return rc == 0 and "autoscaling" in b.read(f"{SVC}/labs/app/values.yaml")
    return boxed(body)


def validate_gated(mutate=None):
    def body(b):
        rc, out = b.run("validate", validate_params("admins", WORKERS[0]), mutate)
        return rc != 0 and "release gate" in out
    return boxed(body)


def preview_params(team, service):
    return {"PARAM_TEAM_NAME": team, "PARAM_COMPONENT_NAME": service, "PARAM_GIT_REF": ""}


def preview_gated(mutate=None):
    def body(b):
        rc, out = b.run("preview", preview_params("admins", WORKERS[0]), mutate)
        return rc != 0 and "release gate" in out
    return boxed(body)


def preview_other():
    def body(b):
        rc, out = b.run("preview", preview_params("labs", "app"))
        return rc == 0 and "release gate" not in out
    return boxed(body)


def validate_other():
    def body(b):
        rc, out = b.run("validate", validate_params("labs", "app"))
        return rc == 0 and "release gate" not in out
    return boxed(body)


def guard_run(tmp, *args):
    return subprocess.run(["sh", str(tmp / GUARD_REL), *args], cwd=tmp, capture_output=True,
                          text=True, env={**os.environ, "GIT_AUTHOR_NAME": "t",
                                          "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                                          "GIT_COMMITTER_EMAIL": "t@t"})


def bad_gate_refuses(gate, guard=GUARD_TEXT):
    """Every service is refused when the gate cannot be read or understood."""
    def body(b):
        before = b.head()
        rc, out = b.run("commit", commit_params("labs", "app"))
        return refused(b, before, rc, out)
    return boxed(body, gate=gate, guard=guard)


def symlinked(guard=GUARD_TEXT):
    def seed(work):
        d = work / SVC / "labs/link"
        d.mkdir()
        (d / "values.yaml").symlink_to(work / SVC / "admins" / WORKERS[0] / "values.yaml")
    def body(b):
        before = b.head()
        rc, out = b.run("commit", commit_params("labs", "link"))
        return rc != 0 and b.head() == before and "release gate" in out
    return boxed(body, seed=seed, guard=guard)


def symlinked_dir(guard=GUARD_TEXT):
    def seed(work):
        (work / SVC / "labs/linkdir").symlink_to(pathlib.Path("../admins") / WORKERS[0])
    def body(b):
        before = b.head()
        rc, out = b.run("commit", commit_params("labs", "linkdir"))
        return rc != 0 and b.head() == before and "release gate" in out
    return boxed(body, seed=seed, guard=guard)


def missing_guard_refuses():
    def seed(work):
        (work / GUARD_REL).unlink()
    def body(b):
        before = b.head()
        rc, out = b.run("commit", commit_params("labs", "app"))
        return rc != 0 and b.head() == before and "commit" not in b.gitlog()
    return boxed(body, seed=seed)


def domain_params(team, service):
    return {"MCTL_API_TOKEN": "x", "MCTL_API_URL": "http://api", "BACKSTAGE_URL": "http://b",
            "PARAM_TEAM": team, "PARAM_SERVICE": service, "PARAM_DOMAIN": "a.example.org",
            "PARAM_DOMAIN_ID": "1"}


def database_params(team, service):
    return {"PARAM_TEAM_NAME": team, "PARAM_APP_NAME": service, "VAULT_ADDR": "http://v",
            "VAULT_TOKEN": "t"}


WRITERS = {"add-domain": domain_params, "remove-domain": domain_params, "database": database_params}


def writer_gated(name, mutate=None):
    def body(b):
        before = b.head()
        rc, out = b.run(name, WRITERS[name]("admins", WORKERS[0]), mutate)
        return refused(b, before, rc, out)
    return boxed(body)


def writer_seed(work):
    """What these operations expect of an ordinary service that has a custom domain."""
    p = work / SVC / "labs/app/values.yaml"
    p.write_text(p.read_text() + "ingress:\n  hosts:\n    - a.example.org\n  tls:\n"
                 "    - secretName: app-custom-tls\n      hosts:\n        - a.example.org\n")
    (work / SVC / "labs/app/custom-tls.yaml").write_text("x: y\n")
    d = work / "platform-gitops/infra-components/data/cnpg/shared"
    d.mkdir(parents=True)
    (d / "cluster.yaml").write_text(
        "spec:\n  postgresql:\n    pg_hba:\n      - local all all trust\n"
        "  managed:\n    roles:\n      # Team app roles\n")
    (d / "databases.yaml").write_text("---\n")
    (d / "secrets.yaml").write_text("---\n")


def writer_other_pushes(name):
    def body(b):
        before = b.head()
        params = WRITERS[name]("labs", "app")
        if name == "add-domain":
            params["PARAM_DOMAIN"] = "b.example.org"  # the seed already has a.example.org
        rc, out = b.run(name, params)
        return rc == 0 and b.head() != before and "release gate" not in out
    return boxed(body, seed=writer_seed)


# wft-rollback-service refuses gated files with its own inline guard, which
# tests/test_release_gate.py covers.
EXEMPT_WRITERS = {"wft-rollback-service.yaml"}


def unguarded_writers(docs):
    """Every template that pushes and touches services/ must carry both checks."""
    found = []
    for path, doc in docs:
        for t in (doc.get("spec") or {}).get("templates") or []:
            c = t.get("script") or t.get("container") or {}
            src = c.get("source") or " ".join(c.get("args") or [])
            if "git push" not in src or not ("platform-gitops/services" in src or "services/$" in src):
                continue
            if path in EXEMPT_WRITERS:
                continue
            if TARGET_CALL not in src or OUTGOING_CALL not in src:
                found.append(f"{path}:{t['name']}")
    return found


def guard_on_gate(gate, *args, guard=GUARD_TEXT):
    with tempfile.TemporaryDirectory() as d:
        w = pathlib.Path(d)
        (w / GUARD_REL).parent.mkdir(parents=True)
        (w / GUARD_REL).write_text(guard)
        (w / GATE_REL).write_text(gate)
        for w_name in WORKERS:
            (w / SVC / "admins" / w_name).mkdir(parents=True)
        return guard_run(w, *args).returncode


# ── Normal services still work ───────────────────────────────────────────────
check("deploy of another service still pushes", deploy_other())
check("update-config of another service still pushes",
      boxed(lambda b: (lambda res: res[0] == 0 and "A:" in b.read(f"{SVC}/labs/app/values.yaml"))(
          b.run("commit", {**commit_params("labs", "app", "update-config"), "PARAM_ENV_VARS": "A=b"}))))
check("retire of another service still removes it", retire_other())
check("autoscaling of another service still pushes", scale_other())
check("validate lets another service through", validate_other())
check("preview lets another service through", preview_other())
check("a concurrent worker bump does not refuse another service", race_unrelated())
check("onboard of a new service still pushes",
      boxed(lambda b: (lambda res: res[0] == 0 and b.read(f"{SVC}/labs/fresh/values.yaml") is not None)(
          b.run("commit", commit_params("labs", "fresh", "onboard")))))

# ── Refusals before anything is written ──────────────────────────────────────
for w in WORKERS:
    check(f"deploy of {w} is refused before any commit", deploy_gated(w))
    check(f"retire of {w} is refused before any commit", retire_gated(w))
check("update-config of a gated worker is refused", deploy_gated(WORKERS[0], "update-config"))
check("onboard onto a gated worker is refused", deploy_gated(WORKERS[0], "onboard"))
check("retire of a gated directory already missing is refused, not exit 0", retire_gated_dir_gone())
check("autoscaling of a gated worker is refused", scale_gated())
check("validate refuses a gated worker before any build or Vault step", validate_gated())
for w in WORKERS:
    check(f"preview refuses gated worker {w} before any build",
          boxed(lambda b, w=w: (lambda res: res[0] != 0 and "release gate" in res[1])(
              b.run("preview", preview_params("admins", w)))))

for name in WRITERS:
    check(f"{name}: a gated worker is refused before any commit", writer_gated(name))
    # provision-database uses GNU/busybox sed syntax, so it cannot finish on macOS.
    if name == "database" and sys.platform == "darwin":
        print(f"SKIP  {name}: another service still pushes (needs Linux sed)")
    else:
        check(f"{name}: another service still pushes", writer_other_pushes(name))

ALL_DOCS = [(p.name, d) for p in sorted(TPL.glob("*.yaml")) for d in yaml.safe_load_all(p.read_text()) if d]
check("every template that pushes and touches services/ carries both checks",
      unguarded_writers(ALL_DOCS) == [], str(unguarded_writers(ALL_DOCS)))
check("the sweep flags a new writer with no guard",
      unguarded_writers([("new.yaml", {"spec": {"templates": [{"name": "n", "script": {
          "source": "git add platform-gitops/services/x/values.yaml\ngit push"}}]}})]) == ["new.yaml:n"])

# ── After a rebase ───────────────────────────────────────────────────────────
check("deploy: gate grows during the run, refused after the rebase",
      race_gate_grows("commit", commit_params("labs", "app")))
check("retire: gate grows during the run, refused after the rebase",
      race_gate_grows("delete", delete_params("labs", "app")))

# ── Fail closed on the gate itself ───────────────────────────────────────────
BAD_GATES = {
    "missing": None,
    "empty": "",
    "no paths key": "gates: []\n",
    "paths with no file": "gates:\n  - name: g\n    paths: []\n",
    "a glob": f"gates:\n  - paths:\n      - {SVC}/admins/*/values.yaml\n",
    "a traversal": f"gates:\n  - paths:\n      - {SVC}/admins/../admins/mctl-agents-worker/values.yaml\n",
    "a relative path": "gates:\n  - paths:\n      - services/admins/x/values.yaml\n",
    "uppercase": f"gates:\n  - paths:\n      - {SVC}/Admins/x/values.yaml\n",
    "another file name": f"gates:\n  - paths:\n      - {SVC}/admins/x/values.yml\n",
    "an extra segment": f"gates:\n  - paths:\n      - {SVC}/admins/x/y/values.yaml\n",
}
for label, gate in BAD_GATES.items():
    check(f"a gate with {label} refuses every service", bad_gate_refuses(gate))
check("a missing guard script refuses", missing_guard_refuses())
check("a values file symlinked to a gated one is refused", symlinked())
check("a service directory symlinked to a gated one is refused", symlinked_dir())

# Nothing but gates[].paths and prepull_paths may decide, in either direction.
_G = f"{SVC}/admins/mctl-agents-worker/values.yaml"
_OK = f"gates:\n  - paths:\n      - {_G}\n"
QUOTED_HASH_GATE = (f'gates:\n  - paths:\n      - {SVC}/labs/app/values.yaml\n    name: g\n'
                    f'  - {{note: "a # b", paths: [{_G}]}}\n')
for label, gate in {
    "a note about values": _OK + '    note: "values move together"\n',
    "a note naming a file": _OK + "    note: bump each values.yaml together\n",
    "an issue URL with services/": _OK + "    issue: https://example.org/services/1\n",
    "a requires key with values": _OK + "    key: helm.values.strategy\n",
    "a trailing comment naming a path": _OK + f'    min_tag: "1.0.0"  # see {SVC}/labs/app/values.yaml\n',
    "a block scalar line": _OK + "    note: |\n      paths: reviewed by hand\n",
    "another key ending in paths": _OK + "    docs_paths: [README.md]\n",
    "a second gate after paths": _OK + f"  - name: b\n    paths:\n      - {SVC}/admins/mctl-agents-worker-exec/values.yaml\n",
    "a hash in a quoted note": QUOTED_HASH_GATE.replace(f"{SVC}/labs/app/values.yaml", f"{SVC}/labs/z/values.yaml"),
}.items():
    check(f"gate with {label}: another service is not refused",
          guard_on_gate(gate, "target", "labs", "app") == 0)
    check(f"gate with {label}: the gated worker still is",
          guard_on_gate(gate, "target", "admins", WORKERS[0]) == 6)
for label, gate in {
    "quoted key and escapes": f'"gates":\n  - "paths": ["platform-gitop\\x73/services/admins/mctl-agents-worker/values\\x2eyaml"]\n',
    "a multi-line flow list": f"gates:\n  - paths: [\n      {_G}\n    ]\n",
    "only prepull_paths naming it": f"gates:\n  - paths:\n      - {SVC}/labs/z/values.yaml\n    prepull_paths:\n      - {_G}\n",
}.items():
    check(f"gate with {label}: the worker is gated, as YAML reads it",
          guard_on_gate(gate, "target", "admins", WORKERS[0]) == 6)
    check(f"gate with {label}: another service is not refused",
          guard_on_gate(gate, "target", "labs", "app") == 0)
for label, gate in {
    "a bare word in a paths list": f"gates:\n  - paths:\n      - {_G}\n      - oops\n",
    "an undefined alias": "gates:\n  - paths: *common\n",
    "a defined alias, which yq does not tag as a list": f"x: &p\n  - {_G}\ngates:\n  - paths: *p\n",
    "a bare word in a flow list": f"gates:\n  - paths: [{_G}, oops]\n",
    "a bare word in prepull_paths": f"{_OK}    prepull_paths:\n      - oops\n",
    "a gate with no paths next to a good one": f"{_OK}  - name: b\n",
    "paths as a string": f"gates:\n  - paths: {_G}\n",
    "a number in a list": f"{_OK}      - 7\n",
    "a broken file": "gates: [\n",
    "gates as a map": f"gates:\n  paths:\n    - {_G}\n",
    "two documents": f"{_OK}---\n{_OK}",
    "prepull_paths as a string": f"{_OK}    prepull_paths: {_G}\n",
    "a merge key list": f"a: &a\n  paths: [{_G}]\nb: &b\n  paths: [{SVC}/labs/z/values.yaml]\ngates:\n  - <<: [*a, *b]\n",
    "a merge key after paths": f"b: &b\n  paths: [{SVC}/labs/z/values.yaml]\ngates:\n  - paths: [{_G}]\n    <<: *b\n",
}.items():
    check(f"{label} refuses", guard_on_gate(gate, "target", "labs", "app") == 6)
real = yaml.safe_load(GATE_TEXT)
for g in real["gates"]:
    for p in g["paths"] + g.get("prepull_paths", []):
        team, service = p.split("/")[2:4]
        check(f"guard agrees with YAML: {team}/{service} in the real gate is refused",
              guard_on_gate(GATE_TEXT, "target", team, service) == 6)


def yq_stub_refuses(stub):
    with tempfile.TemporaryDirectory() as d:
        w = pathlib.Path(d)
        (w / "bin").mkdir()
        (w / "bin/yq").write_text(stub)
        (w / "bin/yq").chmod(0o755)
        (w / GUARD_REL).parent.mkdir(parents=True)
        (w / GUARD_REL).write_text(GUARD_TEXT)
        (w / GATE_REL).write_text(_OK)
        r = subprocess.run(["sh", str(w / GUARD_REL), "target", "labs", "app"], cwd=w, capture_output=True,
                           text=True, env={**os.environ, "PATH": f"{w}/bin:{os.environ['PATH']}"})
        return r.returncode == 6


check("a yq that fails refuses", yq_stub_refuses("#!/bin/sh\nexit 1\n"))
check("a yq that answers nothing refuses", yq_stub_refuses("#!/bin/sh\nexit 0\n"))
check("a yq of another kind refuses", yq_stub_refuses("#!/bin/sh\necho null\n"))

# The shape the worker group will have once mctl-gitops#2394 lands, and flow style.
for label, gate in {
    "requires and prepull_paths": GATE_TEXT.replace(
        "    repository: ghcr.io/mctlhq/mctl-agents\n",
        f"    repository: ghcr.io/mctlhq/mctl-agents\n    requires:\n"
        f"      - path: {SVC}/admins/mctl-agents-worker/values.yaml\n        key: strategy.type\n"
        f"        equals: Recreate\n    prepull_paths:\n"
        f"      - {SVC}/admins/mctl-agents-worker/values.yaml\n", 1),
    "flow style": f'gates:\n  - paths: ["{SVC}/admins/mctl-agents-worker/values.yaml"]\n',
}.items():
    check(f"gate with {label}: gated refused, other deploys",
          deploy_gated(WORKERS[0], gate=gate) and boxed(
              lambda b: b.run("commit", commit_params("labs", "app"))[0] == 0, gate=gate))


# ── The guard script directly ────────────────────────────────────────────────
def direct(fn):
    with tempfile.TemporaryDirectory() as d:
        b = Box(d)
        return fn(b, b.tmp / "seed")


for label, args in {
    "a slash": ("target", "admins", "mctl-agents-worker/."),
    "a traversal": ("target", "admins", "../admins/mctl-agents-worker"),
    "a newline": ("target", "admins", "x\nmctl-agents-worker"),
    "uppercase": ("target", "admins", "Mctl-Agents-Worker"),
    "an empty service": ("target", "admins", ""),
    "a leading dash": ("target", "admins", "-x"),
    "an over-long name": ("target", "admins", "a" * 64),
    "no arguments": ("target",),
    "extra arguments": ("target", "labs", "app", "more"),
    "an unknown mode": ("nonsense", "labs", "app"),
    "no mode": (),
    "a missing base": ("outgoing", "refs/does/not/exist"),
    "an empty base": ("outgoing", ""),
}.items():
    check(f"guard refuses {label}",
          direct(lambda b, w: guard_run(w, *args).returncode == 6))


def outgoing_case(rel, text):
    def fn(b, w):
        p = w / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        b._git("add", "-A", cwd=w)
        b._git("commit", "-q", "-m", "x", cwd=w)
        return guard_run(w, "outgoing", "HEAD~1").returncode
    return direct(fn)


check("outgoing refuses a change to a gated values file",
      outgoing_case(f"{SVC}/admins/{WORKERS[1]}/values.yaml", "x: y\n") == 6)
check("outgoing refuses any other file of a gated service",
      outgoing_case(f"{SVC}/admins/{WORKERS[2]}/catalog-info.yaml", "x: y\n") == 6)
check("outgoing refuses a change to the gate file", outgoing_case(GATE_REL, GATE_TEXT + "# x\n") == 6)
check("outgoing refuses a change to the guard", outgoing_case(GUARD_REL, GUARD_TEXT + "# x\n") == 6)
check("outgoing refuses a path it cannot read unambiguously",
      outgoing_case(f"{SVC}/labs/app/a\tb", "x\n") == 6)
check("outgoing allows another service", outgoing_case(f"{SVC}/labs/app/values.yaml", "x: y\n") == 0)
check("outgoing does not confuse a name sharing a gated prefix",
      outgoing_case(f"{SVC}/admins/{WORKERS[0]}-extra/values.yaml", "x: y\n") == 0)


# ── Wiring: every push in these templates sits behind the check ──────────────
for name, tmpl in TEMPLATES.items():
    if name in READ_ONLY:
        continue
    lines = tmpl["script"]["source"].split("\n")
    pushes = [i for i, ln in enumerate(lines) if ln.strip().startswith(("git push", "if git push"))]
    check(f"{name}: has a push to guard", bool(pushes))
    for i in pushes:
        check(f"{name}: push on line {i} directly follows the outgoing check",
              OUTGOING_CALL in lines[i - 1], lines[i - 1])

retire = yaml.safe_load((TPL / "wft-retire-service.yaml").read_text())
tasks = {t["name"]: t for t in
         [x for x in retire["spec"]["templates"] if x["name"] == "retire-pipeline"][0]["dag"]["tasks"]}
check("retire: Vault secrets wait for the git step that can refuse",
      "delete-from-git" in tasks["delete-vault-secrets"]["dependencies"])
check("preview's image-name step carries the target check",
      TARGET_CALL in TEMPLATES["preview"]["script"]["source"])
check("preview's target check runs before the image-name check",
      0 <= TEMPLATES["preview"]["script"]["source"].find(TARGET_CALL)
      < TEMPLATES["preview"]["script"]["source"].find("check-image-name.sh"))


# ── Mutants: remove each layer, the matching scenario must stop holding ──────
def no_target(src):
    return drop_lines(src, TARGET_CALL)


def no_outgoing(src):
    return drop_lines(src, OUTGOING_CALL)


def no_guard(src):
    return no_outgoing(no_target(src))


def guard_mut(old, new):
    assert old in GUARD_TEXT, old
    return GUARD_TEXT.replace(old, new)


GLOB_GATE = f"gates:\n  - paths:\n      - {SVC}/admins/*/values.yaml\n"
SHAPE_OFF = guard_mut('valid_gated_path "$_t" || refuse', 'true || refuse')
MUTANTS = {
    "commit: target call removed (reaches a commit)":
        lambda: deploy_gated(WORKERS[0], mutate=no_target),
    "commit: both calls removed (reaches main)":
        lambda: deploy_gated(WORKERS[0], mutate=no_guard, wrote_nothing=False),
    "commit: outgoing call removed (rebase not re-decided)":
        lambda: race_gate_grows("commit", commit_params("labs", "app"), mutate=no_outgoing),
    "delete: target call removed (reaches a commit)":
        lambda: retire_gated(WORKERS[0], mutate=no_target),
    "delete: both calls removed (reaches main)":
        lambda: retire_gated(WORKERS[0], mutate=no_guard, wrote_nothing=False),
    "delete: outgoing call removed (rebase not re-decided)":
        lambda: race_gate_grows("delete", delete_params("labs", "app"), mutate=no_outgoing),
    "delete: target call removed (missing directory exits 0)":
        lambda: retire_gated_dir_gone(mutate=no_target),
    "autoscale: target call removed (reaches a commit)":
        lambda: scale_gated(mutate=no_target),
    "autoscale: both calls removed (reaches main)":
        lambda: scale_gated(mutate=no_guard, wrote_nothing=False),
    "validate: target call removed":
        lambda: validate_gated(mutate=no_target),
    "preview: target call removed":
        lambda: preview_gated(mutate=no_target),
    **{f"{n}: target call removed": (lambda n=n: writer_gated(n, mutate=no_target)) for n in WRITERS},
    "guard: shape check off, a glob is accepted":
        lambda: bad_gate_refuses(GLOB_GATE, guard=SHAPE_OFF),
    "guard: set -f off, shape check sees expanded files":
        lambda: bad_gate_refuses(GLOB_GATE, guard=guard_mut("set -f\n", "")),
    "guard: a gate with no paths next to a good one is accepted":
        lambda: bad_gate_refuses(f"{_OK}  - name: b\n", guard=guard_mut(
            '[ "$_bad" = 0 ] || refuse "$GATE_FILE has a gate with no paths"', 'true')),
    "guard: a non-string entry is accepted":
        lambda: bad_gate_refuses(f"{_OK}      - 7\n", guard=guard_mut(
            '[ "$_bad" = 0 ] || refuse "$GATE_FILE lists something that is not a string"', 'true').replace(
            'valid_gated_path "$_t" || refuse', 'true || refuse')),
    "guard: gates that are not a list are accepted":
        lambda: bad_gate_refuses("gates: {}\n", guard=guard_mut(
            """[ "$_shape" = '!!seq' ] || refuse "$GATE_FILE has no list of gates\"""", 'exit 0')),
    "guard: a string prepull_paths is skipped":
        lambda: guard_on_gate(f"{_OK}    prepull_paths: {SVC}/labs/z/values.yaml\n", "target", "labs", "app", guard=guard_mut(
            '[ "$_bad" = 0 ] || refuse "$GATE_FILE has prepull_paths that are not a list"', 'true')) == 6,
    "guard: merge keys are accepted":
        lambda: guard_on_gate(f"b: &b\n  paths: [{SVC}/labs/z/values.yaml]\ngates:\n  - paths: [{_G}]\n    <<: *b\n",
                              "target", "labs", "app",
                              guard=guard_mut('refuse "$GATE_FILE uses a YAML merge key"', 'true')) == 6,
    "guard: unreadable gate no longer refuses":
        lambda: bad_gate_refuses(None, guard=guard_mut(
            '[ -r "$GATE_FILE" ] || refuse "$GATE_FILE cannot be read"', '[ -r "$GATE_FILE" ] || exit 0')),
    "guard: empty group no longer refuses":
        lambda: bad_gate_refuses("gates: []\n", guard=guard_mut(
            '[ -n "$GATED" ] || refuse', '[ -n "$GATED" ] || exit 0; true || refuse')),
    "guard: target compares nothing":
        lambda: deploy_gated(WORKERS[0], guard=guard_mut(
            'if [ "$_gdir" = "$_dir" ] || [ "$_gdir" -ef "$_dir" ] || [ "$_g" -ef "$_dir/values.yaml" ]; then',
            'if false; then')),
    "guard: symlink and identity checks off, values symlink":
        lambda: symlinked(guard=guard_mut('[ ! -L "$_p" ] || refuse', 'true || refuse').replace(
            '|| [ "$_g" -ef "$_dir/values.yaml" ]', '')),
    "guard: symlink and identity checks off, directory symlink":
        lambda: symlinked_dir(guard=guard_mut('[ ! -L "$_p" ] || refuse', 'true || refuse').replace(
            '|| [ "$_gdir" -ef "$_dir" ]', '').replace('|| [ "$_g" -ef "$_dir/values.yaml" ]', '')),
    "guard: outgoing ignores gated paths":
        lambda: boxed(lambda b: (lambda hook: (lambda res: res[0] != 0 and "release gate" in res[1])(
            b.run("commit", commit_params("labs", "app"), race=hook)))(b.race(GATE_REL, GATE_PLUS_APP)),
            guard=guard_mut('"${_g%/values.yaml}"/*)', '"never-matches"/*)')),
}
for label, scenario in MUTANTS.items():
    try:
        held = scenario()
    except Exception as e:  # a crash is not a caught mutant
        check(f"mutant caught: {label}", False, repr(e))
        continue
    check(f"mutant caught: {label}", held is False, "scenario still held with the guard removed")

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f[:300])
    sys.exit(1)
print("all checks passed")
