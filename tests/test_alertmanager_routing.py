"""issue-1771: Alertmanager routing of critical and alerting-path alerts.

Renders the `monitoring` Application from the bootstrap chart, extracts
`alertmanager.config`, runs `amtool check-config`, and pins which receivers
`amtool config routes test` reports for a table of label sets plus every
`severity: critical` alert in `vm-rules/*.yaml`. amtool is the real
Alertmanager routing implementation, so `continue` and default-receiver
semantics are not reimplemented here.

`--selftest` removes the severity route and asserts the test then fails.

Run: python3 tests/test_alertmanager_routing.py [--selftest]
"""
import copy
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
RULES = ROOT / "platform-gitops" / "infra-components" / "observability" / "vm-rules"

AM_VERSION = "0.28.1"
AM_SHA256 = "5ac7ab5e4b8ee5ce4d8fb0988f9cb275efcc3f181b4b408179fafee121693311"

# (labels, expected receivers in amtool output order)
CASES = [
    ({"alertname": "KubeAPIDown", "severity": "critical"}, "telegram,mctl-agent"),
    ({"alertname": "PodCrashLooping", "severity": "warning"}, "mctl-agent"),
    ({"alertname": "Watchdog", "severity": "none"}, "null"),
    ({"alertname": "InfoInhibitor", "severity": "none"}, "null"),
    ({"alertname": "KubeSchedulerDown", "severity": "critical"}, "null"),
    ({"alertname": "KubeControllerManagerDown", "severity": "critical"}, "null"),
    ({"alertname": "KubeProxyDown", "severity": "critical"}, "null"),
    ({"alertname": "VaultBackupStale", "severity": "critical"}, "telegram"),
    ({"alertname": "MctlApiDown", "severity": "critical"}, "telegram,mctl-agent"),
    ({"alertname": "MctlAgentMetricsAbsent", "severity": "warning"}, "telegram,mctl-agent"),
    ({"alertname": "AlertmanagerFailedReload", "severity": "critical"}, "telegram,mctl-agent"),
    ({"alertname": "AlertmanagerFailedToSendAlerts", "severity": "critical"}, "telegram,mctl-agent"),
    ({"alertname": "AlertmanagerFailedToSendAlerts", "severity": "warning"}, "telegram,mctl-agent"),
    ({"alertname": "ServiceDown", "severity": "warning", "job": "vmalert-vmks"}, "telegram,mctl-agent"),
    ({"alertname": "ServiceDown", "severity": "critical", "job": "vmalert-vmks"}, "telegram,mctl-agent"),
    ({"alertname": "ServiceDown", "severity": "critical", "job": "vmalertmanager-vmks"}, "telegram,mctl-agent"),
    ({"alertname": "MctlTelegramPoolNearCapacity", "severity": "warning"}, "mctl-agent"),
    ({"alertname": "ArgoCDApplicationDegraded", "severity": "warning", "project": "platform"}, "telegram,mctl-agent"),
    ({"alertname": "SeerrSenseReviewerConnected", "severity": "info"}, "telegram"),
    ({"alertname": "KubeJobFailed", "severity": "warning", "namespace": "labs"}, "null"),
]


def helm_config():
    proc = subprocess.run(
        ["helm", "template", "test", str(CHART), "-f", str(CHART / "values.yaml")],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"helm template failed: {proc.stderr}")
    for d in yaml.safe_load_all(proc.stdout):
        if d and d.get("kind") == "Application" and d["metadata"]["name"] == "monitoring":
            for src in d["spec"]["sources"]:
                if "values" in src.get("helm", {}):
                    return yaml.safe_load(src["helm"]["values"])["alertmanager"]["config"]
    raise SystemExit("monitoring Application not found in render")


def critical_rules():
    out = []
    for f in sorted(RULES.glob("*.yaml")):
        for d in yaml.safe_load_all(f.read_text()):
            if not d or d.get("kind") != "VMRule":
                continue
            for g in d["spec"].get("groups", []):
                for r in g.get("rules", []):
                    labels = r.get("labels") or {}
                    if "alert" in r and labels.get("severity") == "critical":
                        out.append({"alertname": r["alert"], **labels})
    return out


def amtool_path(tmp):
    found = shutil.which("amtool")
    if found:
        return found
    name = f"alertmanager-{AM_VERSION}.linux-amd64"
    url = f"https://github.com/prometheus/alertmanager/releases/download/v{AM_VERSION}/{name}.tar.gz"
    tgz = pathlib.Path(tmp) / "am.tar.gz"
    urllib.request.urlretrieve(url, tgz)
    if hashlib.sha256(tgz.read_bytes()).hexdigest() != AM_SHA256:
        raise SystemExit("alertmanager tarball sha256 mismatch")
    with tarfile.open(tgz) as t:
        member = t.getmember(f"{name}/amtool")
        member.name = "amtool"
        t.extract(member, tmp)
    p = pathlib.Path(tmp) / "amtool"
    p.chmod(0o755)
    return str(p)


def run_checks(config, tmp, amtool):
    failures = []
    cfg = copy.deepcopy(config)
    secret = pathlib.Path(tmp) / "secret"
    secret.write_text("placeholder")
    for r in cfg["receivers"]:
        for t in r.get("telegram_configs", []):
            t["bot_token_file"] = str(secret)
        for w in r.get("webhook_configs", []):
            w["http_config"]["authorization"]["credentials_file"] = str(secret)
    cfg_file = pathlib.Path(tmp) / "alertmanager.yml"
    cfg_file.write_text(yaml.safe_dump(cfg))

    proc = subprocess.run([amtool, "check-config", str(cfg_file)], capture_output=True, text=True)
    if proc.returncode != 0:
        failures.append(f"amtool check-config failed: {proc.stdout}{proc.stderr}")
        return failures

    def receivers(labels):
        args = [amtool, "config", "routes", "test", f"--config.file={cfg_file}"]
        args += [f"{k}={v}" for k, v in labels.items()]
        p = subprocess.run(args, capture_output=True, text=True)
        if p.returncode != 0:
            return f"ERROR {p.stderr.strip()}"
        return p.stdout.strip()

    for labels, want in CASES:
        got = receivers(labels)
        if got != want:
            failures.append(f"{labels}: want {want!r}, got {got!r}")
    for labels in critical_rules():
        got = receivers(labels)
        parts = got.split(",")
        if parts.count("telegram") != 1:
            failures.append(f"critical {labels['alertname']}: telegram count != 1 ({got!r})")
    return failures


def main():
    selftest = "--selftest" in sys.argv
    config = helm_config()
    with tempfile.TemporaryDirectory() as tmp:
        amtool = amtool_path(tmp)
        if selftest:
            broken = copy.deepcopy(config)
            before = len(broken["route"]["routes"])
            broken["route"]["routes"] = [
                r for r in broken["route"]["routes"]
                if 'severity = "critical"' not in r.get("matchers", [])]
            if len(broken["route"]["routes"]) == before:
                raise SystemExit("selftest: severity route not found in config")
            if not run_checks(broken, tmp, amtool):
                raise SystemExit("selftest FAILED: test passed without the severity route")
            print("selftest ok: test fails without the severity route")
            return
        failures = run_checks(config, tmp, amtool)
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print(f"ok: {len(CASES)} cases + {len(critical_rules())} critical vm-rules alerts")


main()
