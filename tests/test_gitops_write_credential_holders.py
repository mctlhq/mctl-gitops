"""Ledger of everything that renders or mounts the gitops write credentials
(tracker: mctlhq/mctl-gitops#1033).

tests/fixtures/gitops-write-credential-holders.yaml lists every template,
workflow, chart template and script in this repository that refers to the
credentials in tests/gitops_write_set.py, and what the tenant chart renders for
every tenant. The test compares it with what the repository contains, both ways:

- a reference that is not on the ledger fails (a new holder appeared);
- a ledger row with no matching reference fails (the ledger is stale: remove it
  in the same change that removed the holder, so the list can only shrink).

Observation covers every file outside tests/ and agents-state/ (not only the
Argo templates), with no selection by mechanism: volumes, projected sources, env
secretKeyRef, envFrom, ExternalSecret names and remote keys, and any other
mention on a non-comment line all count. An unreadable file, a file that does
not parse, or a failed render is an error, never an empty result.

Run: python3 tests/test_gitops_write_credential_holders.py
"""
import collections
import os
import pathlib
import re
import sys
import tempfile

import yaml

import gitops_write_set as W

ROOT = W.ROOT
LEDGER = ROOT / "tests/fixtures/gitops-write-credential-holders.yaml"
PRUNE = {".git", "tests", "agents-state", "node_modules", ".worktrees"}
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff", ".woff2", ".gz",
          ".tgz", ".zip", ".pdf"}
TEMPLATED = re.compile(r"(^|/)helm-charts/[^/]+/templates/|^platform-gitops/(bootstrap|argocd)/templates/")
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:600]}")


def observe_tree(root):
    """Rows (file, document, template, mechanism, name) for every reference under root."""
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE)
        for fn in sorted(filenames):
            p = pathlib.Path(dirpath) / fn
            rel = p.relative_to(root).as_posix()
            if p.suffix == ".md":
                continue
            try:
                text = p.read_text()
            except UnicodeDecodeError as e:
                if p.suffix in BINARY:
                    continue
                raise W.ReadError(f"{rel}: not text: {e}") from e
            except OSError as e:
                raise W.ReadError(f"{rel}: {e}") from e
            found = W.mentions(text)
            if not found:
                continue
            if p.suffix in (".yaml", ".yml") and not TEMPLATED.search(rel):
                sites = [s for d in W.load_docs(p) for s in W.sites_in_doc(d)]
                for doc, tpl, mech, name in sites:
                    rows.append((rel, doc, tpl, mech, name))
                for name in sorted(found - {s[3] for s in sites}):
                    rows.append((rel, "-", "-", "text-only", name))
            else:
                kind = "(chart template)" if TEMPLATED.search(rel) else "-"
                for name in sorted(found):
                    rows.append((rel, kind, "-", "text", name))
    return sorted(rows)


def observe_rendered():
    """Per tenant: the references in what the tenant chart renders."""
    out = {}
    for vf in W.tenant_values():
        t = vf.parent.name
        docs = W.helm_render(ROOT / "platform-gitops/helm-charts/tenant", vf, f"tenant-{t}", t)
        out[t] = sorted(s for d in docs for s in W.sites_in_doc(d))
    return out


def compare(observed, ledger):
    obs, led = collections.Counter(map(tuple, observed)), collections.Counter(map(tuple, ledger))
    return sorted((obs - led).elements()), sorted((led - obs).elements())


def load_ledger():
    try:
        data = yaml.safe_load(LEDGER.read_text())
        assert isinstance(data["static"], list) and isinstance(data["rendered_per_tenant"], list)
        return data
    except (OSError, ValueError, KeyError, TypeError, AssertionError, yaml.YAMLError) as e:
        raise W.ReadError(f"{LEDGER}: {e}") from e


# ---- converged input: the repository against its ledger -------------------------------
try:
    ledger = load_ledger()
    new, stale = compare(observe_tree(ROOT), ledger["static"])
    check("no holder of the write credentials outside the ledger", not new, new)
    check("every ledger row still has its reference (ledger can only shrink)", not stale, stale)
    check("the ledger observed something", len(ledger["static"]) > 0)
    rendered = observe_rendered()
    for tenant, rows in rendered.items():
        new, stale = compare(rows, ledger["rendered_per_tenant"])
        check(f"{tenant}: the tenant chart renders exactly the ledgered references",
              not new and not stale, (new, stale))
    check("tenant charts were rendered", len(rendered) > 0)
