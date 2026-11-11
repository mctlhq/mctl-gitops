#!/usr/bin/env python3
"""Fail-closed release gate for grouped worker Deployments (mctl-agents#1007).

  release-gate.py check  --files F... --new-tag T   before a bump writes
  release-gate.py verify                            whole tree (CI, post-rebase)
  release-gate.py diff --base B --head H            what a push changed, judged by content
  release-gate.py --selftest

Exit 0 = pass, 6 = refused, 7 = could not observe (diff only). Anything that cannot be observed (gate missing or
malformed, a file or key absent, a tag that is not X.Y.Z) is a refusal:
"could not observe" is never "observed fine".
"""

from __future__ import annotations

import argparse
import copy
import datetime
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE = "platform-gitops/release-gates.yaml"
REFUSED = 6
UNKNOWN = 7
# ASCII digits only, no leading zeros: `\d` accepts Unicode digits and "01".
_N = r"(0|[1-9][0-9]*)"
SEMVER = re.compile(rf"{_N}\.{_N}\.{_N}", re.ASCII)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def _semver(tag: Any) -> tuple[int, int, int] | None:
    m = SEMVER.fullmatch(str(tag)) if tag is not None else None
    return tuple(int(x) for x in m.groups()) if m else None  # type: ignore[return-value]


def _load(root: Path, rel: str) -> Any:
    return yaml.safe_load((root / rel).read_text())


def _dig(doc: Any, key: str) -> Any:
    for part in key.split("."):
        if not isinstance(doc, dict) or part not in doc:
            raise KeyError(key)
        doc = doc[part]
    return doc


def _policy_doc(root: Path, rev: str | None) -> Any:
    """The gate policy: from the working tree, or (rev given) from a git revision.

    The workflows pass `--policy-rev origin/main`, so the policy that judges a
    bump is the reviewed one on main, never a file the pending commit touched.
    A failed git read is an exception, i.e. a refusal.
    """
    if rev is None:
        return _load(root, GATE)
    raw = _blob(root, rev, GATE)
    if raw is None:
        raise ValueError(f"{GATE} absent at {rev}")
    return _parse(raw)


def _gates(root: Path, rev: str | None = None) -> list[dict]:
    doc = _policy_doc(root, rev)
    gates = doc.get("gates") if isinstance(doc, dict) else None
    if not isinstance(gates, list) or not gates:
        raise ValueError("no gates list")
    for g in gates:
        if not (isinstance(g, dict) and g.get("name") and isinstance(g.get("paths"), list) and g["paths"]):
            raise ValueError(f"malformed gate {g!r}")
        if _semver(g.get("min_tag")) is None:
            raise ValueError(f"gate {g.get('name')}: min_tag is not X.Y.Z")
        for r in g.get("requires") or []:
            if not (isinstance(r, dict) and {"path", "key", "equals"} <= set(r) and r["path"] in g["paths"]):
                raise ValueError(f"gate {g['name']}: malformed requires {r!r}")
        for p in g.get("prepull_paths") or []:
            if p not in g["paths"]:
                raise ValueError(f"gate {g['name']}: prepull_paths entry {p!r} is not in paths")
    return gates


