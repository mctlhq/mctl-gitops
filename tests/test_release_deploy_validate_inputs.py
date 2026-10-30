"""Exercise release-deploy.yaml's validate-inputs step against fixtures.

Extracts the step's bash from the workflow (as test_release_deploy_bump.py
does for the bump heredoc), runs it with INPUT_* env, and asserts its prefix
list equals the bump script's ALLOWED_PREFIXES.
"""
import os
import re
import subprocess
import sys
import pathlib
import textwrap

import yaml

WF_PATH = pathlib.Path(".github/workflows/release-deploy.yaml")
WF = WF_PATH.read_text()
doc = yaml.safe_load(WF)
step = doc["jobs"]["validate-inputs"]["steps"][0]
SCRIPT = step["run"]

bump = re.search(r"ALLOWED_PREFIXES = \((.*?)\)", WF, re.S)
assert bump, "could not find bump ALLOWED_PREFIXES"
bump_prefixes = re.findall(r'"([^"]+)"', bump.group(1))
mine = re.search(r"ALLOWED_PREFIXES=\((.*?)\)", SCRIPT, re.S)
assert mine, "could not find validate-inputs ALLOWED_PREFIXES"
mine_prefixes = re.findall(r'"([^"]+)"', mine.group(1))
assert bump_prefixes and bump_prefixes == mine_prefixes, (bump_prefixes, mine_prefixes)

VALID = {
    "REPO": "mctlhq/mctl-docs",
    "GIT_REF": "main-abc1234",
    "IMAGE_NAME": "ghcr.io/mctlhq/mctl-docs",
    "IMAGE_TAG": "0.1.18",
    "DOCKERFILE_PATH": "Dockerfile",
    "TEAM_NAME": "labs",
    "COMPONENT_NAME": "mctl-docs",
    "VALUES_PATH": "",
    "VALUES_GLOB": "",
}


def run(**over):
    env = {k: v for k, v in os.environ.items() if not k.startswith("INPUT_")}
    for k, v in {**VALID, **over}.items():
        env["INPUT_" + k] = v
    p = subprocess.run(["bash", "-c", SCRIPT], env=env, capture_output=True, text=True)
    return p.returncode


ACCEPT = [
    {},
    {"GIT_REF": "v1.2.3"},
    {"VALUES_GLOB": "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml"},
    {"VALUES_PATH": "platform-gitops/services/admins/a/values.yaml,platform-gitops/services/admins/b/values.yaml"},
    {"VALUES_PATH": "platform-gitops/services/admins/a/values.yaml\nplatform-gitops/bootstrap/templates/mctl-platform/x.yaml"},
]
REJECT = [
    {"TEAM_NAME": "labs/other"},
    {"IMAGE_TAG": '1.2.3"\n  x: y'},
    {"GIT_REF": "v1$(id)"},
    {"GIT_REF": "-x"},
    {"VALUES_PATH": "../etc/passwd"},
    {"VALUES_PATH": "/abs"},
    {"VALUES_PATH": "platform-gitops/services/../../x"},
    {"VALUES_GLOB": "other/dir/*.yaml"},
    {"IMAGE_NAME": "ghcr.io/MctlHQ/x"},
    {"IMAGE_NAME": "ghcr.io/mctlhq/x y"},
    {"REPO": "nodash"},
    {"DOCKERFILE_PATH": "../Dockerfile"},
]

for case in ACCEPT:
    assert run(**case) == 0, f"should accept {case!r}"
for case in REJECT:
    assert run(**case) != 0, f"should reject {case!r}"
print("ok")
