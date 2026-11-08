"""Consistency check between the submit contract fixtures and the repository.

Mirrors mctlhq/mctl-gitops#1033 (tests and fixtures only, no runtime change).

Reads
  tests/fixtures/workflow-namespaces.yaml
  tests/fixtures/portal-team-templates.yaml
  tests/fixtures/portal-submit-state.yaml
  platform-gitops/argo-workflows/cluster-templates/*.yaml
  platform-gitops/tenants/*/values.yaml

and asserts:
  1. The namespace fixture accounts for every ClusterWorkflowTemplate in the
     repository exactly once, and the list of names without a template is
     disjoint from the defined ones.
  2. Every portal template has a legacy ClusterWorkflowTemplate; a `-w2`
     variant, if defined, is a ClusterWorkflowTemplate; names are unique, `w2` is `<legacy>-w2`, and neither name is in the
     shared `argo_workflows_namespace` list.
  3. For each tenant the template names it may submit follow its write mode
     (tenant.gitopsWritesMode: legacy|shadow|on, unset = legacy): legacy and
     shadow use the legacy names, on uses the `-w2` names. Every allowed name
     must have a template, so a tenant in mode `on` needs the `-w2` templates
     (they may be absent only while no tenant is in mode `on`).
  4. While the portal fixture says `off`, no tenant is in a mode other than
     `legacy`.

A file that cannot be read or parsed, or a value outside the documented set,
is an error (exit 2), never an empty or clean result. This includes an
unquoted `on`, which YAML reads as a boolean: the mode must be written "on". A violated relation is
exit 1. The mutation cases at the bottom prove the check goes red.
"""
import pathlib
import shutil
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODES = ("legacy", "shadow", "on")
CWT_DIR = "platform-gitops/argo-workflows/cluster-templates"
TENANTS_DIR = "platform-gitops/tenants"
FIX = "tests/fixtures"


class Unknown(Exception):
    """A read or parse failure: could not observe, so no verdict."""


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            docs = [d for d in yaml.safe_load_all(f) if d is not None]
    except (OSError, yaml.YAMLError) as e:
        raise Unknown(f"cannot read {path}: {e}")
    return docs


def load_one(path):
    docs = load(path)
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise Unknown(f"{path}: expected exactly one mapping document")
    return docs[0]


def str_list(doc, key, path):
    v = doc.get(key)
    if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
        raise Unknown(f"{path}: `{key}` must be a list of non-empty strings")
    return v


def template_files(root):
    d = root / CWT_DIR
    files = sorted(set(d.glob("*.yaml")) | set(d.glob("*.yml")))
    if not files:
        raise Unknown(f"no templates found under {d}")
    return files


def cwt_names(root):
    names = []
    for f in template_files(root):
        for doc in load(f):
            if isinstance(doc, dict) and doc.get("kind") == "ClusterWorkflowTemplate":
                n = (doc.get("metadata") or {}).get("name")
                if not isinstance(n, str) or not n:
                    raise Unknown(f"{f}: ClusterWorkflowTemplate without a name")
                names.append(n)
    return names


def other_kind_names(root):
    """Names of documents in the template directory that are not a
    ClusterWorkflowTemplate (for example a namespaced WorkflowTemplate)."""
    names = set()
    for f in template_files(root):
        for doc in load(f):
            if isinstance(doc, dict) and doc.get("kind") != "ClusterWorkflowTemplate":
                n = (doc.get("metadata") or {}).get("name")
                if isinstance(n, str) and n:
                    names.add(n)
    return names


def tenant_modes(root):
    files = sorted((root / TENANTS_DIR).glob("*/values.yaml"))
    if not files:
        raise Unknown(f"no tenant files found under {root / TENANTS_DIR}")
    modes = {}
    for f in files:
        doc = load_one(f)
        t = doc.get("tenant")
        if not isinstance(t, dict):
            raise Unknown(f"{f}: missing `tenant` mapping")
        mode = t.get("gitopsWritesMode", "legacy")
        if mode not in MODES:
            raise Unknown(f"{f}: gitopsWritesMode {mode!r} not in {MODES}")
        modes[f.parent.name] = mode
    return modes


def allowed_names(mode, portal_templates):
    key = "w2" if mode == "on" else "legacy"
    return sorted(t[key] for t in portal_templates)


