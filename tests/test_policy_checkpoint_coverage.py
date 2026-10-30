"""Pin the policy checkpoint coverage of the mctl-agents surfaces (mctlhq/.github#181).

Reads platform-gitops/governance/policy-checkpoint-coverage.yaml and checks it
against the templates and values files, never restating them:

1. Every container running the mctl-agents image (the
   `cwft-mctl-agents-*.yaml` templates, `services/admins/mctl-agents-worker*`)
   has exactly one manifest entry, and no manifest entry is stale.
2. A governed surface carries the literal env `MCTL_POLICY_APPROVALS` equal to
   `approvals_backend`, unless it is marked `rollout: staged` (then it may be
   absent, but if present it must be correct).
3. A governed surface's default image meets `min_approvals_version`.
4. A non-governed boundary holds mechanically: `no-model-session` has no
   CLAUDE_CODE_OAUTH_TOKEN and no agent entry point; `no-mctl-token` has no
   MCTL_TOKEN. A transport entry is `bypass-open`, or `no-mctl-token` when
   the surface it belongs to maps no MCTL_TOKEN and runs at least the entry's
   `min_image_version`.
5. `bypass-open` needs `tracked_by`; a summary line keeps the gap visible.
6. No manifest anywhere sets MCTL_POLICY_APPROVALS to none, empty or valueFrom.

Run: python3 tests/test_policy_checkpoint_coverage.py
"""
import pathlib
import re
import shutil
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
BOUNDARIES = ("no-model-session", "no-mctl-token", "operator-operation", "bypass-open")
TRANSPORT_BOUNDARIES = ("bypass-open", "no-mctl-token")
ENV = "MCTL_POLICY_APPROVALS"
AGENT_ENTRY = re.compile(r"run_issue_investigator|run_implementer|run_shepherd|run_all")
MANIFEST = "platform-gitops/governance/policy-checkpoint-coverage.yaml"


def version_of(tag):
    try:
        return tuple(int(p) for p in str(tag).split("."))
    except ValueError:
        return None


def containers(template):
    for key in ("container", "script"):
        if isinstance(template.get(key), dict):
            yield template[key]
    for key in ("initContainers", "sidecars"):
        yield from template.get(key) or []


def env_list(container):
    return {e.get("name"): e for e in container.get("env") or [] if isinstance(e, dict)}


