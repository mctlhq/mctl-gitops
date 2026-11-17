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
import re
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


def render(template_text, tag="1.2.3"):
    with tempfile.TemporaryDirectory() as tmp:
        chart = pathlib.Path(tmp) / "bootstrap"
        shutil.copytree(CHART, chart)
        (chart / TEMPLATE).write_text(template_text.replace('tag: "0.0.0-unreleased"', f'tag: "{tag}"', 1))
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


DNS1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def migrate_job(rendered):
    jobs = [d for d in yaml.safe_load_all(rendered) if d and d["kind"] == "Job"]
    return jobs[0] if len(jobs) == 1 else None


def deployment_wave(rendered):
    for d in yaml.safe_load_all(rendered):
        if d and d["kind"] == "Deployment" and d["metadata"]["name"] == "mctl-glovo":
            return int(d["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"])
    return None


def migration_problems(text):
    """Problems with the per-release migration Job; empty means consistent."""
    out: list[str] = []
    a, b = render(text, "0.1.0"), render(text, "0.2.0-rc.1")
    if a.returncode or b.returncode:
        return [f"render failed: {(a.stderr or b.stderr)[-200:]}"]
    ja, jb = migrate_job(a.stdout), migrate_job(b.stdout)
    if not ja or not jb:
        return ["expected exactly one migration Job per render"]
    opts = ja["metadata"].get("annotations", {}).get("argocd.argoproj.io/sync-options", "")
    if "Force=true" in opts or "Replace=true" in opts:
        out.append(f"Job sync-options {opts!r}: Force/Replace recreates it on every root-app sync")
    na, nb = ja["metadata"]["name"], jb["metadata"]["name"]
    if na == nb:
        out.append("Job name does not change with the image tag (immutable spec cannot take the new image)")
    for n in (na, nb):
        if not DNS1123.match(n) or len(n) > 63:
            out.append(f"Job name {n!r} is not a valid DNS-1123 name")
    wave = int(ja["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"])
    dep = deployment_wave(a.stdout)
    if dep is None or not wave < dep:
        out.append(f"Deployment wave {dep} does not wait for the migration wave {wave}")
    return out


def main():
    text = (ROOT / "platform-gitops/bootstrap" / TEMPLATE).read_text()
    r = render(text)
    check(r.returncode == 0, f"render failed: {r.stderr[-300:]}")
    if r.returncode == 0:
        for p in pod_problems(r.stdout):
            check(False, p)
    for p in migration_problems(text):
        check(False, p)
    # the placeholder tag must still fail the render when deploy is on
    with tempfile.TemporaryDirectory() as tmp:
        chart = pathlib.Path(tmp) / "bootstrap"
        shutil.copytree(CHART, chart)
        g = subprocess.run(["helm", "template", "t", str(chart), "-f", str(VALUES), *SWITCHES],
                           capture_output=True, text=True)
        check(g.returncode != 0 and "placeholder" in g.stderr, "placeholder tag with deploy on must fail the render")
    if failures:
        print("\n".join("FAIL " + f for f in failures), file=sys.stderr)
        return 1
    print("ok: consent refresher render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