def problems(root: Path, files: list[str] | None, new_tag: str | None, rev: str | None = None,
             today: datetime.date | None = None, image: str | None = None) -> list[str]:
    """Every reason to refuse. `files=None` is verify mode (whole tree)."""
    try:
        gates = _gates(root, rev)
        holds = _holds(_policy_doc(root, rev))
    except Exception as exc:  # noqa: BLE001 - unreadable gate is a refusal
        return [f"UNKNOWN: gate {GATE} unreadable: {type(exc).__name__}: {exc}"]
    out: list[str] = hold_problems(root, holds, files, new_tag, today, image)
    for g in gates:
        paths = g["paths"]
        touched = paths if files is None else [p for p in paths if p in files]
        if not touched:
            continue
        if files is not None:
            if sorted(touched) != sorted(paths):
                missing = sorted(set(paths) - set(touched))
                out.append(f"{g['name']}: partial bump, missing {missing}")
            floor = _semver(g["min_tag"])
            nt = _semver(new_tag)
            if nt is None:
                out.append(f"{g['name']}: new tag {new_tag!r} is not X.Y.Z, cannot compare to the floor")
            elif nt < floor:  # type: ignore[operator]
                out.append(f"{g['name']}: new tag {new_tag} is below the floor {g['min_tag']}")
        tags: dict[str, Any] = {}
        for p in touched:
            try:
                doc = _load(root, p)
                tag = _dig(doc, "image.tag")
                if g.get("repository") and _dig(doc, "image.repository") != g["repository"]:
                    out.append(f"{p}: image.repository is {_dig(doc, 'image.repository')!r}, gate says {g['repository']!r}")
                tags[p] = tag
            except Exception as exc:  # noqa: BLE001
                out.append(f"UNKNOWN: {p} image.tag unreadable: {type(exc).__name__}")
                continue
            cur = _semver(tag)
            if cur is None:
                out.append(f"{p}: current tag {tag!r} is not X.Y.Z")
            elif files is None and cur < _semver(g["min_tag"]):  # type: ignore[operator]
                out.append(f"{p}: tag {tag} is below the floor {g['min_tag']}")
        # The group moves together: after a bump, and in the tree, the tags
        # must be equal. A glob that silently skipped one file (no image
        # pattern matched) leaves exactly this state.
        if len({str(t) for t in tags.values()}) > 1:
            out.append(f"{g['name']}: tags differ across the group: {tags}")
        for r in g.get("requires") or []:
            if r["path"] not in touched:
                continue
            try:
                got = _dig(_load(root, r["path"]), r["key"])
            except Exception as exc:  # noqa: BLE001
                out.append(f"UNKNOWN: {r['path']} {r['key']} unreadable: {type(exc).__name__}")
                continue
            if got != r["equals"]:
                out.append(f"{r['path']}: {r['key']} is {got!r}, requires {r['equals']!r}")
        for p in g.get("prepull_paths") or []:
            if p in touched:
                out.extend(_prepull_problems(root, p, files is not None))
    return out


# -- version holds: a version that needs an explicit, recorded allow -----------
#
# mctl-api is deployed from a bootstrap Application whose Helm values live in a
# YAML block scalar (`values: |`) inside a Helm template, so the file as a whole
# is not parseable YAML and `image.tag` is not a key of any parsed document.
# The hold extracts the block, parses it, and refuses on anything it cannot
# read, in doubt always as a refusal (mctlhq/mctl-gitops#2528).

_VALUES_KEY = re.compile(r"^(\s*)values:\s*\|[+-]?\s*$")
_HELM_LINE = re.compile(r"^\s*\{\{-?.*-?\}\}\s*$")


class _DupKeyLoader(yaml.SafeLoader):
    """safe_load keeps the last of two equal keys silently; a second `tag:` must be an error."""


def _no_dups(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    for k, _ in node.value:
        key = loader.construct_object(k, deep=True)
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_DupKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dups)


def block_values(text: str) -> Any:
    """Parse the one `values: |` block scalar of a bootstrap Application."""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if _VALUES_KEY.match(ln)]
    if len(starts) != 1:
        raise ValueError(f"expected exactly one `values: |` block, found {len(starts)}")
    i = starts[0]
    key_indent = len(_VALUES_KEY.match(lines[i]).group(1))  # type: ignore[union-attr]
    body: list[str] = []
    for ln in lines[i + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip(" ")) <= key_indent:
            break
        body.append(ln)
    body = [ln for ln in body if not _HELM_LINE.match(ln)]  # outer-chart directives, not values
    indents = [len(ln) - len(ln.lstrip(" ")) for ln in body if ln.strip()]
    if not indents:
        raise ValueError("empty values block")
    cut = min(indents)
    doc = yaml.load("\n".join(ln[cut:] for ln in body), Loader=_DupKeyLoader)  # noqa: S506 - SafeLoader subclass
    if not isinstance(doc, dict):
        raise ValueError("values block is not a mapping")
    return doc


