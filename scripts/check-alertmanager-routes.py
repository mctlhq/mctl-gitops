#!/usr/bin/env python3
"""Check the rendered Alertmanager config and test who each alert pages (#1771).

The Alertmanager routing tree in
platform-gitops/bootstrap/templates/observability/monitoring.yaml decides
whether a human hears about an alert at all. Until #1771 a critical alert that
was not on the telegram allowlist went to mctl-agent only, including the alerts
about the notification path itself. Nothing in CI looked at the tree: it is an
opaque string inside an Argo CD Application's helm values, so kubeconform and
yamllint have nothing to say about what it routes where.

This renders the bootstrap chart, extracts `alertmanager.config` from the
monitoring Application's values, and runs the real Alertmanager code against
it with `amtool`:

  1. `amtool check-config` -- the config loads.
  2. `amtool config routes test` for a fixed set of label sets with the exact
     receivers each must resolve to (CASES below): a critical upstream alert
     pages Telegram and still reaches mctl-agent, a warning agent-handled alert
     reaches mctl-agent only, Watchdog stays on "null", and so on.
  3. Every alerting rule under vm-rules/, with its static labels:
       - no alert resolves to telegram more than once (two routes to the same
         receiver are two notification pipelines, i.e. two messages);
       - every severity=critical alert resolves to telegram, unless it is
         muted outright (resolves to "null" only).

amtool is used from PATH only when it reports the pinned version; otherwise
the pinned Alertmanager release below is downloaded once, its sha256
verified, and cached under $XDG_CACHE_HOME (or ~/.cache), so the self-test
and the real run in one CI job share a single download. The version matches
the VMAlertmanager image the victoria-metrics-k8s-stack chart deploys, so
routing semantics are the cluster's.

Needs helm, pyyaml and (without a cached amtool) network egress to github.com;
validate-manifests.yml has all three by the time check-vm-rules.sh runs.

Scope of check 3: rules are routed with their STATIC labels only. A route
gated on a label that comes from the query result (project, namespace, job)
is visible only through CASES, so label-scoped combinations that matter need
an explicit CASES entry.

Run with --selftest to prove the checks still fail on a broken tree: it removes
the critical route, the dedupe exclusion, the trailing mctl-agent route and an
alerting-path route, and buries the trailing route, asserting each is caught.

Run: python3 scripts/check-alertmanager-routes.py [--selftest] [--config FILE]
  --config FILE  test an already-rendered Alertmanager config instead of
                 rendering the chart (for debugging without helm).
"""

from __future__ import annotations

import copy
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CHART = ROOT / "platform-gitops/bootstrap"
VALUES = CHART / "values.yaml"
TEMPLATE = "templates/observability/monitoring.yaml"
# Honours the same RULES_DIR override as check-vm-rules.sh, which passes it
# through, so the promtool half and this half never check different rule sets.
RULES_DIR = Path(os.environ.get(
    "RULES_DIR",
    ROOT / "platform-gitops/infra-components/observability/vm-rules"))

# victoria-metrics-k8s-stack 0.72.5 deploys VMAlertmanager v0.28.1
# (alertmanager.spec.image.tag in the chart's values.yaml).
AM_VERSION = "0.28.1"
AM_TARBALL = f"alertmanager-{AM_VERSION}.linux-amd64.tar.gz"
AM_SHA256 = "5ac7ab5e4b8ee5ce4d8fb0988f9cb275efcc3f181b4b408179fafee121693311"
AM_URL = (f"https://github.com/prometheus/alertmanager/releases/download/"
          f"v{AM_VERSION}/{AM_TARBALL}")

