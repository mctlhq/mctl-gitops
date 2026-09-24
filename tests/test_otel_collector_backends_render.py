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

# --- Quota and limits (issue #1355) -----------------------------------------

default_quota = find(default_docs, "ResourceQuota", name="observability-eval-quota")
default_limitrange = find(default_docs, "LimitRange", name="observability-eval-limits")
check(not default_quota, "default render must not emit the observability-eval-quota ResourceQuota")
check(not default_limitrange, "default render must not emit the observability-eval-limits LimitRange")

eval_quota = find(fanout_docs, "ResourceQuota", name="observability-eval-quota", namespace="observability-eval")
check(len(eval_quota) == 1, f"expected exactly one observability-eval-quota ResourceQuota, got {len(eval_quota)}")
if eval_quota:
    hard = eval_quota[0].get("spec", {}).get("hard", {})
    # The two caps the issue mandates, asserted literally: a later values
    # edit that widens either one must fail this check, not just "the quota
    # rendered something".
    check(
        hard.get("persistentvolumeclaims") == "4",
        f"observability-eval-quota must cap persistentvolumeclaims at \"4\", got {hard.get('persistentvolumeclaims')!r}",
    )
    check(
        hard.get("requests.storage") == "40Gi",
        f"observability-eval-quota must cap requests.storage at \"40Gi\", got {hard.get('requests.storage')!r}",
    )

eval_limitrange = find(fanout_docs, "LimitRange", name="observability-eval-limits", namespace="observability-eval")
check(len(eval_limitrange) == 1, f"expected exactly one observability-eval-limits LimitRange, got {len(eval_limitrange)}")
if eval_limitrange:
    limits = eval_limitrange[0].get("spec", {}).get("limits", [])
    container_limits = [l for l in limits if l.get("type") == "Container"]
    check(len(container_limits) == 1, "observability-eval-limits must have exactly one type: Container entry")
    if container_limits:
        entry = container_limits[0]
        for field in ("default", "defaultRequest", "max"):
            check(field in entry, f"observability-eval-limits Container entry missing {field!r}")

# Sanity check that the two literal assertions above are actually pinned to
# the values input, not a hardcoded coincidence: a values overlay that
# widens persistentvolumeclaims/requests.storage must change the render, so
# a PR that widens either mandated cap in bootstrap/values.yaml is exactly
# what this test catches.
with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
    yaml.safe_dump({
        "otelCollector": {
            "eval": {
                "enabled": True,
                "teardownAfter": "2026-10-31",
                "quota": {"persistentvolumeclaims": "10", "requests.storage": "400Gi"},
            }
        }
    }, fh)
    widened_quota = pathlib.Path(fh.name)
widened_docs = helm_template(DEFAULT_VALUES, widened_quota)
widened_quota_obj = find(widened_docs, "ResourceQuota", name="observability-eval-quota")
if widened_quota_obj:
    hard = widened_quota_obj[0].get("spec", {}).get("hard", {})
    check(
        hard.get("persistentvolumeclaims") == "10" and hard.get("requests.storage") == "400Gi",
        "sanity check: a values override of the quota caps should be reflected verbatim in the render "
        "(if this fails, the literal assertions above are not actually pinned to the values input)",
    )

# --- Per-candidate enablement (issue #1355) ---------------------------------

CANDIDATE_TEMPLATE = {
    "repoURL": "https://charts.example.com/cand",
    "chart": "cand",
    "targetRevision": "1.0.0",
}


def _eval_values(eval_enabled, candidates):
    return {"otelCollector": {"eval": {"enabled": eval_enabled, "teardownAfter": "2026-10-31", "candidates": candidates}}}


def _write_values(doc):
    fh = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    yaml.safe_dump(doc, fh)
    fh.close()
    return pathlib.Path(fh.name)


def _eval_apps(docs):
    return [
        a for a in find(docs, "Application")
        if a.get("spec", {}).get("destination", {}).get("namespace") == "observability-eval"
    ]


all_disabled = _write_values(_eval_values(True, [
    {"name": "cand-a", "enabled": False, **CANDIDATE_TEMPLATE},
    {"name": "cand-b", "enabled": False, **CANDIDATE_TEMPLATE},
]))
all_disabled_docs = helm_template(DEFAULT_VALUES, all_disabled)
check(
    len(_eval_apps(all_disabled_docs)) == 0,
    "eval.enabled=true with every candidate disabled must render zero Applications into observability-eval",
)

one_enabled = _write_values(_eval_values(True, [
    {"name": "cand-a", "enabled": True, **CANDIDATE_TEMPLATE},
    {"name": "cand-b", "enabled": False, **CANDIDATE_TEMPLATE},
]))
one_enabled_docs = helm_template(DEFAULT_VALUES, one_enabled)
one_enabled_apps = _eval_apps(one_enabled_docs)
check(
    len(one_enabled_apps) == 1,
    f"exactly one candidate enabled must render exactly one Application, got {len(one_enabled_apps)}",
)
if one_enabled_apps:
    check(
        one_enabled_apps[0]["metadata"]["name"] == "otel-eval-cand-a",
        f"the enabled candidate's Application should be otel-eval-cand-a, got {one_enabled_apps[0]['metadata']['name']}",
    )

candidate_on_eval_off = _write_values(_eval_values(False, [
    {"name": "cand-a", "enabled": True, **CANDIDATE_TEMPLATE},
]))
candidate_on_eval_off_docs = helm_template(DEFAULT_VALUES, candidate_on_eval_off)
check(
    len(_eval_apps(candidate_on_eval_off_docs)) == 0,
    "a candidate flag true while eval.enabled is false must render nothing -- the namespace guard dominates",
)
check(
    not find(candidate_on_eval_off_docs, "Namespace", name="observability-eval"),
    "a candidate flag true while eval.enabled is false must not render the observability-eval Namespace either",
)