def _holds(doc: Any) -> list[dict]:
    """Validate the `version_holds` section. A missing section is an error, not 'no holds'."""
    holds = doc.get("version_holds") if isinstance(doc, dict) else None
    if not isinstance(holds, list):
        raise ValueError("version_holds missing or not a list")
    for h in holds:
        if not (isinstance(h, dict) and h.get("name") and isinstance(h.get("file"), str) and h["file"]
                and isinstance(h.get("repository"), str) and h["repository"]
                and _semver(h.get("held_from")) is not None):
            raise ValueError(f"malformed hold {h!r}")
        allow = h.get("allow")
        if allow is None:
            allow = h["allow"] = []
        if not isinstance(allow, list):
            raise ValueError(f"hold {h['name']}: allow is not a list")
        seen: set[str] = set()
        for a in allow:
            ok = (isinstance(a, dict) and isinstance(a.get("version"), str) and _semver(a["version"]) is not None
                  and all(isinstance(a.get(k), str) and a[k].strip() for k in ("grant", "approved_by"))
                  and isinstance(a.get("expires"), datetime.date) and not isinstance(a["expires"], datetime.datetime))
            if not ok:
                raise ValueError(f"hold {h['name']}: malformed allow record {a!r}")
            if _semver(a["version"]) < _semver(h["held_from"]):  # type: ignore[operator]
                raise ValueError(f"hold {h['name']}: allow {a['version']} is below held_from")
            if a["version"] in seen:
                raise ValueError(f"hold {h['name']}: two allow records for {a['version']}")
            seen.add(a["version"])
    return holds


def _strip_tag(text: str, hold: dict) -> str:
    """The file with the value of the held image's `tag:` line blanked (what a bump may change)."""
    pat = re.compile(r"(repository:\s*" + re.escape(hold["repository"]) + r"\s*\n\s+tag:)[^\n]*")
    return pat.sub(lambda m: m.group(1), text)


def _bootstrap_tag(root: Path, hold: dict) -> str:
    """The single image tag of the hold's file; any doubt raises."""
    text = (root / hold["file"]).read_text()
    pat = re.compile(r"repository:\s*" + re.escape(hold["repository"]) + r"\s*\n\s+tag:")
    # The bump workflows rewrite every `repository: <image>` + `tag:` pair by
    # text; the parser and that rewrite must see exactly one and the same.
    if len(pat.findall(text)) != 1 or text.count(hold["repository"]) != 1:
        raise ValueError("not exactly one image reference for the repository")
    img = block_values(text).get("image")
    if not isinstance(img, dict) or img.get("repository") != hold["repository"]:
        raise ValueError("image.repository is not the held repository")
    tag = img.get("tag")
    if not isinstance(tag, str):
        raise ValueError(f"image.tag is not a string: {tag!r}")
    return tag


def hold_problems(root: Path, holds: list[dict], files: list[str] | None, new_tag: str | None,
                  today: datetime.date | None = None, image: str | None = None) -> list[str]:
    """Refuse a held version unless an allow record names exactly that version.

    Bump mode (files given): a NEW write, judged on `new_tag`, only for a hold
    whose file is in the bump and whose repository is the image being bumped
    (`image`; unknown image = judged, fail closed). The record must be unexpired.
    Verify mode: every hold, judged on the tag now in the file. That tag is
    already deployed, so a record that exists counts as granted even after
    `expires`: letting it lapse must not freeze every other release and PR.
    Expiry only ever stops the next write of the held version.
    """
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    out: list[str] = []
    for h in holds:
        if files is not None and (h["file"] not in files or (image is not None and image != h["repository"])):
            continue
        try:
            current = _bootstrap_tag(root, h)
        except Exception as exc:  # noqa: BLE001 - could not observe is a refusal
            out.append(f"UNKNOWN: {h['file']} image.tag unreadable for hold {h['name']}: {type(exc).__name__}: {exc}")
            continue
        version = current if files is None else new_tag
        v = _semver(version)
        if v is None:
            out.append(f"{h['name']}: tag {version!r} is not X.Y.Z, cannot compare to the hold")
            continue
        if v < _semver(h["held_from"]):  # type: ignore[operator]
            continue
        rec = [a for a in h["allow"] if a["version"] == version]
        if not rec:
            out.append(f"{h['name']}: {version} is held (from {h['held_from']}) and has no allow record in {GATE}")
        elif files is not None and rec[0]["expires"] < today:
            out.append(f"{h['name']}: allow record for {version} expired on {rec[0]['expires']}")
    return out