# (description, labels, exact receivers in route order)
CASES: list[tuple[str, dict[str, str], list[str]]] = [
    # The three cases #1771 asks for.
    ("critical upstream alert pages and still reaches the agent",
     {"alertname": "KubeAPIDown", "severity": "critical"},
     ["telegram", "mctl-agent"]),
    ("warning agent-handled alert stays agent-only",
     {"alertname": "PodCrashLooping", "severity": "warning",
      "namespace": "labs"},
     ["mctl-agent"]),
    ("Watchdog stays muted",
     {"alertname": "Watchdog", "severity": "none"},
     ["null"]),
    # Neighbours of the above that the change must not break.
    ("InfoInhibitor stays muted",
     {"alertname": "InfoInhibitor", "severity": "none"},
     ["null"]),
    ("k3s control-plane false positive stays muted although critical",
     {"alertname": "KubeControllerManagerDown", "severity": "critical"},
     ["null"]),
    ("KubeletDown pages",
     {"alertname": "KubeletDown", "severity": "critical"},
     ["telegram", "mctl-agent"]),
    ("critical alert already on a telegram-only route pages once",
     {"alertname": "VaultBackupStale", "severity": "critical"},
     ["telegram"]),
    ("critical alert already on a continue:true telegram route pages once",
     {"alertname": "MctlApiDown", "severity": "critical"},
     ["telegram", "mctl-agent"]),
    ("critical alert in the agent catch-all pages and keeps its ticket",
     {"alertname": "VaultSealed", "severity": "critical"},
     ["telegram", "mctl-agent"]),
    ("warning platform ArgoCD app pages once",
     {"alertname": "ArgoCDApplicationDegraded", "severity": "warning",
      "project": "platform"},
     ["telegram", "mctl-agent"]),
    ("warning tenant ArgoCD app stays agent-only",
     {"alertname": "ArgoCDApplicationDegraded", "severity": "warning",
      "project": "apps"},
     ["mctl-agent"]),
    # The alerting path pages regardless of severity.
    ("critical Alertmanager alert pages once",
     {"alertname": "AlertmanagerClusterDown", "severity": "critical"},
     ["telegram", "mctl-agent"]),
    ("warning Alertmanager alert pages",
     {"alertname": "AlertmanagerFailedToSendAlerts", "severity": "warning"},
     ["telegram", "mctl-agent"]),
    ("vmalert -> Alertmanager delivery errors page",
     {"alertname": "AlertmanagerErrors", "severity": "warning",
      "alertgroup": "vmalert"},
     ["telegram", "mctl-agent"]),
    ("vmalert rule evaluation errors page",
     {"alertname": "AlertingRulesError", "severity": "warning",
      "alertgroup": "vmalert"},
     ["telegram", "mctl-agent"]),
    ("vmagent's same-named alert is not on the alerting path",
     {"alertname": "ConfigurationReloadFailure", "severity": "warning",
      "alertgroup": "vmagent"},
     ["mctl-agent"]),
    ("vmalert recording-rule noise stays agent-only",
     {"alertname": "RecordingRulesNoData", "severity": "info",
      "alertgroup": "vmalert", "namespace": "monitoring"},
     ["mctl-agent"]),
    ("mctl-agent liveness pages",
     {"alertname": "MctlAgentMetricsAbsent", "severity": "warning"},
     ["telegram", "mctl-agent"]),
    ("ServiceDown for vmalert pages once",
     {"alertname": "ServiceDown", "severity": "critical",
      "job": "vmalert-monitoring-victoria-metrics-k8s-stack"},
     ["telegram", "mctl-agent"]),
    ("downgraded ServiceDown for vmalertmanager still pages",
     {"alertname": "ServiceDown", "severity": "warning",
      "job": "vmalertmanager-monitoring-victoria-metrics-k8s-stack"},
     ["telegram", "mctl-agent"]),
    ("downgraded ServiceDown for vmsingle does not",
     {"alertname": "ServiceDown", "severity": "warning",
      "job": "vmsingle-monitoring-victoria-metrics-k8s-stack"},
     ["mctl-agent"]),
]


def render_config() -> dict:
    """Render the bootstrap chart and return the Alertmanager config dict."""
    out = subprocess.run(
        ["helm", "template", "guard", str(CHART), "-f", str(VALUES),
         "--show-only", TEMPLATE],
        capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"helm template failed:\n{out.stderr.strip()}")
    for doc in yaml.safe_load_all(out.stdout):
        if (isinstance(doc, dict) and doc.get("kind") == "Application"
                and doc["metadata"]["name"] == "monitoring"):
            for src in doc["spec"]["sources"]:
                if src.get("chart") == "victoria-metrics-k8s-stack":
                    values = yaml.safe_load(src["helm"]["values"])
                    return values["alertmanager"]["config"]
    raise RuntimeError(
        f"no victoria-metrics-k8s-stack source in the monitoring Application "
        f"rendered from {TEMPLATE}")


