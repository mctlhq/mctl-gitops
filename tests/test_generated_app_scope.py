"""Detector tests for scripts/validate-generated-app-scope.py.

Each check is run green on the real tree (converged input) and red on a
deliberate mutation of it. Mutations work on a temporary copy of the
directories and templates the detector reads, or on the parsed render, so the
real checkout is never modified.

Run: python3 tests/test_generated_app_scope.py
"""
import copy
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("gas", REPO / "scripts" / "validate-generated-app-scope.py")
gas = importlib.util.module_from_spec(spec)
sys.modules["gas"] = gas
spec.loader.exec_module(gas)

BOOTSTRAP = None


def bootstrap_docs():
    global BOOTSTRAP
    if BOOTSTRAP is None:
        out = subprocess.run(
            ["helm", "template", "root", str(REPO / "platform-gitops/bootstrap"),
             "-f", str(REPO / "platform-gitops/bootstrap/values.yaml")],
            check=True, capture_output=True, text=True).stdout
        BOOTSTRAP = [d for d in yaml.safe_load_all(out) if isinstance(d, dict)]
    return copy.deepcopy(BOOTSTRAP)


def stub_render(root, app):
    return [{"apiVersion": "apps/v1", "kind": "Deployment",
             "metadata": {"name": app.service, "namespace": app.namespace}}]


