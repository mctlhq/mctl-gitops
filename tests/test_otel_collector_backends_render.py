"""issue-903: default-render golden file, fan-out render, eval-manifest render.

Three checks against the `bootstrap` chart, each rendering
`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
(and, for T5, its two sibling `eval-*.yaml` templates) through `helm
template` and parsing the result -- no pytest, matching the plain
`python3 tests/<file>.py` convention of `tests/test_base_service_otel_env.py`.

T1. Default values (`otelCollector.backends: []`,
    `otelCollector.eval.enabled: false`) must render the collector's
    OpenTelemetry Collector config byte-for-byte identical to the committed
    golden file `tests/fixtures/otel-collector-config-default.yaml` -- the
    mechanism that makes "this merge changes nothing" a check rather than a
    claim (design.md "Proposed solution" #1). `exporters` must carry exactly
    `debug`, and the traces pipeline's exporter list must be `["debug"]`.

T2. With two `otelCollector.backends` entries (from
    `tests/fixtures/otel-eval-candidates.example-values.yaml`): both render
    as `otlp/<name>` exporters with their own `sending_queue` and
    `retry_on_failure`, `debug` stays present, an entry's `headers` renders
    as an `${env:...}` expansion expression rather than a literal, and
    `numConsumers`/`queueSize` fall back to their defaults when the entry
    omits them. Then the legacy-scalar regression: `backendEndpoint` alone
    still renders `otlp/backend` unchanged, and both keys set render both,
    so the one-key-swap procedure in `docs/runbooks/otel-collector.md` stays
    literally true.

T5. Eval-manifest render. With `otelCollector.eval.enabled: false` (the
    default) no `observability-eval` Namespace and no Application in that
    namespace renders at all. With the example overlay: the Namespace
    carries both `mctl.ai/purpose` and `mctl.ai/teardown-after`; a
    `podSelector: {}` NetworkPolicy exists and its namespace is
    `observability-eval`, never `monitoring`; each candidate Application has
    `automated.prune: true` and no `selfHeal` key; the entry without
    `manifestsPath` renders exactly one source; every Application's
    `targetRevision` is a concrete string.

On failure, T1 prints the exact command that regenerates the golden file --
any legitimate future edit to the collector config must regenerate it.

Run: python3 tests/test_otel_collector_backends_render.py
"""
import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
DEFAULT_VALUES = CHART / "values.yaml"
EXAMPLE_OVERLAY = ROOT / "tests" / "fixtures" / "otel-eval-candidates.example-values.yaml"
GOLDEN = ROOT / "tests" / "fixtures" / "otel-collector-config-default.yaml"

REGEN_COMMAND = (
    "python3 tests/test_otel_collector_backends_render.py --write-golden"
)

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def helm_template(*value_files):
    cmd = ["helm", "template", "test", str(CHART)]
    for vf in value_files:
        cmd += ["-f", str(vf)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"helm template failed: {proc.stderr}")
    return list(yaml.safe_load_all(proc.stdout))


def find(docs, kind, name=None, namespace=None):
    out = []
    for d in docs:
        if not d or d.get("kind") != kind:
            continue
        meta = d.get("metadata", {})
        if name is not None and meta.get("name") != name:
            continue
        if namespace is not None and meta.get("namespace") != namespace:
            continue
        out.append(d)
    return out


def collector_config(docs):
    apps = find(docs, "Application", name="otel-collector")
    assert len(apps) == 1, f"expected exactly one otel-collector Application, got {len(apps)}"
    src = apps[0]["spec"]["sources"][0]
    return yaml.safe_load(src["helm"]["values"])["config"]


# --- T1: default render is the golden file ---------------------------------

default_docs = helm_template(DEFAULT_VALUES)
default_cfg = collector_config(default_docs)
default_rendered = yaml.safe_dump(default_cfg, sort_keys=False, default_flow_style=False, width=100)

if "--write-golden" in sys.argv:
    header = GOLDEN.read_text().split("receivers:")[0] if GOLDEN.exists() else ""
    GOLDEN.write_text(header + default_rendered)
    print(f"wrote {GOLDEN}")
    sys.exit(0)

golden_body = GOLDEN.read_text()
# Strip the leading `#`-comment header before comparing -- only the config
# itself is the golden contract; the regeneration instructions above it are
# free to be edited without failing this check.
golden_cfg_text = "\n".join(
    line for line in golden_body.splitlines() if not line.startswith("#")
).lstrip("\n") + "\n"

check(
    golden_cfg_text == default_rendered,
    f"default render no longer matches {GOLDEN} -- regenerate with: {REGEN_COMMAND}",
)
check(
    list(default_cfg["exporters"].keys()) == ["debug"],
    f"default exporters should be exactly ['debug'], got {list(default_cfg['exporters'].keys())}",
)
check(
    default_cfg["service"]["pipelines"]["traces"]["exporters"] == ["debug"],
    "default traces pipeline exporters should be exactly ['debug'], got "
    f"{default_cfg['service']['pipelines']['traces']['exporters']}",
)

# --- T2: fan-out render ------------------------------------------------------

fanout_docs = helm_template(DEFAULT_VALUES, EXAMPLE_OVERLAY)
fanout_cfg = collector_config(fanout_docs)
exporters = fanout_cfg["exporters"]
pipeline_exporters = fanout_cfg["service"]["pipelines"]["traces"]["exporters"]

