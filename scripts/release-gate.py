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
             today: datetime.date | None = None, image: str | None = None,
             ledger_digest: str | None = None, new_digest: str | None = None,
             preflight: bool = False) -> list[str]:
    """Every reason to refuse. `files=None` is verify mode (whole tree)."""
    try:
        gates = _gates(root, rev)
        holds = _holds(_policy_doc(root, rev))
    except Exception as exc:  # noqa: BLE001 - unreadable gate is a refusal
        return [f"UNKNOWN: gate {GATE} unreadable: {type(exc).__name__}: {exc}"]
    out: list[str] = hold_problems(root, holds, files, new_tag, today, image, ledger_digest, new_digest,
                                   preflight)
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
        _ledger_cfg(h)
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


LEDGER_MODES = ("shadow", "enforce")


def _ledger_cfg(h: dict) -> dict | None:
    """The hold's optional `ledger:` block (mctlhq/mctl-api#1022 S4), validated.

    mode shadow:  the YAML allow records decide; release-deploy only reports
                  what the release ledger would decide.
    mode enforce: the ledger decides. A bump of the held image needs an
                  approved, MFA-backed ledger decision for exactly the image
                  digest being written (release-deploy's ledger-gate job hands
                  it over), the YAML allow records are not consulted, and a
                  pull request may change the held tag only when it is the
                  release bot's bump PR.
    """
    led = h.get("ledger")
    if led is None:
        return None
    if not isinstance(led, dict) or led.get("mode") not in LEDGER_MODES:
        raise ValueError(f"hold {h.get('name')}: ledger.mode must be one of {LEDGER_MODES}")
    w = led.get("wait_minutes")
    if not isinstance(w, int) or isinstance(w, bool) or not 1 <= w <= 180:
        raise ValueError(f"hold {h.get('name')}: ledger.wait_minutes must be an integer 1..180")
    for k in ("bump_pr_author", "bump_pr_branch_prefix"):
        if not isinstance(led.get(k), str) or not led[k].strip():
            raise ValueError(f"hold {h.get('name')}: ledger.{k} is required")
    return led