# --- Fan-out derived from candidates (issue #1355) ---------------------------

one_enabled_with_endpoint = _write_values(_eval_values(True, [
    {"name": "cand-a", "enabled": True, "otlpEndpoint": "cand-a.observability-eval.svc.cluster.local:4317", "insecure": True, **CANDIDATE_TEMPLATE},
    {"name": "cand-b", "enabled": False, "otlpEndpoint": "cand-b.observability-eval.svc.cluster.local:4317", **CANDIDATE_TEMPLATE},
]))
fanout_one_docs = helm_template(DEFAULT_VALUES, one_enabled_with_endpoint)
fanout_one_cfg = collector_config(fanout_one_docs)
eval_exporter_keys = [k for k in fanout_one_cfg["exporters"] if k.startswith("otlp/eval-")]
check(eval_exporter_keys == ["otlp/eval-cand-a"], f"expected exactly one otlp/eval-<name> exporter, got {eval_exporter_keys}")
check(
    fanout_one_cfg["service"]["pipelines"]["traces"]["exporters"] == ["debug", "otlp/eval-cand-a"],
    f"traces pipeline exporters should be exactly [debug, otlp/eval-cand-a], got {fanout_one_cfg['service']['pipelines']['traces']['exporters']}",
)
check(
    "sending_queue" in fanout_one_cfg["exporters"]["otlp/eval-cand-a"],
    "otlp/eval-cand-a missing its own sending_queue",
)
check(
    "retry_on_failure" in fanout_one_cfg["exporters"]["otlp/eval-cand-a"],
    "otlp/eval-cand-a missing its own retry_on_failure",
)

# Structural diff: with one candidate enabled, receivers and the ordered
# processor list of the traces pipeline must be byte-equal to the default
# render -- the ONLY difference is the appended exporter.
check(
    fanout_one_cfg["service"]["pipelines"]["traces"]["receivers"] == default_cfg["service"]["pipelines"]["traces"]["receivers"],
    "enabling a candidate must not change the traces pipeline's receivers",
)
check(
    fanout_one_cfg["service"]["pipelines"]["traces"]["processors"] == default_cfg["service"]["pipelines"]["traces"]["processors"],
    "enabling a candidate must not change the traces pipeline's ordered processor list",
)

# All eval candidate flags off (but present, with an otlpEndpoint) must
# render no otlp/eval-* exporter at all and leave the pipeline exactly
# ["debug"] -- same invariant T1 proves for an empty candidates list, proved
# again here for a non-empty-but-disabled list.
all_off_with_endpoint = _write_values(_eval_values(True, [
    {"name": "cand-a", "enabled": False, "otlpEndpoint": "cand-a.observability-eval.svc.cluster.local:4317", **CANDIDATE_TEMPLATE},
]))
all_off_docs = helm_template(DEFAULT_VALUES, all_off_with_endpoint)
all_off_cfg = collector_config(all_off_docs)
check(
    not [k for k in all_off_cfg["exporters"] if k.startswith("otlp/eval-")],
    "every candidate disabled must render no otlp/eval-* exporter even with eval.enabled=true",
)
check(
    all_off_cfg["service"]["pipelines"]["traces"]["exporters"] == ["debug"],
    "every candidate disabled must leave the traces pipeline exporters exactly ['debug']",
)


def valid_eval_headers(headers):
    """Every header value must be an ${env:...} expansion, never a literal --
    the same rule test_otel_collector_backends_render.py already enforces
    for otelCollector.backends[].headers (see candidate_b above)."""
    if not headers:
        return True
    return all(str(v).startswith("${env:") for v in headers.values())


# Prove the validator actually distinguishes the two cases before trusting
# it against the real committed candidates below.
assert valid_eval_headers(None) is True
assert valid_eval_headers({"authorization": "${env:CANDIDATE_AUTH_HEADER}"}) is True
assert valid_eval_headers({"authorization": "hardcoded-secret-value"}) is False

# A literal (non-${env:) header value on an eval candidate must fail this
# render test -- rendered here to prove the assertion actually fires, not
# folded into `failures` (which would fail the whole suite).
literal_header_candidate = _write_values(_eval_values(True, [
    {
        "name": "cand-a",
        "enabled": True,
        "otlpEndpoint": "cand-a.observability-eval.svc.cluster.local:4317",
        "headers": {"authorization": "not-an-env-expansion"},
        **CANDIDATE_TEMPLATE,
    },
]))
literal_header_docs = helm_template(DEFAULT_VALUES, literal_header_candidate)
literal_header_cfg = collector_config(literal_header_docs)
literal_headers = literal_header_cfg["exporters"].get("otlp/eval-cand-a", {}).get("headers", {})
check(
    not valid_eval_headers(literal_headers),
    "sanity check: a literal header value fixture should be rejected by valid_eval_headers "
    "(if this fails, the negative-case fixture above stopped exercising the literal-value path)",
)

# Every real, committed eval candidate must satisfy the same rule.
committed_candidates = yaml.safe_load(DEFAULT_VALUES.read_text())["otelCollector"]["eval"]["candidates"]
for candidate in committed_candidates:
    check(
        valid_eval_headers(candidate.get("headers")),
        f"committed candidate {candidate.get('name')!r} has a header value that is not an ${{env:...}} expansion",
    )

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("otel-collector backends/eval render: default matches golden, fan-out and eval manifests correct")
