#!/usr/bin/env python3
"""scripts/portal-catalogue-land.py writes only what cannot widen exposure."""
import base64
import copy
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("land", ROOT / "scripts" / "portal-catalogue-land.py")
land = importlib.util.module_from_spec(spec)
sys.modules["land"] = land  # dataclasses looks its module up here
spec.loader.exec_module(land)

A = land.ALLOWLISTS
TODAY = "2026-11-07"
BUMP = "portal-allowlist/api-1234567"
# Literal, as `gh pr list --json author` printed it for bump PR #2420.
BOT = {"is_bot": True, "login": "app/mctl-agents"}


def allowlist(**tools):
    return {"tools": [{"name": k, "enabled": v, "reason": "r"} for k, v in tools.items()]}


def baseline(enabled=("on",), total=2):
    return {"servers": {"api": {"tools_total": total, "tools_enabled": len(enabled),
                                "enabled_tools": list(enabled), "recorded": "2026-01-01"}}}


class FakeGh:
    """A repository of branches, holding JSON files. Records every write."""

    def __init__(self, files=None, prs=None, by_branch=None, branches=None):
        main = {
            f"{A}/mapping.json": {"servers": {"api": {"vendored": True}}},
            f"{A}/catalogue.json": {"servers": {"api": ["on", "off"]}},
            f"{A}/baseline.json": baseline(),
            f"{A}/api.json": allowlist(on=True, off=False, new=False),
        }
        main.update(files or {})
        self.refs = {"m" * 40: main, "b" * 40: copy.deepcopy(main)}
        self.prs = prs or []
        self.by_branch = by_branch or []
        self.branches = branches or {}
        self.writes = []

    def main_sha(self):
        return "m" * 40

    def read(self, path, ref, rewrite=False):
        if path not in self.refs[ref]:
            raise land.NotFound(path)
        return self.refs[ref][path], f"blob-{ref[0]}-{path.rsplit('/', 1)[-1]}"

    def open_prs(self):
        return self.prs

    def prs_for(self, branch):
        return self.by_branch

    def branch_head(self, branch):
        return self.branches.get(branch)

    def create_branch(self, branch, sha):
        self.writes.append(("branch", branch, sha))

    def put(self, path, text, blob, branch, message):
        self.writes.append(("put", path.rsplit("/", 1)[-1], branch, json.loads(text), blob))

    def create_pr(self, branch, title, body):
        self.writes.append(("pr", branch))
        # The REST shape: `url` is the API endpoint.
        return {"number": 9, "url": "https://api.github.com/repos/x/y/pulls/9",
                "html_url": "https://github.com/x/y/pull/9"}

    def puts(self):
        return [w for w in self.writes if w[0] == "put"]


def bump_pr(**over):
    return {"number": 7, "url": "https://github.com/x/y/pull/7", "headRefName": BUMP, "headRefOid": "b" * 40,
            "isCrossRepository": False, "author": BOT, **over}