otlp_keys = sorted(k for k in exporters if k.startswith("otlp/") and k != "otlp/backend")
check(len(otlp_keys) == 2, f"expected exactly two otlp/<name> exporters, got {otlp_keys}")
check("debug" in exporters, "debug exporter missing from fan-out render")
for key in otlp_keys:
    check(key in pipeline_exporters, f"{key} not listed in traces pipeline exporters")
    check("sending_queue" in exporters[key], f"{key} missing its own sending_queue")
    check("retry_on_failure" in exporters[key], f"{key} missing its own retry_on_failure")

candidate_b = exporters.get("otlp/candidate-b", {})
headers = candidate_b.get("headers", {})
check(
    headers.get("authorization", "").startswith("${env:"),
    f"candidate-b headers should be an ${{env:...}} expansion, got {headers.get('authorization')!r}",
)
check(
    candidate_b.get("sending_queue", {}).get("num_consumers") == 8,
    "candidate-b numConsumers override did not render",
)
check(
    candidate_b.get("sending_queue", {}).get("queue_size") == 10000,
    "candidate-b queueSize override did not render",
)
candidate_a = exporters.get("otlp/candidate-a", {})
check(
    candidate_a.get("sending_queue", {}).get("num_consumers") == 4,
    "candidate-a should fall back to the default numConsumers (4)",
)
check(
    candidate_a.get("sending_queue", {}).get("queue_size") == 5000,
    "candidate-a should fall back to the default queueSize (5000)",
)

# Legacy-scalar regression: backendEndpoint alone, and both set together.
import tempfile

with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
    yaml.safe_dump({"otelCollector": {"backendEndpoint": "otlp.example.com:4317"}}, fh)
    legacy_only = pathlib.Path(fh.name)
legacy_docs = helm_template(DEFAULT_VALUES, legacy_only)
legacy_cfg = collector_config(legacy_docs)
check(
    "otlp/backend" in legacy_cfg["exporters"] and list(legacy_cfg["exporters"].keys()) == ["debug", "otlp/backend"],
    f"backendEndpoint alone should render exactly [debug, otlp/backend], got {list(legacy_cfg['exporters'].keys())}",
)

with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
    yaml.safe_dump({
        "otelCollector": {
            "backendEndpoint": "otlp.example.com:4317",
            "backends": [{"name": "candidate-a", "endpoint": "candidate-a:4317"}],
        }
    }, fh)
    both_set = pathlib.Path(fh.name)
both_docs = helm_template(DEFAULT_VALUES, both_set)
both_cfg = collector_config(both_docs)
check(
    set(both_cfg["exporters"].keys()) == {"debug", "otlp/backend", "otlp/candidate-a"},
    f"both keys set should render both exporters, got {sorted(both_cfg['exporters'].keys())}",
)

# --- T5: eval-manifest render ------------------------------------------------

default_ns = find(default_docs, "Namespace", name="observability-eval")
default_apps = [
    a for a in find(default_docs, "Application")
    if a.get("spec", {}).get("destination", {}).get("namespace") == "observability-eval"
]
check(not default_ns, "default render must not emit the observability-eval Namespace")
check(not default_apps, "default render must not emit any Application into observability-eval")

eval_ns = find(fanout_docs, "Namespace", name="observability-eval")
check(len(eval_ns) == 1, f"expected exactly one observability-eval Namespace, got {len(eval_ns)}")
if eval_ns:
    ns = eval_ns[0]
    check(
        ns.get("metadata", {}).get("labels", {}).get("mctl.ai/purpose") == "issue-903-spike",
        "observability-eval Namespace missing mctl.ai/purpose label",
    )
    check(
        "mctl.ai/teardown-after" in ns.get("metadata", {}).get("annotations", {}),
        "observability-eval Namespace missing mctl.ai/teardown-after annotation",
    )

deny_all_policies = find(fanout_docs, "NetworkPolicy", name="default-deny-all")
eval_deny_all = [
    p for p in deny_all_policies
    if p.get("spec", {}).get("podSelector") == {} and p["metadata"]["namespace"] == "observability-eval"
]
check(len(eval_deny_all) == 1, "expected one podSelector:{} default-deny-all policy in observability-eval")
monitoring_deny_all = [
    p for p in deny_all_policies
    if p.get("spec", {}).get("podSelector") == {} and p["metadata"]["namespace"] == "monitoring"
]
check(not monitoring_deny_all, "a podSelector:{} policy must never be rendered into monitoring")

eval_apps = [
    a for a in find(fanout_docs, "Application")
    if a.get("spec", {}).get("destination", {}).get("namespace") == "observability-eval"
]
check(len(eval_apps) == 2, f"expected two candidate Applications, got {len(eval_apps)}")
for app in eval_apps:
    sync = app["spec"]["syncPolicy"]["automated"]
    check(sync.get("prune") is True, f"{app['metadata']['name']} must set automated.prune: true")
    check("selfHeal" not in sync, f"{app['metadata']['name']} must not set selfHeal")
    if "sources" in app["spec"]:
        check(len(app["spec"]["sources"]) == 2, f"{app['metadata']['name']} with manifestsPath should have two sources")
    else:
        check("source" in app["spec"], f"{app['metadata']['name']} without manifestsPath should render a single source")
    rev = (app["spec"].get("source") or app["spec"]["sources"][0]).get("targetRevision")
    check(isinstance(rev, str) and rev, f"{app['metadata']['name']} targetRevision must be a concrete string, got {rev!r}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("otel-collector backends/eval render: default matches golden, fan-out and eval manifests correct")
