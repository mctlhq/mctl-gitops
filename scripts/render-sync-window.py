#!/usr/bin/env python3
"""Render-only sync-window proposal: patch plus lock-out / match report.

Step 2 of the release-window write path (proposal issue-2828, sections 3.2 and
8.2). It WRITES NOTHING: it takes one requested deny window, builds the
Application inventory from the rendered bootstrap and argocd charts (plus the
`apps` and `tenants` ApplicationSet generators expanded over the working
tree), and prints a JSON report:

  verdict        "ok" | "refuse"
  problems       rule violations, from validate-argocd-sync-windows.py
  window         the AppProject syncWindows entry that would be added
  patch          that entry as YAML, to paste under the project's spec
  matched        Applications the window matches in its target project
                 (Argo semantics: only that project's Applications are
                 evaluated; glob over applications, namespaces, clusters;
                 OR across selectors)
  unknown_apps   requested names that exist in no project (refused)
  recovery_chain_hit   matched Applications in the recovery chain (refused)
  would_hit_if_in_default   what the same window would match if it were put
                 in `default`, to show the blast radius that rule prevents

An inventory that cannot be built (a required ApplicationSet missing from the
render, an unreadable file) is exit 2, never a shorter inventory.

Usage:
  render-sync-window.py --repo-root DIR --project P --application A [--application A ...]
      --schedule "0 22 * * 5" --duration 48h [--namespace N ...] BOOTSTRAP.yaml ARGOCD.yaml
  render-sync-window.py --selftest
Exit: 0 ok, 1 refuse, 2 unreadable input or selftest failure.
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import importlib.util
import json
import os
import re
import sys

import yaml

RECOVERY_CHAIN = {"root-app", "argocd-self-managed"}
HERE = os.path.dirname(os.path.abspath(__file__))


def _validator():
    spec = importlib.util.spec_from_file_location("vsw", os.path.join(HERE, "validate-argocd-sync-windows.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Unreadable(Exception):
    pass


def load_docs(paths: list[str]) -> list[dict]:
    docs: list[dict] = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                docs.extend(d for d in yaml.safe_load_all(fh) if isinstance(d, dict))
        except (OSError, yaml.YAMLError) as e:
            raise Unreadable(f"{p}: {e}") from e
    return docs


_SEGMENT = re.compile(r"\{\{\s*index \.path\.segments (\d+)\s*\}\}")
_BASENAME = re.compile(r"\{\{\s*\.path\.basename\s*\}\}")


def _expand(value: str, path: str) -> str:
    """Resolve the go-template forms the ApplicationSets use; anything else is unreadable."""
    segs = path.split(os.sep)

    def seg(m: re.Match) -> str:
        i = int(m.group(1))
        if i >= len(segs):
            raise Unreadable(f"template index {i} is outside path {path}")
        return segs[i]

    out = _BASENAME.sub(segs[-1], _SEGMENT.sub(seg, value))
    if "{{" in out:
        raise Unreadable(f"template expression left unresolved: {out!r}")
    return out


def inventory(docs: list[dict], repo_root: str) -> list[dict]:
    """Applications: static ones from the renders plus the two generators."""
    apps: list[dict] = []
    sets: dict[str, dict] = {}
    for d in docs:
        name = (d.get("metadata") or {}).get("name")
        if d.get("kind") == "Application":
            sp = d.get("spec") or {}
            dest = sp.get("destination") or {}
            if not name or not sp.get("project"):
                raise Unreadable(f"Application without name or project: {name!r}")
            apps.append({"name": name, "project": sp["project"],
                         "namespace": dest.get("namespace", ""), "server": dest.get("server", ""),
                         "dest_name": dest.get("name", "")})
        elif d.get("kind") == "ApplicationSet" and name:
            sets[name] = d
    server = next((a["server"] for a in apps if a["server"]), "")
    for need, project in (("apps", "apps"), ("tenants", "platform")):
        st = sets.get(need)
        if st is None:
            raise Unreadable(f"ApplicationSet {need!r} not found in the render")
        spec = st.get("spec") or {}
        tmpl = (spec.get("template") or {})
        tp = tmpl.get("spec") or {}
        if tp.get("project") != project:
            raise Unreadable(f"ApplicationSet {need!r} project is {tp.get('project')!r}, expected {project!r}")
        name_t = (tmpl.get("metadata") or {}).get("name")
        ns_t = (tp.get("destination") or {}).get("namespace")
        srv_t = (tp.get("destination") or {}).get("server", server)
        patterns = [(g.get("git") or {}).get("directories") or [] for g in spec.get("generators") or []]
        # `exclude: true` removes matches from the set; honouring it is not implemented,
        # so reading it as an include would widen the inventory. Unreadable, not shorter/wider.
        if any(isinstance(d, dict) and d.get("exclude") for ds in patterns for d in ds):
            raise Unreadable(f"ApplicationSet {need!r}: directory generator with exclude is not supported")
        dirs = [d.get("path") for ds in patterns for d in ds if isinstance(d, dict)]
        if not name_t or not ns_t or not dirs or not all(isinstance(d, str) for d in dirs):
            raise Unreadable(f"ApplicationSet {need!r}: name, namespace or directory generator not readable")
        for pat in dirs:
            found = sorted(g for g in glob.glob(os.path.join(repo_root, pat)) if os.path.isdir(g))
            if not found:
                raise Unreadable(f"ApplicationSet {need!r}: generator path {pat!r} matches no directory")
            for g in found:
                rel = os.path.relpath(g, repo_root)
                apps.append({"name": _expand(name_t, rel), "project": project,
                             "namespace": _expand(ns_t, rel), "server": _expand(srv_t, rel),
                             "dest_name": ""})
    names = [a["name"] for a in apps]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise Unreadable(f"duplicate Application names in inventory: {dup}")
    return apps


def matches(window: dict, app: dict) -> bool:
    """Argo v3.3.8 semantics without andOperator: OR across selectors."""
    def any_glob(patterns, value):
        return any(fnmatch.fnmatchcase(value, p) for p in patterns or [])
    return (any_glob(window.get("applications"), app["name"])
            or any_glob(window.get("namespaces"), app["namespace"])
            or any_glob(window.get("clusters"), app["server"])
            or any_glob(window.get("clusters"), app["dest_name"]))


def render(apps: list[dict], project: str, window: dict) -> dict:
    vsw = _validator()
    problems = vsw.check_window(project, 0, window)
    in_project = [a for a in apps if a["project"] == project]
    matched = [a for a in in_project if matches(window, a)]
    known = {a["name"] for a in apps}
    unknown = sorted(n for n in window.get("applications", []) if n not in known)
    # Project must exist in the inventory, else the window would match nothing.
    if not in_project and project not in {a["project"] for a in apps}:
        problems.append(f"{project}: UNKNOWN_PROJECT no Application belongs to this project")
    elsewhere = sorted(n for n in window.get("applications", [])
                       if n in known and n not in {a["name"] for a in in_project})
    chain = sorted(a["name"] for a in matched if a["name"] in RECOVERY_CHAIN)
    in_default = [a for a in apps if a["project"] == "default" and matches(window, a)]
    if unknown:
        problems.append(f"{project}: UNKNOWN_APPLICATION {unknown} not in the rendered inventory")
    if elsewhere:
        problems.append(f"{project}: WRONG_PROJECT {elsewhere} belong to another project and would not be matched")
    if chain:
        problems.append(f"{project}: RECOVERY_CHAIN window matches {chain}")
    if not matched and not unknown and not elsewhere:
        problems.append(f"{project}: MATCHES_NOTHING window matches no Application")
    return {
        "verdict": "refuse" if problems else "ok",
        "problems": problems,
        "project": project,
        "window": window,
        "patch": yaml.safe_dump({"spec": {"syncWindows": [window]}}, sort_keys=False),
        "matched": [{"name": a["name"], "project": a["project"], "namespace": a["namespace"]} for a in matched],
        "unknown_apps": unknown,
        "recovery_chain_hit": chain,
        "would_hit_if_in_default": sorted(a["name"] for a in in_default),
        "writes": "none",
    }


def _fixture() -> list[dict]:
    mk = lambda n, p, ns: {"name": n, "project": p, "namespace": ns, "server": "https://k", "dest_name": ""}
    return [mk("root-app", "default", "argocd"), mk("argocd-self-managed", "default", "argocd"),
            mk("vault", "default", "vault"), mk("labs-bot", "apps", "labs"), mk("labs-web", "apps", "labs"),
            mk("tenant-labs", "platform", "labs")]


def selftest() -> int:
    ok = True

    def case(label, project, window, want_verdict, want_text=""):
        nonlocal ok
        r = render(_fixture(), project, window)
        hit = r["verdict"] == want_verdict and (not want_text or any(want_text in p for p in r["problems"]))
        print(f"selftest {'ok  ' if hit else 'FAIL'} {label}")
        ok = ok and hit
        return r

    good = {"kind": "deny", "schedule": "0 22 * * 5", "duration": "48h", "applications": ["labs-bot"]}
    r = case("exact app in apps is ok", "apps", good, "ok")
    if r["matched"] != [{"name": "labs-bot", "project": "apps", "namespace": "labs"}] or r["writes"] != "none":
        print("selftest FAIL matched set wrong"); ok = False
    case("window in default is refused", "default", {**good, "applications": ["vault"]}, "refuse", "DEFAULT_PROJECT")
    case("recovery chain app is refused", "default", {**good, "applications": ["root-app"]}, "refuse", "RECOVERY_CHAIN")
    case("unknown app is refused", "apps", {**good, "applications": ["labs-nope"]}, "refuse", "UNKNOWN_APPLICATION")
    case("app of another project is refused", "apps", {**good, "applications": ["vault"]}, "refuse", "WRONG_PROJECT")
    case("allow is refused", "apps", {**good, "kind": "allow"}, "refuse", "KIND_NOT_DENY")
    case("manualSync true is refused", "apps", {**good, "manualSync": True}, "refuse", "MANUAL_SYNC")
    case("unknown project is refused", "nope", good, "refuse", "UNKNOWN_PROJECT")
    # Namespace selector widens the match (OR): in apps it reaches both labs apps.
    w = {**good, "namespaces": ["labs"]}
    if {a["name"] for a in render(_fixture(), "apps", w)["matched"]} != {"labs-bot", "labs-web"}:
        print("selftest FAIL namespace OR-match"); ok = False
    else:
        print("selftest ok   namespace selector widens the match set")
    # Blast radius if wrongly placed in default.
    r = render(_fixture(), "apps", {**good, "applications": ["root-app"]})
    if r["would_hit_if_in_default"] != ["root-app"]:
        print("selftest FAIL would_hit_if_in_default"); ok = False
    else:
        print("selftest ok   would_hit_if_in_default reports the chain member")
    # Namespace-only and clusters-only selectors that reach the recovery chain
    # must be reported as RECOVERY_CHAIN on their own, not only as other rules.
    case("namespace-only window reaching the chain", "default",
         {"kind": "deny", "schedule": "0 22 * * 5", "duration": "2h", "namespaces": ["argocd"]},
         "refuse", "RECOVERY_CHAIN")
    case("clusters-only window reaching the chain", "default",
         {"kind": "deny", "schedule": "0 22 * * 5", "duration": "2h", "clusters": ["https://k"]},
         "refuse", "RECOVERY_CHAIN")
    if {a["name"] for a in render(_fixture(), "apps", {**good, "applications": ["labs-bot"], "clusters": ["https://k"]})["matched"]} \
            != {"labs-bot", "labs-web"}:
        print("selftest FAIL clusters selector OR-match"); ok = False
    else:
        print("selftest ok   clusters selector widens the match set")
    # Names and namespaces follow the ApplicationSet templates, not a built-in pattern.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("platform-gitops/services/t1/s1", "platform-gitops/tenants/x1"):
            os.makedirs(os.path.join(tmp, d))
        def aset(name, project, path, tname, ns):
            return {"kind": "ApplicationSet", "metadata": {"name": name}, "spec": {
                "generators": [{"git": {"directories": [{"path": path}]}}],
                "template": {"metadata": {"name": tname}, "spec": {"project": project,
                             "destination": {"server": "https://k", "namespace": ns}}}}}
        docs = [aset("apps", "apps", "platform-gitops/services/*/*",
                     "svc-{{ index .path.segments 3 }}-{{ index .path.segments 2 }}", "{{ index .path.segments 2 }}"),
                aset("tenants", "platform", "platform-gitops/tenants/*", "ten-{{ .path.basename }}", "{{ .path.basename }}")]
        got = {a["name"]: a["namespace"] for a in inventory(docs, tmp)}
        if got != {"svc-s1-t1": "t1", "ten-x1": "x1"}:
            print("selftest FAIL template-derived inventory", got); ok = False
        else:
            print("selftest ok   inventory follows the ApplicationSet templates")
        docs[0]["spec"]["generators"][0]["git"]["directories"][0]["path"] = "platform-gitops/nope/*"
        try:
            inventory(docs, tmp)
            print("selftest FAIL generator matching nothing must be unreadable"); ok = False
        except Unreadable:
            print("selftest ok   generator matching no directory is unreadable")
        # Without the exclude check this builds cleanly (svc-s2-t2 is a unique extra name),
        # so only the explicit refusal can make it unreadable.
        os.makedirs(os.path.join(tmp, "platform-gitops/services/t2/s2"))
        docs[0]["spec"]["generators"][0]["git"]["directories"] = [
            {"path": "platform-gitops/services/t1/*"}, {"path": "platform-gitops/services/t2/s2", "exclude": True}]
        try:
            inventory(docs, tmp)
            print("selftest FAIL generator with exclude must be unreadable"); ok = False
        except Unreadable:
            print("selftest ok   generator with exclude is unreadable")
    # Inventory that cannot be built is unreadable, never shorter.
    try:
        inventory([], "/nonexistent")
        print("selftest FAIL empty render must be unreadable"); ok = False
    except Unreadable:
        print("selftest ok   missing ApplicationSets are unreadable")
    return 0 if ok else 2


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--repo-root")
    ap.add_argument("--project")
    ap.add_argument("--application", action="append", default=[])
    ap.add_argument("--namespace", action="append", default=[])
    ap.add_argument("--schedule")
    ap.add_argument("--duration")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv[1:])
    if a.selftest:
        rc = selftest()
        if rc != 0 or not a.files:
            return rc
    if not (a.repo_root and a.project and a.schedule and a.duration and a.files):
        print("missing arguments", file=sys.stderr)
        return 2
    window: dict = {"kind": "deny", "schedule": a.schedule, "duration": a.duration,
                    "applications": a.application}
    if a.namespace:
        window["namespaces"] = a.namespace
    try:
        report = render(inventory(load_docs(a.files), a.repo_root), a.project, window)
    except Unreadable as e:
        print(f"unreadable: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 1 if report["verdict"] == "refuse" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
