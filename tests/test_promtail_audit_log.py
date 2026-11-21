#!/usr/bin/env python3
"""The Kubernetes API audit log reaches Loki (#871, SOC F20).

kube.tf points the apiserver at audit-log-path, but nothing read that file, so
an auditor needed ssh/kubectl exec on the control-plane node. Pins, on the
bootstrap render of loki.yaml:
  - promtail mounts the directory of kube.tf's audit-log-path, read-only;
  - a scrape job labelled job=kube-apiserver-audit globs the audit log under
    that mount (the live file only);
  - the audit policy never records Secret or token bodies, which is what makes
    shipping the file to Loki acceptable: Secrets and token objects stay at
    Metadata, and the only Request/RequestResponse rules are authorization
    reviews. A policy that starts logging bodies must fail here first.

Run: python3 tests/test_promtail_audit_log.py   (needs helm, pyyaml)
"""
import fnmatch
import pathlib
import re
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
KUBE_TF = ROOT / "infrastructure" / "k3s-preview" / "kube.tf"
POLICY = ROOT / "infrastructure" / "k3s-preview" / "audit-policy.yaml"
TEMPLATE = "templates/observability/loki.yaml"

failures: list[str] = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def promtail_values():
    out = subprocess.run(["helm", "template", "t", str(CHART), "-f", str(CHART / "values.yaml"),
                          "--show-only", TEMPLATE], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"helm template failed: {out.stderr.strip()}")
    for d in yaml.safe_load_all(out.stdout):
        if d and d.get("kind") == "Application" and d["metadata"]["name"] == "loki-stack":
            return yaml.safe_load(d["spec"]["source"]["helm"]["values"])["promtail"]
    raise SystemExit("loki-stack Application not rendered")


def audit_log_path():
    m = re.search(r'"audit-log-path=([^"]+)"', KUBE_TF.read_text())
    if not m:
        raise SystemExit("kube.tf has no audit-log-path")
    return pathlib.PurePosixPath(m.group(1))


def check_mount_and_scrape(pt, log):
    vols = [v for v in pt.get("extraVolumes") or [] if (v.get("hostPath") or {}).get("path") == str(log.parent)]
    check(len(vols) == 1, f"promtail has no hostPath volume for {log.parent}")
    if len(vols) != 1:
        return
    mounts = [m for m in pt.get("extraVolumeMounts") or [] if m.get("name") == vols[0]["name"]]
    check(len(mounts) == 1 and mounts[0].get("readOnly") is True,
          "the audit-log mount is missing or not readOnly")
    if len(mounts) != 1:
        return
    jobs = yaml.safe_load(pt["config"]["snippets"].get("extraScrapeConfigs") or "[]") or []
    jobs = [j for j in jobs if j.get("job_name") == "kube-apiserver-audit"]
    check(len(jobs) == 1, "no kube-apiserver-audit scrape job")
    if len(jobs) != 1:
        return
    sc = jobs[0]["static_configs"][0]
    check(sc["labels"].get("job") == "kube-apiserver-audit", "scrape job lacks job=kube-apiserver-audit")
    glob = sc["labels"].get("__path__", "")
    mount = pathlib.PurePosixPath(mounts[0]["mountPath"])
    check(str(pathlib.PurePosixPath(glob).parent) == str(mount), f"scrape glob {glob!r} is not under {mount}")
    live = str(mount / log.name)
    check(fnmatch.fnmatch(live, glob), f"glob {glob!r} does not match the live file {live}")
    # lumberjack rotates to audit-<timestamp>.log
    rotated = str(mount / (log.stem + "-2026-11-21T10-00-00.000" + log.suffix))
    # promtail keys positions by path: a rotated copy would be re-read from 0
    check(not fnmatch.fnmatch(rotated, glob), f"glob {glob!r} matches rotated copies like {rotated}; events ship twice")


def check_policy(doc):
    rules = doc["rules"]
    levels = {}
    for r in rules:
        for res in r.get("resources") or []:
            for name in res.get("resources") or []:
                levels.setdefault((res.get("group", ""), name), []).append(r["level"])
    check(levels.get(("", "secrets")) == ["Metadata"], f"secrets must be Metadata only: {levels.get(('', 'secrets'))}")
    for name in ("tokenreviews", "tokenrequests"):
        check(levels.get(("authentication.k8s.io", name)) == ["Metadata"], f"{name} must be Metadata only")
    for r in rules:
        if r["level"] in ("Request", "RequestResponse"):
            groups = {res.get("group") for res in r.get("resources") or []}
            check(groups == {"authorization.k8s.io"},
                  f"a {r['level']} rule outside authorization reviews would ship bodies to Loki: {r}")
    check(rules[-1] == {"level": "Metadata"}, "the catch-all must stay Metadata")


def main():
    check_mount_and_scrape(promtail_values(), audit_log_path())
    check_policy(yaml.safe_load(POLICY.read_text()))
    if failures:
        print("\n".join("FAIL " + f for f in failures), file=sys.stderr)
        return 1
    print("ok: promtail ships the audit log, policy keeps bodies out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
