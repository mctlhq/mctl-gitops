#!/usr/bin/env python3
"""Fail when an ExecutionProfile's content changed without bumping spec.version.

`spec.version` is what a ReleaseBindingIntent references and what an
AgentDefinition's compatibility range is evaluated against. Nothing else
describes a profile's content — so if the file can change while the version
string stays put, the version is a claim about the content rather than the
content itself, and nobody checks the claim.

That is not hypothetical. gitops#1002 changed
`issue-investigator-default/profile.yaml` and did not bump `spec.version`, so
`1.0.0` named two different files until gitops#1007 corrected it. Every check
was green throughout, correctly: none of them looked at this.

It matters more since mctlhq/mctl-agents#291 pointed the declarative resolver
at this catalog. The in-repo fixture it replaced used the sha256 of the profile
file as its version, so a content edit without re-pinning could not resolve —
drift was impossible by construction. Moving to semver deliberately gave that
up, because the catalog is the source of truth and semver is its model. This
check is the other half of that trade (gitops#1009).

The resolver still checks what it can from its own side (the binding's mirrored
profileCompatibility, spec.profile.version against the profile's declared
spec.version, and the range). None of those notice an edit that leaves the
version string alone. Only a diff against the base can.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILE_GLOB = "platform-gitops/agent-platform/execution-profiles/*/profile.yaml"


class BaseUnavailable(RuntimeError):
    """The base commit could not be resolved, so nothing could be compared.

    Deliberately an error rather than a skip. A check that returns success
    when it cannot compute its input reports green in the one environment that
    gates the merge — the shape that left `_check_cluster_workflow_template`
    dead in CI for its whole life (mctl-agents#277) and that slipped through
    review again in mctl-agents#288, inside a PR arguing against it.
    """


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BaseUnavailable(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def resolve_base(explicit: str | None = None, cwd: Path | None = None) -> str:
    """The commit to diff against, as a resolvable rev.

    Order: an explicit --base, then GITHUB_BASE_REF (set on pull_request runs),
    then origin/HEAD's default branch, then origin/main. Each candidate is
    verified to actually resolve — a ref that names nothing is the same as no
    base at all, and must raise rather than quietly falling through to a
    comparison against the working tree.
    """
    # An EXPLICIT base that does not resolve is an error, never a fallback.
    # Falling through to the auto-detection chain would silently compare
    # against a different commit than the caller asked for and report success
    # for it — caught by this script's own selftest, which is the entire
    # argument for having one.
    if explicit:
        try:
            return _git("rev-parse", "--verify", f"{explicit}^{{commit}}", cwd=cwd).strip()
        except BaseUnavailable as exc:
            raise BaseUnavailable(f"explicit base {explicit!r} does not resolve") from exc

    candidates: list[str] = []
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    if base_ref:
        candidates += [f"origin/{base_ref}", base_ref]
    candidates += ["origin/main", "main"]

    tried: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        tried.append(candidate)
        try:
            return _git("rev-parse", "--verify", f"{candidate}^{{commit}}", cwd=cwd).strip()
        except BaseUnavailable:
            continue
    raise BaseUnavailable(
        "could not resolve a base commit to diff against; tried "
        f"{tried}. On a shallow clone, fetch the base branch first "
        "(actions/checkout with fetch-depth: 0)."
    )


def _spec_version(document: object) -> str | None:
    """`spec.version` of a parsed profile, or None if it is missing or unusable.

    Deliberately shared by both sides of the comparison. A defensive read on
    the base side and a bare `document["spec"]["version"]` on the edited side
    means a malformed `spec` raises an `AttributeError` traceback instead of
    this script's `❌ ...` message, and a *removed* version reads as "not the
    same string as before" — that is, as a bump.
    """
    if not isinstance(document, dict):
        return None
    spec = document.get("spec")
    if not isinstance(spec, dict):
        return None
    version = spec.get("version")
    return version if isinstance(version, str) else None


def _version_at(rev: str, path: str, cwd: Path | None = None) -> str | None:
    """`spec.version` of `path` at `rev`, or None if the file is absent there."""
    try:
        blob = _git("show", f"{rev}:{path}", cwd=cwd)
    except BaseUnavailable:
        return None  # added in this change — nothing to compare against
    try:
        document = yaml.safe_load(blob)
    except yaml.YAMLError as exc:
        raise BaseUnavailable(f"{path} at {rev} is not valid YAML: {exc}") from exc
    return _spec_version(document)


def changed_profiles(base: str, cwd: Path | None = None) -> list[str]:
    """Profile paths that differ between `base` and the working tree.

    Deliberately `base..` (two dots, against the working tree) rather than a
    three-dot merge-base diff: this runs on a checked-out PR head, and the
    question is "what does this change do to the catalog", not "what does the
    branch history contain".
    """
    out = _git("diff", "--name-only", base, "--", PROFILE_GLOB, cwd=cwd)
    return sorted(line for line in out.splitlines() if line.strip())


def check(base: str | None = None, cwd: Path | None = None) -> list[str]:
    resolved = resolve_base(base, cwd=cwd)
    errors: list[str] = []
    for path in changed_profiles(resolved, cwd=cwd):
        before = _version_at(resolved, path, cwd=cwd)
        if before is None:
            continue  # newly added profile
        after_path = (cwd or ROOT) / path
        if not after_path.is_file():
            continue  # deleted
        try:
            document = yaml.safe_load(after_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{path}: is not valid YAML: {exc}")
            continue
        after = _spec_version(document)
        if after is None:
            errors.append(
                f"{path}: content changed and spec.version is now missing or not a "
                f"string (it was {before!r}). Dropping the version is not a bump — "
                "the release binding that references it has nothing left to pin to. "
                "Set spec.version to a quoted version string above the previous one."
            )
            continue
        if after == before:
            errors.append(
                f"{path}: content changed but spec.version is still {before!r}. "
                "A profile's version is what its release binding references and what "
                "an AgentDefinition's compatibility range is evaluated against — "
                "leaving it put makes one version name two different files. Bump it "
                "and re-pin the binding under releases/."
            )
    return errors


def selftest() -> int:
    """Build a throwaway repository and prove both directions.

    A checker that has never been seen to fail is not known to work, and this
    one reads git rather than files, so a fixture directory cannot exercise it.
    """
    profile = {
        "apiVersion": "agents.mctl.ai/v1alpha2",
        "kind": "ExecutionProfile",
        "metadata": {"name": "selftest-default", "owner": "platform"},
        "spec": {"version": "1.0.0", "tools": ["Read"]},
    }
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        rel = "platform-gitops/agent-platform/execution-profiles/selftest-default/profile.yaml"
        target = repo / rel
        target.parent.mkdir(parents=True)
        target.write_text(yaml.safe_dump(profile), encoding="utf-8")
        _git("init", "-q", "-b", "main", cwd=repo)
        _git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A", cwd=repo)
        _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base", cwd=repo)
        base = _git("rev-parse", "HEAD", cwd=repo).strip()

        # 1. content changed, version left alone -> must fire
        profile["spec"]["tools"] = ["Read", "Grep"]
        target.write_text(yaml.safe_dump(profile), encoding="utf-8")
        errors = check(base=base, cwd=repo)
        if not errors or "still '1.0.0'" not in errors[0]:
            print(f"❌ selftest: detector did not fire on an unbumped edit; got {errors}", file=sys.stderr)
            return 1

        # 2. same content change, version bumped -> must pass
        profile["spec"]["version"] = "1.1.0"
        target.write_text(yaml.safe_dump(profile), encoding="utf-8")
        if check(base=base, cwd=repo):
            print("❌ selftest: detector fired on a properly bumped edit", file=sys.stderr)
            return 1

        # 3. a brand-new profile has nothing to compare against -> must pass
        new = repo / "platform-gitops/agent-platform/execution-profiles/brand-new/profile.yaml"
        new.parent.mkdir(parents=True)
        new.write_text(yaml.safe_dump(profile), encoding="utf-8")
        if check(base=base, cwd=repo):
            print("❌ selftest: detector fired on a newly added profile", file=sys.stderr)
            return 1

        # 4. dropping spec.version is not a bump -> must fire, and a `spec`
        #    that is not a mapping must reach the same clean error, not a traceback.
        target.write_text(yaml.safe_dump(dict(profile, spec={"tools": ["Read", "Grep"]})), encoding="utf-8")
        errors = check(base=base, cwd=repo)
        if not errors or "missing or not a string" not in errors[0]:
            print(f"❌ selftest: a dropped spec.version passed as a bump; got {errors}", file=sys.stderr)
            return 1
        target.write_text(yaml.safe_dump(dict(profile, spec="oops")), encoding="utf-8")
        errors = check(base=base, cwd=repo)
        if not errors or "missing or not a string" not in errors[0]:
            print(f"❌ selftest: a non-mapping spec passed as a bump; got {errors}", file=sys.stderr)
            return 1
        target.write_text(yaml.safe_dump(profile), encoding="utf-8")

        # 5. an unresolvable base must RAISE, never pass. This is the branch
        #    that decides whether the check works in CI at all.
        try:
            check(base="0000000000000000000000000000000000000000", cwd=repo)
        except BaseUnavailable:
            pass
        else:
            print("❌ selftest: an unresolvable base did not raise", file=sys.stderr)
            return 1

    print(
        "✅ selftest: fires on an unbumped edit and on a dropped or malformed version, "
        "stays quiet on a bumped one and on a new profile, and refuses to run without a base"
    )
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    base = None
    if "--base" in argv:
        base = argv[argv.index("--base") + 1]
    try:
        errors = check(base=base)
    except BaseUnavailable as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"❌ {error}", file=sys.stderr)
        print(f"profile version bumps: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    print("✅ every changed ExecutionProfile bumped its spec.version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