def _shape_problems(path: str, tag: str, digest: str, ref_tag: str, ref_digest: str) -> list[str]:
    """The two-commit deploy leaves exactly three shapes in the tree.

    image = (tag, digest) is what the Deployment runs, ref = (ref_tag, ref_digest)
    is what the DaemonSet holds. The Deployment and DaemonSet must use the same
    repo:tag@digest string, or the pull is not a cache hit.
      settled:  digest == ref digest and tag == ref tag        (after step 2)
      legacy:   no image.digest and tag == ref tag             (before the first digest deploy)
      staged:   ref differs from the image                     (after step 1)
    Everything else is an inconsistent tag / digest / prepull.ref combination.
    """
    if digest:
        if digest == ref_digest:
            if tag != ref_tag:
                return [f"{path}: image.digest equals the prepull.ref digest but image.tag {tag!r} is not its tag "
                        f"{ref_tag!r}: the Deployment would not match the pre-pulled reference"]
        elif tag == ref_tag:
            return [f"{path}: image.tag {tag!r} equals the prepull.ref tag but image.digest differs from its digest: "
                    "one tag, two digests (step 2 without the new digest?)"]
        return []
    if tag == ref_tag:
        return []
    t, rt = _semver(tag), _semver(ref_tag)
    if t is None or rt is None:
        return [f"{path}: image.tag {tag!r} or prepull.ref tag {ref_tag!r} is not X.Y.Z, and image.digest is unset: "
                "cannot tell a staged pre-pull from a tag-only bump"]
    if rt < t:
        return [f"{path}: image.tag {tag!r} is ahead of prepull.ref tag {ref_tag!r} and image.digest is unset: "
                "a tag-only bump; stage prepull.ref first, then set image.tag and image.digest together"]
    return []


def _prepull_problems(root: Path, path: str, is_bump: bool) -> list[str]:
    """A pre-pulled worker moves through two reviewed commits, never one bump."""
    if is_bump:
        return [f"{path}: pre-pull rollout, an automated tag bump would be stopped by PreSync: use the reviewed PRs"]
    try:
        doc = _load(root, path)
        repo = _dig(doc, "image.repository")
        tag = _dig(doc, "image.tag")
        ref = _dig(doc, "prepull.ref")
        digest = (doc["image"].get("digest") or "")
    except Exception as exc:  # noqa: BLE001
        return [f"UNKNOWN: {path} pre-pull settings unreadable: {type(exc).__name__}"]
    out = []
    m = re.fullmatch(re.escape(str(repo)) + r":([^@: ]+)@(.+)", str(ref))
    ref_ok = bool(m and DIGEST.fullmatch(m.group(2)))
    if not ref_ok:
        out.append(f"{path}: prepull.ref {ref!r} is not {repo}:tag@sha256:<64 hex>")
    digest_ok = not digest or bool(DIGEST.fullmatch(str(digest)))
    if not digest_ok:
        out.append(f"{path}: image.digest {digest!r} is not sha256:<64 hex>")
    if ref_ok and digest_ok:
        out.extend(_shape_problems(path, str(tag), str(digest), m.group(1), m.group(2)))  # type: ignore[union-attr]
    return out


def run(root: Path, files: list[str] | None, new_tag: str | None, rev: str | None = None,
        image: str | None = None) -> int:
    found = problems(root, files, new_tag, rev, image=image)
    for line in found:
        print(f"::error::release gate: {line}", file=sys.stderr)
    if found:
        return REFUSED
    print("release gate: pass")
    return 0


# -- diff: judge a pushed commit by the content it changed ---------------------
#
# The policy is read from the parent commit (the side that was reviewed), never
# from the commit being judged. Files are compared by parsed content, not by
# tag string. A failed read of either side is UNKNOWN, which outranks a
# reported divergence and is never clean.


class GitReadError(Exception):
    """A read that failed, as opposed to a path that is absent."""


