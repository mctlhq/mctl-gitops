#!/usr/bin/env python3
"""Generate (or check) assurance/web-contracts/cases.json, the case catalogue.

Preview assurance only; not production conformance (mctlhq/mctl-gitops#2929).

  gen_cases.py          rewrite cases.json
  gen_cases.py --check  exit 1 when cases.json differs from what this script generates

The specs (tests/header.spec.ts, tests/assets.spec.ts) generate one test per catalogued case,
titled with the case id, so this file is the single source of what exists. The report iterates
over the catalogue, so a case no test executed is NOT-RUN and never PASS.
Stdlib only.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "cases.json"

ALL4 = ["B-1", "B", "375", "1280"]
NARROW = ["B-1", "375"]
HDR_VIEWPORTS = {1: ALL4, 13: ALL4, 14: ALL4, 16: ALL4, 11: ["B-1"]}
for _h in (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15):
    HDR_VIEWPORTS[_h] = NARROW
SENSITIVE_HDRS = (3, 7, 8, 10, 12, 16)  # contract section 10: the behaviour-relevant subset

CONSUMERS = {  # site -> (contract consumer code, route classes with their contract letter)
    "mctl-web": ("WEB", {"landing": "L"}),
    "mctl-docs": ("DOCS", {"content": "C"}),
    "mctl-telegram": ("TG", {"landing": "L", "sensitive": "S"}),
    "mctl-academy": ("ACAD", {"landing": "L"}),
    "mctl-alice": ("ALICE", {"landing": "L", "sensitive": "S"}),
    "seerrsense": ("SEERR", {"landing": "L", "sensitive": "S"}),
}
EXCEPTIONS = {"mctl-telegram": {5: "EX-1", 6: "EX-1", 8: "EX-2", 12: "EX-2"}}
FIXTURES = ["fixture-reference", "fixture-reference-wide", "fixture-checkbox"]
# Observed limits of the CSS-checkbox pattern for which the contract registers no exception.
KNOWN_GAPS = {
    ("fixture-checkbox", 4): "a native checkbox does not toggle on Enter (only Space); HDR-4 requires both keys and the contract registers no exception for it",
    ("fixture-checkbox", 11): "CSS alone cannot clear :checked when the viewport grows past B, so the panel reopens on return to narrow; the contract registers no exception for HDR-11",
    # observed in the consumer markup and in the mctl-design reference stories alike: the burger follows the nav
    ("mctl-web", 7): "the toggle follows the panel in DOM order (as in the mctl-design SiteHeader reference stories), so Tab from the toggle cannot reach the panel links; HDR-7 requires the toggle then the panel links in DOM order and the contract registers no exception",
}


def header_cases():
    cases = []
    for site in FIXTURES:
        for hdr, vps in sorted(HDR_VIEWPORTS.items()):
            for vp in vps:
                c = {"id": f"WCA-H-HDR{hdr}-{site}-landing-{vp}", "site": site, "kind": "case",
                     "contract_id": f"HDR-{hdr}", "gate": None, "hdr": hdr, "route_class": "landing",
                     "viewport": vp, "provenance": "[PREVIEW]", "exception": None}
                if site == "fixture-checkbox":
                    c["exception"] = {5: "EX-1", 6: "EX-1", 8: "EX-2", 12: "EX-2"}.get(hdr)
                    if (site, hdr) in KNOWN_GAPS:
                        c["known_gap"] = KNOWN_GAPS[(site, hdr)]
                cases.append(c)
    # a positive control of the HDR-15 detector's meaning: the global 0.01ms reset on top of transition: none must PASS
    cases.append({"id": "WCA-H-HDR15-fixture-reset-landing-375", "site": "fixture-reset", "kind": "case",
                  "contract_id": "HDR-15", "gate": None, "hdr": 15, "route_class": "landing",
                  "viewport": "375", "provenance": "[PREVIEW]", "exception": None})
    for site, (code, classes) in CONSUMERS.items():
        for rc, letter in classes.items():
            for hdr, vps in sorted(HDR_VIEWPORTS.items()):
                if rc == "sensitive" and hdr not in SENSITIVE_HDRS:
                    continue
                for vp in vps:
                    c = {"id": f"WCA-H-HDR{hdr}-{site}-{rc}-{vp}", "site": site, "kind": "case",
                         "contract_id": f"AC-{hdr}-{code}-{letter}", "gate": None, "hdr": hdr,
                         "route_class": rc, "viewport": vp, "provenance": "not-run",
                         "exception": EXCEPTIONS.get(site, {}).get(hdr)}
                    if (site, hdr) in KNOWN_GAPS:
                        c["known_gap"] = KNOWN_GAPS[(site, hdr)]
                    cases.append(c)
    for hdr, defect in ((8, "no-escape"), (12, "focus-lost"), (5, "no-aria-expanded"), (15, "motion-ignored")):
        cases.append({"id": f"WCA-H-HDR{hdr}-fixture-broken-{defect}-375", "site": "fixture-broken",
                      "kind": "negative-control", "contract_id": f"HDR-{hdr}", "gate": None, "hdr": hdr,
                      "defect": defect, "route_class": "landing", "viewport": "375",
                      "provenance": "[PREVIEW]", "exception": None})
    return cases


def asset_cases():
    WAI = "web-asset-integrity"
    base = {"site": "fixture-reference", "kind": "case", "contract_id": WAI, "route_class": None,
            "viewport": None, "provenance": "[PREVIEW]", "exception": None}
    cases = []
    for version in ("0.21.0", "0.20.2"):
        for sheet in ("mctl.css", "global.css", "prose.css", "site.css"):
            cases.append({**base, "id": f"WCA-A-G1-sha256-{version}-{sheet}", "gate": "G1", "behaviour": "sha256",
                          "version": version, "sheet": sheet, "target": "fixtures/manifest-0.21.0.test-only.json"})
    for gate, name in (("G2", "sri-valid-applies"), ("G2", "sri-mismatch-blocked"), ("G2", "no-acao-blocked"),
                       ("G2", "modeb-parity"), ("G2", "csp-allow-applies"), ("G2", "csp-deny-blocked"),
                       ("G3", "cache-versioned"), ("G3", "cache-floating"), ("G3", "origin-down-nojs")):
        cases.append({**base, "id": f"WCA-A-{gate}-{name}", "gate": gate, "behaviour": name})
    cases.append({**base, "id": "WCA-A-G4-exact-pinning", "gate": "G4", "behaviour": "exact-pinning",
                  "provenance": "not-run"})
    for gate, name in (("G1", "bad-sha"), ("G2", "sri-mismatch"), ("G2", "no-acao"), ("G2", "csp-deny")):
        c = {**base, "id": f"WCA-A-{gate}-control-{name}", "site": "fixture-broken", "kind": "negative-control",
             "gate": gate, "behaviour": "sha256" if name == "bad-sha" else f"control-{name}"}
        if name == "bad-sha":
            c.update({"version": "0.21.0", "sheet": "site.css", "target": "fixtures/broken/manifest-bad-sha.test-only.json"})
        cases.append(c)
    for name in ("prod-host", "oauth-path", "design-host", "expected-blocked"):
        cases.append({**base, "id": f"WCA-A-ISO-guard-{name}", "gate": "ISO", "contract_id": None,
                      "behaviour": f"guard-{name}"})
    return cases


def build():
    return {"schema_version": 1,
            "note": "Case catalogue for mctlhq/mctl-gitops#2929; generated by report/gen_cases.py. "
                    "Preview assurance only; not production conformance.",
            "cases": header_cases() + asset_cases()}


def main(argv):
    text = json.dumps(build(), indent=1, sort_keys=False) + "\n"
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text() != text:
            print("cases.json is out of date: run report/gen_cases.py", file=sys.stderr)
            return 1
        print("cases.json: OK (matches gen_cases.py)")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT} ({len(build()['cases'])} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