class Tree:
    """Temporary copy of the files the directory and name checks read."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        for rel in (gas.SERVICES, gas.TENANTS):
            shutil.copytree(REPO / rel, self.root / rel, ignore=shutil.ignore_patterns("*.md"))
        for rel in (gas.CREATE_TENANT, gas.DELETE_TENANT):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, self.root / rel)
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()


def run(root, docs, render=stub_render, prefix="tenant-"):
    return gas.run_all(root, docs, prefix, render=render, consumers=False)


class Converged(unittest.TestCase):
    def test_real_tree_is_clean(self):
        found = gas.run_all(REPO, bootstrap_docs(), "tenant-")
        self.assertEqual(found, [])

    def test_expansion_covers_real_directories(self):
        docs = bootstrap_docs()
        sets = {d["metadata"]["name"]: d for d in docs if d.get("kind") == "ApplicationSet"}
        apps = gas.expand(REPO, sets["apps"])
        self.assertEqual(len(apps), len([p for p in (REPO / gas.SERVICES).glob("*/*") if p.is_dir()]))
        self.assertTrue(all(a.name == f"{a.team}-{a.service}" and a.namespace == a.team for a in apps))
        tenants = gas.expand(REPO, sets["tenants"])
        self.assertTrue(all(a.name == "tenant-" + a.path.split("/")[-1] for a in tenants))


class Mutations(unittest.TestCase):
    def assertRed(self, found, needle):
        self.assertTrue(any(needle in f for f in found), f"{needle!r} not in {found}")

    def test_undefined_project(self):
        docs = bootstrap_docs()
        for d in docs:
            if d.get("kind") == "ApplicationSet" and d["metadata"]["name"] == "apps":
                d["spec"]["template"]["spec"]["project"] = "missing"
        with Tree() as t:
            self.assertRed(run(t.root, docs), "is not defined")

    def test_server_string_differs(self):
        docs = bootstrap_docs()
        for d in docs:
            if d.get("kind") == "AppProject" and d["metadata"]["name"] == "apps":
                d["spec"]["destinations"] = [{"server": "https://kubernetes.default.svc?", "namespace": "*"}]
        with Tree() as t:
            self.assertTrue(run(t.root, docs))

    def test_source_repo_not_permitted(self):
        docs = bootstrap_docs()
        for d in docs:
            if d.get("kind") == "AppProject" and d["metadata"]["name"] == "apps":
                d["spec"]["sourceRepos"] = ["https://example.invalid/other.git"]
        with Tree() as t:
            self.assertRed(run(t.root, docs), "is not permitted by AppProject")

    def test_rendered_foreign_namespace(self):
        def render(root, app):
            return [{"apiVersion": "v1", "kind": "ConfigMap",
                     "metadata": {"name": "x", "namespace": "argocd"}}]
        with Tree() as t:
            self.assertRed(run(t.root, bootstrap_docs(), render), "not the destination")

    def test_rendered_application(self):
        def render(root, app):
            return [{"apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
                     "metadata": {"name": "x", "namespace": app.namespace}}]
        with Tree() as t:
            self.assertRed(run(t.root, bootstrap_docs(), render), "may not render")

    def test_rendered_cluster_scoped_kind(self):
        def render(root, app):
            return [{"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRoleBinding",
                     "metadata": {"name": "x"}}]
        with Tree() as t:
            self.assertRed(run(t.root, bootstrap_docs(), render), "cluster-scoped")

    def test_rendered_kind_outside_whitelist(self):
        docs = bootstrap_docs()
        for d in docs:
            if d.get("kind") == "AppProject" and d["metadata"]["name"] == "apps":
                d["spec"]["namespaceResourceWhitelist"] = [{"group": "", "kind": "ConfigMap"}]
        with Tree() as t:
            self.assertRed(run(t.root, docs), "is not permitted by AppProject apps")

    def test_service_without_tenant_directory(self):
        with Tree() as t:
            (t.root / gas.SERVICES / "orphanteam" / "svc").mkdir(parents=True)
            (t.root / gas.SERVICES / "orphanteam" / "svc" / "values.yaml").write_text("{}\n")
            self.assertRed(run(t.root, bootstrap_docs()), "has no matching")

    def test_reserved_directory_name(self):
        with Tree() as t:
            for base in (gas.SERVICES, gas.TENANTS):
                (t.root / base / "vault-x").mkdir(parents=True)
            (t.root / gas.SERVICES / "vault-x" / "svc").mkdir()
            (t.root / gas.SERVICES / "vault-x" / "svc" / "values.yaml").write_text("{}\n")
            self.assertRed(run(t.root, bootstrap_docs()), "reserved tenant-name matcher")

    def test_reserved_copy_drift(self):
        with Tree() as t:
            f = t.root / gas.DELETE_TENANT
            text = f.read_text()
            f.write_text(text.replace("temporal|backstage|", "backstage|", 1))
            with self.assertRaises(gas.CheckError):
                run(t.root, bootstrap_docs())

    def test_handwritten_prefixed_project(self):
        docs = bootstrap_docs()
        docs.append({"apiVersion": "argoproj.io/v1alpha1", "kind": "AppProject",
                     "metadata": {"name": "tenant-x"}, "spec": {"sourceRepos": ["*"], "destinations": []}})
        with Tree() as t:
            self.assertRed(run(t.root, docs), "hand-written")

    def test_unresolved_template_is_an_error(self):
        docs = bootstrap_docs()
        for d in docs:
            if d.get("kind") == "ApplicationSet" and d["metadata"]["name"] == "apps":
                d["spec"]["template"]["spec"]["destination"]["namespace"] = "{{ .unknown }}"
        with Tree() as t:
            with self.assertRaises(gas.CheckError):
                run(t.root, docs)

    def test_empty_generator_match_is_an_error(self):
        docs = bootstrap_docs()
        for d in docs:
            if d.get("kind") == "ApplicationSet" and d["metadata"]["name"] == "apps":
                d["spec"]["generators"][0]["git"]["directories"][0]["path"] = "platform-gitops/services/*/*/none"
        with Tree() as t:
            with self.assertRaises(gas.CheckError):
                run(t.root, docs)

    def test_application_name_collision(self):
        docs = bootstrap_docs()
        docs.append({"apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
                     "metadata": {"name": "tenant-karabu"}, "spec": {}})
        with Tree() as t:
            self.assertRed(run(t.root, docs), "collides")

    def test_preserve_flag_flipped(self):
        docs = bootstrap_docs()
        for d in docs:
            if d.get("kind") == "ApplicationSet" and d["metadata"]["name"] == "apps":
                d["spec"]["syncPolicy"]["preserveResourcesOnDeletion"] = True
        with Tree() as t:
            self.assertRed(run(t.root, docs), "preserveResourcesOnDeletion")


class StrictGenerated(unittest.TestCase):
    def project(self, **over):
        spec_ = {"sourceRepos": ["https://github.com/mctlhq/mctl-gitops.git"],
                 "destinations": [{"server": "https://kubernetes.default.svc", "namespace": "karabu"}],
                 "clusterResourceWhitelist": [],
                 "namespaceResourceWhitelist": [{"group": "", "kind": "*"}]}
        spec_.update(over)
        return {"kind": "AppProject", "metadata": {"name": "tenant-karabu"}, "spec": spec_}

    def check(self, **over):
        projects = gas.project_specs([self.project(**over)])
        return gas.check_strict_generated(projects, [], "tenant-")

    def test_good_project_is_clean(self):
        self.assertEqual(self.check(), [])

    def test_mutations_are_red(self):
        srv = "https://kubernetes.default.svc"
        cases = {
            "second destination": {"destinations": [{"server": srv, "namespace": "karabu"},
                                                    {"server": srv, "namespace": "labs"}]},
            "wildcard namespace": {"destinations": [{"server": srv, "namespace": "*"}]},
            "wrong namespace": {"destinations": [{"server": srv, "namespace": "labs"}]},
            "second repo": {"sourceRepos": ["https://a.invalid/x", "https://b.invalid/y"]},
            "wildcard repo": {"sourceRepos": ["*"]},
            "cluster list non-empty": {"clusterResourceWhitelist": [{"group": "", "kind": "Namespace"}]},
            "cluster list absent": {"clusterResourceWhitelist": None},
            "namespaced list empty": {"namespaceResourceWhitelist": []},
        }
        for label, over in cases.items():
            p = self.project(**over)
            if over.get("clusterResourceWhitelist", 0) is None:
                del p["spec"]["clusterResourceWhitelist"]
            with self.subTest(label):
                self.assertTrue(gas.check_strict_generated(gas.project_specs([p]), [], "tenant-"))


class GeneratedNames(unittest.TestCase):
    """The strict checks must actually run for a project the generator makes."""

    NAME = "tenant-karabu"

    def docs(self, **over):
        docs = bootstrap_docs()
        proj = StrictGenerated.project(None, **over)
        proj["metadata"]["name"] = self.NAME
        return docs + [proj]

    def test_declared_generated_project_is_accepted(self):
        with Tree() as t:
            self.assertEqual(run_gen(t.root, self.docs(), {self.NAME}), [])

    def test_undeclared_prefixed_project_is_rejected(self):
        with Tree() as t:
            self.assertTrue(any("hand-written" in m for m in run_gen(t.root, self.docs(), set())))

    def test_declared_but_malformed_project_is_rejected(self):
        with Tree() as t:
            bad = self.docs(sourceRepos=["*"])
            out = run_gen(t.root, bad, {self.NAME})
            self.assertTrue(any("literal source repository" in m for m in out))
            self.assertFalse(any("hand-written" in m for m in out))

    def test_application_with_mismatched_namespace_is_rejected(self):
        app = gas.Generated(appset="apps", name="x-svc", labels={}, project=self.NAME, sources=[],
                            server="s", namespace="labs", path="p")
        projects = gas.project_specs([StrictGenerated.project(None)])
        out = gas.check_strict_generated(projects, [app], "tenant-")
        self.assertTrue(any("outside project" in m for m in out))
        app.namespace = "karabu"
        self.assertEqual(gas.check_strict_generated(projects, [app], "tenant-"), [])


def run_gen(root, docs, names):
    return gas.run_all(root, docs, "tenant-", render=stub_render, consumers=False, generated_names=names)


class ConsumerSweep(unittest.TestCase):
    def repo(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        return root

    def test_converged_then_mutated(self):
        root = self.repo({"a.yaml": "spec:\n  project: apps\n", "b.txt": "nothing here\n"})
        counts = gas.consumer_counts(root)
        self.assertEqual(counts, {"a.yaml": 1})
        self.assertEqual(gas.check_consumers(counts, {"a.yaml": 1}), [])
        # new consumer in an unlisted file
        (root / "c.sh").write_text('x=$a.spec.project != "apps"\n')
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        self.assertTrue(gas.check_consumers(gas.consumer_counts(root), {"a.yaml": 1}))
        # extra line in a listed file
        (root / "a.yaml").write_text("spec:\n  project: apps\n  other:\n    project: apps\n")
        self.assertTrue(gas.check_consumers({"a.yaml": 2}, {"a.yaml": 1}))
        # stale entry
        self.assertTrue(gas.check_consumers({}, {"a.yaml": 1}))

    def test_unreadable_listing_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(gas.CheckError):
                gas.consumer_counts(pathlib.Path(d))

    def test_real_allowlist_matches_tree(self):
        self.assertEqual(gas.check_consumers(gas.consumer_counts(REPO), gas.load_allowlist(REPO),
                                             gas.load_patterns(REPO)), [])

    def test_real_inventory_has_no_per_tenant_entries(self):
        self.assertFalse([f for f in gas.load_allowlist(REPO) if "/rbac/tenants/" in f])
        self.assertIn(FRAGMENT_GLOB, gas.load_patterns(REPO))


FRAGMENT_GLOB = "platform-gitops/argocd/rbac/tenants/*.csv"
FRAGMENT = "".join(f"p, role:team-{{t}}, applications, get, apps/{{t}}-*, allow\n" for _ in range(6))
HANDWRITTEN = "scripts/other.sh"


class TenantFragmentPattern(unittest.TestCase):
    """Per-tenant fragments are created and deleted by workflows without
    touching the inventory; the pattern must absorb that and nothing else."""

    ALLOW = {HANDWRITTEN: 1}
    PATS = {FRAGMENT_GLOB: 6}

    def tree(self, tenants, extra=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        files = {f"platform-gitops/argocd/rbac/tenants/{t}.csv": FRAGMENT.format(t=t) for t in tenants}
        files[HANDWRITTEN] = 'x=$a.spec.project != "apps"\n'
        files.update(extra or {})
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        return root

    def check(self, root):
        return gas.check_consumers(gas.consumer_counts(root), self.ALLOW, self.PATS)

    def test_converged(self):
        self.assertEqual(self.check(self.tree(["a", "b"])), [])

    def test_new_tenant_fragment_passes(self):
        self.assertEqual(self.check(self.tree(["a", "b", "c"])), [])

    def test_removed_tenant_fragment_passes(self):
        self.assertEqual(self.check(self.tree(["a"])), [])
        self.assertEqual(self.check(self.tree([])), [])

    def test_fragment_with_extra_consumer_fails(self):
        root = self.tree(["a"])
        f = root / "platform-gitops/argocd/rbac/tenants/a.csv"
        f.write_text(f.read_text() + "p, role:team-a, applications, update, apps/a-*, allow\n")
        self.assertTrue(self.check(root))

    def test_fragment_missing_a_line_fails(self):
        root = self.tree(["a"])
        f = root / "platform-gitops/argocd/rbac/tenants/a.csv"
        f.write_text("".join(f.read_text().splitlines(True)[:-1]))
        self.assertTrue(self.check(root))

    def test_handwritten_file_outside_pattern_fails(self):
        root = self.tree(["a"], {"platform-gitops/argocd/rbac/extra.csv": FRAGMENT.format(t="x"),
                                 "platform-gitops/argocd/rbac/tenants/sub/y.csv": FRAGMENT.format(t="y")})
        out = self.check(root)
        self.assertTrue(any("extra.csv" in m for m in out))
        self.assertTrue(any("sub/y.csv" in m for m in out), "a star must not cross a path separator")

    def test_name_and_pattern_overlap_is_rejected(self):
        root = self.tree(["a"])
        out = gas.check_consumers(gas.consumer_counts(root),
                                  {**self.ALLOW, "platform-gitops/argocd/rbac/tenants/a.csv": 6}, self.PATS)
        self.assertTrue(out)


class Cli(unittest.TestCase):
    SCRIPT = str(REPO / "scripts" / "validate-generated-app-scope.py")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", self.SCRIPT, *args], capture_output=True, text=True)

    def test_print_consumers_without_bootstrap(self):
        r = self.run_cli("--root", str(REPO), "--print-consumers")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["consumers"], gas.load_allowlist(REPO))
        self.assertEqual(data["patterns"], gas.load_patterns(REPO))

    def test_neither_flag_is_rejected(self):
        r = self.run_cli("--root", str(REPO))
        self.assertEqual(r.returncode, 2)
        self.assertIn("--bootstrap", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
