"""Image names: a team builds into and runs only names it owns.

Tenant builds push ghcr.io/mctlhq/<component_name> and tenant services run the
same name, so the component name is the image name. check-image-name.sh
decides whether a team may use one, from config/image-names.txt and the
services/ tree. This runs that script:

  * against fixtures, for each branch of the rule and for the fail-closed
    paths (bad input, missing or malformed list);
  * against this repository, so that every service that exists today still
    passes and every image the platform references outside services/ is
    reserved;

and checks that the three callers (deploy-service validation, preview-deploy,
build-image.yaml) actually run it before anything is built or pushed.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "platform-gitops/argo-workflows/scripts/check-image-name.sh"
READER = REPO / "platform-gitops/argo-workflows/scripts/values-images.sh"
LIST = REPO / "platform-gitops/argo-workflows/config/image-names.txt"

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


REG = "ghcr.io/mctlhq"


def run(root, team, name, *flags, registry=REG):
    return subprocess.run(["sh", str(SCRIPT), *flags, str(root), registry, team, name],
                          capture_output=True, text=True).returncode


def fixture(list_text, services, tenants=("labs", "ovk", "karabu", "admins"), reader=True):
    """services: {"team/name": values.yaml text or None}"""
    d = pathlib.Path(tempfile.mkdtemp())
    scripts = d / "platform-gitops/argo-workflows/scripts"
    scripts.mkdir(parents=True)
    if reader:
        shutil.copy(READER, scripts / READER.name)
    shutil.copytree(REPO / "platform-gitops/argo-workflows/service-templates",
                    d / "platform-gitops/argo-workflows/service-templates")
    for t in tenants:
        (d / "platform-gitops/tenants" / t).mkdir(parents=True)
    cfg = d / "platform-gitops/argo-workflows/config"
    cfg.mkdir(parents=True)
    if list_text is not None:
        (cfg / "image-names.txt").write_text(list_text)
    svc = d / "platform-gitops/services"
    svc.mkdir(parents=True)
    for path, values in services.items():
        p = svc / path
        p.mkdir(parents=True)
        if values is not None:
            (p / "values.yaml").write_text(values)
    return d


LIST_TEXT = """# comment
registry ghcr.io/mctlhq
reserved-prefix mctl-
reserved grafana-iac
grant platform grafana-iac
grant labs mctl-academy
grant ovk mctl-academy
shared openclaw
grant labs openclaw
"""
SERVICES = {
    "labs/kuptsi-app": "image:\n  repository: ghcr.io/mctlhq/kuptsi-app\n",
    "labs/telegram-preview": "image:\n  repository: \"ghcr.io/mctlhq/bot-image\"\n",
    "labs/mctl-academy": None,
    # onboarded, values not written yet: the directory alone claims the name
    "labs/fresh-svc": None,
    "ovk/mctl-academy": None,
    "admins/openclaw": "image:\n  repository: ghcr.io/mctlhq/mctl-openclaw\n",
    "labs/openclaw": None,
}
root = fixture(LIST_TEXT, SERVICES)

CASES = [
    # (team, name, expected exit, why[, flags])
    ("karabu", "brand-new", 0, "an unused name is free"),
    ("labs", "kuptsi-app", 0, "a team keeps its own service name"),
    ("karabu", "kuptsi-app", 1, "another team's service name"),
    ("karabu", "fresh-svc", 1, "another team's service directory, no values yet"),
    ("labs", "fresh-svc", 0, "the owning team, no values yet"),
    ("karabu", "bot-image", 1, "an image another team's service runs"),
    ("labs", "bot-image", 0, "the team running that image may build it"),
    ("karabu", "mctl-api", 1, "reserved prefix"),
    ("karabu", "grafana-iac", 1, "reserved name"),
    ("platform", "grafana-iac", 0, "explicit grant"),
    ("labs", "mctl-academy", 0, "explicit grant"),
    ("ovk", "mctl-academy", 0, "explicit grant for a second team"),
    ("karabu", "mctl-academy", 1, "a grant is for its team only"),
    ("karabu", "openclaw", 0, "a shared name may be run by any team"),
    ("karabu", "openclaw", 1, "only a granted team may build a shared name", "--build"),
    ("labs", "openclaw", 0, "the granted team may build a shared name", "--build"),
    ("karabu", "brand-new", 0, "build mode does not change a free name", "--build"),
    ("karabu", "brand-new", 0, "an existing tenant", "--tenant"),
    ("platform", "grafana-iac", 1, "a tenant workflow can never act as team platform", "--tenant"),
    ("platform", "brand-new", 1, "nor use team platform for anything", "--tenant"),
    ("nosuch", "brand-new", 1, "a tenant workflow's team must exist", "--tenant"),
    ("labs", "mctl-academy", 0, "a grant still applies to a real tenant", "--tenant", "--build"),
    ("Karabu", "x", 2, "team outside the name grammar"),
    ("karabu", "x/../y", 2, "name outside the name grammar"),
    ("karabu", "ok\nmctl-api", 2, "multi-line name"),
    ("karabu", "", 2, "empty name"),
]
for team, name, want, why, *flags in CASES:
    got = run(root, team, name, *flags)
    check(got == want, f"fixture {flags} {team}/{name!r}: exit {got}, want {want} ({why})")

# The registry is part of the decision: a caller deriving another one is
# refused, not checked against names it does not use.
check(run(root, "karabu", "kuptsi-app", registry="ghcr.io/otherorg") == 2,
      "a registry other than the list's must refuse (exit 2)")
check(run(fixture(LIST_TEXT.replace("registry ghcr.io/mctlhq\n", ""), SERVICES),
          "karabu", "brand-new") == 2,
      "a list without a registry line must refuse (exit 2)")
check(run(fixture(LIST_TEXT + "grant * mctl-api\n", SERVICES), "karabu", "brand-new") == 2,
      "a wildcard grant must make the list unusable (exit 2)")
check(run(root, "karabu", "brand-new", "--bogus") == 2, "unknown option must refuse (exit 2)")
# Even if a tenants/platform directory appeared, a tenant workflow may not act
# as team platform.
check(run(fixture(LIST_TEXT, SERVICES, tenants=("platform",)), "platform", "grafana-iac",
          "--tenant") == 1,
      "--tenant must refuse team platform even with a tenants/platform directory")

# A --tenant check without the tenants tree cannot decide; it is not "no
# such tenant". Without --tenant the tree is not read.
check(run(fixture(LIST_TEXT, SERVICES, tenants=()), "karabu", "brand-new", "--tenant") == 2,
      "--tenant without platform-gitops/tenants/ must be exit 2 (could not decide)")
check(run(fixture(LIST_TEXT, SERVICES, tenants=()), "karabu", "brand-new") == 0,
      "without --tenant the tenants tree is not needed")

# Ownership reads values through the same reader: a commented line still
# claims its image; a values.yaml it cannot read makes the values scan
# undecidable (exit 2), while names decided before the scan are unaffected.
check(run(fixture(LIST_TEXT, {"labs/x": "image:\n  repository: ghcr.io/mctlhq/claimed  # c\n"}),
          "ovk", "claimed") == 1,
      "a commented repository line must still claim its image for its team")
bad_values = {"labs/x": "image: {repository: ghcr.io/mctlhq/x}\n"}
check(run(fixture(LIST_TEXT, bad_values), "ovk", "brand-new") == 2,
      "an unreadable values.yaml must make the values scan undecidable (exit 2)")
check(run(fixture(LIST_TEXT, bad_values), "labs", "mctl-academy") == 0,
      "a granted name is decided before the values scan")
# Text in a block scalar claims nothing and is not unreadable, whether a
# key or a sequence item opens it (the openclaw values' `- |` scripts).
script_values = {"labs/x": "command:\n  - |\n    repository: ghcr.io/mctlhq/in-script\n"
                           "    echo \"repository: $X\"\nimage:\n  repository: ghcr.io/mctlhq/x\n"}
check(run(fixture(LIST_TEXT, script_values), "ovk", "in-script") == 0,
      "a repository line inside a `- |` script must not claim its image")
check(run(fixture(LIST_TEXT, script_values), "ovk", "x") == 1,
      "the real repository key after the script still claims its image")
check(run(fixture(LIST_TEXT, SERVICES, reader=False), "ovk", "brand-new") == 2,
      "a missing values-images.sh must be exit 2")

# Fail closed: no list, a list line the script does not understand.
check(run(fixture(None, SERVICES), "karabu", "brand-new") == 2,
      "missing image-names.txt must refuse (exit 2)")
check(run(fixture(LIST_TEXT + "allow karabu mctl-api\n", SERVICES),
          "karabu", "brand-new") == 2,
      "an unrecognised list line must refuse every check (exit 2)")
check(run(fixture(LIST_TEXT + "grant karabu\n", SERVICES),
          "karabu", "brand-new") == 2,
      "a grant with a missing field must refuse every check (exit 2)")

# This repository: every existing service passes.
for d in sorted((REPO / "platform-gitops/services").glob("*/*/")):
    team, name = d.parent.name, d.name
    flags = ["--tenant"] if (REPO / "platform-gitops/tenants" / team).is_dir() else []
    got = run(REPO, team, name, *flags)
    check(got == 0, f"existing service {team}/{name} is refused (exit {got}); "
                    "add a reviewed grant to image-names.txt")

# This repository: every image the platform references outside services/ is
# reserved, so no tenant can take its name.
entries = [ln.split() for ln in LIST.read_text().splitlines()
           if ln.strip() and not ln.lstrip().startswith("#")]
reserved = {e[1] for e in entries if e[0] == "reserved"}
prefixes = [e[1] for e in entries if e[0] == "reserved-prefix"]
SKIP = ("platform-gitops/services/", "platform-gitops/agents-state/",
        "platform-gitops/platform-skills/")
files = subprocess.check_output(
    ["git", "ls-files", "platform-gitops", ".github/workflows"],
    cwd=REPO, text=True).split()
referenced = {}
for f in files:
    if f.startswith(SKIP) or f.endswith(".md"):
        continue
    try:
        text = (REPO / f).read_text()
    except (UnicodeDecodeError, IsADirectoryError):
        continue
    for m in re.finditer(r"ghcr\.io/mctlhq/([a-z0-9][a-z0-9._-]*[a-z0-9])", text):
        referenced.setdefault(m.group(1), f)
    for m in re.finditer(r"registry:\s*[\"']?ghcr\.io[\"']?\s*\n\s*repository:\s*"
                         r"[\"']?mctlhq/([a-z0-9][a-z0-9._-]*[a-z0-9])", text):
        referenced.setdefault(m.group(1), f)
check("mctl-portal" in referenced and "mctl-api" in referenced,
      "the reference scan no longer finds mctl-api/mctl-portal; fix the scan")
for name, f in sorted(referenced.items()):
    check(name in reserved or any(name.startswith(p) for p in prefixes),
          f"ghcr.io/mctlhq/{name} (referenced in {f}) is not reserved in image-names.txt")

# The callers run the check before anything is built or pushed.
tpl = yaml.safe_load((REPO / "platform-gitops/argo-workflows/cluster-templates/"
                      "tpl-validate-tenant.yaml").read_text())
by_name = {t["name"]: t for t in tpl["spec"]["templates"]}
src = by_name["validate"]["script"]["source"]
call = ('\nif ! sh platform-gitops/argo-workflows/scripts/check-image-name.sh --tenant $BUILD_FLAG \\\n'
        '    . "$PARAM_CONTAINER_REGISTRY" "$TEAM" "$SERVICE"')
check(call in src, "validate does not run check-image-name.sh --tenant with its registry")
check(call in src and src.index(call) < src.index("# ── 4."),
      "validate must check the image name before the action-specific checks")
# The build decision: extracted from validate and run against a fixture, so
# it is the template's own block that is tested. Its result is both the
# --build flag and the `builds` output deploy-service's build runs on.
m = re.search(r'^(BUILDS=false\n.*?\necho "\$BUILDS" > /tmp/builds)$', src, re.S | re.M)
check(m is not None, "could not extract validate's build decision")
check('\n[ "$BUILDS" = true ] && BUILD_FLAG="--build"' in src,
      "validate must pass --build exactly when it decided to build")
outs = {o["name"]: o for o in by_name["validate"]["outputs"]["parameters"]}
check(outs.get("builds", {}).get("valueFrom", {}).get("path") == "/tmp/builds",
      "validate must output its build decision")
if m:
    decide_root = fixture(LIST_TEXT, {
        "labs/own": "image:\n  repository: ghcr.io/mctlhq/own\n  tag: x\n",
        "labs/quoted": 'image:\n  repository: "ghcr.io/mctlhq/quoted"\n',
        "ovk/openclaw": "image:\n  repository: ghcr.io/mctlhq/mctl-openclaw\n",
        "labs/runs-other": "image:\n  repository: ghcr.io/mctlhq/own\n",
        "labs/no-image": "replicas: 1\n",
        "labs/no-values": None,
        "labs/commented": "image:\n  repository: ghcr.io/mctlhq/commented  # built here\n",
        "labs/single": "image:\n  repository: 'ghcr.io/mctlhq/single'\n",
        "labs/flow": "image: {repository: ghcr.io/mctlhq/flow, tag: x}\n",
        "labs/block": "image:\n  repository: >-\n    ghcr.io/mctlhq/block\n",
        "labs/script": "command:\n  - |\n    repository: ghcr.io/mctlhq/other\n"
                       "image:\n  repository: ghcr.io/mctlhq/script\n",
    })
    # Templates using the other substituted placeholder, and one this step
    # does not substitute.
    tdir = decide_root / "platform-gitops/argo-workflows/service-templates"
    (tdir / "team-named").mkdir()
    (tdir / "team-named/values.yaml.tpl").write_text(
        "image:\n  repository: ghcr.io/mctlhq/__TEAM_NAME__-__SERVICE_NAME__\n")
    (tdir / "odd").mkdir()
    (tdir / "odd/values.yaml.tpl").write_text(
        "image:\n  repository: ghcr.io/mctlhq/__OTHER__\n")

    def builds(action, team, service, repo="org/repo", template="default",
               ctype="base-service"):
        with tempfile.TemporaryDirectory() as out:
            block = (m.group(1).replace("/tmp/builds", f"{out}/builds")
                     .replace("/tmp/onboard-values.yaml", f"{out}/onboard-values.yaml"))
            env = {"PATH": "/usr/bin:/bin", "ACTION": action, "TEAM": team,
                   "SERVICE": service, "REPO": repo, "SERVICE_TEMPLATE": template,
                   "TYPE": ctype, "PARAM_CONTAINER_REGISTRY": REG}
            r = subprocess.run(["sh", "-c", "set -e\n" + block], cwd=decide_root,
                               env=env, capture_output=True, text=True)
            if r.returncode != 0:
                return f"error: {r.stderr}"
            return (pathlib.Path(out) / "builds").read_text().strip()

    for args, want, why in (
        (("update-config", "labs", "own"), "false", "update-config never builds"),
        (("deploy", "labs", "own", ""), "false", "no dockerfile_repo, nothing to build"),
        (("onboard", "labs", "brand-new"), "true", "onboard builds the new service"),
        (("onboard", "ovk", "claw", "org/repo", "openclaw"), "false",
         "the openclaw template runs mctl-openclaw"),
        (("deploy", "labs", "own"), "true", "the service runs <registry>/<name>"),
        (("deploy", "labs", "quoted"), "true", "a quoted repository still matches"),
        (("deploy", "ovk", "openclaw"), "false",
         "an existing openclaw service runs mctl-openclaw, whatever service_template says"),
        (("deploy", "labs", "runs-other"), "false", "the service runs another image"),
        (("deploy", "labs", "no-image"), "true", "no image named: builds as before"),
        (("deploy", "labs", "no-values"), "true", "no values.yaml: builds (step 6 refuses deploy)"),
        (("deploy", "labs", "commented"), "true", "a trailing comment is not another image"),
        (("deploy", "labs", "single"), "true", "single quotes still match"),
        (("onboard", "labs", "brand-new", "org/repo", "no-such-template"), "true",
         "an unknown template falls back to default, as tpl-git-commit does"),
        (("onboard", "labs", "brand-new", "org/repo", "default", "worker-service"), "true",
         "worker-service onboard renders the worker template"),
        (("deploy", "labs", "script"), "true", "text in a `- |` script is not another image"),
        (("onboard", "labs", "x", "org/repo", "team-named"), "false",
         "__TEAM_NAME__ is substituted: the template runs labs-x, not x"),
    ):
        got = builds(*args)
        check(got == want, f"validate build decision {args}: {got!r}, want {want!r} ({why})")
    # A repository line the reader cannot read fails the step: never a
    # silent "no build" that would bump image.tag to a tag nothing pushed.
    for svc in ("flow", "block"):
        got = builds("deploy", "labs", svc)
        check(got.startswith("error:"), f"validate must fail on labs/{svc}'s values, got {got!r}")
    got = builds("onboard", "labs", "x", "org/repo", "odd")
    check(got.startswith("error:"), f"validate must fail on an unsubstituted placeholder, got {got!r}")

# values-images.sh: the one reader of `repository:` both callers use.
check(subprocess.run(["git", "ls-files", "-s", str(READER)], cwd=REPO, capture_output=True,
                     text=True).stdout.startswith("100755"),
      "values-images.sh must be committed executable, like its siblings")
def read_images(text):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(text)
    r = subprocess.run(["sh", str(READER), f.name], capture_output=True, text=True)
    pathlib.Path(f.name).unlink()
    return r.returncode, r.stdout.split()

for text, want in (
    ("image:\n  repository: ghcr.io/mctlhq/a\n", (0, ["ghcr.io/mctlhq/a"])),
    ('image:\n  repository: "ghcr.io/mctlhq/a"\n', (0, ["ghcr.io/mctlhq/a"])),
    ("image:\n  repository: 'ghcr.io/mctlhq/a'  # c\n", (0, ["ghcr.io/mctlhq/a"])),
    ("image:\n  repository: ghcr.io/mctlhq/a # c\n  tag: x\n", (0, ["ghcr.io/mctlhq/a"])),
    ("image:\n\trepository:\tghcr.io/mctlhq/a\n", (0, ["ghcr.io/mctlhq/a"])),
    ("a:\n  repository: x/a\nb:\n  repository: x/b\n", (0, ["x/a", "x/b"])),
    ("# repository: ghcr.io/mctlhq/a\nreplicas: 1\n", (0, [])),
    ("image_repository: something odd here\n", (0, [])),
    ("replicas: 1\n", (0, [])),
    ("image: {repository: ghcr.io/mctlhq/a}\n", (2, [])),
    ("image:\n  repository: >-\n    ghcr.io/mctlhq/a\n", (2, [])),
    ("image:\n  repository:\n", (2, [])),
    ('image:\n  repository: ""\n', (2, [])),
    ("image:\n  repository: *img\n", (2, [])),
    ('image:\n  repository: "ghcr.io/mctlhq/a # b"\n', (2, [])),
    ("image:\n  repository: ghcr.io/mctlhq/a extra\n", (2, [])),
    ("image:\n  repository:ghcr.io/mctlhq/a\n", (2, [])),
    ("image:\n  repository : ghcr.io/mctlhq/a\n", (2, [])),
    ('image:\n  "repository": ghcr.io/mctlhq/a\n', (2, [])),
    ("image:\n  'repository': ghcr.io/mctlhq/a\n", (2, [])),
    ("- repository: ghcr.io/mctlhq/a\n", (2, [])),
    ("image:\n  repository: ghcr.io/mctlhq/a\r\n", (0, ["ghcr.io/mctlhq/a"])),
    # Block scalars are text, skipped: opened by a key or by a sequence
    # item, they hold the lines deeper than that key or dash, and end at the
    # next line no deeper.
    ('config: |\n  {"subject": {"repository": ["x"]}}\nimage:\n  repository: x/a\n',
     (0, ["x/a"])),
    ("config: |\n  repository: x/b\nimage:\n  repository: x/a\n", (0, ["x/a"])),
    ("env:\n  - name: X\n    value: >-\n      repository: y\n", (0, [])),
    ("note: |  # c\n  text\n\n  more\nimage:\n  repository: x/a\n", (0, ["x/a"])),
    ("command:\n  - |\n    repository: x/y\n", (0, [])),
    ('command:\n  - |\n    {"repository": ["x"]}\n    echo "repository: $X"\n', (0, [])),
    # A sibling `- |` at the dash's column closes the previous scalar.
    ("command:\n  - |\n    echo\n  - |\n    repository: x/y\n  - image:\n      repository: x/a\n",
     (0, ["x/a"])),
    ("command:\n- |\n  repository: x/y\nimage:\n  repository: x/a\n", (0, ["x/a"])),
    # A key in a sequence item opens at the key's column, not the dash's.
    ("jobs:\n  - run: |\n      repository: x/b\n    image:\n      repository: x/a\n",
     (0, ["x/a"])),
    ("c: &a |\n  repository: x/b\nd: !!str >-\n  repository: x/c\nimage:\n  repository: x/a\n",
     (0, ["x/a"])),
    # A plain value that merely ends in " - |" opens no scalar.
    ("  d: a - |\n  image:\n    repository: x/a\n", (0, ["x/a"])),
    ("d: pipe - >\nimage:\n  repository: x/a\n", (0, ["x/a"])),
    ("- d: a - |\n  repository: x/a\n", (0, ["x/a"])),
):
    rc, out = read_images(text)
    check((rc, out if rc == 0 else []) == want,
          f"values-images.sh on {text!r}: {(rc, out)}, want {want}")
# The reader against the real files: every service values.yaml and every
# template (with the placeholders an image can use substituted) reads, and
# yields exactly the repository keys a structural parse finds. A
# mis-measured block scalar that swallows a key, or a form the reader reads
# differently from YAML, fails here rather than losing a claim silently.
def yaml_repos(text):
    found = []
    def walk(n):
        if isinstance(n, dict):
            for k, v in n.items():
                if k == "repository" and isinstance(v, str):
                    found.append(v)
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(yaml.safe_load(text))
    return found

real_values = (sorted((REPO / "platform-gitops/services").glob("*/*/values.yaml"))
               + sorted((REPO / "platform-gitops/argo-workflows/service-templates").glob("*/values.yaml.tpl")))
check(len(real_values) > 4, "no real values files found")
for f in real_values:
    text = f.read_text().replace("__SERVICE_NAME__", "svc").replace("__TEAM_NAME__", "team")
    rc, out = read_images(text)
    want = yaml_repos(text)
    check(rc == 0 and out == want,
          f"values-images.sh on {f.relative_to(REPO)}: {(rc, out)}, want {want}")

env = {e["name"]: e["value"] for e in by_name["validate"]["script"].get("env", [])}
check(env.get("PARAM_CONTAINER_REGISTRY") == "{{inputs.parameters.container_registry}}",
      "validate must take the registry as a bound env value")
img = by_name.get("image-name", {}).get("script", {}).get("source", "")
check('\nif ! sh /tmp/mctl-gitops/platform-gitops/argo-workflows/scripts/check-image-name.sh --tenant $BUILD_FLAG' in img and '"ghcr.io/${GITOPS_ORG}"' in img,
      "image-name template must run the script with --tenant and the org's registry")
check('[ -n "$PARAM_GIT_REF" ] && BUILD_FLAG="--build"' in img,
      "image-name template must check in build mode when preview-deploy builds")
for t in ("validate", "image-name"):
    lim = by_name.get(t, {}).get("script", {}).get("resources", {}).get("limits", {})
    check(lim.get("memory") and lim.get("cpu"), f"{t} must declare resource limits")

ds = yaml.safe_load((REPO / "platform-gitops/argo-workflows/cluster-templates/"
                     "wft-deploy-service.yaml").read_text())
dtasks = {t["name"]: t for t in
          [t for t in ds["spec"]["templates"] if t["name"] == "deploy-pipeline"][0]["dag"]["tasks"]}
vparams = {p["name"]: p["value"] for p in dtasks["validate"]["arguments"]["parameters"]}
check(vparams.get("container_registry") == "{{workflow.parameters.container_registry}}",
      "deploy-service must hand validate the registry it builds into")
check(dtasks["build-image"]["when"] == '"{{tasks.validate.outputs.parameters.builds}}" == "true"',
      "deploy-service must build exactly when validate decided to (and checked with --build)")

ct = (REPO / "platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml").read_text()
reserved_line = [ln for ln in ct.splitlines() if "for reserved in" in ln][0]
reserved_names = reserved_line.split("for reserved in", 1)[1].split(";")[0].split()
check("platform" in reserved_names,
      "wft-create-tenant must reserve the tenant name 'platform' (image-names.txt grants to it)")

# Direct dispatchers of build-image.yaml outside Argo, as found on each
# repository's default branch (all other organisation workflows call
# release-deploy.yaml): each must keep passing the push-time check.
# mctl-openclaw's upstream sync (team labs, openclaw) is gone with that
# repository's archiving, and so is its grant: nobody may build openclaw.
check(run(REPO, "labs", "openclaw", "--build") == 1,
      "no team may build openclaw now that its only builder is archived")
for team, name in (("platform", "grafana-iac"),  # platform-gitops/images/*, by hand
                   ("platform", "mc"),
                   ("platform", "vault-iac"),
                   ("platform", "zitadel-iac"),
                   ("platform", "mctl-agent")):
    check(run(REPO, team, name, "--build") == 0,
          f"direct build-image dispatcher {team}/{name} would be refused")

pv = yaml.safe_load((REPO / "platform-gitops/argo-workflows/cluster-templates/"
                     "wft-preview-deploy.yaml").read_text())
tasks = {t["name"]: t for t in
         [t for t in pv["spec"]["templates"] if t["name"] == "preview-pipeline"][0]["dag"]["tasks"]}
check(tasks.get("image-name", {}).get("templateRef", {}).get("template") == "image-name",
      "preview-deploy does not run the image-name check")
check("image-name" in tasks["build-image"].get("dependencies", []),
      "preview-deploy's build must depend on the image-name check")
check("image-name" in tasks["deploy-preview"].get("dependencies", []),
      "preview-deploy's deploy must depend on the image-name check")
iparams = {p["name"]: p["value"] for p in tasks["image-name"]["arguments"]["parameters"]}
check(iparams.get("git_ref") == "{{workflow.parameters.git_ref}}",
      "preview-deploy must tell image-name whether it will build (git_ref)")

# build-image.yaml's push-time check pins image_name to
# <registry>/<component_name> and checks team_name, so both Argo callers must
# send team_name and component_name in the dispatch: an empty one would
# refuse every tenant build. Pinned from the task arguments through the
# trigger template's env into the dispatch payload.
for label, doc, pipeline in (("deploy-service", ds, "deploy-pipeline"),
                             ("preview-deploy", pv, "preview-pipeline")):
    ptasks = {t["name"]: t for t in
              [t for t in doc["spec"]["templates"] if t["name"] == pipeline][0]["dag"]["tasks"]}
    bargs = {p["name"]: p["value"] for p in ptasks["build-image"]["arguments"]["parameters"]}
    trig = [t for t in doc["spec"]["templates"]
            if t["name"] == ptasks["build-image"]["template"]][0]
    tenv = {e["name"]: e.get("value") for e in trig["script"].get("env", [])}
    tsrc = trig["script"]["source"]
    for p in ("team_name", "component_name"):
        check(bargs.get(p) == "{{workflow.parameters.%s}}" % p,
              f"{label}'s build-image must pass {p}")
        check(tenv.get("PARAM_" + p.upper()) == "{{inputs.parameters.%s}}" % p,
              f"{label}'s trigger template must bind {p} from its inputs")
        check(re.search(r'\b%s\s*=\s*os\.environ\["PARAM_%s"\]' % (p, p.upper()), tsrc) is not None
              and re.search(r'"%s":\s*%s,' % (p, p), tsrc) is not None,
              f"{label}'s dispatch payload must carry {p}")
dbargs = {p["name"]: p["value"] for p in dtasks["build-image"]["arguments"]["parameters"]}
check(dbargs.get("image_name")
      == "{{workflow.parameters.container_registry}}/{{workflow.parameters.component_name}}",
      "deploy-service must build <registry>/<component_name>")

bi = yaml.safe_load((REPO / ".github/workflows/build-image.yaml").read_text())
steps = bi["jobs"]["build"]["steps"]
names = [s.get("name", "") for s in steps]
check("Check image name" in names, "build-image.yaml has no image-name check")
if "Check image name" in names:
    idx = names.index("Check image name")
    for later in ("Fetch Vault PAT", "Log in to GHCR", "Build and push"):
        check(later in names and idx < names.index(later),
              f"build-image.yaml must check the image name before '{later}'")
    run_src = steps[idx]["run"]
    check("check-image-name.sh" in run_src, "build-image's check does not run the script")
    check('"$INPUT_IMAGE_NAME" != "$expected"' in run_src,
          "build-image must pin image_name to ghcr.io/<org>/<component_name>")
    check('\nif ! sh .image-name-policy/platform-gitops/argo-workflows/scripts/check-image-name.sh --build' in run_src
          and '"${REGISTRY}/${GITHUB_REPOSITORY_OWNER}"' in run_src,
          "build-image must check in build mode against its own registry")
# The caller is classified from github.workflow_ref bound explicitly into the
# step (in a called run it names the caller's workflow), not from the
# implicit GITHUB_WORKFLOW_REF or the event name.
caller = [s for s in steps if s.get("id") == "caller"]
check(len(caller) == 1
      and caller[0].get("env", {}).get("CALLER_WORKFLOW_REF") == "${{ github.workflow_ref }}"
      and 'case "$CALLER_WORKFLOW_REF" in' in caller[0]["run"]
      and "GITHUB_WORKFLOW_REF" not in caller[0]["run"],
      "build-image must classify its caller from an explicitly bound github.workflow_ref")
# Every release dispatcher in the organisation (release-please.yml in
# mctl-academy, -agent, -agents, -api, -docs, -portal, -telegram, -web,
# portfolio, seerrsense; mctl-alice release-deploy.yml; mctl-design
# deploy.yml; mctl-telegram preview-deploy.yml) runs release-deploy.yaml,
# which reaches build-image.yaml as a workflow_call. There the caller is
# classified as not direct, so the image-name pin does not apply and
# release names that differ from the component (mctl-telegram-preview ->
# mctl-telegram) keep building. Run the classification for both refs.
rd = yaml.safe_load((REPO / ".github/workflows/release-deploy.yaml").read_text())
check(any(j.get("uses") == "./.github/workflows/build-image.yaml" for j in rd["jobs"].values()),
      "release-deploy.yaml must call build-image.yaml as a reusable workflow")
if len(caller) == 1:
    for ref, want in (("mctlhq/mctl-gitops/.github/workflows/release-deploy.yaml@refs/heads/main", "false"),
                      ("mctlhq/mctl-gitops/.github/workflows/build-image.yaml@refs/heads/main", "true")):
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run(["bash", "-c", caller[0]["run"]], capture_output=True, text=True,
                               env={"PATH": "/usr/bin:/bin", "CALLER_WORKFLOW_REF": ref,
                                    "GITHUB_REPOSITORY": "mctlhq/mctl-gitops",
                                    "GITHUB_OUTPUT": f"{out}/o"})
            got = (pathlib.Path(out) / "o").read_text().strip() if r.returncode == 0 else r.stderr
            check(got == f"direct={want}", f"caller classification for {ref}: {got!r}")
# ...and the steps that enforce the pin run only for a direct dispatch, so a
# release workflow_call skips them.
for step in ("Check out image-name policy", "Check image name"):
    st = [x for x in steps if x.get("name") == step]
    check(len(st) == 1 and st[0].get("if") == "steps.caller.outputs.direct == 'true'",
          f"'{step}' must run only for a direct dispatch, not for release workflow_calls")
# The check reads team_name and component_name, so both trigger kinds must
# declare them: an undeclared dispatch input is refused by GitHub.
on = bi.get("on", bi.get(True, {}))
for trigger in ("workflow_dispatch", "workflow_call"):
    declared = (on.get(trigger) or {}).get("inputs", {})
    for inp in ("image_name", "team_name", "component_name"):
        check(inp in declared, f"build-image.yaml must declare {inp} under {trigger}")
push = [s for s in steps if s.get("name") == "Build and push"][0]["with"]["tags"]
latest = [ln for ln in push.splitlines() if "latest" in ln]
check(len(latest) == 1 and "steps.caller.outputs.direct != 'true'" in latest[0],
      "build-image must push :latest only for release (workflow_call) builds")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"OK: {len(CASES) + 7} fixture cases, "
      f"{len(list((REPO / 'platform-gitops/services').glob('*/*/')))} existing services, "
      f"{len(referenced)} referenced platform images, "
      f"{len(real_values)} real values files read")