def _blob(repo: Path, rev: str, rel: str) -> bytes | None:
    """File bytes at rev, None only when git says the path does not exist."""
    def git(*args: str) -> bytes:
        try:
            r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            raise GitReadError(f"git {args[0]} failed: {type(exc).__name__}") from exc
        if r.returncode != 0:
            raise GitReadError(f"git {args[0]} {rev[:12]} exited {r.returncode}")
        return r.stdout

    listing = git("ls-tree", "-z", rev, "--", rel)
    if not listing:
        return None
    meta, _, name = listing.rstrip(b"\0").partition(b"\t")
    fields = meta.split()
    if len(fields) != 3 or fields[1] != b"blob" or name.decode(errors="replace") != rel:
        raise GitReadError(f"{rel} at {rev[:12]} is not a regular file")
    return git("cat-file", "blob", fields[2].decode())


def _parse(raw: bytes) -> Any:
    return yaml.safe_load(raw.decode())


def _without_tag(doc: Any) -> Any:
    doc = copy.deepcopy(doc)
    if isinstance(doc, dict) and isinstance(doc.get("image"), dict):
        doc["image"].pop("tag", None)
    return doc


def _deploy_state(doc: Any) -> tuple[Any, Any, Any]:
    img = doc.get("image") if isinstance(doc, dict) else None
    pre = doc.get("prepull") if isinstance(doc, dict) else None
    return (
        img.get("tag") if isinstance(img, dict) else None,
        (img.get("digest") or None) if isinstance(img, dict) else None,
        pre.get("ref") if isinstance(pre, dict) else None,
    )


def _without_deploy_keys(doc: Any) -> Any:
    """Like _without_tag, plus image.digest and prepull.ref (a pre-pulled file)."""
    doc = _without_tag(doc)
    if isinstance(doc, dict):
        if isinstance(doc.get("image"), dict):
            doc["image"].pop("digest", None)
        if isinstance(doc.get("prepull"), dict):
            doc["prepull"].pop("ref", None)
    return doc


def _step_problem(old: Any, new: Any) -> str | None:
    """None when old -> new is one sanctioned step of the two-commit deploy.

    step 1: only prepull.ref moves (image.tag and image.digest untouched).
    step 2: image.tag and image.digest move together, prepull.ref untouched,
            and the result is settled: both equal the staged reference.
    pin:    image.digest alone moves (the tag already is the staged tag), prepull.ref
            untouched, and the result is settled. This is the legacy shape
            (tag, no digest) becoming the settled one for the SAME image.
    Anything else (a tag-only change, both halves in one commit, a digest alone
    that is not the staged one) is not a deploy step the PreSync gate was
    designed for.
    """
    (bt, bd, br), (nt, nd, nr) = _deploy_state(old), _deploy_state(new)
    ct, cd, cr = bt != nt, bd != nd, br != nr
    if not (ct or cd or cr):
        return None
    if cr and not ct and not cd:
        return None
    if cd and not cr:
        m = re.fullmatch(r"[^@]+:([^@: ]+)@(sha256:[0-9a-f]{64})", str(nr))
        if m and m.group(1) == str(nt) and m.group(2) == str(nd):
            return None
        if not ct:
            return "image.digest moved but the result does not equal prepull.ref"
        return "image.tag and image.digest moved but do not both equal prepull.ref"
    parts = [n for n, c in (("image.tag", ct), ("image.digest", cd), ("prepull.ref", cr)) if c]
    return "not one step of the two-commit deploy (changed together: " + ", ".join(parts) + ")"


