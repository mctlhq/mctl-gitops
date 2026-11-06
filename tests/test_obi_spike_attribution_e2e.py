#!/usr/bin/env python3
"""issue-2286 T3: tenant attribution in the OBI spike collector, run in the
real otelcol-contrib binary (Docker, the tag the chart pins; OTELCOL_BIN may
name a local otelcol-contrib 0.160.0 instead).

The spike collector config is rendered from the enabled overlay. Only
`k8sattributes/obi` is swapped for a test-only `transform/fixture-metadata`
that sets mctl.tenant.resolved and the namespace by k8s.pod.uid lookup (there
is no API server here). A static assertion separately pins the real
k8sattributes/obi block (single pod_association source k8s.pod.uid, namespace
label mctl.me/tenant -> mctl.tenant.resolved) and that no OTTL statement reads
mctl.team; `resource`, `redaction` and `filter/health` must equal production's.

Fixture spans:
  tenant A UID                        -> mctl.tenant=labs
  tenant B UID                        -> mctl.tenant=mctl
  mctl-api UID                        -> unattributed
  forged UID in labs, mctl.tenant=mctl in its resource -> labs
  unlabelled forged UID               -> unattributed, no mctl.tenant
  unknown UID                         -> unattributed

--mutation {ip-association,read-team,keep-incoming} puts one defect back and
the test must then fail.
Run: python3 tests/test_obi_spike_attribution_e2e.py
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
VALUES = CHART / "values.yaml"
OVERLAY = ROOT / "tests" / "fixtures" / "obi-spike.example-values.yaml"
MUTATIONS = {"ip-association", "read-team", "keep-incoming"}

# uid -> (namespace, resolved tenant from the namespace label or None, forged resource tenant)
FIXTURES = {
    "uid-tenant-a": ("labs", "labs", None),
    "uid-tenant-b": ("mctl", "mctl", None),
    "uid-mctl-api": ("mctl-api", None, None),
    "uid-forged": ("labs", "labs", "mctl"),
    "uid-unlabelled": ("observability-obi-spike", None, "mctl"),
    "uid-unknown": (None, None, None),
}
EXPECT = {
    "uid-tenant-a": "labs",
    "uid-tenant-b": "mctl",
    "uid-mctl-api": None,
    "uid-forged": "labs",
    "uid-unlabelled": None,
    "uid-unknown": None,
}


def helm(*extra):
    return subprocess.run(["helm", "template", "t", str(CHART), "-f", str(VALUES), *extra],
                          capture_output=True, text=True, check=True).stdout


def render():
    teardown = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    out = helm("-f", str(OVERLAY), "--set", f"obiSpike.teardownAfter={teardown}")
    cfg = tag = None
    for d in yaml.safe_load_all(out):
        if d and d["kind"] == "ConfigMap" and d["metadata"]["name"] == "obi-spike-collector-config":
            cfg = yaml.safe_load(d["data"]["config.yaml"])
        if d and d["kind"] == "Deployment" and d["metadata"]["name"] == "obi-spike-collector":
            tag = d["spec"]["template"]["spec"]["containers"][0]["image"]
    prod = None
    for d in yaml.safe_load_all(helm()):
        if d and d.get("kind") == "Application" and d["metadata"]["name"] == "otel-collector":
            prod = yaml.safe_load(d["spec"]["sources"][0]["helm"]["values"])["config"]["processors"]
    assert cfg and tag and prod, "spike collector or production collector not found in render"
    return cfg, tag, prod


def apply_mutation(cfg, mutation):
    procs = cfg["processors"]
    if mutation == "ip-association":
        procs["k8sattributes/obi"]["pod_association"].append({"sources": [{"from": "connection"}]})
    elif mutation == "read-team":
        procs["transform/attribution"]["trace_statements"][0]["statements"].insert(
            0, 'set(attributes["mctl.tenant"], attributes["mctl.team"]) where attributes["mctl.team"] != nil')
    elif mutation == "keep-incoming":
        procs["transform/pre"]["trace_statements"][0]["statements"] = []


def static_checks(cfg, prod):
    f = []
    k = cfg["processors"]["k8sattributes/obi"]
    if k.get("pod_association") != [{"sources": [{"from": "resource_attribute", "name": "k8s.pod.uid"}]}]:
        f.append(f"pod_association is not k8s.pod.uid only: {k.get('pod_association')}")
    tenant = [l for l in k["extract"]["labels"] if l["tag_name"] == "mctl.tenant.resolved"]
    if tenant != [{"tag_name": "mctl.tenant.resolved", "key": "mctl.me/tenant", "from": "namespace"}]:
        f.append(f"namespace label extraction not pinned: {tenant}")
    stmts = []
    for key in ("transform/pre", "transform/attribution"):
        for kind in ("trace_statements", "metric_statements"):
            for ctx in cfg["processors"][key].get(kind, []):
                stmts += ctx["statements"]
    if any('attributes["mctl.team"]' in s for s in stmts):
        f.append("an OTTL statement reads mctl.team")
    for name in ("resource", "redaction", "filter/health"):
        if cfg["processors"].get(name) != prod.get(name):
            f.append(f"processor {name} differs from the production collector")
    return f


def attr(k, v):
    return {"key": k, "value": {"stringValue": v}}


def payload():
    now = time.time_ns()
    rs = []
    for i, (uid, (_, _, forged)) in enumerate(FIXTURES.items()):
        attrs = [attr("service.name", f"fixture-{uid}"), attr("k8s.pod.uid", uid)]
        if forged:
            attrs.append(attr("mctl.tenant", forged))
        rs.append({"resource": {"attributes": attrs}, "scopeSpans": [{"spans": [{
            "traceId": f"{i + 1:032x}", "spanId": f"{i + 1:016x}", "name": "GET /", "kind": 2,
            "startTimeUnixNano": str(now - 1_000_000), "endTimeUnixNano": str(now),
        }]}]})
    return {"resourceSpans": rs}


def test_config(cfg):
    procs = cfg["processors"]
    statements = []
    for uid, (ns, resolved, _) in FIXTURES.items():
        if ns:
            statements.append(f'set(attributes["k8s.namespace.name"], "{ns}") where attributes["k8s.pod.uid"] == "{uid}"')
        if resolved:
            statements.append(f'set(attributes["mctl.tenant.resolved"], "{resolved}") where attributes["k8s.pod.uid"] == "{uid}"')
    procs["transform/fixture-metadata"] = {
        "error_mode": "propagate",
        "trace_statements": [{"context": "resource", "statements": statements}],
    }
    pipe = [("transform/fixture-metadata" if p == "k8sattributes/obi" else p)
            for p in cfg["service"]["pipelines"]["traces"]["processors"]]
    del procs["k8sattributes/obi"]
    return {
        "receivers": {"otlp": {"protocols": {"http": {"endpoint": "0.0.0.0:4318"}}}},
        "processors": {k: v for k, v in procs.items() if k in pipe},
        "exporters": {"file": {"path": "/out/spans.json"}},
        "service": {"pipelines": {"traces": {"receivers": ["otlp"], "processors": pipe, "exporters": ["file"]}}},
    }


def run_collector(config, image):
    work = pathlib.Path(tempfile.mkdtemp(prefix="obi-attribution-e2e-"))
    out = work / "out"
    out.mkdir()
    out.chmod(0o777)
    (work / "config.yaml").write_text(yaml.safe_dump(config))
    body = json.dumps(payload()).encode()
    local = os.environ.get("OTELCOL_BIN")
    if local:
        config["exporters"]["file"]["path"] = str(out / "spans.json")
        config["receivers"]["otlp"]["protocols"]["http"]["endpoint"] = "127.0.0.1:43180"
        (work / "config.yaml").write_text(yaml.safe_dump(config))
        proc = subprocess.Popen([local, f"--config={work / 'config.yaml'}"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        url = "http://127.0.0.1:43180/v1/traces"
        stop = proc.terminate
        logs = lambda: ""
    else:
        cid = subprocess.run(
            ["docker", "run", "-d", "--rm", "-p", "127.0.0.1::4318",
             "-v", f"{work / 'config.yaml'}:/etc/otelcol/config.yaml:ro", "-v", f"{out}:/out",
             image, "--config=/etc/otelcol/config.yaml"],
            capture_output=True, text=True, check=True).stdout.strip()
        port = subprocess.run(["docker", "port", cid, "4318/tcp"], capture_output=True, text=True,
                              check=True).stdout.strip().splitlines()[0].rsplit(":", 1)[1]
        url = f"http://127.0.0.1:{port}/v1/traces"
        stop = lambda: subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
        logs = lambda: subprocess.run(["docker", "logs", cid], capture_output=True, text=True).stderr[-3000:]
    try:
        deadline = time.time() + 60
        while True:
            try:
                urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}), timeout=5)
                break
            except (urllib.error.URLError, ConnectionError):
                if time.time() > deadline:
                    raise AssertionError("collector never accepted the spans:\n" + logs())
                time.sleep(1)
        spans = out / "spans.json"
        deadline = time.time() + 30
        while not (spans.exists() and spans.read_text().strip()):
            if time.time() > deadline:
                raise AssertionError("file exporter wrote nothing:\n" + logs())
            time.sleep(1)
        time.sleep(1)
        return [json.loads(l) for l in spans.read_text().strip().splitlines()]
    finally:
        stop()


def check(batches):
    f = []
    seen = {}
    for b in batches:
        for rs in b["resourceSpans"]:
            res = {a["key"]: a["value"].get("stringValue") for a in rs["resource"]["attributes"]}
            seen[res.get("k8s.pod.uid")] = res
    for uid, want in EXPECT.items():
        res = seen.get(uid)
        if res is None:
            f.append(f"{uid}: no span exported")
            continue
        got = res.get("mctl.tenant")
        if got != want:
            f.append(f"{uid}: mctl.tenant={got!r}, expected {want!r}")
        mode = res.get("mctl.tenant.attribution")
        want_mode = "unattributed" if want is None else "namespace-label"
        if mode != want_mode:
            f.append(f"{uid}: mctl.tenant.attribution={mode!r}, expected {want_mode!r}")
        if "mctl.tenant.resolved" in res:
            f.append(f"{uid}: temporary key mctl.tenant.resolved leaked")
    return f


def main():
    args = sys.argv[1:]
    mutation = args[args.index("--mutation") + 1] if "--mutation" in args else None
    if mutation and mutation not in MUTATIONS:
        sys.exit(f"unknown mutation {mutation!r}")
    cfg, image, prod = render()
    if mutation:
        apply_mutation(cfg, mutation)
    failures = static_checks(cfg, prod)
    failures += check(run_collector(test_config(cfg), image))
    if failures:
        for x in failures:
            print(f"FAIL: {x}", file=sys.stderr)
        sys.exit(1)
    print(f"obi spike attribution e2e: {len(EXPECT)} fixture UIDs attributed as expected")


if __name__ == "__main__":
    main()