def check(root):
    """Return a list of violations. Raises Unknown when nothing can be said."""
    errs = []
    names = cwt_names(root)
    nameset = set(names)
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        errs.append(f"duplicate ClusterWorkflowTemplate names: {dup}")

    # 1. namespace fixture
    p = root / FIX / "workflow-namespaces.yaml"
    ns = load_one(p)
    central = str_list(ns, "argo_workflows_namespace", p)
    central_nt = str_list(ns, "argo_workflows_namespace_no_template", p)
    other = str_list(ns, "other_repo_templates", p)
    listed = central + central_nt + other
    if len(set(listed)) != len(listed):
        errs.append("workflow-namespaces: a name appears more than once")
    for n in central_nt:
        if n in nameset:
            errs.append(f"workflow-namespaces: {n} is listed as having no template but one is defined")
    in_fixture = set(central) | set(other)
    for n in sorted(nameset - in_fixture):
        errs.append(f"workflow-namespaces: template {n} is defined but not in the fixture")
    for n in sorted(in_fixture - nameset):
        errs.append(f"workflow-namespaces: {n} is in the fixture but no template is defined")

    # 2. portal templates
    p = root / FIX / "portal-team-templates.yaml"
    pt = load_one(p).get("templates")
    if not isinstance(pt, list) or not pt:
        raise Unknown(f"{p}: `templates` must be a non-empty list")
    for t in pt:
        if not (isinstance(t, dict) and isinstance(t.get("legacy"), str)
                and isinstance(t.get("w2"), str)):
            raise Unknown(f"{p}: each entry needs string `legacy` and `w2`")
    other_kinds = other_kind_names(root)
    legacy = [t["legacy"] for t in pt]
    if len(set(legacy)) != len(legacy):
        errs.append("portal-team-templates: duplicate legacy name")
    for t in pt:
        if t["w2"] != t["legacy"] + "-w2":
            errs.append(f"portal-team-templates: {t['w2']} is not {t['legacy']}-w2")
        if t["legacy"] not in nameset:
            errs.append(f"portal-team-templates: no template defined for {t['legacy']}")
        for key in ("legacy", "w2"):
            if t[key] in central or t[key] in central_nt:
                errs.append(f"portal-team-templates: {t[key]} is a shared-namespace template, not a team one")
        if t["w2"] in other_kinds:
            errs.append(f"portal-team-templates: {t['w2']} is defined but not as a ClusterWorkflowTemplate")

    # 3 + 4. tenants versus portal state
    p = root / FIX / "portal-submit-state.yaml"
    state = load_one(p).get("submitViaMctlApi")
    if state not in ("on", "off"):
        raise Unknown(f"{p}: submitViaMctlApi must be the string on or off, got {state!r}")
    modes = tenant_modes(root)
    for tenant, mode in sorted(modes.items()):
        want = allowed_names(mode, pt)
        # Every name a tenant may submit must have a template. The `-w2`
        # variants are introduced later, so while no tenant is in mode `on`
        # their absence is allowed; a tenant in mode `on` needs them.
        for n in want:
            if n not in nameset:
                errs.append(f"{tenant}: allowed name {n} has no template (mode {mode})")
        if state == "off" and mode != "legacy":
            errs.append(f"{tenant}: mode {mode} while submitViaMctlApi is off")
    return errs


# ---- proof both ways -------------------------------------------------------

def snapshot(root, dest):
    for rel in (CWT_DIR, TENANTS_DIR, FIX):
        shutil.copytree(root / rel, dest / rel)
    return dest


W2_NAMES = ("deploy-service-w2", "retire-service-w2", "provision-database-w2")


def add_w2_templates(dest, kind="ClusterWorkflowTemplate", register=True):
    """Define the `-w2` variants; register them as team-namespace names."""
    for n in W2_NAMES:
        (dest / CWT_DIR / f"probe-{n}.yaml").write_text(
            f"apiVersion: argoproj.io/v1alpha1\nkind: {kind}\n"
            f"metadata:\n  name: {n}\nspec:\n  templates: []\n")
    if register:
        p = dest / FIX / "workflow-namespaces.yaml"
        p.write_text(p.read_text() + "".join(f"  - {n}\n" for n in W2_NAMES))


def set_tenant_on(dest):
    (dest / FIX / "portal-submit-state.yaml").write_text('submitViaMctlApi: "on"\n')
    p = next((dest / TENANTS_DIR).glob("*/values.yaml"))
    p.write_text(p.read_text().replace("tenant:\n", "tenant:\n  gitopsWritesMode: \"on\"\n", 1))