def diff_problems(repo: Path, base: str, head: str) -> tuple[list[str], list[str]]:
    """(violations, unknowns) for the change from base to head."""
    viol: list[str] = []
    unk: list[str] = []
    try:
        pol_base = _blob(repo, base, GATE)
        pol_head = _blob(repo, head, GATE)
    except GitReadError as exc:
        return [], [f"gate policy unreadable: {exc}"]
    if pol_base is None:
        return [], [f"gate policy absent in parent {base[:12]}: nothing to judge against"]
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / GATE).parent.mkdir(parents=True)
        (tmp / GATE).write_bytes(pol_base)  # trusted side
        try:
            gates = _gates(tmp)
            base_policy = _parse(pol_base)
            holds = _holds(base_policy)
        except Exception as exc:  # noqa: BLE001
            return [], [f"parent gate policy unreadable: {type(exc).__name__}: {exc}"]
        if pol_head is None:
            viol.append(f"{GATE} was removed")
        elif pol_head != pol_base:
            try:
                if _parse(pol_head) != base_policy:
                    viol.append(f"{GATE} content changed")
            except Exception as exc:  # noqa: BLE001
                viol.append(f"{GATE} no longer parses: {type(exc).__name__}")
        for g in gates:
            for p in g["paths"]:
                try:
                    b, h = _blob(repo, base, p), _blob(repo, head, p)
                except GitReadError as exc:
                    unk.append(f"{p}: {exc}")
                    continue
                if b is None:
                    unk.append(f"{p}: absent in parent {base[:12]}")
                    continue
                if h is None:
                    viol.append(f"{p}: gated file was removed")
                    continue
                (tmp / p).parent.mkdir(parents=True, exist_ok=True)
                (tmp / p).write_bytes(h)
                if b == h:
                    continue
                try:
                    old = _parse(b)
                except Exception as exc:  # noqa: BLE001
                    unk.append(f"{p}: parent content unreadable: {type(exc).__name__}")
                    continue
                try:
                    new = _parse(h)
                except Exception as exc:  # noqa: BLE001
                    viol.append(f"{p}: new content does not parse: {type(exc).__name__}")
                    continue
                if p in (g.get("prepull_paths") or []):
                    if _without_deploy_keys(old) != _without_deploy_keys(new):
                        viol.append(f"{p}: content other than image.tag, image.digest and prepull.ref changed")
                    else:
                        why = _step_problem(old, new)
                        if why:
                            viol.append(f"{p}: {why}")
                elif _without_tag(old) != _without_tag(new):
                    viol.append(f"{p}: content other than image.tag changed")
        # Held files: the pushed content is what the hold judges. A removed or
        # unreadable one is reported here, so the final check cannot pass on a
        # file that is merely missing from the scratch tree.
        for hold in holds:
            p = hold["file"]
            try:
                h = _blob(repo, head, p)
            except GitReadError as exc:
                unk.append(f"{p}: {exc}")
                continue
            if h is None:
                viol.append(f"{p}: held file was removed")
                continue
            (tmp / p).parent.mkdir(parents=True, exist_ok=True)
            (tmp / p).write_bytes(h)
            # The bump workflows rewrite only the repository+tag pair: any other
            # byte that moved (env flags, repoURL, targetRevision, a second image
            # reference) is not a release bump, as for the gated `paths` files.
            try:
                b0 = _blob(repo, base, p)
                if b0 is not None and _strip_tag(b0.decode(), hold) != _strip_tag(h.decode(), hold):
                    viol.append(f"{p}: content other than the image tag changed")
            except UnicodeDecodeError:
                viol.append(f"{p}: held file is not text")
            except GitReadError:
                pass  # reported as unknown by the base read below
            # A push that changes the held tag is a new write: judged like a bump
            # (expiry applies). An unchanged tag is only the deployed state.
            try:
                b = _blob(repo, base, p)
                with tempfile.TemporaryDirectory() as t2:
                    (Path(t2) / p).parent.mkdir(parents=True)
                    (Path(t2) / p).write_bytes(b if b is not None else b"")
                    old_tag = _bootstrap_tag(Path(t2), hold) if b is not None else None
            except Exception:  # noqa: BLE001 - cannot tell whether it changed: judge as a write
                old_tag = None
            try:
                new_t = _bootstrap_tag(tmp, hold)
            except Exception:  # noqa: BLE001 - reported by the tree check below
                continue
            if new_t != old_tag:
                viol.extend(hold_problems(tmp, [hold], [p], new_t, image=hold["repository"]))
        # The pushed tree must satisfy the parent's policy.
        # A file already reported as a violation (removed, unparsable) is not
        # also an unknown: the read worked, the content is what is wrong.
        flagged = [v.split(":")[0] for v in viol]
        for line in problems(tmp, None, None):
            if line.startswith("UNKNOWN: "):
                if any(line.startswith(f"UNKNOWN: {f} ") for f in flagged):
                    continue
                unk.append(line[len("UNKNOWN: "):])
            else:
                viol.append(line)
    return viol, unk


def run_diff(repo: Path, base: str, head: str) -> int:
    viol, unk = diff_problems(repo, base, head)
    for line in unk:
        print(f"::error::release gate diff: UNKNOWN: {line}", file=sys.stderr)
    for line in viol:
        print(f"::error::release gate diff: {line}", file=sys.stderr)
    if unk:
        return UNKNOWN
    if viol:
        return REFUSED
    print("release gate diff: pass")
    return 0