def _enforced(h: dict) -> bool:
    led = h.get("ledger")
    return isinstance(led, dict) and led.get("mode") == "enforce"


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
                  today: datetime.date | None = None, image: str | None = None,
                  ledger_digest: str | None = None, new_digest: str | None = None,
                  preflight: bool = False) -> list[str]:
    """Refuse a held version unless an allow record names exactly that version.

    Bump mode (files given): a NEW write, judged on `new_tag`, only for a hold
    whose file is in the bump and whose repository is the image being bumped
    (`image`; unknown image = judged, fail closed). The record must be unexpired.
    Verify mode: every hold, judged on the tag now in the file. That tag is
    already deployed, so a record that exists counts as granted even after
    `expires`: letting it lapse must not freeze every other release and PR.
    Expiry only ever stops the next write of the held version.

    A hold whose ledger mode is `enforce` ignores the allow records. A bump
    then needs `ledger_digest` (the digest the ledger-gate job found an
    approved decision for) equal to `new_digest` (the digest being written);
    nothing else stands in for it, so gitops-bump.yaml, which has no ledger
    step, cannot bump the held image at all. Verify mode accepts the held
    version in the tree without a record: how it got there is judged by the
    bump gate (gitops-bump.yaml has no ledger step, so it cannot bump the
    held image) and by the pull-request identity check (`pr-identity`).
    Direct pushes with another bypassing deploy key (runbook
    mctl-api-release-hold.md, P5b/P6) are not judged by either, and in
    enforce mode the offline `diff` no longer flags them either. They are
    caught after the push by release-gate-watch's ledger step (S4b,
    `ledger_changes` + release-ledger-shadow.py watch), which asks the
    ledger whether the written digest was approved.
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
        if _enforced(h):
            if files is None:
                continue
            # Preflight runs before the build, so no digest exists yet and the
            # ledger cannot be asked. It defers only this judgement: the bump
            # step calls check without --preflight and refuses an unknown
            # digest there. The version checks above still ran.
            if preflight:
                continue
            if not (isinstance(new_digest, str) and DIGEST.fullmatch(new_digest)):
                out.append(f"{h['name']}: ledger enforced, but the digest being written is unknown ({new_digest!r})")
            elif ledger_digest != new_digest:
                out.append(f"{h['name']}: ledger enforced and no approved release-ledger decision was handed over "
                           f"for {version} @ {new_digest} (got {ledger_digest!r})")
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
        image: str | None = None, ledger_digest: str | None = None, new_digest: str | None = None,
        preflight: bool = False) -> int:
    found = problems(root, files, new_tag, rev, image=image, ledger_digest=ledger_digest, new_digest=new_digest,
                     preflight=preflight)
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
    if len(fields) != 3 or fields[1] != b"blob" or fields[0] not in (b"100644", b"100755") \
            or name.decode(errors="replace") != rel:
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
                h, b = _blob(repo, head, p), _blob(repo, base, p)
            except GitReadError as exc:
                unk.append(f"{p}: {exc}")
                continue
            if b is None:
                unk.append(f"{p}: absent in parent {base[:12]}")
                continue
            if h is None:
                viol.append(f"{p}: held file was removed")
                continue
            (tmp / p).parent.mkdir(parents=True, exist_ok=True)
            (tmp / p).write_bytes(h)
            try:
                old_text = b.decode()
            except UnicodeDecodeError:
                unk.append(f"{p}: parent content is not text")
                continue
            try:
                new_text = h.decode()
            except UnicodeDecodeError:
                viol.append(f"{p}: held file is not text")
                continue
            # The bump workflows rewrite only the repository+tag pair: any other
            # byte that moved (env flags, repoURL, targetRevision, a second image
            # reference) is not a release bump, as for the gated `paths` files.
            # A reviewed PR that edits the file also lands here, by design: the
            # watcher cannot tell a reviewed merge from a deploy-key push (#2543).
            content_changed = _strip_tag(old_text, hold) != _strip_tag(new_text, hold)
            if content_changed:
                viol.append(f"{p}: content other than the image tag changed (expected when a reviewed PR edits it)")
            # A push that changes the held tag is a new write: judged like a bump
            # (expiry applies). An unchanged tag is only the deployed state.
            # Either side unreadable is UNKNOWN, never "no change".
            try:
                with tempfile.TemporaryDirectory() as t2:
                    (Path(t2) / p).parent.mkdir(parents=True)
                    (Path(t2) / p).write_bytes(b)
                    old_tag = _bootstrap_tag(Path(t2), hold)
            except Exception as exc:  # noqa: BLE001
                unk.append(f"{p}: parent image.tag unreadable: {type(exc).__name__}: {exc}")
                continue
            try:
                new_t = _bootstrap_tag(tmp, hold)
            except Exception as exc:  # noqa: BLE001
                if not content_changed:  # else the content is what is wrong, already a violation
                    unk.append(f"{p}: pushed image.tag unreadable: {type(exc).__name__}: {exc}")
                continue
            # An enforced ledger hold is judged where the change is made (the
            # bump gate, `pr-identity`); this offline diff cannot read the
            # ledger, and the allow records no longer decide for that hold.
            if new_t != old_tag and not _enforced(hold):
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


# -- ledger holds: who may change a held tag, and what the watch must read ----


def pr_identity_problems(repo: Path, base: str, head: str, author: str, branch: str,
                         pusher: str | None = None) -> list[str]:
    """A pull request may change an enforced hold's tag only as the release bot's bump PR.

    Pull-request CI cannot read the release ledger (mctl-api admits only
    workflows on refs/heads/main as its reader), so it cannot check a
    decision. It can check who proposes the change: release-deploy's
    publish-pr job opens bump PRs as the GitHub App bot from a branch named
    release-bump/<image>-<version>, after its ledger-gate job found the
    decision. The policy is read from `base`, never from the pull request.
    A failed read is a problem, never a pass.

    The opener alone proves nothing about later commits: anyone with write
    access can push onto the bot's open branch, and the PR's author stays the
    bot. So `pusher`, the account that caused this run (the event sender: the
    opener on `opened`, whoever pushed on `synchronize`, whoever reopened),
    must be the bot as well. Commit author names would not do: they are
    free text and the bot's commits are unsigned.
    """
    try:
        raw = _blob(repo, base, GATE)
        if raw is None:
            return [f"{GATE} absent at {base}"]
        holds = _holds(_parse(raw))
    except Exception as exc:  # noqa: BLE001
        return [f"UNKNOWN: policy unreadable at {base}: {type(exc).__name__}: {exc}"]
    out: list[str] = []
    for h in holds:
        if not _enforced(h):
            continue
        tags = []
        for rev in (base, head):
            try:
                b = _blob(repo, rev, h["file"])
                if b is None:
                    raise ValueError("file absent")
                with tempfile.TemporaryDirectory() as t:
                    (Path(t) / h["file"]).parent.mkdir(parents=True)
                    (Path(t) / h["file"]).write_bytes(b)
                    tags.append(_bootstrap_tag(Path(t), h))
            except Exception as exc:  # noqa: BLE001
                out.append(f"UNKNOWN: {h['file']} image.tag unreadable at {rev}: {type(exc).__name__}: {exc}")
                break
        else:
            if tags[0] == tags[1]:
                continue
            led = h["ledger"]
            if author != led["bump_pr_author"] or not branch.startswith(led["bump_pr_branch_prefix"]):
                out.append(f"{h['name']}: {h['file']} changes {h['repository']} {tags[0]} -> {tags[1]}, but the "
                           f"ledger is enforced and only {led['bump_pr_author']} on a "
                           f"{led['bump_pr_branch_prefix']}* branch may propose that (got {author!r} on {branch!r}); "
                           f"release it through release-deploy instead")
            elif pusher != led["bump_pr_author"]:
                out.append(f"{h['name']}: {h['file']} changes {h['repository']} {tags[0]} -> {tags[1]} on the release "
                           f"bot's PR, but this run was caused by {pusher!r}, not {led['bump_pr_author']}: a commit "
                           f"pushed onto the bump branch carries no ledger decision")
    return out


def _held_image(repo: Path, rev: str, hold: dict) -> tuple[str, str | None]:
    """(image.tag, image.digest or None) of the hold's file at `rev`; any doubt raises.

    A file without a digest key yields None (the bootstrap file pins none
    today); a digest key that is present but not a string is an error.
    """
    raw = _blob(repo, rev, hold["file"])
    if raw is None:
        raise ValueError(f"{hold['file']} absent at {rev[:12]}")
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / hold["file"]).parent.mkdir(parents=True)
        (Path(t) / hold["file"]).write_bytes(raw)
        tag = _bootstrap_tag(Path(t), hold)
        digest = block_values((Path(t) / hold["file"]).read_text())["image"].get("digest")
    if digest is not None and not isinstance(digest, str):
        raise ValueError(f"image.digest is not a string: {digest!r}")
    return tag, digest or None


def ledger_changes(repo: Path, base: str, head: str) -> tuple[list[dict], list[tuple[str | None, str]]]:
    """Held-image writes a push made, for the S4b ledger read in release-gate-watch.

    For every hold with a `ledger:` block in the policy at `base` (the trusted
    side, as in `diff`): when the push changed the file's image.tag or
    image.digest to a version at or above held_from, one change
    {mode, hold, repository, version, digest, old_version}. `digest` is None
    when the file pins none. A tag or digest that did not move is the
    deployed state, not a write, and yields nothing.

    Unknowns are (mode, why); mode None means the policy itself could not be
    read, so no hold's mode is known. A read that fails is never "no change".
    """
    try:
        raw = _blob(repo, base, GATE)
        if raw is None:
            return [], [(None, f"{GATE} absent at {base[:12]}")]
        holds = _holds(_parse(raw))
    except Exception as exc:  # noqa: BLE001
        return [], [(None, f"policy unreadable at {base[:12]}: {type(exc).__name__}: {exc}")]
    changes: list[dict] = []
    unk: list[tuple[str | None, str]] = []
    for h in holds:
        led = h.get("ledger")
        if not led:
            continue
        try:
            old = _held_image(repo, base, h)
            new = _held_image(repo, head, h)
        except Exception as exc:  # noqa: BLE001
            unk.append((led["mode"], f"{h['name']}: {h['file']} image unreadable: {type(exc).__name__}: {exc}"))
            continue
        if new == old:
            continue
        v = _semver(new[0])
        if v is None:
            unk.append((led["mode"], f"{h['name']}: pushed tag {new[0]!r} is not X.Y.Z"))
            continue
        if v >= _semver(h["held_from"]):  # type: ignore[operator]  # below it the hold does not apply
            changes.append({"mode": led["mode"], "hold": h["name"], "repository": h["repository"],
                            "version": new[0], "digest": new[1], "old_version": old[0]})
    return changes, unk


def ledger_holds(root: Path) -> list[str]:
    """`<mode> <repository> <version>` per ledger hold (for operators and the S4b watch step)."""
    out = []
    for h in _holds(_policy_doc(root, None)):
        led = h.get("ledger")
        if led:
            out.append(f"{led['mode']} {h['repository']} {_bootstrap_tag(root, h)}")
    return out


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
    c.add_argument("--new-digest", default=None, help="digest of the image being written (ledger holds)")
    c.add_argument("--ledger-approved-digest", default=None,
                   help="digest release-deploy's ledger-gate job found an approved decision for")
    c.add_argument("--preflight", action="store_true",
                   help="before the build (release-preflight.py): an enforced ledger hold is judged at the bump")
    d = sub.add_parser("diff")
    d.add_argument("--base", required=True)
    d.add_argument("--head", required=True)
    pi = sub.add_parser("pr-identity")
    pi.add_argument("--base", required=True)
    pi.add_argument("--head", required=True)
    pi.add_argument("--author", required=True)
    pi.add_argument("--branch", required=True)
    pi.add_argument("--pusher", required=True, help="github.event.sender.login of the pull_request event")
    sub.add_parser("ledger-holds")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "check":
        return run(Path(a.root), a.files, a.new_tag, a.policy_rev, a.image,
                   a.ledger_approved_digest or None, a.new_digest or None, a.preflight)
    if a.cmd == "verify":
        return run(Path(a.root), None, None, a.policy_rev)
    if a.cmd == "diff":
        return run_diff(Path(a.root), a.base, a.head)
    if a.cmd == "pr-identity":
        found = pr_identity_problems(Path(a.root), a.base, a.head, a.author, a.branch, a.pusher)
        for line in found:
            print(f"::error::release gate pr-identity: {line}", file=sys.stderr)
        if any(x.startswith("UNKNOWN") for x in found):
            return UNKNOWN
        if found:
            return REFUSED
        print("release gate pr-identity: pass")
        return 0
    if a.cmd == "ledger-holds":
        try:
            for line in ledger_holds(Path(a.root)):
                print(line)
        except Exception as exc:  # noqa: BLE001 - could not observe
            print(f"::error::release gate ledger-holds: {type(exc).__name__}: {exc}", file=sys.stderr)
            return UNKNOWN
        return 0
    ap.error("a command or --selftest is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
