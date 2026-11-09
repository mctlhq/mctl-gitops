"""Ledger of everything that renders or mounts the gitops write credentials
(tracker: mctlhq/mctl-gitops#1033).

tests/fixtures/gitops-write-credential-holders.yaml lists every template,
workflow, chart template and script in this repository that refers to the
credentials in tests/gitops_write_set.py, and what the tenant chart renders for
every tenant. The test compares it with what the repository contains, both ways:

- a reference that is not on the ledger fails (a new holder appeared);
- a ledger row with no matching reference fails (the ledger is stale: remove it
  in the same change that removed the holder, so the list can only shrink).

Observation covers every file outside the repository-root tests/ and agents-state/
(nested directories with those names are scanned; not only the
Argo templates), with no selection by mechanism: volumes, projected sources, env
secretKeyRef, envFrom, ExternalSecret names and remote keys, and any other
mention on a non-comment line all count. A text mention counts once per
non-comment line that contains the name (repeated ledger rows), so a second
reference in a file already on the ledger is detected. An unreadable file, a file that does
not parse, or a failed render is an error, never an empty result.

Run: python3 tests/test_gitops_write_credential_holders.py
"""
import collections
import os
import pathlib
import re
import shutil
import sys
import tempfile

import yaml

import gitops_write_set as W

ROOT = W.ROOT
LEDGER = ROOT / "tests/fixtures/gitops-write-credential-holders.yaml"
# Directories skipped, by path relative to the repository root only. A nested
# directory with the same name is scanned.
PRUNE = {".git", "tests", "agents-state", "node_modules", ".worktrees"}
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff", ".woff2", ".gz",
          ".tgz", ".zip", ".pdf", ".pyc"}
TEMPLATED = re.compile(r"(^|/)helm-charts/[^/]+/templates/|^platform-gitops/(bootstrap|argocd)/templates/")
ROOT_PRUNED = ("tests", "agents-state", "node_modules", ".worktrees")
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:600]}")


def observe_tree(root, names=W.ALL_NAMES):
    """Rows (file, document, template, mechanism, name) for every reference under root."""
    rows = []

    def unreadable(err):
        # os.walk ignores listing errors by default, which would drop a whole
        # directory from the observation without a word.
        raise W.ReadError(f"{err.filename}: cannot list directory: {err.strerror}") from err

    for dirpath, dirnames, filenames in os.walk(root, onerror=unreadable):
        at_root = pathlib.Path(dirpath) == pathlib.Path(root)
        dirnames[:] = sorted(d for d in dirnames if not (at_root and d in PRUNE))
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
            found = W.mention_counts(text, names)
            if not found:
                continue
            if p.suffix in (".yaml", ".yml") and not TEMPLATED.search(rel):
                sites = [s for d in W.load_docs(p) for s in W.sites_in_doc(d, names)]
                for doc, tpl, mech, name in sites:
                    rows.append((rel, doc, tpl, mech, name))
                for name in sorted(set(found) - {s[3] for s in sites}):
                    rows.extend([(rel, "-", "-", "text-only", name)] * found[name])
            else:
                kind = "(chart template)" if TEMPLATED.search(rel) else "-"
                for name in sorted(found):
                    rows.extend([(rel, kind, "-", "text", name)] * found[name])
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
REF = W.SECRET_NAMES[0]


def doc_with(**fields):
    d = {"kind": "ClusterWorkflowTemplate", "metadata": {"name": "x"},
         "spec": {"templates": [dict({"name": "t"}, **fields)]}}
    return d


cases = {
    "volume": {"volumes": [{"name": "k", "secret": {"secretName": REF}}]},
    "projected source": {"volumes": [{"name": "k", "projected": {"sources": [{"secret": {"name": REF}}]}}]},
    "env secretKeyRef": {"script": {"env": [{"name": "A", "valueFrom": {"secretKeyRef": {"name": REF, "key": "k"}}}]}},
    "envFrom": {"script": {"envFrom": [{"secretRef": {"name": REF}}]}},
    "init container env": {"initContainers": [{"name": "i", "env": [
        {"name": "A", "valueFrom": {"secretKeyRef": {"name": REF, "key": "k"}}}]}]},
    "mention inside a script": {"script": {"source": f"kubectl get secret {REF} -o yaml"}},
    "a mechanism not seen before": {"artifactRepositoryRef": {"accessKeySecret": {"name": REF, "key": "k"}}},
}
for label, fields in cases.items():
    got = W.sites_in_doc(doc_with(**fields))
    check(f"detector sees: {label}", len(got) >= 1 and all(s[1] == "t" for s in got), got)
check("a name only in a comment line is not a reference",
      W.sites_in_doc(doc_with(script={"source": f"# {REF}\necho hi"})) == [])
check("an unrelated secret is not a reference",
      W.sites_in_doc(doc_with(script={"env": [{"name": "A", "valueFrom": {"secretKeyRef": {"name": "other", "key": "k"}}}]})) == [])

observed = [("a.yaml", "Kind/x", "t", "secret.secretName", REF)]
check("ledger comparison: a new reference is reported", compare(observed, [])[0] == observed)
check("ledger comparison: a removed reference leaves a stale row", compare([], observed)[1] == observed)
check("ledger comparison: equal input is clean", compare(observed, observed) == ([], []))