class Land(unittest.TestCase):
    def test_disabled_tool_with_no_bump_pr_opens_a_new_pr(self):
        gh = FakeGh()
        out = land.land(gh, "api", ["on", "off", "new"], TODAY)
        self.assertIn('href="https://github.com/x/y/pull/9"', out)
        self.assertEqual(gh.writes[0][0], "branch")
        self.assertRegex(gh.writes[0][1], r"^portal-catalogue/api-[0-9a-f]{7}$")
        put = {w[1]: w[3] for w in gh.puts()}
        self.assertEqual(put["catalogue.json"]["servers"]["api"], ["on", "off", "new"])
        entry = put["baseline.json"]["servers"]["api"]
        self.assertEqual(entry["tools_total"], 3)
        self.assertEqual(entry["recorded"], TODAY)
        # The whole point: what may be enabled does not move.
        self.assertEqual(entry["enabled_tools"], ["on"])
        self.assertEqual(entry["tools_enabled"], 1)
        self.assertEqual(gh.writes[-1][0], "pr")

    def test_disabled_tool_goes_into_the_open_bump_pr(self):
        gh = FakeGh(prs=[bump_pr()])
        out = land.land(gh, "api", ["on", "off", "new"], TODAY)
        self.assertIn("#7", out)
        self.assertFalse([w for w in gh.writes if w[0] in ("branch", "pr")])
        self.assertTrue(all(w[2] == BUMP for w in gh.puts()))

    def test_decision_is_read_from_the_bump_branch_not_main(self):
        gh = FakeGh(prs=[bump_pr()])
        gh.refs["m" * 40][f"{A}/api.json"] = allowlist(on=True, off=False)
        gh.refs["b" * 40][f"{A}/api.json"] = allowlist(on=True, off=False, new=False)
        land.land(gh, "api", ["on", "off", "new"], TODAY)
        self.assertTrue(gh.puts())

    def assert_refused(self, gh, live, needle):
        out = land.land(gh, "api", live, TODAY)
        self.assertIn(needle, out)
        self.assertEqual(gh.writes, [], "a refusal must write nothing")

    def test_added_tool_enabled_is_refused_even_if_baseline_allows_it(self):
        gh = FakeGh(files={f"{A}/api.json": allowlist(on=True, off=False, new=True),
                           f"{A}/baseline.json": baseline(enabled=("on", "new"))})
        self.assert_refused(gh, ["on", "off", "new"], "would turn on new")

    def test_added_tool_with_no_decision_is_refused(self):
        self.assert_refused(FakeGh(), ["on", "off", "ghost"], "no decision")

    def test_enabled_tool_leaving_the_portal_is_refused(self):
        self.assert_refused(FakeGh(), ["off"], "enabled tools left the portal")

    def test_widening_by_name_is_refused(self):
        gh = FakeGh(files={f"{A}/api.json": allowlist(on=True, off=True, new=False)})
        self.assert_refused(gh, ["on", "off", "new"], "widens exposure")

    def test_widening_by_count_is_refused(self):
        doc = baseline(enabled=("on", "off"))
        doc["servers"]["api"]["tools_enabled"] = 1
        gh = FakeGh(files={f"{A}/api.json": allowlist(on=True, off=True, new=False), f"{A}/baseline.json": doc})
        self.assert_refused(gh, ["on", "off", "new"], "baseline.json allows 1")

    def test_bump_pr_with_edited_baseline_is_left_alone(self):
        gh = FakeGh(prs=[bump_pr()])
        gh.refs["b" * 40][f"{A}/baseline.json"] = baseline(enabled=("on", "new"))
        self.assert_refused(gh, ["on", "off", "new"], "a person is deciding")

    def test_bump_pr_the_bot_did_not_open_is_not_trusted(self):
        gh = FakeGh(prs=[bump_pr(author={"login": "someone"})])
        self.assert_refused(gh, ["on", "off", "new"], "nothing was written")

    def test_bump_pr_from_a_fork_is_not_trusted(self):
        gh = FakeGh(prs=[bump_pr(isCrossRepository=True)])
        self.assert_refused(gh, ["on", "off", "new"], "nothing was written")

    def test_two_bump_prs_are_refused(self):
        gh = FakeGh(prs=[bump_pr(), bump_pr(number=8, headRefName="portal-allowlist/api-7654321")])
        self.assert_refused(gh, ["on", "off", "new"], "more than one")

    def test_another_servers_bump_pr_does_not_match(self):
        gh = FakeGh(prs=[bump_pr(headRefName="portal-allowlist/api-extra-1234567")])
        land.land(gh, "api", ["on", "off", "new"], TODAY)
        self.assertEqual(gh.writes[0][0], "branch")

    def test_open_proposal_is_not_duplicated(self):
        gh = FakeGh(by_branch=[{"number": 5, "url": "https://github.com/x/y/pull/5", "state": "OPEN"}])
        self.assert_refused(gh, ["on", "off", "new"], "already proposed")

    def test_merged_proposal_does_not_block_a_new_one(self):
        gh = FakeGh(by_branch=[{"number": 5, "url": "https://github.com/x/y/pull/5", "state": "MERGED"}])
        out = land.land(gh, "api", ["on", "off", "new"], TODAY)
        self.assertNotIn("was closed", out)
        self.assertTrue(gh.puts())

    def test_leftover_branch_continues_from_its_head(self):
        live = ["on", "off", "new"]
        digest = land.hashlib.sha256("\n".join(live).encode()).hexdigest()[:7]
        branch = f"portal-catalogue/api-{digest}"
        gh = FakeGh(branches={branch: "b" * 40})
        gh.refs["b" * 40][f"{A}/catalogue.json"] = {"servers": {"api": live}}
        land.land(gh, "api", live, TODAY)
        self.assertFalse([w for w in gh.writes if w[0] == "branch"])
        puts = gh.puts()
        self.assertEqual([w[1] for w in puts], ["baseline.json"], "the catalogue commit is already there")
        self.assertEqual(puts[0][4], "blob-b-baseline.json", "a main blob sha would answer 409 forever")
        self.assertEqual(gh.writes[-1][0], "pr")

    def test_closed_proposal_is_not_reopened(self):
        gh = FakeGh(by_branch=[{"number": 5, "url": "https://github.com/x/y/pull/5", "state": "CLOSED"}])
        self.assert_refused(gh, ["on", "off", "new"], "was closed")

    def test_unvendored_server_is_refused(self):
        gh = FakeGh(files={f"{A}/mapping.json": {"servers": {"api": {"vendored": False}}}})
        self.assert_refused(gh, ["on", "off", "new"], "not a vendored server")

    def test_rerun_of_a_landed_bump_writes_nothing(self):
        gh = FakeGh(prs=[bump_pr()])
        gh.refs["b" * 40][f"{A}/catalogue.json"] = {"servers": {"api": ["on", "off", "new"]}}
        # The script's own earlier write: main still records the old total.
        doc = baseline(total=3)
        doc["servers"]["api"]["recorded"] = TODAY
        gh.refs["b" * 40][f"{A}/baseline.json"] = doc
        out = land.land(gh, "api", ["on", "off", "new"], TODAY)
        self.assertEqual(gh.writes, [])
        self.assertIn("already carries", out)