def scalars(node):
    """Every dict key and scalar in a parsed document (comments excluded)."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k)
            yield from scalars(v)
    elif isinstance(node, list):
        for v in node:
            yield from scalars(v)
    elif node is not None:
        yield str(node)


def load_one(path):
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d is not None]
    return docs[0] if len(docs) == 1 else None


def discover(root):
    """Return {(relpath, template|None): info} for every mctl-agents container."""
    gitops = root / "platform-gitops"
    found = {}
    for path in sorted((gitops / "argo-workflows/cluster-templates").glob("cwft-mctl-agents-*.yaml")):
        doc = load_one(path) or {}
        spec = doc.get("spec") or {}
        params = {p.get("name"): p.get("value") for p in (spec.get("arguments") or {}).get("parameters") or []}
        for t in spec.get("templates") or []:
            for c in containers(t):
                image = str(c.get("image", ""))
                if "agent_image" in image or image.startswith("ghcr.io/mctlhq/mctl-agents"):
                    rel = path.relative_to(gitops).as_posix()
                    found[(rel, t.get("name"))] = {
                        "env": {n: e for n, e in env_list(c).items()},
                        "image": str(params.get("agent_image", image)),
                        "text": list(scalars(c.get("command"))) + list(scalars(c.get("args"))),
                        "strings": set(scalars(c.get("env"))),
                    }
    for path in sorted((gitops / "services/admins").glob("mctl-agents-worker*/values.yaml")):
        doc = load_one(path) or {}
        image = doc.get("image") or {}
        env = {k: {"name": k, "value": v} for k, v in (doc.get("env") or {}).items()}
        found[(path.relative_to(gitops).as_posix(), None)] = {
            "env": env,
            "image": f"{image.get('repository')}:{image.get('tag')}",
            "text": [],
            "strings": set(scalars(doc)),
        }
    return found


def analyze(root):
    failures = []
    manifest_path = root / MANIFEST
    manifest = load_one(manifest_path) or {}
    backend = manifest.get("approvals_backend")
    min_ver = version_of(manifest.get("min_approvals_version"))
    if manifest.get("schema") != "mctl-policy-coverage/v1":
        failures.append("manifest schema is not mctl-policy-coverage/v1")
    if not backend or min_ver is None:
        failures.append("manifest lacks approvals_backend or a valid min_approvals_version")
    surfaces = manifest.get("surfaces") or []
    ids = [s.get("id") for s in surfaces]
    for dup in {i for i in ids if ids.count(i) > 1}:
        failures.append(f"duplicate surface id {dup}")
    entries = {}
    for s in surfaces:
        if s.get("kind") == "transport":
            continue
        key = (s.get("path"), s.get("template"))
        if key in entries:
            failures.append(f"{s.get('id')}: second entry for {key}")
        entries[key] = s

    found = discover(root)
    for key in sorted(found, key=str):
        if key not in entries:
            failures.append(f"{key[0]} template {key[1]}: mctl-agents container has no manifest entry")
    for key, s in entries.items():
        if key not in found:
            failures.append(f"{s.get('id')}: stale entry, {key} no longer runs the mctl-agents image")

    bypass = 0
    staged = 0
    for s in surfaces:
        sid = s.get("id")
        if s.get("kind") == "transport":
            if s.get("of") not in ids:
                failures.append(f"{sid}: transport 'of' names no surface")
            boundary = s.get("boundary")
            if boundary not in TRANSPORT_BOUNDARIES:
                failures.append(f"{sid}: transport entries must be one of {TRANSPORT_BOUNDARIES}, got {boundary!r}")
            elif boundary == "no-mctl-token":
                # The transport is the agent's own tool subprocesses: they can
                # reach no admin credential once the surface's container maps
                # no MCTL_TOKEN, and its image no longer needs one for its
                # own REST calls (mctlhq/mctl-agents#717).
                of = next((o for o in surfaces if o.get("id") == s.get("of") and o.get("kind") != "transport"), None)
                of_info = found.get((of.get("path"), of.get("template"))) if of else None
                need = version_of(s.get("min_image_version"))
                if not s.get("reason"):
                    failures.append(f"{sid}: non-governed entry needs a reason")
                if need is None:
                    failures.append(f"{sid}: no-mctl-token transport needs a valid min_image_version")
                if of_info is None:
                    failures.append(f"{sid}: no-mctl-token transport names no discovered surface")
                    continue
                if "MCTL_TOKEN" in of_info["env"] or "MCTL_TOKEN" in of_info["strings"]:
                    failures.append(f"{sid}: no-mctl-token transport, but {s.get('of')} still maps MCTL_TOKEN")
                got = version_of(of_info["image"].rpartition(":")[2])
                if need is not None and (got is None or got < need):
                    failures.append(f"{sid}: image {of_info['image']} is older than min_image_version")
                continue
        info = found.get((s.get("path"), s.get("template")))
        if s.get("governed"):
            if info is None:
                continue
            got = info["env"].get(ENV)
            if s.get("rollout") == "staged":
                staged += 1
                if got is not None and got.get("value") != backend:
                    failures.append(f"{sid}: {ENV} must be the literal {backend!r}, got {got!r}")
            elif got is None or got.get("value") != backend:
                failures.append(f"{sid}: governed surface must set {ENV}={backend} as a literal value, got {got!r}")
            ver = version_of(info["image"].rpartition(":")[2])
            if min_ver and (ver is None or ver < min_ver):
                failures.append(f"{sid}: image {info['image']} is older than min_approvals_version")
            continue
        boundary = s.get("boundary")
        if boundary not in BOUNDARIES:
            failures.append(f"{sid}: non-governed entry needs a boundary in {BOUNDARIES}, got {boundary!r}")
            continue
        if not s.get("reason"):
            failures.append(f"{sid}: non-governed entry needs a reason")
        if boundary == "bypass-open":
            bypass += 1
            if not s.get("tracked_by"):
                failures.append(f"{sid}: bypass-open needs tracked_by")
        if info is None:
            continue
        if boundary == "no-model-session":
            if "CLAUDE_CODE_OAUTH_TOKEN" in info["strings"] or "CLAUDE_CODE_OAUTH_TOKEN" in info["env"]:
                failures.append(f"{sid}: no-model-session surface carries CLAUDE_CODE_OAUTH_TOKEN")
            if any(AGENT_ENTRY.search(t) for t in info["text"]):
                failures.append(f"{sid}: no-model-session surface runs an agent entry point")
        if boundary == "no-mctl-token" and ("MCTL_TOKEN" in info["env"] or "MCTL_TOKEN" in info["strings"]):
            failures.append(f"{sid}: no-mctl-token surface still maps MCTL_TOKEN")

    # No manifest may turn governance off, anywhere.
    gitops = root / "platform-gitops"
    for path in sorted(list(gitops.rglob("*.yaml")) + list(gitops.rglob("*.yml"))):
        rel = path.relative_to(gitops)
        if rel.parts[0] in ("agents-state", "governance") or ENV not in path.read_text():
            continue
        try:
            docs = [d for d in yaml.safe_load_all(path.read_text()) if d is not None]
        except yaml.YAMLError:
            failures.append(f"{rel}: mentions {ENV} but is not parseable YAML")
            continue
        for doc in docs:
            for bad in walk_env(doc):
                failures.append(f"{rel}: {ENV} must be the literal {backend!r}, got {bad!r}")
    return failures, bypass, staged


def walk_env(node):
    if isinstance(node, dict):
        if node.get("name") == ENV and node.get("value") != "mctl-api":
            yield {k: v for k, v in node.items() if k != "name"}
        if ENV in node and not isinstance(node[ENV], (dict, list)) and node[ENV] != "mctl-api":
            yield node[ENV]
        for v in node.values():
            yield from walk_env(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_env(v)


def make_fixture(tmp, mutate):
    """Copy the real manifest + templates, then apply a mutation."""
    dst = pathlib.Path(tmp)
    src = REPO / "platform-gitops"
    for sub in ("governance", "argo-workflows/cluster-templates", "services/admins"):
        shutil.copytree(src / sub, dst / "platform-gitops" / sub,
                        ignore=shutil.ignore_patterns("*.tf", "mctl-design", "mctl-docs", "mctl-web", "umami"))
    mutate(dst / "platform-gitops")
    return dst


def edit(path, fn):
    path.write_text(fn(path.read_text()))


def self_test():
    """Synthetic fixtures: each defect must fail and name the surface."""
    results = []
    cwft = "argo-workflows/cluster-templates/"

    def expect(name, mutate, needle):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_fixture(tmp, mutate)
            fails, _, _ = analyze(root)
            ok = any(needle in f for f in fails)
            results.append((f"fixture: {name}", ok, str(fails)))

    def new_template(gp):
        edit(gp / (cwft + "cwft-mctl-agents-reconcile.yaml"), lambda t: t)
        (gp / (cwft + "cwft-mctl-agents-extra.yaml")).write_text(
            "apiVersion: argoproj.io/v1alpha1\nkind: ClusterWorkflowTemplate\nmetadata:\n  name: x\n"
            "spec:\n  templates:\n    - name: extra-run\n      container:\n"
            "        image: ghcr.io/mctlhq/mctl-agents:1.86.1\n")
    expect("unlisted mctl-agents template", new_template, "extra-run")

    def set_env(raw):
        def mutate(gp):
            p = gp / (cwft + "cwft-mctl-agents-investigate.yaml")
            edit(p, lambda t: re.sub(
                r"( +)- name: MCTL_POLICY_APPROVALS\n +(value: mctl-api|valueFrom:.*\n.*)\n",
                lambda m: f"{m.group(1)}- name: {ENV}\n{m.group(1)}  {raw}\n", t))
        return mutate
    expect("investigate env none", set_env("value: none"), "investigate")
    expect("investigate env empty", set_env('value: ""'), "investigate")
    expect("investigate env valueFrom", set_env("valueFrom: {secretKeyRef: {name: s, key: k}}"), "investigate")

    def stale(gp):
        (gp / (cwft + "cwft-mctl-agents-usage-collector.yaml")).unlink()
    expect("stale entry", stale, "usage-collector")

    def no_tracker(gp):
        edit(gp / "governance/policy-checkpoint-coverage.yaml",
             lambda t: t.replace("    tracked_by: mctlhq/mctl-agents#717\n", "", 1))
    expect("bypass-open without tracked_by", no_tracker, "bypass-open needs tracked_by")

    def token_leak(gp):
        edit(gp / "governance/policy-checkpoint-coverage.yaml",
             lambda t: t.replace("boundary: no-model-session\n    reason: run_usage", "boundary: no-mctl-token\n    reason: run_usage", 1))
        p = gp / (cwft + "cwft-mctl-agents-usage-collector.yaml")
        edit(p, lambda t: t.replace("        env:\n", "        env:\n          - name: MCTL_TOKEN\n            value: x\n", 1))
    expect("no-mctl-token surface maps MCTL_TOKEN", token_leak, "usage-collector")

    investigate_tpl = cwft + "cwft-mctl-agents-investigate.yaml"

    def leak_token(gp):
        edit(gp / investigate_tpl, lambda t: t.replace(
            "          - name: MCTL_RUN_TOKEN_MODE\n",
            "          - name: MCTL_TOKEN\n            valueFrom:\n"
            "              secretKeyRef: {name: s, key: k}\n"
            "          - name: MCTL_RUN_TOKEN_MODE\n", 1))
    expect("no-mctl-token transport whose surface maps MCTL_TOKEN",
           leak_token, "still maps MCTL_TOKEN")

    def older_image(gp):
        edit(gp / investigate_tpl, lambda t: re.sub(
            r"(value: ghcr\.io/mctlhq/mctl-agents:)[0-9.]+", r"\g<1>1.0.0", t, count=1))
    expect("no-mctl-token transport on an older image",
           older_image, "older than min_image_version")
    return results


def main():
    failures, bypass, staged = analyze(REPO)
    results = [("coverage manifest matches the repository", not failures, "; ".join(failures))]
    results += self_test()
    bad = []
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            bad.append(f"{name}: {detail}")
    print(f"bypass-open: {bypass}")
    print(f"governed, rollout staged (no {ENV} yet): {staged}")
    if failures:
        print("\n".join(["", "COVERAGE FAILURES:"] + failures))
    if bad:
        sys.exit(1)
    print("policy checkpoint coverage holds")


if __name__ == "__main__":
    main()