# The synthetic trees use a placeholder name, passed as `names`, not a real credential name.
SYNTH_NAME = "example-holder-name"
SYNTH = (SYNTH_NAME,)
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    for d in ROOT_PRUNED:
        (root / d).mkdir()
        (root / d / "ignored.yaml").write_text(f"x: {SYNTH_NAME}\n")
    (root / "scripts").mkdir()
    (root / "scripts/a.sh").write_text(f"# {SYNTH_NAME}\necho ok\n")
    check("root-level excluded directories (tests, agents-state, node_modules, .worktrees) are not scanned "
          "and comment-only mentions observe nothing", observe_tree(root, SYNTH) == [])
    for d in ROOT_PRUNED:
        # Mutation-discriminating: with an any-depth prune these go red.
        (root / "platform-gitops/x" / d).mkdir(parents=True)
        (root / "platform-gitops/x" / d / "nested.yaml").write_text(f"x: {SYNTH_NAME}\n")
        check(f"a nested directory named {d} is still scanned",
              any(r[0] == f"platform-gitops/x/{d}/nested.yaml" for r in observe_tree(root, SYNTH)), observe_tree(root, SYNTH))
    (root / "scripts/__pycache__").mkdir()
    (root / "scripts/__pycache__/m.cpython-314.pyc").write_bytes(b"\x00\x8b\xff")
    try:
        observe_tree(root, SYNTH)
        check("a compiled .pyc is not an unreadable-file error", True)
    except W.ReadError as e:
        check("a compiled .pyc is not an unreadable-file error", False, e)
    (root / "scripts/__pycache__/m.cpython-314.pyc").unlink()
    (root / "scripts/__pycache__").rmdir()
    for d in ROOT_PRUNED:
        shutil.rmtree(root / "platform-gitops/x" / d)
    (root / "scripts/a.sh").write_text(f"kubectl get secret {SYNTH_NAME}\n")
    check("a script mention is observed", [r[3:] for r in observe_tree(root, SYNTH)] == [("text", SYNTH_NAME)])
    two = sorted(r for r in observe_tree(root, SYNTH) if r[0] == "scripts/a.sh")
    (root / "scripts/a.sh").write_text(f"kubectl get secret {SYNTH_NAME}\necho x\nkubectl delete secret {SYNTH_NAME}\n")
    after = sorted(r for r in observe_tree(root, SYNTH) if r[0] == "scripts/a.sh")
    check("a second mention in a file that is already listed adds a row", len(after) == len(two) + 1
          and compare(after, two) == ([after[0]], []), (two, after))
    (root / "scripts/a.sh").write_text(f"kubectl get secret {SYNTH_NAME}\n")
    (root / "scripts/two.yaml").write_text(f"kind: Workflow\nmetadata: {{name: w}}\nspec:\n  templates:\n  - name: t\n"
                                           f"    script:\n      source: |\n        a {SYNTH_NAME}\n        b {SYNTH_NAME}\n")
    check("two mentions in one script body are two rows",
          sum(1 for r in observe_tree(root, SYNTH) if r[0] == "scripts/two.yaml") == 2)
    (root / "scripts/two.yaml").unlink()
    (root / "platform-gitops/helm-charts/c/templates").mkdir(parents=True)
    (root / "platform-gitops/helm-charts/c/templates/es.yaml").write_text(
        f"{{{{- if x }}}}\nname: {SYNTH_NAME}\n{{{{- end }}}}\n")
    check("a templated chart file (not parseable YAML) is observed by text",
          any(r[1] == "(chart template)" for r in observe_tree(root, SYNTH)))
    (root / "wf.yaml").write_text(
        f"kind: Workflow\nmetadata: {{name: w}}\nspec:\n  templates:\n  - name: t\n    volumes:\n"
        f"    - name: k\n      secret: {{secretName: {SYNTH_NAME}}}\n")
    check("a new workflow volume is observed with its template",
          ("wf.yaml", "Workflow/w", "t", "secret.secretName", SYNTH_NAME) in observe_tree(root, SYNTH))
    (root / "wf.yaml").write_text("kind: [unclosed\n")
    try:
        observe_tree(root, SYNTH)
        check("an unparsable file that mentions nothing is not an error", True)
    except W.ReadError:
        check("an unparsable file that mentions nothing is not an error", False)
    (root / "bad.yaml").write_text(f"a: [{SYNTH_NAME}\n")
    try:
        observe_tree(root, SYNTH)
        check("an unparsable file that mentions a credential is an error, not an empty result", False)
    except W.ReadError:
        check("an unparsable file that mentions a credential is an error, not an empty result", True)

# An unlistable directory is a ReadError, not a shorter tree. chmod 000 does not
# stop root (CI containers, some dev shells), so the case is skipped, loudly, when
# the process is root or the mode change is not enforced.
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    (root / "scripts/locked").mkdir(parents=True)
    (root / "scripts/locked/a.sh").write_text(f"kubectl get secret {SYNTH_NAME}\n")
    locked = root / "scripts/locked"
    os.chmod(locked, 0)
    try:
        enforced = not os.access(locked, os.R_OK)
        if not enforced:
            print("SKIP  unlistable directory cases: permissions not enforced "
                  f"(euid={os.geteuid()}; root ignores chmod 000)")
        else:
            try:
                observe_tree(root, SYNTH)
                check("a directory that cannot be listed is a ReadError, not a shorter tree", False)
            except W.ReadError:
                check("a directory that cannot be listed is a ReadError, not a shorter tree", True)
            try:
                W.list_dir(locked)
                check("list_dir on an unlistable directory is a ReadError", False)
            except W.ReadError:
                check("list_dir on an unlistable directory is a ReadError", True)
            try:
                W.yaml_files(locked)
                check("yaml_files on an unlistable directory is a ReadError", False)
            except W.ReadError:
                check("yaml_files on an unlistable directory is a ReadError", True)
    finally:
        os.chmod(locked, 0o755)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
