#!/usr/bin/env python3
"""Validate project scope for generated applications.

The `apps` and `tenants` ApplicationSets generate one Application per
directory under platform-gitops/services/*/* and platform-gitops/tenants/*.
scripts/validate-argocd-project-scope.py checks Applications as rendered by
Helm, where a generated Application's project, namespace and name are still
templates. This script expands those templates over the real directories and
checks the result, offline:

  1. expansion: both ApplicationSet shapes are expanded over the real paths.
     A generator or template field that cannot be resolved is an error, never
     an empty expansion; zero matched directories is an error.
  2. scope: every expanded Application's project exists, permits its source
     repositories, and permits its destination (server string compared
     literally, namespace by glob).
  3. rendered objects: the base-service chart is rendered for every service
     directory with the Application's release name and namespace, and every
     object is checked against the resolved project: kind and group against
     the project's namespaced/cluster lists, namespace against the project's
     destinations and against the Application's own namespace, and no
     Application / ApplicationSet / AppProject may be rendered at all.
  4. generated projects (--strict-generated PREFIX): any AppProject whose name
     starts with PREFIX must have exactly one repository, exactly one literal
     destination whose namespace is the name after the prefix, no wildcard, and
     an empty cluster-scoped list; a hand-written AppProject with that prefix
     in the bootstrap render is rejected. Names the generator is known to
     produce are passed with --generated-project; the default is none.
  5. directory names: every services/<team> has a tenants/<team>, no team or
     tenant directory name matches the reserved tenant-name matcher, and the
     matcher is identical in all four shell copies in the workflow templates.
  6. application names: expanded names are unique across ApplicationSets and
     do not collide with a hand-written Application.
  7. consumer inventory: every place that spells the literal project name
     `apps` (project comparisons, project fields, RBAC object prefixes) is
     listed in an allowlist with its line count; an unlisted or changed
     consumer fails, so a rename of the project cannot miss one. Files that
     the platform workflows create or delete at runtime (per-tenant RBAC
     fragments) are matched by a path pattern with a fixed per-file line
     count instead of being listed by name, so adding or removing one never
     changes the inventory, while a fragment whose count differs, or a file
     outside every pattern, still fails.
  8. `apps` ApplicationSet keeps preserveResourcesOnDeletion: false.

Something that cannot be read is an error (exit 2), never a pass.

Usage:
  validate-generated-app-scope.py [--root DIR] [--strict-generated PREFIX]
      [--generated-project NAME ...] --bootstrap RENDER.yaml
  validate-generated-app-scope.py [--root DIR] --print-consumers
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import fnmatch
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass, field

import yaml

_HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("project_scope", _HERE / "validate-argocd-project-scope.py")
scope = importlib.util.module_from_spec(_spec)
sys.modules["project_scope"] = scope
_spec.loader.exec_module(scope)  # type: ignore[union-attr]

CheckError = scope.CheckError

SERVICES = "platform-gitops/services"
TENANTS = "platform-gitops/tenants"
CHART = "platform-gitops/helm-charts/base-service"
CREATE_TENANT = "platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml"
DELETE_TENANT = "platform-gitops/argo-workflows/cluster-templates/wft-delete-tenant-safe.yaml"
ALLOWLIST = "scripts/app-project-consumers.json"

# Kinds that may never be rendered by a service chart, whatever the project.
FORBIDDEN_RENDERED = {"Application", "ApplicationSet", "AppProject"}

# Group is the apiVersion prefix; core resources have none.
def group_of(doc: dict) -> str:
    api = str(doc.get("apiVersion", ""))
    return api.split("/")[0] if "/" in api else ""


# ---------------------------------------------------------------- expansion

@dataclass
class Generated:
    appset: str
    name: str
    labels: dict
    project: str
    sources: list[str]
    server: str
    namespace: str
    path: str
    team: str = ""
    service: str = ""
    docs: list[dict] = field(default_factory=list)


_SEGMENT = re.compile(r"\{\{\s*index \.path\.segments (\d+)\s*\}\}")
_BASENAME = re.compile(r"\{\{\s*\.path\.basename\s*\}\}")
_PATH = re.compile(r"\{\{\s*\.path\.path\s*\}\}")


def substitute(value, path: str):
    """Resolve the three go-template forms the ApplicationSets use."""
    if isinstance(value, dict):
        return {k: substitute(v, path) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, path) for v in value]
    if not isinstance(value, str):
        return value
    segs = path.split("/")

    def seg(m: re.Match) -> str:
        i = int(m.group(1))
        if i >= len(segs):
            raise CheckError(f"template index {i} is outside path {path}")
        return segs[i]

    out = _SEGMENT.sub(seg, value)
    out = _BASENAME.sub(segs[-1], out)
    out = _PATH.sub(path, out)
    if "{{" in out:
        raise CheckError(f"template expression left unresolved after expansion: {out!r}")
    return out


def directories(root: pathlib.Path, appset: dict) -> list[str]:
    name = appset["metadata"]["name"]
    gens = (appset.get("spec") or {}).get("generators") or []
    if not gens:
        raise CheckError(f"ApplicationSet {name}: no generators")
    include: set[str] = set()
    exclude: set[str] = set()
    for g in gens:
        git = g.get("git")
        if git is None or "directories" not in git:
            raise CheckError(f"ApplicationSet {name}: only git directory generators are supported")
        for d in git["directories"]:
            pat = d["path"]
            if pat.startswith("/") or ".." in pat.split("/"):
                raise CheckError(f"ApplicationSet {name}: unsupported generator path {pat!r}")
            hits = {str(p.relative_to(root)) for p in root.glob(pat) if p.is_dir()}
            (exclude if d.get("exclude") else include).update(hits)
    found = sorted(include - exclude)
    if not found:
        raise CheckError(f"ApplicationSet {name}: generators matched no directory under {root}")
    return found


def expand(root: pathlib.Path, appset: dict) -> list[Generated]:
    name = appset["metadata"]["name"]
    tpl = (appset.get("spec") or {}).get("template") or {}
    out = []
    for path in directories(root, appset):
        meta = substitute(tpl.get("metadata") or {}, path)
        spec = substitute(tpl.get("spec") or {}, path)
        if not meta.get("name"):
            raise CheckError(f"ApplicationSet {name}: template has no name")
        dest = spec.get("destination") or {}
        if "server" not in dest or not dest.get("namespace"):
            raise CheckError(f"{name}/{path}: destination needs a server and a namespace")
        out.append(Generated(
            appset=name, name=meta["name"], labels=meta.get("labels") or {},
            project=spec.get("project") or "default",
            sources=scope._sources(spec, f"{name}/{path}"),
            server=str(dest["server"]), namespace=str(dest["namespace"]), path=path,
            team=path.split("/")[2] if path.startswith(SERVICES + "/") else "",
            service=path.split("/")[3] if path.startswith(SERVICES + "/") else ""))
    return out


# ------------------------------------------------------------------ projects

@dataclass
class ProjectSpec:
    name: str
    base: object
    ns_white: list[tuple[str, str]] | None
    ns_black: list[tuple[str, str]]
    cluster_white: list[tuple[str, str]] | None


def _gk(items) -> list[tuple[str, str]]:
    return [(str(i.get("group", "")), str(i.get("kind", ""))) for i in items or []]


def project_specs(docs: list[dict]) -> dict[str, ProjectSpec]:
    base = scope.projects_of(docs)
    out = {}
    for d in docs:
        if d.get("kind") != "AppProject":
            continue
        spec = d.get("spec") or {}
        name = d["metadata"]["name"]
        out[name] = ProjectSpec(
            name, base[name],
            _gk(spec["namespaceResourceWhitelist"]) if "namespaceResourceWhitelist" in spec else None,
            _gk(spec.get("namespaceResourceBlacklist")),
            _gk(spec["clusterResourceWhitelist"]) if "clusterResourceWhitelist" in spec else None)
    return out


def gk_match(entries: list[tuple[str, str]], group: str, kind: str) -> bool:
    return any(fnmatch.fnmatchcase(group, g) and fnmatch.fnmatchcase(kind, k) for g, k in entries)


# -------------------------------------------------------------------- checks

def check_scope(projects: dict[str, ProjectSpec], apps: list[Generated]) -> list[str]:
    found = []
    for a in apps:
        label = f"{a.appset}/{a.name}"
        p = projects.get(a.project)
        if p is None:
            found.append(f"{label}: project {a.project!r} is not defined in the render")
            continue
        for url in a.sources:
            if not p.base.repo_permitted(url):
                found.append(f"{label}: source {url} is not permitted by AppProject {p.name}")
        hits = p.base.dest_permitted(a.server, a.namespace)
        if not hits:
            found.append(f"{label}: destination {a.server} / {a.namespace} is not permitted by AppProject {p.name}")
        elif not any(s in ("*", a.server) for s, _ in hits):
            found.append(f"{label}: server string {a.server!r} differs from the one written in AppProject {p.name}")
    return found


def check_rendered(project: ProjectSpec, app: Generated, docs: list[dict]) -> list[str]:
    found = []
    label = f"{app.appset}/{app.name}"
    for d in docs:
        kind = d.get("kind")
        if not kind:
            continue
        who = f"{label}: rendered {kind}/{(d.get('metadata') or {}).get('name', '?')}"
        group = group_of(d)
        if kind in FORBIDDEN_RENDERED:
            found.append(f"{who} is a kind a service chart may not render")
            continue
        ns = (d.get("metadata") or {}).get("namespace")
        if kind in scope.CLUSTER_SCOPED:
            if project.cluster_white is None or not gk_match(project.cluster_white, group, kind):
                found.append(f"{who} is cluster-scoped and not permitted by AppProject {project.name}")
            continue
        if project.ns_white is None or not gk_match(project.ns_white, group, kind) \
                or gk_match(project.ns_black, group, kind):
            found.append(f"{who} ({group or 'core'}/{kind}) is not permitted by AppProject {project.name}")
        eff = ns or app.namespace
        if eff != app.namespace:
            found.append(f"{who} names namespace {eff!r}, not the destination {app.namespace!r}")
        if not project.base.dest_permitted(app.server, eff):
            found.append(f"{who} namespace {eff!r} is not permitted by AppProject {project.name}")
    return found


def check_strict_generated(projects: dict[str, ProjectSpec], apps: list[Generated], prefix: str) -> list[str]:
    found = []
    for name, p in projects.items():
        if not name.startswith(prefix):
            continue
        b = p.base
        if len(b.source_repos) != 1 or "*" in b.source_repos[0]:
            found.append(f"AppProject {name}: needs exactly one literal source repository")
        if len(b.destinations) != 1:
            found.append(f"AppProject {name}: needs exactly one destination")
        else:
            server, ns = b.destinations[0]
            if "*" in server or "*" in ns or "?" in ns:
                found.append(f"AppProject {name}: destination must not contain a wildcard")
            if ns != name[len(prefix):]:
                found.append(f"AppProject {name}: destination namespace {ns!r} must be {name[len(prefix):]!r}")
        if p.cluster_white != []:
            found.append(f"AppProject {name}: clusterResourceWhitelist must be present and empty")
        if p.ns_white is None or not p.ns_white:
            found.append(f"AppProject {name}: namespaceResourceWhitelist must be present and non-empty")
        for a in apps:
            if a.project == name and a.namespace != name[len(prefix):]:
                found.append(f"{a.appset}/{a.name}: namespace {a.namespace!r} is outside project {name}")
    return found


def check_handwritten_prefix(docs: list[dict], prefix: str, generator_names: set[str]) -> list[str]:
    return [f"AppProject {d['metadata']['name']} in the bootstrap render is hand-written; names starting with "
            f"{prefix!r} are reserved for generated projects"
            for d in docs if d.get("kind") == "AppProject" and d["metadata"]["name"].startswith(prefix)
            and d["metadata"]["name"] not in generator_names]


_CASE = re.compile(r"tenant_name_reserved\(\) \{\s*case \"\$1\" in(.*?)\n\s*esac", re.S)


def reserved_patterns(text: str) -> list[list[str]]:
    """Return the pattern list of every tenant_name_reserved copy in `text`."""
    copies = []
    for m in _CASE.finditer(text):
        body = m.group(1).replace("\\\n", " ")
        pats = []
        for arm in re.split(r"\)\s*return 0 ;;", body):
            arm = arm.strip()
            if arm:
                pats.extend(p for p in arm.split("|") if p.strip())
        copies.append(sorted(p.strip() for p in pats))
    return copies


def load_reserved(root: pathlib.Path) -> list[str]:
    copies: list[list[str]] = []
    for rel in (CREATE_TENANT, DELETE_TENANT):
        try:
            text = (root / rel).read_text()
        except OSError as exc:
            raise CheckError(f"cannot read {rel}: {exc}") from exc
        found = reserved_patterns(text)
        if len(found) != 2:
            raise CheckError(f"{rel}: expected 2 tenant_name_reserved copies, found {len(found)}")
        copies.extend(found)
    if any(not c for c in copies):
        raise CheckError("a tenant_name_reserved copy has no patterns")
    if any(c != copies[0] for c in copies[1:]):
        raise CheckError("tenant_name_reserved copies differ between the four shell copies")
    return copies[0]


def check_directories(root: pathlib.Path, reserved: list[str]) -> list[str]:
    def names(rel: str) -> list[str]:
        d = root / rel
        if not d.is_dir():
            raise CheckError(f"cannot read directory {rel}")
        return sorted(p.name for p in d.iterdir() if p.is_dir())

    teams, tenants = names(SERVICES), names(TENANTS)
    found = []
    for t in teams:
        if t not in tenants:
            found.append(f"{SERVICES}/{t} has no matching {TENANTS}/{t}")
    for kind, group in (("services", teams), ("tenants", tenants)):
        for n in group:
            if any(fnmatch.fnmatchcase(n, p) for p in reserved):
                found.append(f"{kind}/{n}: directory name matches the reserved tenant-name matcher")
    return found


def check_unique_names(apps: list[Generated], docs: list[dict]) -> list[str]:
    seen: dict[str, str] = {}
    found = []
    for d in docs:
        if d.get("kind") == "Application":
            seen[d["metadata"]["name"]] = "hand-written Application"
    for a in apps:
        if a.name in seen:
            found.append(f"Application name {a.name!r} from {a.appset}/{a.path} collides with {seen[a.name]}")
        seen[a.name] = f"{a.appset}/{a.path}"
    return found


def check_preserve_flag(docs: list[dict]) -> list[str]:
    for d in docs:
        if d.get("kind") == "ApplicationSet" and d["metadata"]["name"] == "apps":
            flag = ((d.get("spec") or {}).get("syncPolicy") or {}).get("preserveResourcesOnDeletion")
            return [] if flag is False else [f"ApplicationSet apps: preserveResourcesOnDeletion must be false, got {flag!r}"]
    raise CheckError("ApplicationSet apps is not in the render")


# Spellings of the literal project name `apps`. Each is one line-level regex.
CONSUMER_PATTERNS = [
    re.compile(r"""project\s*(==|!=)\s*\\?["']apps\\?["']"""),
    re.compile(r"""^\s*project:\s*["']?apps["']?\s*$"""),
    re.compile(r"""["']project["']\s*:\s*["']apps["']"""),
    re.compile(r"""(in|outside|foreign|and still in) project\s+\\?"?apps\b"""),
    re.compile(r"""project\s+\(?"apps"|project "apps"|project apps\b"""),
    re.compile(r"""/spec/project.*apps"""),
    re.compile(r"""(^|,|\s)apps/(\$\{[A-Z_]+\}|<[a-z]+>|[a-z0-9-]+)-\*"""),
]
CONSUMER_SKIP = ("platform-gitops/agents-state/", ALLOWLIST, "scripts/validate-generated-app-scope.py",
                 "tests/test_generated_app_scope.py", "docs/")