def amtool_version(path: str) -> str | None:
    out = subprocess.run([path, "--version"], capture_output=True, text=True,
                         check=False)
    # "amtool, version 0.28.1 (branch: ..."
    words = (out.stdout + out.stderr).split()
    if "version" in words and words.index("version") + 1 < len(words):
        return words[words.index("version") + 1]
    return None


def find_amtool() -> str:
    found = shutil.which("amtool")
    if found and amtool_version(found) == AM_VERSION:
        return found
    if found:
        print(f"amtool on PATH is {amtool_version(found)}, not {AM_VERSION}; "
              f"using the pinned release instead", file=sys.stderr)
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    dest = cache / "mctl-amtool" / AM_VERSION / "amtool"
    if dest.is_file() and amtool_version(str(dest)) == AM_VERSION:
        return str(dest)
    with urllib.request.urlopen(AM_URL, timeout=60) as resp:  # noqa: S310
        blob = resp.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != AM_SHA256:
        raise RuntimeError(f"{AM_TARBALL}: sha256 {digest} != pinned {AM_SHA256}")
    member = f"alertmanager-{AM_VERSION}.linux-amd64/amtool"
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        src = tar.extractfile(member)
        if src is None:
            raise RuntimeError(f"{member} missing from {AM_TARBALL}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(src.read())
    tmp.chmod(0o755)
    tmp.replace(dest)
    return str(dest)


def rule_label_sets() -> list[tuple[str, dict[str, str]]]:
    """(file, labels) for every alerting rule under vm-rules/."""
    sets = []
    for path in sorted(RULES_DIR.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not isinstance(doc, dict) or doc.get("kind") != "VMRule":
                continue
            for group in doc.get("spec", {}).get("groups") or []:
                for rule in group.get("rules") or []:
                    if "alert" not in rule:
                        continue
                    labels = {k: str(v) for k, v in
                              (rule.get("labels") or {}).items()}
                    labels["alertname"] = rule["alert"]
                    sets.append((path.name, labels))
    return sets


class Router:
    def __init__(self, amtool: str, config: dict, workdir: Path):
        self.amtool = amtool
        fd, name = tempfile.mkstemp(suffix=".yml", dir=workdir)
        with os.fdopen(fd, "w") as fh:
            yaml.safe_dump(config, fh, sort_keys=False)
        self.path = name

    def check_config(self) -> str | None:
        out = subprocess.run([self.amtool, "check-config", self.path],
                             capture_output=True, text=True, check=False)
        if out.returncode != 0:
            return (out.stdout + out.stderr).strip()
        return None

    def receivers(self, labels: dict[str, str]) -> list[str]:
        args = [f"{k}={v}" for k, v in sorted(labels.items())]
        out = subprocess.run(
            [self.amtool, "config", "routes", "test",
             f"--config.file={self.path}", "--", *args],
            capture_output=True, text=True, check=False)
        if out.returncode != 0:
            raise RuntimeError(
                f"amtool routes test {args} failed: {out.stderr.strip()}")
        return out.stdout.strip().split(",")


def problems(amtool: str, config: dict, workdir: Path,
             verbose: bool = False) -> list[str]:
    router = Router(amtool, config, workdir)
    err = router.check_config()
    if err:
        return [f"amtool check-config failed:\n{err}"]
    found = []

    # The matcher-less mctl-agent route stands in for the root default
    # receiver; anything appended after it is unreachable.
    tail = (config.get("route", {}).get("routes") or [None])[-1]
    if tail != {"receiver": "mctl-agent"}:
        found.append(f"the last child route must be the matcher-less "
                     f"mctl-agent route (it replaces the root default once a "
                     f"continue: true route has matched); found {tail}")

    for desc, labels, want in CASES:
        got = router.receivers(labels)
        if verbose:
            print(f"  {','.join(got):<28} {labels}")
        if got != want:
            found.append(f"{desc}: {labels} -> {','.join(got)}, "
                         f"want {','.join(want)}")

    checked = 0
    for fname, labels in rule_label_sets():
        checked += 1
        got = router.receivers(labels)
        pages = got.count("telegram")
        name = f"{fname}:{labels['alertname']} (severity={labels.get('severity')})"
        if pages > 1:
            found.append(f"{name} pages Telegram {pages} times: {','.join(got)}")
        if (labels.get("severity") == "critical" and pages == 0
                and got != ["null"]):
            found.append(f"{name} is critical but does not page Telegram: "
                         f"{','.join(got)}")
    if checked == 0:
        found.append(f"no alerting rules found under {RULES_DIR}")
    elif verbose:
        print(f"  {checked} vm-rules alerts: none pages twice, every critical pages")
    return found


def routes(config: dict) -> list[dict]:
    return config["route"]["routes"]


def matcher_index(config: dict, needle: str) -> int:
    hits = [i for i, r in enumerate(routes(config))
            if any(needle in m for m in r.get("matchers") or [])]
    if len(hits) != 1:
        raise RuntimeError(f"selftest: {len(hits)} routes carry {needle!r}")
    return hits[0]


def selftest(config: dict, amtool: str, workdir: Path) -> int:
    """Each mutation re-opens a defect #1771 fixed and must be caught."""
    def drop_critical(cfg):
        del routes(cfg)[matcher_index(cfg, 'severity = "critical"')]

    def drop_dedupe(cfg):
        r = routes(cfg)[matcher_index(cfg, 'severity = "critical"')]
        r["matchers"] = [m for m in r["matchers"] if "!~" not in m]

    def drop_agent_tail(cfg):
        routes(cfg).pop()

    def bury_agent_tail(cfg):
        routes(cfg).append({"receiver": "telegram"})

    def drop_meta(cfg):
        del routes(cfg)[matcher_index(cfg, "MctlAgentMetricsAbsent")]

    failed = 0
    base = problems(amtool, config, workdir)
    if base:
        print("self-test FAILED: the unmodified config already fails:",
              *base, sep="\n  ", file=sys.stderr)
        failed = 1
    for name, mutate, expect in [
        ("critical route removed", drop_critical, "KubeAPIDown"),
        ("dedupe exclusion removed", drop_dedupe, "pages Telegram 2 times"),
        ("trailing mctl-agent route removed", drop_agent_tail, "KubeAPIDown"),
        ("route appended after the mctl-agent tail", bury_agent_tail,
         "last child route"),
        ("alerting-path route removed", drop_meta, "MctlAgentMetricsAbsent"),
    ]:
        cfg = copy.deepcopy(config)
        mutate(cfg)
        got = problems(amtool, cfg, workdir)
        if not any(expect in p for p in got):
            print(f"self-test FAILED: {name}: no problem mentioning "
                  f"{expect!r}. Got: {got}", file=sys.stderr)
            failed = 1
    if not failed:
        print("check-alertmanager-routes.py self-test: all 5 mutations caught")
    return failed


def main(argv: list[str]) -> int:
    args = list(argv)
    do_selftest = "--selftest" in args
    if do_selftest:
        args.remove("--selftest")
    config_file = None
    if args[:1] == ["--config"] and len(args) == 2:
        config_file = Path(args[1])
    elif args:
        print(__doc__, file=sys.stderr)
        return 2

    if config_file:
        config = yaml.safe_load(config_file.read_text())
    else:
        config = render_config()

    amtool = find_amtool()
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        if do_selftest:
            return selftest(config, amtool, workdir)
        print(f"== amtool check-config + routes test ({TEMPLATE}) ==")
        found = problems(amtool, config, workdir, verbose=True)
    for p in found:
        print(f"::error file=platform-gitops/bootstrap/{TEMPLATE}::{p}")
    if not found:
        print("alertmanager routing: OK")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