except W.ReadError as e:
    check("the repository could be observed", False, e)

# ---- mutations: the detector goes red on each deliberate change -----------------------
SEC = W.SECRET_NAMES[0]


def doc_with(**fields):
    d = {"kind": "ClusterWorkflowTemplate", "metadata": {"name": "x"},
         "spec": {"templates": [dict({"name": "t"}, **fields)]}}
    return d


cases = {
    "volume": {"volumes": [{"name": "k", "secret": {"secretName": SEC}}]},
    "projected source": {"volumes": [{"name": "k", "projected": {"sources": [{"secret": {"name": SEC}}]}}]},
    "env secretKeyRef": {"script": {"env": [{"name": "A", "valueFrom": {"secretKeyRef": {"name": SEC, "key": "k"}}}]}},
    "envFrom": {"script": {"envFrom": [{"secretRef": {"name": SEC}}]}},
    "init container env": {"initContainers": [{"name": "i", "env": [
        {"name": "A", "valueFrom": {"secretKeyRef": {"name": SEC, "key": "k"}}}]}]},
    "mention inside a script": {"script": {"source": f"kubectl get secret {SEC} -o yaml"}},
    "a mechanism not seen before": {"artifactRepositoryRef": {"accessKeySecret": {"name": SEC, "key": "k"}}},
}
for label, fields in cases.items():
    got = W.sites_in_doc(doc_with(**fields))
    check(f"detector sees: {label}", len(got) >= 1 and all(s[1] == "t" for s in got), got)
check("a name only in a comment line is not a reference",
      W.sites_in_doc(doc_with(script={"source": f"# {SEC}\necho hi"})) == [])
check("an unrelated secret is not a reference",
      W.sites_in_doc(doc_with(script={"env": [{"name": "A", "valueFrom": {"secretKeyRef": {"name": "other", "key": "k"}}}]})) == [])

observed = [("a.yaml", "Kind/x", "t", "secret.secretName", SEC)]
check("ledger comparison: a new reference is reported", compare(observed, [])[0] == observed)
check("ledger comparison: a removed reference leaves a stale row", compare([], observed)[1] == observed)
check("ledger comparison: equal input is clean", compare(observed, observed) == ([], []))

with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    (root / "tests").mkdir()
    (root / "tests/ignored.yaml").write_text(f"x: {SEC}\n")
    (root / "scripts").mkdir()
    (root / "scripts/a.sh").write_text(f"# {SEC}\necho ok\n")
    check("a tree with only comment mentions and ignored paths observes nothing", observe_tree(root) == [])
    (root / "scripts/a.sh").write_text(f"kubectl get secret {SEC}\n")
    check("a script mention is observed", [r[3:] for r in observe_tree(root)] == [("text", SEC)])
    (root / "platform-gitops/helm-charts/c/templates").mkdir(parents=True)
    (root / "platform-gitops/helm-charts/c/templates/es.yaml").write_text(
        f"{{{{- if x }}}}\nname: {SEC}\n{{{{- end }}}}\n")
    check("a templated chart file (not parseable YAML) is observed by text",
          any(r[1] == "(chart template)" for r in observe_tree(root)))
    (root / "wf.yaml").write_text(
        f"kind: Workflow\nmetadata: {{name: w}}\nspec:\n  templates:\n  - name: t\n    volumes:\n"
        f"    - name: k\n      secret: {{secretName: {SEC}}}\n")
    check("a new workflow volume is observed with its template",
          ("wf.yaml", "Workflow/w", "t", "secret.secretName", SEC) in observe_tree(root))
    (root / "wf.yaml").write_text("kind: [unclosed\n")
    try:
        observe_tree(root)
        check("an unparsable file that mentions nothing is not an error", True)
    except W.ReadError:
        check("an unparsable file that mentions nothing is not an error", False)
    (root / "bad.yaml").write_text(f"a: [{SEC}\n")
    try:
        observe_tree(root)
        check("an unparsable file that mentions a credential is an error, not an empty result", False)
    except W.ReadError:
        check("an unparsable file that mentions a credential is an error, not an empty result", True)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