# -- selftest: green on a converged tree, red on every deliberate mutation ----

_P = [
    "platform-gitops/services/admins/mctl-agents-worker/values.yaml",
    "platform-gitops/services/admins/mctl-agents-worker-exec/values.yaml",
    "platform-gitops/services/admins/mctl-agents-worker-implement/values.yaml",
]


def _tree(d: Path, *, tags=("1.117.0",) * 3, strategy: str | None = "Recreate", gate: str | None = None,
          skip: str | None = None):
    for p, t in zip(_P, tags):
        f = d / p
        f.parent.mkdir(parents=True, exist_ok=True)
        if p == skip:
            continue
        body = {"image": {"tag": t, "repository": "ghcr.io/x/y"}}
        if p == _P[0] and strategy is not None:
            body["strategy"] = {"type": strategy}
        f.write_text(yaml.safe_dump(body))
    g = d / GATE
    g.parent.mkdir(parents=True, exist_ok=True)
    g.write_text(
        gate
        if gate is not None
        else yaml.safe_dump(
            {"version_holds": [],
             "gates": [{"name": "g", "paths": _P, "min_tag": "1.117.0", "repository": "ghcr.io/x/y",
                        "requires": [{"path": _P[0], "key": "strategy.type", "equals": "Recreate"}]}]}
        )
    )


def _prepull_selftest() -> list[str]:
    good = "ghcr.io/x/y:1.118.0@sha256:" + "a" * 64
    cases: list[tuple[str, dict, list[str] | None, bool]] = [
        ("pre-pull verify", {"prepull": {"ref": good}}, None, True),
        ("pre-pull digest pinned", {"prepull": {"ref": good}, "digest": "sha256:" + "b" * 64}, None, True),
        ("pre-pull refuses a bump", {"prepull": {"ref": good}}, _P, False),
        ("pre-pull ref missing", {}, None, False),
        ("pre-pull ref is a tag", {"prepull": {"ref": "ghcr.io/x/y:1.118.0"}}, None, False),
        ("pre-pull ref short digest", {"prepull": {"ref": "ghcr.io/x/y:1.118.0@sha256:abc"}}, None, False),
        ("pre-pull other repository", {"prepull": {"ref": "ghcr.io/x/z:1.118.0@sha256:" + "a" * 64}}, None, False),
        ("image digest malformed", {"prepull": {"ref": good}, "digest": "sha256:zz"}, None, False),
        # The three shapes the two-commit deploy leaves behind, and the ways to get them wrong.
        ("shape settled (step 2 done)", {"tag": "1.118.0", "prepull": {"ref": good}, "digest": "sha256:" + "a" * 64}, None, True),
        ("shape legacy (tag, no digest)", {"tag": "1.118.0", "prepull": {"ref": good}}, None, True),
        ("shape staged over a digest (step 1)", {"prepull": {"ref": good}, "digest": "sha256:" + "b" * 64}, None, True),
        ("tag-only bump over a stale ref", {"tag": "1.119.0", "prepull": {"ref": good}}, None, False),
        ("tag-only bump over a settled tree", {"tag": "1.119.0", "prepull": {"ref": good}, "digest": "sha256:" + "a" * 64}, None, False),
        ("step 2 with the old digest", {"tag": "1.118.0", "prepull": {"ref": good}, "digest": "sha256:" + "b" * 64}, None, False),
        ("ref tag is not X.Y.Z without a digest", {"tag": "1.118.0", "prepull": {"ref": "ghcr.io/x/y:1.118.0-rc1@sha256:" + "a" * 64}}, None, False),
    ]
    bad = []
    for name, kw, files, ok in cases:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            gate = yaml.safe_dump({"version_holds": [],
                                   "gates": [{"name": "g", "paths": _P, "min_tag": "1.117.0", "repository": "ghcr.io/x/y",
                                              "prepull_paths": [_P[0]]}]})
            _tree(d, gate=gate, tags=(kw.get("tag", "1.117.0"),) * 3)
            doc = yaml.safe_load((d / _P[0]).read_text())
            if "prepull" in kw:
                doc["prepull"] = kw["prepull"]
            if "digest" in kw:
                doc["image"]["digest"] = kw["digest"]
            (d / _P[0]).write_text(yaml.safe_dump(doc))
            found = problems(d, files, "1.118.0" if files else None)
            if bool(found) == ok:
                bad.append(f"{name}: {found}")
    return bad


