"""issue-903: default-render golden file, fan-out render, eval-manifest render.

Three checks against the `bootstrap` chart, each rendering
`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
(and, for T5, its two sibling `eval-*.yaml` templates) through `helm
template` and parsing the result -- no pytest, matching the plain
`python3 tests/<file>.py` convention of `tests/test_base_service_otel_env.py`.

T1. The eval-off baseline (committed values plus an overlay setting
    `otelCollector.eval.enabled: false`, with `otelCollector.backends: []`)
    must render the collector's
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
    eval-off baseline) no `observability-eval` Namespace and no Application in that
    namespace renders at all. With the example overlay: the Namespace
    carries both `mctl.ai/purpose` and `mctl.ai/teardown-after`; a
    `podSelector: {}` NetworkPolicy exists and its namespace is
    `observability-eval`, never `monitoring`; each candidate Application has
    `automated.prune: true` and no `selfHeal` key; the entry without
    `manifestsPath` renders exactly one source; every Application's
    `targetRevision` is a concrete string.

Committed default (#1280). bootstrap/values.yaml ships the sandbox OPEN
    with exactly one candidate, tempo. The committed render must differ from
    the eval-off baseline only by the appended `otlp/eval-tempo` exporter
    (receivers and processors unchanged), and must emit the "Tempo (eval)"
    Grafana datasource, whose host matches the candidate's otlpEndpoint host.
    The baseline must emit no datasource.

On failure, T1 prints the exact command that regenerates the golden file --
any legitimate future edit to the collector config must regenerate it.

Run: python3 tests/test_otel_collector_backends_render.py
"""
import pathlib
import subprocess
import sys
import tempfile

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


# --- T1: eval-off baseline render is the golden file -------------------------
#
# bootstrap/values.yaml ships otelCollector.eval.enabled: true while the
# Tempo bake-off (#1280) runs, so the "nothing changes" baseline is rendered
# with an explicit eval-off overlay. The committed default itself is checked
# separately below ("Committed default").

with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
    yaml.safe_dump({"otelCollector": {"eval": {"enabled": False}}}, fh)
    EVAL_OFF = pathlib.Path(fh.name)

default_docs = helm_template(DEFAULT_VALUES, EVAL_OFF)
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
with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
    yaml.safe_dump({"otelCollector": {"backendEndpoint": "otlp.example.com:4317"}}, fh)
    legacy_only = pathlib.Path(fh.name)
