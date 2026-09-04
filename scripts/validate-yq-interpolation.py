#!/usr/bin/env python3
"""Fail when a shell variable is interpolated into a yq expression.

yq's expression language is not data. A value that closes the string literal
keeps executing, against a file the pipeline holds write access to:

    DOMAIN='a.example.com")) | .image.tag = "pwned" # '
    yq eval -i "del(.ingress.hosts[] | select(. == \\"${DOMAIN}\\"))" values.yaml
    # → .image.tag is now "pwned"

The fix is to pass values through the environment, where yq treats them as
data no matter what they contain:

    export DOMAIN
    yq eval -i '.ingress.hosts += [strenv(DOMAIN)]' values.yaml

strenv() substitutes in value and comparison positions but NOT in an
expression *path*: `.env.${key}` cannot be parameterised, so a key is
additionally shape-checked at the point it enters the loop and written via the
`.env[strenv(KEY)]` subscript instead.

This is a ratchet. BASELINE records the sites that legitimately still carry a
variable; the check fails on anything not listed, so the count can go down and
never up. Companion to validate-shell-param-interpolation.py, which guards the
neighbouring invariant (Argo parameters interpolated into shell text,
gitops#992). See gitops#990, #995, #997.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "platform-gitops/argo-workflows/cluster-templates"

# A yq invocation, and everything up to the end of the line.
YQ_CALL = re.compile(r"(?<![\w./-])yq\b(.*)$")

# Options that take no value, so the token after them may still be the
# expression. `-i`/`--inplace` and the eval/eval-all subcommands.
SKIPPABLE = {"eval", "eval-all", "e", "ea", "-i", "--inplace", "-N", "--no-doc",
             "-r", "--raw-output", "-o", "--output-format", "-P", "--prettyPrint"}

# (file, template, expression) that may keep a variable, each with a reason.
# Shrink this list, never grow it.
BASELINE: set[tuple[str, str, str]] = {
    # config_patch IS the expression, not a value in one — there is no
    # strenv() shape for a caller-supplied yq *program*. It is defended
    # differently: mctl-api drops parameters an operation does not declare
    # (config_patch is not declared on deploy-service, mctlhq/mctl-api#246),
    # and the call site restricts it to the .configMaps subtree its only
    # intended producer writes.
    ("tpl-git-commit.yaml", "commit-service", '"$CONFIG_PATCH"'),
}


def tokenize(line: str) -> list[str]:
    """Split a shell line into tokens, keeping quotes so `$` stays visible."""
    tokens, cur, quote = [], "", None
    for ch in line:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch.isspace():
            if cur:
                tokens.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        tokens.append(cur)
    return tokens


def expression_of(line: str) -> str | None:
    """The yq expression argument of a yq call, if the line has one."""
    m = YQ_CALL.search(line)
    if not m:
        return None
    for tok in tokenize(m.group(1)):
        if tok in SKIPPABLE or tok.startswith("-"):
            continue
        return tok
    return None


def scan(directory: Path):
    for path in sorted(directory.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc:
                continue
            for tmpl in (doc.get("spec") or {}).get("templates") or []:
                source = (tmpl.get("script") or {}).get("source")
                if not source:
                    continue
                for line in source.splitlines():
                    expr = expression_of(line)
                    if expr and "$" in expr:
                        yield path.name, tmpl.get("name"), expr.strip()


def selftest() -> int:
    """A checker that has never been seen to fail is not known to work."""
    bad = """
apiVersion: argoproj.io/v1alpha1
kind: ClusterWorkflowTemplate
metadata: {name: selftest}
spec:
  templates:
    - name: t
      script:
        source: |
          yq eval -i ".ingress.hosts += [\\"${DOMAIN}\\"]" values.yaml
"""
    good = """
apiVersion: argoproj.io/v1alpha1
kind: ClusterWorkflowTemplate
metadata: {name: selftest}
spec:
  templates:
    - name: t
      script:
        source: |
          export DOMAIN
          yq eval -i '.ingress.hosts += [strenv(DOMAIN)]' "${DIR}/values.yaml"
"""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "bad.yaml").write_text(bad)
        if not list(scan(tmp)):
            print("❌ selftest: detector did not fire on an interpolated yq call",
                  file=sys.stderr)
            return 1
        (tmp / "bad.yaml").unlink()
        (tmp / "good.yaml").write_text(good)
        found = list(scan(tmp))
        if found:
            print(f"❌ selftest: detector fired on the strenv() shape: {found}",
                  file=sys.stderr)
            return 1
    print("✅ selftest: detector fires on interpolation and not on strenv()")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not TEMPLATES.is_dir():
        print(f"❌ {TEMPLATES} not found — refusing to pass vacuously", file=sys.stderr)
        return 2

    new, stale = [], set(BASELINE)
    for fname, tname, expr in scan(TEMPLATES):
        key = (fname, tname, expr)
        stale.discard(key)
        if key in BASELINE:
            continue
        new.append(key)

    if new:
        print("❌ Shell variables interpolated into a yq expression:\n", file=sys.stderr)
        for fname, tname, expr in new:
            print(f"   {fname} / {tname}: {expr}", file=sys.stderr)
        print(
            "\n   yq's expression language is not data: a value that closes the\n"
            "   string literal keeps executing against the file. Export the value\n"
            "   and read it with strenv() —\n\n"
            "       export DOMAIN\n"
            "       yq eval -i '.ingress.hosts += [strenv(DOMAIN)]' values.yaml\n\n"
            "   strenv() does not substitute in an expression PATH; write those as\n"
            "   `.env[strenv(KEY)]` and shape-check the key. See gitops#997.\n",
            file=sys.stderr,
        )
        return 1

    if stale:
        print("❌ BASELINE lists sites that no longer exist — remove them:\n", file=sys.stderr)
        for entry in sorted(stale):
            print(f"   {entry}", file=sys.stderr)
        print("\n   A baseline that outlives its sites stops being a ratchet.\n",
              file=sys.stderr)
        return 1

    print(f"✅ No yq expression interpolates a shell variable "
          f"({len(BASELINE)} known site remains, gitops#997)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