def selftest() -> int:
    cases: list[tuple[str, dict, list[str] | None, str | None, bool]] = [
        ("converged bump", {}, _P, "1.118.0", True),
        ("converged verify", {}, None, None, True),
        ("unrelated file is not gated", {}, ["platform-gitops/services/x/values.yaml"], "0.0.1", True),
        ("partial bump", {}, _P[:2], "1.118.0", False),
        ("tag below floor", {}, _P, "1.116.0", False),
        ("non-semver new tag", {}, _P, "latest", False),
        ("Recreate removed", {"strategy": "RollingUpdate"}, _P, "1.118.0", False),
        ("tags differ across the group (verify)", {"tags": ("1.118.0", "1.117.0", "1.118.0")}, None, None, False),
        ("numeric not string floor", {}, _P, "1.99.0", False),
        ("leading zero tag", {}, _P, "01.118.0", False),
        ("unicode digit tag", {}, _P, "1.\u0661\u0661\u0668.0", False),
        ("prerelease suffix", {}, _P, "1.118.0-rc.1", False),
        ("required key absent", {"strategy": None}, _P, "1.118.0", False),
        ("Recreate removed (verify)", {"strategy": "RollingUpdate"}, None, None, False),
        ("current tag below floor (verify)", {"tags": ("1.116.0",) * 3}, None, None, False),
        ("other image at a high tag", {"gate": "REPO"}, _P, "1.118.0", False),
        ("requires names a file outside the group", {"gate": "OUTSIDE"}, _P, "1.118.0", False),
        ("gate file malformed", {"gate": "gates: nope"}, _P, "1.118.0", False),
        ("gate file not yaml", {"gate": ": : :"}, None, None, False),
        ("listed file missing", {"skip": _P[1]}, _P, "1.118.0", False),
    ]
    bad = []
    for name, kw, files, tag, want_pass in cases:
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            if kw.get("gate") == "REPO":
                kw = {"gate": yaml.safe_dump({"version_holds": [], "gates": [{"name": "g", "paths": _P, "min_tag": "1.117.0",
                                                         "repository": "ghcr.io/other/img"}]})}
            if kw.get("gate") == "OUTSIDE":
                kw = {"gate": yaml.safe_dump({"version_holds": [], "gates": [{"name": "g", "paths": _P, "min_tag": "1.117.0",
                                                         "requires": [{"path": "elsewhere.yaml", "key": "a", "equals": 1}]}]})}
            _tree(d, **kw)
            rc = 0 if not problems(d, files, tag) else REFUSED
        if (rc == 0) != want_pass:
            bad.append(name)
    with tempfile.TemporaryDirectory() as t:  # gate absent entirely
        d = Path(t)
        _tree(d)
        (d / GATE).unlink()
        if not problems(d, _P, "1.118.0"):
            bad.append("gate file missing")
    bad.extend(_prepull_selftest())
    if bad:
        print(f"selftest FAILED: {bad}", file=sys.stderr)
        return 1
    print(f"selftest ok ({len(cases) + 1} cases)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("--files", nargs="+", required=True)
    c.add_argument("--new-tag", required=True)
    c.add_argument("--image", default=None, help="image being bumped; a hold for another repository is skipped")
    v = sub.add_parser("verify")
    for sp in (c, v):
        sp.add_argument("--policy-rev", default=None,
                        help="read release-gates.yaml from this git revision (e.g. origin/main), not the tree")
    d = sub.add_parser("diff")
    d.add_argument("--base", required=True)
    d.add_argument("--head", required=True)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "check":
        return run(Path(a.root), a.files, a.new_tag, a.policy_rev, a.image)
    if a.cmd == "verify":
        return run(Path(a.root), None, None, a.policy_rev)
    if a.cmd == "diff":
        return run_diff(Path(a.root), a.base, a.head)
    ap.error("a command or --selftest is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
