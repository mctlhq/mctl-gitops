#!/usr/bin/env python3
"""Check that zitadel-iac's Login V2 overrides still cover every "Zitadel".

Reads the ZITADEL release the zitadel chart pin deploys (the chart's
appVersion), fetches that release's hosted login locale files
(apps/login/locales/*.json in zitadel/zitadel) and compares them with
platform-gitops/helm-charts/zitadel-iac/iac/login_texts.json. Fails when:

  - a locale value names Zitadel and login_texts.json does not override it;
  - an override itself names Zitadel;
  - an override sets a language or key that release does not have (a key
    moved or was renamed upstream, so the override no longer applies).

Every read is required: a failed or empty fetch is an error, never "no
locales" (an empty set would pass every check).

  check-zitadel-login-texts.py               # the release the chart pins
  check-zitadel-login-texts.py --locales DIR # local locale files (tests)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "platform-gitops/bootstrap/templates/core-infra/zitadel.yaml"
OVERRIDES = ROOT / "platform-gitops/helm-charts/zitadel-iac/iac/login_texts.json"
CHART_REPO = "https://charts.zitadel.com"


def chart_version() -> str:
    text = APP.read_text()
    m = re.search(r"repoURL: https://charts\.zitadel\.com\s+chart: zitadel\s+(?:#.*\n\s+)*targetRevision: (\S+)", text)
    if not m:
        sys.exit(f"could not find the zitadel chart pin in {APP}")
    return m.group(1)


def app_version(chart: str) -> str:
    out = subprocess.run(
        ["helm", "show", "chart", "zitadel", "--repo", CHART_REPO, "--version", chart],
        check=True, capture_output=True, text=True,
    ).stdout
    m = re.search(r"^appVersion:\s*['\"]?([^'\"\s]+)", out, re.M)
    if not m:
        sys.exit(f"chart zitadel {chart} has no appVersion")
    return m.group(1)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "mctl-gitops-ci"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def upstream_locales(tag: str) -> dict[str, dict]:
    listing = json.loads(fetch(
        f"https://api.github.com/repos/zitadel/zitadel/contents/apps/login/locales?ref={tag}"))
    files = [f for f in listing if f["name"].endswith(".json")]
    if not files:
        sys.exit(f"no locale files at zitadel/zitadel {tag}")
    return {f["name"][:-5]: json.loads(fetch(f["download_url"])) for f in files}


def local_locales(directory: str) -> dict[str, dict]:
    files = sorted(Path(directory).glob("*.json"))
    if not files:
        sys.exit(f"no locale files in {directory}")
    return {f.stem: json.loads(f.read_text()) for f in files}


def leaves(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, path + (k,))
    elif isinstance(obj, str):
        yield path, obj
    else:
        yield path, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locales", help="directory of locale files instead of the pinned release")
    args = ap.parse_args()

    if args.locales:
        source, locales = args.locales, local_locales(args.locales)
    else:
        chart = chart_version()
        tag = app_version(chart)
        source, locales = f"zitadel {tag} (chart {chart})", upstream_locales(tag)

    overrides = json.loads(OVERRIDES.read_text())
    errors = []

    for lang, tree in sorted(locales.items()):
        upstream = dict(leaves(tree))
        mine = dict(leaves(overrides.get(lang, {})))
        for path, text in upstream.items():
            if text and "zitadel" in text.lower() and path not in mine:
                errors.append(f"{lang}: {'.'.join(path)} = {text!r} names Zitadel and is not overridden")
        for path, text in mine.items():
            if path not in upstream:
                errors.append(f"{lang}: override {'.'.join(path)} is not a key of {source}")
            elif not isinstance(text, str) or not text.strip():
                errors.append(f"{lang}: override {'.'.join(path)} is not a non-empty string")
            elif "zitadel" in text.lower():
                errors.append(f"{lang}: override {'.'.join(path)} still names Zitadel: {text!r}")

    for lang in sorted(set(overrides) - set(locales)):
        errors.append(f"{lang}: login_texts.json overrides a language {source} does not ship")

    if errors:
        print(f"Login V2 texts vs {source}:", *errors, sep="\n  ")
        return 1
    print(f"Login V2 texts cover every Zitadel mention of {source} ({len(locales)} locales).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
