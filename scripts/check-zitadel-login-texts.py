#!/usr/bin/env python3
"""Check that zitadel-iac's Login V2 overrides still cover every "Zitadel".

Reads the ZITADEL release the zitadel chart pin deploys (the chart's
appVersion), fetches that release's hosted login locale files
(apps/login/locales/*.json in zitadel/zitadel) and compares them with
platform-gitops/helm-charts/zitadel-iac/iac/login_texts.json. Fails when:

  - a locale value names Zitadel and login_texts.json does not override it;
  - an override is not exactly the upstream string with Zitadel replaced by
    MCTL (plus the grammar fixes listed in GRAMMAR): this catches an
    upstream re-word of an overridden key and a dropped {placeholder};
  - an override sets a language or key that release does not have (a key
    moved or was renamed upstream, so the override no longer applies).

Every read is required: a failed or empty fetch is an error, never "no
locales" (an empty set would pass every check).

  check-zitadel-login-texts.py               # the release the chart pins
  check-zitadel-login-texts.py --locales DIR # local locale files
  check-zitadel-login-texts.py --selftest    # prove the checks fire
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "platform-gitops/bootstrap/templates/core-infra/zitadel.yaml"
OVERRIDES = ROOT / "platform-gitops/helm-charts/zitadel-iac/iac/login_texts.json"
CHART_REPO = "https://charts.zitadel.com"

# Deliberate deviations from the plain Zitadel -> MCTL substitution:
# (language, text after substitution) -> override text.
GRAMMAR = {
    # Hungarian takes "az" before a vowel sound; MCTL is read "em-...".
    ("hu", "Bejelentkezés a MCTL-lel"): "Bejelentkezés az MCTL-lel",
    ("hu", "Hozd létre a MCTL fiókodat."): "Hozd létre az MCTL-fiókodat.",
    ("hu", "Az Engedélyezés gombra kattintva engedélyezed, hogy a(z) {appName} és a MCTL a saját felhasználási feltételeik és adatvédelmi irányelveik szerint használja az adataidat. Ezt a hozzáférést bármikor visszavonhatod."):
        "Az Engedélyezés gombra kattintva engedélyezed, hogy a(z) {appName} és az MCTL a saját felhasználási feltételeik és adatvédelmi irányelveik szerint használja az adataidat. Ezt a hozzáférést bármikor visszavonhatod.",
    # Turkish genitive after an acronym read with a final vowel: 'nin.
    ("tr", "İzin Ver'e tıklayarak, {appName} ve MCTL'in bilgilerinizi kendi hizmet şartları ve gizlilik politikalarına uygun olarak kullanmasına izin vermiş olursunuz. Bu erişimi istediğiniz zaman iptal edebilirsiniz."):
        "İzin Ver'e tıklayarak, {appName} ve MCTL'nin bilgilerinizi kendi hizmet şartları ve gizlilik politikalarına uygun olarak kullanmasına izin vermiş olursunuz. Bu erişimi istediğiniz zaman iptal edebilirsiniz.",
}


def expected(lang: str, upstream: str) -> str:
    text = re.sub("(?i)zitadel", "MCTL", upstream)
    return GRAMMAR.get((lang, text), text)


def chart_version() -> str:
    text = APP.read_text()
    m = re.search(r"repoURL: https://charts\.zitadel\.com\s+chart: zitadel\s+(?:#.*\n\s+)*targetRevision: (\S+)", text)
    if not m:
        sys.exit(f"could not find the zitadel chart pin in {APP}")
    return m.group(1)


def app_version(chart: str) -> str:
    proc = subprocess.run(
        ["helm", "show", "chart", "zitadel", "--repo", CHART_REPO, "--version", chart],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"helm show chart zitadel {chart} failed: {proc.stderr.strip()}")
    m = re.search(r"^appVersion:\s*['\"]?([^'\"\s]+)", proc.stdout, re.M)
    if not m:
        sys.exit(f"chart zitadel {chart} has no appVersion")
    return m.group(1)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "mctl-gitops-ci"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        req.add_header("Authorization", f"Bearer {token}")
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                sys.exit(f"fetching {url} failed: {e}")
            time.sleep(5)
    raise AssertionError("unreachable")


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
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, path + (str(i),))
    else:
        yield path, obj


def problems(locales: dict[str, dict], overrides: dict, source: str) -> list[str]:
    errors = []
    for lang, tree in sorted(locales.items()):
        upstream = dict(leaves(tree))
        mine = dict(leaves(overrides.get(lang, {})))
        for path, text in upstream.items():
            if isinstance(text, str) and "zitadel" in text.lower() and path not in mine:
                errors.append(f"{lang}: {'.'.join(path)} = {text!r} names Zitadel and is not overridden")
        for path, text in mine.items():
            key = ".".join(path)
            if path not in upstream:
                errors.append(f"{lang}: override {key} is not a key of {source}")
            elif not isinstance(upstream[path], str):
                errors.append(f"{lang}: override {key} replaces a non-string upstream value")
            elif text != expected(lang, upstream[path]):
                errors.append(f"{lang}: override {key} is {text!r}, expected {expected(lang, upstream[path])!r} from {source}")
    for lang in sorted(set(overrides) - set(locales)):
        errors.append(f"{lang}: login_texts.json overrides a language {source} does not ship")
    return errors


def selftest() -> list[str]:
    """Every check must pass on a matching pair and fire on each mutation."""
    base_locales = {
        "en": {"common": {"title": "Login with Zitadel", "back": "Back"},
               "device": {"request": {"disclaimer": "allow {appName} and Zitadel"}}},
        "hu": {"common": {"title": "Bejelentkezés a Zitadel-lel"}},
    }
    base_overrides = {
        "en": {"common": {"title": "Login with MCTL"},
               "device": {"request": {"disclaimer": "allow {appName} and MCTL"}}},
        "hu": {"common": {"title": "Bejelentkezés az MCTL-lel"}},
    }

    def mutate(fn, target):
        locales, overrides = copy.deepcopy(base_locales), copy.deepcopy(base_overrides)
        fn(locales if target == "locales" else overrides)
        return locales, overrides

    cases = {
        "upstream adds a Zitadel string": ("locales", lambda d: d["en"]["common"].__setitem__("new", "Zitadel x")),
        "upstream re-words an overridden key": ("locales", lambda d: d["en"]["common"].__setitem__("title", "Sign in with Zitadel")),
        "upstream drops an overridden key": ("locales", lambda d: d["en"]["common"].pop("title")),
        "upstream Zitadel string inside a list": ("locales", lambda d: d["en"].__setitem__("list", ["a", "Zitadel b"])),
        "override still names Zitadel": ("overrides", lambda d: d["en"]["common"].__setitem__("title", "Login with Zitadel")),
        "override drops a placeholder": ("overrides", lambda d: d["en"]["device"]["request"].__setitem__("disclaimer", "allow this app and MCTL")),
        "override removed": ("overrides", lambda d: d["en"]["common"].pop("title")),
        "override of an unknown key": ("overrides", lambda d: d["en"]["common"].__setitem__("gone", "x")),
        "override of an unshipped language": ("overrides", lambda d: d.__setitem__("xx", {"common": {"title": "x"}})),
        "grammar fix missing": ("overrides", lambda d: d["hu"]["common"].__setitem__("title", "Bejelentkezés a MCTL-lel")),
    }

    failures = []
    if problems(base_locales, base_overrides, "fixture"):
        failures.append(f"matching fixture reported problems: {problems(base_locales, base_overrides, 'fixture')}")
    for name, (target, fn) in cases.items():
        locales, overrides = mutate(fn, target)
        if not problems(locales, overrides, "fixture"):
            failures.append(f"did not fire: {name}")

    with tempfile.TemporaryDirectory() as empty:
        proc = subprocess.run([sys.executable, __file__, "--locales", empty], capture_output=True, text=True)
        if proc.returncode == 0:
            failures.append("an empty locale directory passed")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locales", help="directory of locale files instead of the pinned release")
    ap.add_argument("--selftest", action="store_true", help="prove every check fires, then exit")
    args = ap.parse_args()

    if args.selftest:
        failures = selftest()
        if failures:
            print("login texts selftest failed:", *failures, sep="\n  ", file=sys.stderr)
            return 1
        print("login texts selftest ok")
        return 0

    if args.locales:
        source, locales = args.locales, local_locales(args.locales)
    else:
        chart = chart_version()
        tag = app_version(chart)
        source, locales = f"zitadel {tag} (chart {chart})", upstream_locales(tag)

    errors = problems(locales, json.loads(OVERRIDES.read_text()), source)
    if errors:
        print(f"Login V2 texts vs {source}:", *errors, sep="\n  ")
        return 1
    print(f"Login V2 texts cover every Zitadel mention of {source} ({len(locales)} locales).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
