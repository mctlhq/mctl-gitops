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
import subprocess
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "platform-gitops/argo-workflows/scripts/check-image-name.sh"
LIST = REPO / "platform-gitops/argo-workflows/config/image-names.txt"

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


REG = "ghcr.io/mctlhq"


def run(root, team, name, *flags, registry=REG):
    return subprocess.run(["sh", str(SCRIPT), *flags, str(root), registry, team, name],
                          capture_output=True, text=True).returncode


def fixture(list_text, services, tenants=("labs", "ovk", "karabu", "admins")):
    """services: {"team/name": values.yaml text or None}"""
    d = pathlib.Path(tempfile.mkdtemp())
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
build_cond = ('if [ "$ACTION" != "update-config" ] && [ -n "$REPO" ] && '
              '[ "$SERVICE_TEMPLATE" != "openclaw" ]; then\n  BUILD_FLAG="--build"')
check(build_cond in src, "validate must pass --build exactly when deploy-service builds")
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
when = dtasks["build-image"]["when"]
for part in ('"{{workflow.parameters.action}}\" != \"update-config\"',
             '"{{workflow.parameters.dockerfile_repo}}\" != \"\"',
             '"{{workflow.parameters.service_template}}\" != \"openclaw\"'):
    check(part.replace('\\"', '"') in when.replace('\\"', '"'),
          f"deploy-service build condition changed; keep validate's --build in step ({part})")

ct = (REPO / "platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml").read_text()
reserved_line = [ln for ln in ct.splitlines() if "for reserved in" in ln][0]
reserved_names = reserved_line.split("for reserved in", 1)[1].split(";")[0].split()
for t in ("platform", "admins"):
    check(t in reserved_names,
          f"wft-create-tenant must reserve the tenant name '{t}' (image-names.txt grants to it)")

# Direct dispatchers of build-image.yaml outside Argo, as found on each
# repository's default branch (all other organisation workflows call
# release-deploy.yaml): each must keep passing the push-time check.
for team, name in (("labs", "openclaw"),          # mctl-openclaw upstream-sync-release.yml
                   ("platform", "grafana-iac"),  # platform-gitops/images/*, by hand
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
push = [s for s in steps if s.get("name") == "Build and push"][0]["with"]["tags"]
latest = [ln for ln in push.splitlines() if "latest" in ln]
check(len(latest) == 1 and "steps.caller.outputs.direct != 'true'" in latest[0],
      "build-image must push :latest only for release (workflow_call) builds")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"OK: {len(CASES) + 7} fixture cases, "
      f"{len(list((REPO / 'platform-gitops/services').glob('*/*/')))} existing services, "
      f"{len(referenced)} referenced platform images")
