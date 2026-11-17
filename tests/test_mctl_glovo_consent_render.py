#!/usr/bin/env python3
"""The C2 service pod with the consent switch on: refresher command and key file access.

Pins, on the bootstrap render of the server Deployment:
  - the consent token refresher is the third binary of the SAME image as the
    server (the image ENTRYPOINT is the server), so it must set
    command ["token-refresher"] and use the server's image reference;
  - every secret volume mounted by a container is readable by that container:
    a group-readable, not world-readable file (0440) is owned root:<fsGroup>, so
    the pod must set fsGroup and it must equal the gid the container runs as
    (the pod-level runAsGroup unless the container overrides it); a world
    readable mode needs nothing.

The image tag lives in the template (the release flow rewrites it), so the
render runs on a copy of the chart with the placeholder tag replaced.

Run: python3 tests/test_mctl_glovo_consent_render.py   (needs helm)
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
VALUES = CHART / "values.yaml"
TEMPLATE = "templates/mctl-platform/mctl-glovo.yaml"
SWITCHES = ["--set", "mctlGlovo.deploy=true", "--set", "mctlGlovo.c2=true", "--set", "mctlGlovo.consent=true"]

failures: list[str] = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def render(template_text):
    with tempfile.TemporaryDirectory() as tmp:
        chart = pathlib.Path(tmp) / "bootstrap"
        shutil.copytree(CHART, chart)
        (chart / TEMPLATE).write_text(template_text.replace('tag: "0.0.0-unreleased"', 'tag: "1.2.3"', 1))
        return subprocess.run(["helm", "template", "t", str(chart), "-f", str(VALUES), *SWITCHES],
                              capture_output=True, text=True)


def pod_problems(rendered):
    """Every problem found in the server pod of one render; empty means consistent."""
    out: list[str] = []
    dep = [d for d in yaml.safe_load_all(rendered) if d and d["kind"] == "Deployment"
           and d["metadata"]["name"] == "mctl-glovo"]
    if len(dep) != 1:
        return [f"expected exactly one Deployment, got {len(dep)}"]
    spec = dep[0]["spec"]["template"]["spec"]
    psc = spec.get("securityContext") or {}
    containers = {c["name"]: c for c in spec["containers"]}
    server, refresher = containers.get("server"), containers.get("consent-token-refresher")
    if not server or not refresher:
        return ["server or consent-token-refresher container missing"]
    if refresher.get("command") != ["token-refresher"]:
        out.append(f"refresher command is {refresher.get('command')!r}, want ['token-refresher']")
    if refresher.get("image") != server.get("image"):
        out.append("refresher image differs from the server image (it is a binary of the same image)")
    secrets = {v["name"]: v["secret"] for v in spec.get("volumes", []) if "secret" in v}
    for c in spec["containers"] + spec.get("initContainers", []):
        gid = (c.get("securityContext") or {}).get("runAsGroup", psc.get("runAsGroup"))
        for m in c.get("volumeMounts", []):
            sec = secrets.get(m["name"])
            if sec is None:
                continue
            mode = sec.get("defaultMode", 0o644)
            if mode & 0o007:
                continue  # world readable: needs no group
            if not mode & 0o070:
                out.append(f"{c['name']}: secret volume {m['name']} mode {mode:o} has no group read bit")
            elif psc.get("fsGroup") is None:
                out.append(f"{c['name']}: secret volume {m['name']} mode {mode:o} but no pod fsGroup "
                           "(files stay root:root, unreadable by the non-root uid)")
            elif psc["fsGroup"] != gid:
                out.append(f"{c['name']}: fsGroup {psc['fsGroup']} != container gid {gid}")
    return out


def main():
    text = (ROOT / "platform-gitops/bootstrap" / TEMPLATE).read_text()
    r = render(text)
    check(r.returncode == 0, f"render failed: {r.stderr[-300:]}")
    if r.returncode == 0:
        for p in pod_problems(r.stdout):
            check(False, p)
    if failures:
        print("\n".join("FAIL " + f for f in failures), file=sys.stderr)
        return 1
    print("ok: consent refresher render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
