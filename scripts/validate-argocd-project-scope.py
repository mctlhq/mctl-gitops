#!/usr/bin/env python3
"""Check that every Argo CD Application stays inside its AppProject, and back.

An AppProject's `sourceRepos` and `destinations` are only a boundary if they
are exact. Too narrow, and Argo CD stops syncing the Application it was meant
to scope (ComparisonError: "... is not permitted in project ..."), which on
the `default` project means the whole platform tier, root-app included, stops
reconciling. Too wide, and the boundary means nothing. Both directions are
checked here, against `helm template` output rather than live state:

Forward (every use is permitted):
  - each Application's project is defined in the render;
  - each of its sources' repoURL matches the project's sourceRepos;
  - its destination (server, namespace) matches the project's destinations;
  - each namespaced resource a rendered chart owns names a namespace its
    owning Application's project permits (FILE:OWNER below; root-app owns the
    bootstrap render, argocd-self-managed owns the argocd render);
  - the same for ApplicationSet templates. A templated field (`{{ ... }}`)
    can resolve to anything, so it is only permitted by a `*` entry.

Reverse (every permission is used), for each literal entry:
  - each sourceRepos entry is matched by at least one source in that project;
  - each destination namespace is the destination of at least one
    Application, or holds at least one resource an owner in that project
    renders.
  Entries containing a wildcard (`*`) are exempt from the reverse check, so
  the projects named with --strict may not contain one anywhere: not in
  sourceRepos, not in a destination server, not in a destination namespace.

Matching follows Argo CD's: repository URLs are compared lowercased with a
trailing `.git` removed, as globs in which `*` does not cross `/` and `**`
does, and a bare `*` permits any repository; destination server and
namespace are plain globs. A trailing `/` is significant, as it is in Argo
CD's own normalization, so the pinned entries are written exactly as the
Applications spell them.

Something that cannot be read (no AppProject, a source with no repoURL) is an
error, exit 2, never a pass.

Usage:
  validate-argocd-project-scope.py [--selftest] [--strict PROJECT ...] FILE[:OWNER] ...
  validate-argocd-project-scope.py --live APPS.json [--strict PROJECT ...] FILE[:OWNER] ...

--live evaluates live Applications (`kubectl get applications -A -o json`)
against the AppProjects in the rendered FILEs, i.e. "would the projects in
this branch admit what is running today", and prints a table. It uses each
live Application's sources, destination and status.resources namespaces.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from dataclasses import dataclass, field

import yaml


class CheckError(Exception):
    """The inputs could not be read; distinct from a violation."""


# Cluster-scoped kinds that can appear without a namespace. Anything else
# without one defaults to its Application's destination namespace, exactly as
# Argo CD applies it, so it is checked as that namespace.
CLUSTER_SCOPED = {
    "APIService", "CSIDriver", "ClusterIssuer",
    "ClusterRole", "ClusterRoleBinding", "ClusterSecretStore",
    "ClusterExternalSecret", "ClusterWorkflowTemplate",
    "CustomResourceDefinition", "IngressClass", "MutatingWebhookConfiguration",
    "Namespace", "PersistentVolume", "PriorityClass", "RuntimeClass",
    "StorageClass", "ValidatingAdmissionPolicy",
    "ValidatingAdmissionPolicyBinding", "ValidatingWebhookConfiguration",
    "VolumeSnapshotClass", "ClusterImagePolicy", "ImageReview",
}

TEMPLATED = re.compile(r"\{\{.*\}\}")


def _glob_regex(pattern: str, separator: str | None) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append(f"[^{re.escape(separator)}]*" if separator else ".*")
        elif ch == "?":
            out.append(f"[^{re.escape(separator)}]" if separator else ".")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def normalize_repo(url: str) -> str:
    url = url.strip().lower()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    return url


def repo_matches(pattern: str, url: str) -> bool:
    if pattern.strip() in ("*", "**"):
        return True
    return bool(_glob_regex(normalize_repo(pattern), "/").match(normalize_repo(url)))


def plain_matches(pattern: str, value: str) -> bool:
    return bool(_glob_regex(pattern, None).match(value))


@dataclass
class Project:
    name: str
    source_repos: list[str]
    destinations: list[tuple[str, str]]  # (server, namespace)

    def repo_permitted(self, url: str) -> list[str]:
        """Return the entries matching `url`; a templated url needs `*`."""
        if TEMPLATED.search(url):
            return [p for p in self.source_repos if p == "*"]
        denied = any(p.startswith("!") and repo_matches(p[1:], url) for p in self.source_repos)
        if denied:
            return []
        return [p for p in self.source_repos if not p.startswith("!") and repo_matches(p, url)]

    def dest_permitted(self, server: str, namespace: str) -> list[tuple[str, str]]:
        out = []
        for s, n in self.destinations:
            if TEMPLATED.search(server) and s != "*":
                continue
            if TEMPLATED.search(namespace) and n != "*":
                continue
            if plain_matches(s, server) and plain_matches(n, namespace):
                out.append((s, n))
        return out


@dataclass
class App:
    name: str
    kind: str  # Application | ApplicationSet | live
    project: str
    sources: list[str]
    server: str
    namespace: str
    resource_namespaces: set[str] = field(default_factory=set)


def load(path: str) -> list[dict]:
    try:
        with open(path) as fh:
            return [d for d in yaml.safe_load_all(fh) if isinstance(d, dict)]
    except (OSError, yaml.YAMLError) as exc:
        raise CheckError(f"cannot read {path}: {exc}") from exc


def projects_of(docs: list[dict]) -> dict[str, Project]:
    out: dict[str, Project] = {}
    for d in docs:
        if d.get("kind") != "AppProject":
            continue
        spec = d.get("spec") or {}
        name = d["metadata"]["name"]
        dests = []
        for item in spec.get("destinations") or []:
            if "server" not in item:
                raise CheckError(f"AppProject {name}: destination without server: {item}")
            dests.append((item["server"], item.get("namespace", "")))
        out[name] = Project(name, list(spec.get("sourceRepos") or []), dests)
    if not out:
        raise CheckError("no AppProject in the rendered input")
    return out


def _sources(spec: dict, label: str) -> list[str]:
    srcs = ([spec["source"]] if spec.get("source") else []) + list(spec.get("sources") or [])
    if not srcs:
        raise CheckError(f"{label}: no source")
    urls = []
    for s in srcs:
        if not s.get("repoURL"):
            raise CheckError(f"{label}: source without repoURL: {s}")
        urls.append(str(s["repoURL"]))
    return urls


def apps_of(docs: list[dict]) -> list[App]:
    out = []
    for d in docs:
        kind = d.get("kind")
        if kind == "Application":
            spec = d.get("spec") or {}
            label = f"Application {d['metadata']['name']}"
        elif kind == "ApplicationSet":
            spec = ((d.get("spec") or {}).get("template") or {}).get("spec") or {}
            label = f"ApplicationSet {d['metadata']['name']}"
        else:
            continue
        dest = spec.get("destination") or {}
        if "server" not in dest:
            raise CheckError(f"{label}: destination has no server (name-only destinations are not supported here)")
        out.append(App(d["metadata"]["name"], kind, spec.get("project") or "default",
                       _sources(spec, label), str(dest["server"]), str(dest.get("namespace", ""))))
    return out


def owned_namespaces(docs: list[dict], default_ns: str) -> set[str]:
    out = set()
    for d in docs:
        kind = d.get("kind")
        if not kind or kind in CLUSTER_SCOPED:
            continue
        out.add((d.get("metadata") or {}).get("namespace") or default_ns)
    return out


def violations(projects: dict[str, Project], apps: list[App], strict: list[str]) -> list[str]:
    found: list[str] = []
    used_repo: dict[str, set[str]] = {p: set() for p in projects}
    used_ns: dict[str, set[tuple[str, str]]] = {p: set() for p in projects}

    for name in strict:
        proj = projects.get(name)
        if proj is None:
            found.append(f"strict project {name!r} is not defined in the render")
            continue
        if any("*" in p for p in proj.source_repos):
            found.append(f"AppProject {name}: sourceRepos must not contain a wildcard")
        if any("*" in s or "*" in n for s, n in proj.destinations):
            found.append(f"AppProject {name}: destinations must not contain a wildcard")

    for app in apps:
        label = f"{app.kind} {app.name}"
        proj = projects.get(app.project)
        if proj is None:
            found.append(f"{label}: project {app.project!r} is not defined in the render")
            continue
        for url in app.sources:
            hits = proj.repo_permitted(url)
            if not hits:
                found.append(f"{label}: source {url} is not permitted by AppProject {proj.name}")
            used_repo[proj.name].update(hits)
        for ns in sorted({app.namespace} | app.resource_namespaces):
            hits = proj.dest_permitted(app.server, ns)
            if not hits:
                what = "destination" if ns == app.namespace else "resource namespace"
                found.append(f"{label}: {what} {app.server} / {ns} is not permitted by AppProject {proj.name}")
            used_ns[proj.name].update(hits)

    for proj in projects.values():
        for entry in proj.source_repos:
            if entry.startswith("!") or "*" in entry:
                continue
            if entry not in used_repo[proj.name]:
                found.append(f"AppProject {proj.name}: sourceRepos entry {entry} is used by no Application")
        for dest in proj.destinations:
            if "*" in dest[0] or "*" in dest[1]:
                continue
            if dest not in used_ns[proj.name]:
                found.append(f"AppProject {proj.name}: destination {dest[0]} / {dest[1]} is used by no Application")
    return found


def parse_inputs(args: list[str]) -> tuple[dict[str, Project], list[App], dict[str, list[dict]]]:
    if not args:
        raise CheckError("no rendered input given")
    all_docs: list[dict] = []
    owned: dict[str, list[dict]] = {}
    for arg in args:
        path, _, owner = arg.partition(":")
        docs = load(path)
        if not docs:
            raise CheckError(f"{path}: empty render")
        all_docs.extend(docs)
        if owner:
            owned.setdefault(owner, []).extend(docs)
    projects = projects_of(all_docs)
    apps = apps_of(all_docs)
    attach_owned(apps, owned)
    return projects, apps, owned


def attach_owned(apps: list[App], owned: dict[str, list[dict]]) -> None:
    by_name = {a.name: a for a in apps if a.kind == "Application"}
    for owner, docs in owned.items():
        app = by_name.get(owner)
        if app is None:
            raise CheckError(f"owner Application {owner!r} is not in the render")
        app.resource_namespaces = owned_namespaces(docs, app.namespace)


def selftest(projects: dict[str, Project], apps: list[App], strict: list[str]) -> None:
    assert violations(projects, apps, strict) == [], "selftest: the real render must be clean"
    target = next(a for a in apps if a.kind == "Application" and (not strict or a.project in strict))
    proj_name = target.project

    def fires(mutate, what: str) -> None:
        p2, a2 = copy.deepcopy(projects), copy.deepcopy(apps)
        mutate(p2, a2)
        assert violations(p2, a2, strict), f"selftest: {what} must fire"

    def by_name(a2):
        return next(a for a in a2 if a.name == target.name and a.kind == target.kind)

    fires(lambda p, a: by_name(a).sources.append("https://example.invalid/unlisted.git"),
          "an unlisted source repository")
    fires(lambda p, a: setattr(by_name(a), "namespace", "selftest-unlisted"),
          "an unlisted destination namespace")
    fires(lambda p, a: by_name(a).resource_namespaces.add("selftest-unlisted"),
          "a rendered resource in an unlisted namespace")
    fires(lambda p, a: setattr(by_name(a), "server", "https://selftest.invalid"),
          "an unlisted destination server")
    fires(lambda p, a: setattr(by_name(a), "project", "selftest-missing"),
          "an undefined project")
    fires(lambda p, a: p[proj_name].source_repos.append("https://example.invalid/unused"),
          "an unused sourceRepos entry")
    fires(lambda p, a: p[proj_name].destinations.append((target.server, "selftest-unused")),
          "an unused destination namespace")
    fires(lambda p, a: p[proj_name].source_repos.remove(
              next(e for e in p[proj_name].source_repos if repo_matches(e, target.sources[0]))),
          "removing an entry an Application uses")
    if strict:
        fires(lambda p, a: p[strict[0]].source_repos.append("*"), "a bare wildcard in a strict project")
        fires(lambda p, a: p[strict[0]].source_repos.append("https://github.com/**"),
              "a glob sourceRepos entry in a strict project")
        fires(lambda p, a: p[strict[0]].destinations.append((target.server, "*")),
              "a namespace wildcard in a strict project")
        fires(lambda p, a: p[strict[0]].destinations.append(("*", target.namespace)),
              "a server wildcard in a strict project")
    # Matching semantics: `.git` and case are normalized, `*` does not cross `/`.
    assert repo_matches("https://github.com/mctlhq/mctl-gitops.git", "https://GitHub.com/mctlhq/mctl-gitops")
    assert not repo_matches("https://github.com/mctlhq/*", "https://github.com/mctlhq/a/b")
    assert repo_matches("https://github.com/mctlhq/**", "https://github.com/mctlhq/a/b")
    assert repo_matches("*", "https://github.com/mctlhq/a/b")
    assert Project("p", ["*"], []).repo_permitted("https://example.invalid/x/y")
    assert not repo_matches("https://github.com/mctlhq/mctl-gitops.git", "https://github.com/mctlhq/mctl-gitops-fork.git")
    print("selftest OK: clean render passes; unlisted source, namespace, resource namespace, server, "
          "undefined project, unused entries, a removed entry and a wildcard all fire")


def live(apps_json: str, projects: dict[str, Project]) -> int:
    try:
        with open(apps_json) as fh:
            items = json.load(fh)["items"]
    except (OSError, ValueError, KeyError) as exc:
        raise CheckError(f"cannot read {apps_json}: {exc}") from exc
    if not items:
        raise CheckError(f"{apps_json}: no Applications")
    rows, bad = [], 0
    for it in items:
        spec = it.get("spec") or {}
        name = it["metadata"]["name"]
        dest = spec.get("destination") or {}
        project = spec.get("project") or "default"
        sources = _sources(spec, f"live Application {name}")
        res_ns = {r["namespace"] for r in (it.get("status") or {}).get("resources") or [] if r.get("namespace")}
        proj = projects.get(project)
        if "server" not in dest:
            # Same stance as the render path: not evaluated, so not a verdict.
            rows.append((name, project, "; ".join(sources), dest.get("namespace", ""), "-",
                         "UNKNOWN (name-only destination)"))
            bad += 1
            continue
        if proj is None:
            # Projects this branch does not render (none today) are reported, not guessed.
            rows.append((name, project, "; ".join(sources), dest.get("namespace", ""), "-", "UNKNOWN (project not rendered)"))
            bad += 1
            continue
        src_bad = [u for u in sources if not proj.repo_permitted(u)]
        ns_bad = [n for n in sorted({dest.get("namespace", "")} | res_ns)
                  if not proj.dest_permitted(dest.get("server", ""), n)]
        verdict = "PERMITTED" if not (src_bad or ns_bad) else "DENIED " + ", ".join(src_bad + ns_bad)
        bad += bool(src_bad or ns_bad)
        rows.append((name, project, "; ".join(sorted(set(sources))), dest.get("namespace", ""),
                     ",".join(sorted(res_ns - {dest.get("namespace", "")})) or "-", verdict))
    print("| Application | Project | Sources | Destination ns | Other resource ns | Verdict |")
    print("|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (r[1], r[0])):
        print("| " + " | ".join(r) + " |")
    print(f"\n{len(rows) - bad}/{len(rows)} live Applications permitted by the rendered projects")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    args = list(argv)
    strict: list[str] = []
    live_json = None
    do_selftest = False
    rest = []
    while args:
        a = args.pop(0)
        if a == "--selftest":
            do_selftest = True
        elif a == "--strict":
            if not args:
                print(__doc__, file=sys.stderr)
                return 2
            strict.append(args.pop(0))
        elif a == "--live":
            if not args:
                print(__doc__, file=sys.stderr)
                return 2
            live_json = args.pop(0)
        else:
            rest.append(a)
    try:
        projects, apps, _ = parse_inputs(rest)
        if do_selftest:
            selftest(projects, apps, strict)
        found = violations(projects, apps, strict)
        if live_json and not found:
            # The live table is only meaningful for projects that pass the
            # render checks (strict included), so those run first.
            return live(live_json, projects)
    except CheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if found:
        for item in found:
            print(f"::error::{item}", file=sys.stderr)
        return 1
    print(f"OK: {len(apps)} Applications/ApplicationSets are inside their projects "
          f"({', '.join(sorted(projects))}) and every literal project entry is in use")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