def consumer_counts(root: pathlib.Path) -> dict[str, int]:
    try:
        files = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True,
                               capture_output=True).stdout.decode().split("\0")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CheckError(f"cannot list tracked files under {root}: {exc}") from exc
    counts: dict[str, int] = {}
    for rel in filter(None, files):
        if rel.endswith(".md") or any(rel.startswith(s) or rel == s for s in CONSUMER_SKIP):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise CheckError(f"cannot read {rel}: {exc}") from exc
        n = sum(1 for line in text.splitlines() if any(p.search(line) for p in CONSUMER_PATTERNS))
        if n:
            counts[rel] = n
    return counts


def _glob_re(pattern: str) -> re.Pattern:
    """Path glob where `*` matches within one path segment only."""
    return re.compile("".join("[^/]*" if c == "*" else re.escape(c) for c in pattern) + r"\Z")


def check_consumers(counts: dict[str, int], allow: dict[str, int],
                    patterns: dict[str, int] | None = None) -> list[str]:
    found = []
    pats = [(p, _glob_re(p), n) for p, n in sorted((patterns or {}).items())]
    for f in sorted(allow):
        for p, rx, _ in pats:
            if rx.match(f):
                found.append(f"{f}: listed by name in {ALLOWLIST} but also covered by pattern {p}")
    for f, n in sorted(counts.items()):
        hit = next(((p, want) for p, rx, want in pats if rx.match(f)), None)
        if hit is not None:
            if n != hit[1] and f not in allow:
                found.append(f"{f}: {n} line(s) spell the project name `apps`, pattern {hit[0]} requires {hit[1]}")
            continue
        if f not in allow:
            found.append(f"{f}: {n} line(s) spell the project name `apps` and the file is not in {ALLOWLIST}")
        elif allow[f] != n:
            found.append(f"{f}: {n} line(s) spell the project name `apps`, allowlist has {allow[f]}")
    for f in sorted(set(allow) - set(counts)):
        found.append(f"{f}: listed in {ALLOWLIST} but no longer spells the project name `apps`")
    return found