legacy_docs = helm_template(DEFAULT_VALUES, EVAL_OFF, legacy_only)
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
both_docs = helm_template(DEFAULT_VALUES, EVAL_OFF, both_set)
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
check(
    not find(default_docs, "ConfigMap", name="tempo-eval-grafana-datasource"),
    "eval-off render must not emit the Tempo (eval) Grafana datasource",
)

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
    # The two storage caps, asserted literally: a later values edit that
    # widens either one must fail this check, not just "the quota rendered
    # something". #1280 pins both to zero -- the Tempo candidate keeps its WAL
    # on an emptyDir and its blocks in object storage, and a PVC here would
    # be a paid cloud volume.
    check(
        hard.get("persistentvolumeclaims") == "0",
        f"observability-eval-quota must cap persistentvolumeclaims at \"0\", got {hard.get('persistentvolumeclaims')!r}",
    )
    check(
        hard.get("requests.storage") == "0",
        f"observability-eval-quota must cap requests.storage at \"0\", got {hard.get('requests.storage')!r}",
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

# --- Committed tempo candidate actually renders (#1355, #1280) ---------------
# Every check above only exercises fabricated candidates (cand-a, cand-b,
# CANDIDATE_TEMPLATE). The one candidate this repo actually ships -- tempo,
# committed in bootstrap/values.yaml -- must be rendered through `helm
# template` for real, and its pins asserted literally: the community
# monolithic chart, 1 replica, 14-day retention, WAL on a size-capped
# emptyDir, object-storage settings that are ${...} placeholders filled from
# the tempo-r2 Secret at runtime (never a literal endpoint or bucket), and
# no chart-rendered ServiceMonitor (the VMServiceScrape in its manifestsPath
# is the one scrape).

tempo_candidate = next(c for c in committed_candidates if c.get("name") == "tempo")
tempo_enabled = dict(tempo_candidate, enabled=True)

tempo_values = _write_values(_eval_values(True, [tempo_enabled]))
tempo_docs = helm_template(DEFAULT_VALUES, tempo_values)
tempo_apps = _eval_apps(tempo_docs)
check(len(tempo_apps) == 1, f"expected exactly one tempo Application, got {len(tempo_apps)}")
if tempo_apps:
    tempo_app = tempo_apps[0]
    check(
        tempo_app["metadata"]["name"] == "otel-eval-tempo",
        f"the tempo candidate's Application should be otel-eval-tempo, got {tempo_app['metadata']['name']}",
    )
    sources = tempo_app["spec"].get("sources") or []
    check(
        len(sources) == 2 and "source" not in tempo_app["spec"],
        "otel-eval-tempo has a manifestsPath, so it should render exactly two sources, "
        f"got {sorted(tempo_app['spec'])!r} with {len(sources)} sources",
    )
    source = sources[0] if sources else {}
    check(
        source.get("repoURL") == "https://grafana-community.github.io/helm-charts",
        f"tempo chart repoURL should be the grafana-community repo, got {source.get('repoURL')!r}",
    )
    check(source.get("chart") == "tempo", f"tempo chart should be 'tempo' (monolithic), got {source.get('chart')!r}")
    check(source.get("targetRevision") == "2.4.0", f"tempo chart should be pinned to 2.4.0, got {source.get('targetRevision')!r}")
    if len(sources) == 2:
        check(
            sources[1].get("path") == tempo_candidate.get("manifestsPath"),
            f"tempo's second source should be its manifestsPath, got {sources[1].get('path')!r}",
        )
    vo = source.get("helm", {}).get("valuesObject", {})
    t = vo.get("tempo", {})
    check(vo.get("replicas") == 1, f"tempo replicas should be 1, got {vo.get('replicas')!r}")
    check(t.get("retention") == "336h", f"tempo retention should be 336h (14 days), got {t.get('retention')!r}")
    check(t.get("memBallastSizeMbs") == 0, f"tempo memBallastSizeMbs should be 0 (GOMEMLIMIT governs), got {t.get('memBallastSizeMbs')!r}")
    check(t.get("reportingEnabled") is False, "tempo usage reporting should be disabled")
    env = {e.get("name"): e.get("value") for e in t.get("extraEnv", [])}
    check(env.get("GOMEMLIMIT") == "800MiB", f"tempo GOMEMLIMIT should be 800MiB, got {env.get('GOMEMLIMIT')!r}")
    check(
        t.get("resources", {}).get("limits", {}).get("memory") == "1Gi",
        f"tempo memory limit should be 1Gi, got {t.get('resources', {}).get('limits', {}).get('memory')!r}",
    )
    check(
        t.get("extraArgs", {}).get("config.expand-env") == "true",
        "tempo must run with -config.expand-env=true, or the ${...} storage placeholders are used verbatim",
    )
    check(
        [e.get("secretRef", {}).get("name") for e in t.get("extraEnvFrom", [])] == ["tempo-r2"],
        "tempo must take its object-storage settings from the tempo-r2 Secret via envFrom",
    )
    check(vo.get("persistence", {}).get("enabled") is False, "tempo persistence must be disabled (quota allows no PVC)")
    wal_vols = [v for v in vo.get("extraVolumes", []) if "emptyDir" in v]
    check(
        len(wal_vols) == 1 and wal_vols[0]["emptyDir"].get("sizeLimit") == "2Gi",
        f"tempo WAL should be one emptyDir with sizeLimit 2Gi, got {wal_vols!r}",
    )
    check(vo.get("serviceMonitor", {}).get("enabled") is False, "the chart's ServiceMonitor must stay disabled")
    s3 = t.get("storage", {}).get("trace", {}).get("s3", {})
    check(t.get("storage", {}).get("trace", {}).get("backend") == "s3", "tempo trace backend should be s3")
    for key, var in (
        ("bucket", "TEMPO_S3_BUCKET"),
        ("endpoint", "TEMPO_S3_ENDPOINT"),
        ("access_key", "TEMPO_S3_ACCESS_KEY"),
        ("secret_key", "TEMPO_S3_SECRET_KEY"),
    ):
        check(
            s3.get(key) == "${" + var + "}",
            f"tempo storage.trace.s3.{key} must be the ${{{var}}} placeholder, never a literal, got {s3.get(key)!r}",
        )
    check(s3.get("insecure") in (None, False), "tempo must reach object storage over TLS (s3.insecure unset/false)")

# A manifestsPath directory becomes a second ArgoCD source synced as raw
# Kubernetes manifests (no Chart.yaml), so every YAML document in it must be a
# resource. ArgoCD's repo-server skips a non-resource file there in silence
# (configuration that looks in force but is not), and hard-fails manifest
# generation if the file's bytes contain apiVersion:, kind: and metadata:
# anywhere, comments included. Either way it only surfaces once the candidate
# is enabled -- exactly the case no default render can catch.
for cand in committed_candidates:
    mpath = cand.get("manifestsPath")
    if not mpath:
        continue
    mdir = ROOT / mpath
    check(mdir.is_dir(), f"candidate {cand.get('name')!r} manifestsPath {mpath} does not exist")
    for f in sorted(mdir.rglob("*.y*ml")) if mdir.is_dir() else []:
        for doc in yaml.safe_load_all(f.read_text()):
            if doc is None:
                continue
            check(
                isinstance(doc, dict) and "apiVersion" in doc and "kind" in doc,
                f"{f.relative_to(ROOT)} is under candidate {cand.get('name')!r}'s manifestsPath "
                "but is not a Kubernetes resource (no apiVersion/kind); ArgoCD would fail to sync it",
            )

tempo_fanout_cfg = collector_config(tempo_docs)
tempo_pipeline_exporters = tempo_fanout_cfg["service"]["pipelines"]["traces"]["exporters"]
check(
    "otlp/eval-tempo" in tempo_pipeline_exporters,
    f"otlp/eval-tempo missing from traces pipeline exporters, got {tempo_pipeline_exporters}",
)

# --- Committed default (#1280) -----------------------------------------------
# What bootstrap/values.yaml actually ships: the sandbox open with tempo as
# the only candidate. Relative to the eval-off baseline the collector gains
# exactly one exporter and nothing else; the Grafana datasource renders and
# points at the same Service the collector exports to.

committed_docs = helm_template(DEFAULT_VALUES)
committed_cfg = collector_config(committed_docs)
committed_traces = committed_cfg["service"]["pipelines"]["traces"]
check(
    list(committed_cfg["exporters"].keys()) == ["debug", "otlp/eval-tempo"],
    f"committed exporters should be exactly [debug, otlp/eval-tempo], got {list(committed_cfg['exporters'].keys())}",
)
check(
    committed_traces["exporters"] == ["debug", "otlp/eval-tempo"],
    f"committed traces pipeline exporters should be [debug, otlp/eval-tempo], got {committed_traces['exporters']}",
)
check(
    committed_traces["receivers"] == default_cfg["service"]["pipelines"]["traces"]["receivers"]
    and committed_traces["processors"] == default_cfg["service"]["pipelines"]["traces"]["processors"],
    "the committed default must not change the traces pipeline's receivers or processors",
)
check(
    committed_cfg["receivers"] == default_cfg["receivers"] and committed_cfg["processors"] == default_cfg["processors"],
    "the committed default must not change the collector's receivers or processors blocks",
)
check(
    {k: v for k, v in committed_cfg["service"]["pipelines"].items() if k != "traces"}
    == {k: v for k, v in default_cfg["service"]["pipelines"].items() if k != "traces"},
    "the committed default must not change any non-traces pipeline",
)

committed_ds = find(committed_docs, "ConfigMap", name="tempo-eval-grafana-datasource", namespace="monitoring")
check(len(committed_ds) == 1, f"committed default should emit one Tempo (eval) datasource, got {len(committed_ds)}")
if committed_ds:
    ds_doc = yaml.safe_load(next(iter(committed_ds[0]["data"].values())))
    ds = ds_doc["datasources"][0]
    check(committed_ds[0]["metadata"]["labels"].get("grafana_datasource") == "1", "datasource ConfigMap needs grafana_datasource: \"1\"")
    check(ds.get("type") == "tempo" and ds.get("uid") == "tempo-eval", f"unexpected datasource type/uid: {ds!r}")
    ds_host = ds.get("url", "").split("://", 1)[-1].rsplit(":", 1)[0]
    otlp_host = tempo_candidate["otlpEndpoint"].rsplit(":", 1)[0]
    check(ds_host == otlp_host, f"datasource host {ds_host!r} should match the tempo otlpEndpoint host {otlp_host!r}")

# Loki <-> Tempo navigation (agent#97). The Loki datasource keeps its live uid
# (Grafana cannot change a provisioned uid in place), gains a trace_id derived
# field only while the tempo candidate is rendered, and the Tempo datasource's
# trace-to-logs link points back at that same uid.
LOKI_UID = "P8E80F9AEF21F6940"


def _loki_ds(docs):
    cms = find(docs, "ConfigMap", name="loki-grafana-datasource", namespace="monitoring")
    check(len(cms) == 1, f"expected one Loki datasource ConfigMap, got {len(cms)}")
    if not cms:
        return {}
    return yaml.safe_load(next(iter(cms[0]["data"].values())))["datasources"][0]


loki_on = _loki_ds(committed_docs)
check(loki_on.get("uid") == LOKI_UID, f"Loki datasource uid must stay {LOKI_UID}, got {loki_on.get('uid')!r}")
derived = loki_on.get("jsonData", {}).get("derivedFields", [])
check(
    [(f.get("name"), f.get("datasourceUid")) for f in derived] == [("trace_id", "tempo-eval")],
    f"eval-on Loki datasource needs exactly one trace_id derived field to tempo-eval, got {derived!r}",
)
if derived:
    import re as _re
    m = _re.search(derived[0]["matcherRegex"], "INFO:x:msg trace_id=" + "ab" * 16 + " span_id=" + "cd" * 8)
    check(m is not None and m.group(1) == "ab" * 16, "trace_id matcherRegex must capture the 32-hex trace id")
    # "$$" is Grafana's provisioning escape: an unescaped ${...} is read as an
    # environment variable at load time and expands to nothing.
    check(derived[0].get("url") == "$${__value.raw}", f"derived field url must be $${{__value.raw}}, got {derived[0].get('url')!r}")

if committed_ds:
    t2l = yaml.safe_load(next(iter(committed_ds[0]["data"].values())))["datasources"][0].get("jsonData", {}).get("tracesToLogsV2", {})
    check(t2l.get("datasourceUid") == LOKI_UID, f"tracesToLogsV2 must point at the Loki uid, got {t2l!r}")
    check("k8s.pod.name" in t2l.get("query", ""), "tracesToLogsV2 query must scope by the span's pod")

loki_off = _loki_ds(default_docs)
check(loki_off.get("uid") == LOKI_UID, "eval-off Loki datasource must keep the same uid")
check(
    not loki_off.get("jsonData", {}).get("derivedFields"),
    "eval-off Loki datasource must not link to a Tempo datasource that does not exist",
)

# Tempo disabled with the sandbox open: no datasource pointing at nothing.
tempo_off = _write_values(_eval_values(True, [dict(tempo_candidate, enabled=False)]))
check(
    not find(helm_template(DEFAULT_VALUES, tempo_off), "ConfigMap", name="tempo-eval-grafana-datasource"),
    "a disabled tempo candidate must not emit the Tempo (eval) datasource",
)

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("otel-collector backends/eval render: default matches golden, fan-out and eval manifests correct")