class Unknowns(unittest.TestCase):
    """Could not observe is never observed absent."""

    def assert_unknown(self, **kw):
        gh = FakeGh()
        for name, value in kw.items():
            gh.refs["m" * 40][f"{A}/{name}.json"] = value
        with self.assertRaises((land.Unknown, KeyError, TypeError)):
            land.land(gh, "api", ["on", "off", "new"], TODAY)
        self.assertEqual(gh.writes, [])

    def test_malformed_documents(self):
        self.assert_unknown(api={"tools": []})
        self.assert_unknown(api={"tools": [{"enabled": True}]})
        self.assert_unknown(api={"tools": [{"name": "new", "enabled": "no"}]})
        self.assert_unknown(catalogue={"servers": {}})
        self.assert_unknown(baseline={"servers": {}})
        self.assert_unknown(api=allowlist(**{"bad\nname": False}))
        self.assert_unknown(catalogue={"servers": {"api": ["on", "bad\nname"]}})

    def test_bad_live_lists(self):
        for live in ([], ["on", "on"], ["<b>x</b>"], [1]):
            gh = FakeGh()
            with self.assertRaises(land.Unknown):
                land.land(gh, "api", live, TODAY)
            self.assertEqual(gh.writes, [])

    def test_missing_allowlist_is_not_treated_as_no_decision(self):
        gh = FakeGh()
        del gh.refs["m" * 40][f"{A}/api.json"]
        with self.assertRaises(land.NotFound):
            land.land(gh, "api", ["on", "off", "new"], TODAY)
        self.assertEqual(gh.writes, [])

    def test_bad_server_id(self):
        with self.assertRaises(land.Unknown):
            land.land(FakeGh(), "../api", ["on"], TODAY)


class GhClient(unittest.TestCase):
    """The real client's reading of `gh` results."""

    def client(self, stdout="", rc=0, stderr=""):
        gh = land.Gh("x/y")

        class P:
            pass
        P.returncode, P.stdout, P.stderr = rc, stdout, stderr
        land.subprocess.run, self._orig = (lambda *a, **k: P), land.subprocess.run
        self.addCleanup(setattr, land.subprocess, "run", self._orig)
        return gh

    def test_full_listing_is_unknown(self):
        gh = self.client(json.dumps([{"number": i} for i in range(land.PR_LIMIT)]))
        with self.assertRaises(land.Unknown):
            gh.open_prs()

    def test_failed_listing_is_unknown_not_empty(self):
        with self.assertRaises(land.Unknown):
            self.client(rc=1, stderr="HTTP 502").open_prs()

    def test_malformed_listing_is_unknown(self):
        with self.assertRaises(land.Unknown):
            self.client("oops").open_prs()
        with self.assertRaises(land.Unknown):
            self.client('{"a":1}').open_prs()

    def test_only_404_means_branch_absent(self):
        self.assertIsNone(self.client(rc=1, stderr="gh: Not Found (HTTP 404)").branch_head("b"))
        with self.assertRaises(land.Unknown):
            self.client(rc=1, stderr="HTTP 500").branch_head("b")

    def test_read_decodes_contents(self):
        body = {"encoding": "base64", "sha": "s", "content": base64.b64encode(b'{"a": 1}').decode()}
        self.assertEqual(self.client(json.dumps(body)).read("p", "r"), ({"a": 1}, "s"))
        with self.assertRaises(land.Unknown):
            self.client(json.dumps({"encoding": "none", "sha": "s"})).read("p", "r")

    def test_a_file_a_rewrite_would_reformat_is_refused(self):
        body = {"encoding": "base64", "sha": "s", "content": base64.b64encode(b'{"a": 1}').decode()}
        with self.assertRaises(land.Unknown):
            self.client(json.dumps(body)).read("p", "r", rewrite=True)
        clean = {**body, "content": base64.b64encode(land.dumps({"a": 1}).encode()).decode()}
        self.assertEqual(self.client(json.dumps(clean)).read("p", "r", rewrite=True), ({"a": 1}, "s"))


class RealFiles(unittest.TestCase):
    def test_dumps_reproduces_the_committed_files(self):
        # A rewrite must not reformat either file, or the diff hides the change.
        for name in ("catalogue.json", "baseline.json"):
            text = (ROOT / A / name).read_text(encoding="utf-8")
            self.assertEqual(land.dumps(json.loads(text)), text, name)


if __name__ == "__main__":
    unittest.main()
