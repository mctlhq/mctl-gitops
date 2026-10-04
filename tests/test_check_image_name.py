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


def run(root, team, name):
    return subprocess.run(["sh", str(SCRIPT), str(root), team, name],
                          capture_output=True, text=True).returncode


def fixture(list_text, services):
    """services: {"team/name": values.yaml text or None}"""
    d = pathlib.Path(tempfile.mkdtemp())
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
reserved-prefix mctl-
reserved grafana-iac
grant platform grafana-iac
grant labs mctl-academy
grant ovk mctl-academy
grant * openclaw
"""
SERVICES = {
    "labs/kuptsi-app": "image:\n  repository: ghcr.io/mctlhq/kuptsi-app\n",
    "labs/telegram-preview": "image:\n  repository: \"ghcr.io/mctlhq/bot-image\"\n",
    "labs/mctl-academy": None,
    # onboarded, values not written yet: the directory alone claims the name
    "labs/fresh-svc": None,
    "ovk/mctl-academy": None,
    "admins/openclaw": "image:\n  repository: ghcr.io/mctlhq/mctl-openclaw\n",
}
root = fixture(LIST_TEXT, SERVICES)

CASES = [
    # (team, name, expected exit, why)
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
    ("karabu", "openclaw", 0, "wildcard grant"),
    ("Karabu", "x", 2, "team outside the name grammar"),
    ("karabu", "x/../y", 2, "name outside the name grammar"),
    ("karabu", "ok\nmctl-api", 2, "multi-line name"),
    ("karabu", "", 2, "empty name"),
]
for team, name, want, why in CASES:
    got = run(root, team, name)
    check(got == want, f"fixture {team}/{name!r}: exit {got}, want {want} ({why})")

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
    got = run(REPO, team, name)
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
call = 'check-image-name.sh . "$TEAM" "$SERVICE"'
check(call in src, "validate does not run check-image-name.sh")
check(call in src and src.index(call) < src.index("# ── 4."),
      "validate must check the image name before the action-specific checks")
check("check-image-name.sh" in by_name.get("image-name", {}).get("script", {}).get("source", ""),
      "tpl-validate-tenant has no image-name template running the script")

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
push = [s for s in steps if s.get("name") == "Build and push"][0]["with"]["tags"]
latest = [ln for ln in push.splitlines() if "latest" in ln]
check(len(latest) == 1 and "steps.caller.outputs.direct != 'true'" in latest[0],
      "build-image must push :latest only for release (workflow_call) builds")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"OK: {len(CASES) + 3} fixture cases, "
      f"{len(list((REPO / 'platform-gitops/services').glob('*/*/')))} existing services, "
      f"{len(referenced)} referenced platform images")