def mutate(dest, case):
    fx = dest / FIX
    if case == "template-not-in-fixture":
        (dest / CWT_DIR / "wft-extra-probe.yaml").write_text(
            "apiVersion: argoproj.io/v1alpha1\nkind: ClusterWorkflowTemplate\n"
            "metadata:\n  name: extra-probe\nspec:\n  templates: []\n")
    elif case == "fixture-name-without-template":
        p = fx / "workflow-namespaces.yaml"
        p.write_text(p.read_text() + "  - ghost-template\n")
    elif case == "portal-name-without-template":
        p = fx / "portal-team-templates.yaml"
        p.write_text(p.read_text() + "  - legacy: ghost-service\n    w2: ghost-service-w2\n")
    elif case == "tenant-shadow-while-portal-off":
        p = next((dest / TENANTS_DIR).glob("*/values.yaml"))
        p.write_text(p.read_text().replace("tenant:\n", "tenant:\n  gitopsWritesMode: shadow\n", 1))
    elif case == "tenant-unknown-mode":
        p = next((dest / TENANTS_DIR).glob("*/values.yaml"))
        p.write_text(p.read_text().replace("tenant:\n", "tenant:\n  gitopsWritesMode: sideways\n", 1))
    elif case == "portal-state-unreadable":
        (fx / "portal-submit-state.yaml").write_text("submitViaMctlApi: [unterminated\n")
    elif case == "portal-state-bare-bool":
        (fx / "portal-submit-state.yaml").write_text("submitViaMctlApi: off\n")
    elif case == "tenant-on-without-w2-templates":
        set_tenant_on(dest)
    elif case == "w2-in-shared-namespace":
        add_w2_templates(dest, register=False)
        p = fx / "workflow-namespaces.yaml"
        p.write_text(p.read_text().replace(
            "argo_workflows_namespace:\n", "argo_workflows_namespace:\n  - deploy-service-w2\n", 1))
    elif case == "w2-wrong-kind":
        (dest / CWT_DIR / "probe-wrong-kind.yaml").write_text(
            "apiVersion: argoproj.io/v1alpha1\nkind: WorkflowTemplate\n"
            "metadata:\n  name: deploy-service-w2\nspec:\n  templates: []\n")
    elif case == "portal-duplicate-legacy":
        p = fx / "portal-team-templates.yaml"
        p.write_text(p.read_text() + "  - legacy: deploy-service\n    w2: deploy-service-w2\n")
    elif case == "portal-bad-w2-naming":
        p = fx / "portal-team-templates.yaml"
        p.write_text(p.read_text().replace("w2: retire-service-w2", "w2: retire-service-v2", 1))
    elif case == "yml-template-not-in-fixture":
        (dest / CWT_DIR / "wft-extra-yml-probe.yml").write_text(
            "apiVersion: argoproj.io/v1alpha1\nkind: ClusterWorkflowTemplate\n"
            "metadata:\n  name: extra-yml-probe\nspec:\n  templates: []\n")
    else:
        raise AssertionError(case)


RED = {  # case -> (exit class, substring)
    "template-not-in-fixture": (1, "extra-probe is defined but not in the fixture"),
    "fixture-name-without-template": (1, "ghost-template is in the fixture"),
    "portal-name-without-template": (1, "no template defined for ghost-service"),
    "tenant-shadow-while-portal-off": (1, "while submitViaMctlApi is off"),
    "tenant-unknown-mode": (2, "sideways"),
    "portal-state-unreadable": (2, "cannot read"),
    "portal-state-bare-bool": (2, "must be the string on or off"),
    "tenant-on-without-w2-templates": (1, "allowed name deploy-service-w2 has no template (mode on)"),
    "w2-in-shared-namespace": (1, "deploy-service-w2 is a shared-namespace template"),
    "w2-wrong-kind": (1, "deploy-service-w2 is defined but not as a ClusterWorkflowTemplate"),
    "portal-duplicate-legacy": (1, "duplicate legacy name"),
    "portal-bad-w2-naming": (1, "retire-service-v2 is not retire-service-w2"),
    "yml-template-not-in-fixture": (1, "extra-yml-probe is defined but not in the fixture"),
}


def run(root):
    try:
        errs = check(root)
    except Unknown as e:
        return 2, [str(e)]
    return (1 if errs else 0), errs


def main():
    failures = []

    def expect(name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failures.append(f"{name}: {detail}")

    code, msgs = run(ROOT)
    expect("converged repository is green", code == 0, "; ".join(msgs))

    # A tenant set to `on` with the portal flag on is a valid converged state.
    with tempfile.TemporaryDirectory() as td:
        d = snapshot(ROOT, pathlib.Path(td) / "t")
        set_tenant_on(d)
        add_w2_templates(d)
        code, msgs = run(d)
        expect("mode on with portal flag on and -w2 templates defined is green", code == 0, "; ".join(msgs))

    for case, (want_code, needle) in RED.items():
        with tempfile.TemporaryDirectory() as td:
            d = snapshot(ROOT, pathlib.Path(td) / "t")
            mutate(d, case)
            code, msgs = run(d)
            expect(f"mutation {case} is red",
                   code == want_code and any(needle in m for m in msgs),
                   f"code={code} msgs={msgs}")

    # A missing tenant directory is unknown, never an empty clean set.
    with tempfile.TemporaryDirectory() as td:
        d = snapshot(ROOT, pathlib.Path(td) / "t")
        shutil.rmtree(d / TENANTS_DIR)
        (d / TENANTS_DIR).mkdir()
        code, _ = run(d)
        expect("no tenant files is unknown (exit 2)", code == 2, f"code={code}")

    if failures:
        print("\n".join(failures))
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    main()