def _load_inventory(root: pathlib.Path) -> dict:
    try:
        data = json.loads((root / ALLOWLIST).read_text(encoding="utf-8"))
        return {"consumers": {str(k): int(v) for k, v in data["consumers"].items()},
                "patterns": {str(k): int(v) for k, v in (data.get("patterns") or {}).items()}}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CheckError(f"cannot read {ALLOWLIST}: {exc}") from exc


def load_allowlist(root: pathlib.Path) -> dict[str, int]:
    return _load_inventory(root)["consumers"]


def load_patterns(root: pathlib.Path) -> dict[str, int]:
    return _load_inventory(root)["patterns"]


# ----------------------------------------------------------------- rendering

def helm_render(root: pathlib.Path, app: Generated) -> list[dict]:
    values = root / app.path / "values.yaml"
    if not values.is_file():
        raise CheckError(f"{app.path}: no values.yaml")
    cmd = ["helm", "template", app.name, str(root / CHART), "--namespace", app.namespace, "-f", str(values)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return [d for d in yaml.safe_load_all(res.stdout) if isinstance(d, dict)]
    except (OSError, subprocess.CalledProcessError, yaml.YAMLError) as exc:
        detail = getattr(exc, "stderr", "") or exc
        raise CheckError(f"cannot render {app.path}: {detail}") from exc


def run_all(root: pathlib.Path, docs: list[dict], strict_prefix: str, render=helm_render,
            allow: dict[str, int] | None = None, consumers: bool = True,
            generated_names: set[str] | None = None,
            patterns: dict[str, int] | None = None) -> list[str]:
    projects = project_specs(docs)
    appsets = {d["metadata"]["name"]: d for d in docs if d.get("kind") == "ApplicationSet"}
    apps: list[Generated] = []
    for n in ("apps", "tenants"):
        if n not in appsets:
            raise CheckError(f"ApplicationSet {n} is not in the render")
        apps.extend(expand(root, appsets[n]))
    found = check_scope(projects, apps)
    found += check_handwritten_prefix(docs, strict_prefix, set(generated_names or ()))
    found += check_strict_generated(projects, apps, strict_prefix)
    found += check_unique_names(apps, docs)
    found += check_preserve_flag(docs)
    found += check_directories(root, load_reserved(root))
    services = [a for a in apps if a.appset == "apps"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rendered = list(pool.map(lambda a: render(root, a), services))
    for a, r in zip(services, rendered):
        if not r:
            raise CheckError(f"{a.path}: render produced no objects")
        a.docs = r
        if a.project in projects:
            found += check_rendered(projects[a.project], a, r)
    if consumers:
        inv = _load_inventory(root) if allow is None else {"consumers": allow, "patterns": patterns or {}}
        found += check_consumers(consumer_counts(root), inv["consumers"], inv["patterns"])
    return found


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--bootstrap", help="helm template output of platform-gitops/bootstrap (required unless "
                    "--print-consumers)")
    ap.add_argument("--generated-project", action="append", default=[], metavar="NAME",
                    help="AppProject name the generator produces (repeatable)")
    ap.add_argument("--strict-generated", default="tenant-", metavar="PREFIX")
    ap.add_argument("--print-consumers", action="store_true", help="print the current consumer counts as JSON")
    args = ap.parse_args(argv)
    if not args.print_consumers and not args.bootstrap:
        ap.error("the following arguments are required: --bootstrap")
    root = pathlib.Path(args.root).resolve()
    try:
        if args.print_consumers:
            counts = consumer_counts(root)
            pats = load_patterns(root)
            rxs = [_glob_re(p) for p in pats]
            exact = {f: n for f, n in counts.items() if not any(r.match(f) for r in rxs)}
            print(json.dumps({"consumers": exact, "patterns": pats}, indent=2, sort_keys=True))
            return 0
        docs = scope.load(args.bootstrap)
        if not docs:
            raise CheckError(f"{args.bootstrap}: empty render")
        found = run_all(root, docs, args.strict_generated, generated_names=set(args.generated_project))
    except CheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if found:
        for f in found:
            print(f"::error::{f}", file=sys.stderr)
        return 1
    print("OK: generated applications are inside their projects, directory names and the project-name "
          "consumer inventory are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
