#!/usr/bin/env python3
"""Probe that a Cloudflare Access login can still reach a working IdP (#1329).

On 2026-09-21 Google sign-in to every Access application had been broken for
an unknown time: the upstream OAuth client was deleted, Access kept serving
its login page, and the only signal was a person failing to sign in. The
failure shows before any credential is entered, at the IdP's authorization
endpoint, so this follows a browser's first steps without one:

  1. GET the application with no session. Access must intercept it and
     redirect to the team domain's login page.
  2. GET that page. It must offer the IdP, as a link to the IdP's
     authorization endpoint carrying the client id Git declares, the Access
     callback, and an S256 PKCE challenge.
  3. GET that link. The IdP must answer by starting a login (a redirect to its
     login UI), not with an error such as an unknown client.

Nothing signs in, and no credential is held: every request is anonymous.
Step 3 leaves one unfinished authorization request in the IdP, which expires
on its own.

The expected client id is read from the Cloudflare root, so a ZITADEL client
recreated with a new id fails here instead of failing the next person.

Usage:
    access-login-probe.py [--repo-root DIR]
    access-login-probe.py --selftest

Exit status: 0 every target healthy, 1 a target is broken, 2 could not be
determined (network, an unexpected answer). Unknown never reads as healthy.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

TEAM_DOMAIN = "mbank.cloudflareaccess.com"
CALLBACK = f"https://{TEAM_DOMAIN}/cdn-cgi/access/callback"
ZITADEL_IDP_TF = "infrastructure/cloudflare/account/zitadel-idp.tf"


@dataclass(frozen=True)
class Target:
    name: str
    app_url: str
    authorize_url: str  # the IdP's authorization endpoint, scheme+host+path
    login_ui_path: str  # where a healthy IdP redirects to start a login
    client_id_source: str  # file declaring the expected client id


TARGETS = [
    Target(
        name="ZITADEL (access-zitadel-test.mctl.ai)",
        app_url="https://access-zitadel-test.mctl.ai/",
        authorize_url="https://auth.mctl.ai/oauth/v2/authorize",
        login_ui_path="/ui/v2/login/login",
        client_id_source=ZITADEL_IDP_TF,
    ),
]


class Broken(Exception):
    """The target answered, and the answer means sign-in is broken."""


class Unknown(Exception):
    """The target could not be observed; nothing is known about it."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def fetch(url: str) -> tuple[int, str, str]:
    """GET without following redirects: (status, Location, body)."""
    req = urllib.request.Request(url, headers={"User-Agent": "mctl-access-login-probe"})
    try:
        with _opener.open(req, timeout=20) as resp:
            return resp.status, resp.headers.get("Location", ""), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # 3xx and 4xx/5xx land here
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        return e.code, e.headers.get("Location", "") if e.headers else "", body
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Unknown(f"GET {redact(url)}: {e}") from e


def redact(url: str) -> str:
    """Per-request values make every message unique; keep host and path."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def expected_client_id(repo_root: str, source: str) -> str:
    path = os.path.join(repo_root, source)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise Unknown(f"cannot read {source}: {e}") from e
    return parse_client_id_default(text, source)


def parse_client_id_default(text: str, source: str) -> str:
    m = re.search(r'variable\s+"zitadel_access_client_id"\s*\{(.*?)\n\}', text, re.S)
    d = m and re.search(r'^\s*default\s*=\s*"([0-9]+)"', m.group(1), re.M)
    if not d:
        raise Unknown(f"no numeric default for zitadel_access_client_id in {source}")
    return d.group(1)


def idp_links(page: str, authorize_url: str) -> list[str]:
    """Every link on the login page that points at the IdP's endpoint."""
    links = [html.unescape(h) for h in re.findall(r'href="([^"]+)"', page)]
    return [l for l in links if l.split("?", 1)[0] == authorize_url]


def judge_link(link: str, client_id: str) -> None:
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(link).query))
    want = {
        "client_id": client_id,
        "redirect_uri": CALLBACK,
        "response_type": "code",
        "code_challenge_method": "S256",
    }
    wrong = [f"{k}={q.get(k)!r} (want {v!r})" for k, v in want.items() if q.get(k) != v]
    if not q.get("code_challenge"):
        wrong.append("no code_challenge")
    if wrong:
        raise Broken("Access sends the IdP a request Git does not describe: " + ", ".join(wrong))


def judge_authorize(status: int, location: str, body: str, t: Target) -> None:
    if status in (301, 302, 303, 307, 308):
        loc = urllib.parse.urlsplit(location)
        q = dict(urllib.parse.parse_qsl(loc.query))
        if "error" in q:
            raise Broken(f"IdP refused the authorization request: {q['error']}: {q.get('error_description', '')}")
        if loc.path == t.login_ui_path and q.get("authRequest"):
            return
        raise Unknown(f"IdP redirected somewhere unexpected: {redact(location)}")
    if 400 <= status < 500:
        raise Broken(f"IdP refused the authorization request: HTTP {status} {body[:200].strip()}")
    raise Unknown(f"IdP answered HTTP {status}")


def probe(t: Target, repo_root: str) -> None:
    client_id = expected_client_id(repo_root, t.client_id_source)

    status, location, _ = fetch(t.app_url)
    login = urllib.parse.urlsplit(location)
    if status not in (302, 303) or login.netloc != TEAM_DOMAIN or not login.path.startswith("/cdn-cgi/access/login/"):
        if 200 <= status < 300:
            raise Broken(f"Access did not intercept {t.app_url}: HTTP {status} with no login redirect")
        raise Unknown(f"{t.app_url} answered HTTP {status} {redact(location)}")

    status, _, page = fetch(location)
    if status != 200:
        raise Unknown(f"Access login page answered HTTP {status}")
    links = idp_links(page, t.authorize_url)
    if not links:
        # Unknown, not Broken: the page loaded, but finding no link may be
        # this scraper missing changed markup as much as the IdP being gone.
        raise Unknown(f"found no link to {t.authorize_url} on the Access login page")
    for link in links:
        judge_link(link, client_id)

    judge_authorize(*fetch(links[0]), t)


def run(repo_root: str, targets=TARGETS, check=probe) -> int:
    # A confirmed break outranks anything unknown elsewhere, in any order:
    # the alert for an outage must not be downgraded to "could not tell".
    broken = unknown = False
    for t in targets:
        try:
            check(t, repo_root)
            print(f"ok      {t.name}")
        except Broken as e:
            print(f"BROKEN  {t.name}: {e}")
            broken = True
        except Unknown as e:
            print(f"UNKNOWN {t.name}: {e}")
            unknown = True
        except Exception as e:  # a crash here proves nothing about the IdP
            print(f"UNKNOWN {t.name}: probe failed: {type(e).__name__}: {e}")
            unknown = True
    return 1 if broken else 2 if unknown else 0


def selftest() -> int:
    t = TARGETS[0]
    good = (
        f"{t.authorize_url}?client_id=42&code_challenge=abc&code_challenge_method=S256"
        f"&redirect_uri={urllib.parse.quote(CALLBACK, safe='')}&response_type=code&state=s"
    )
    cases = []

    def case(name, fn, expect):
        try:
            fn()
            got = None
        except (Broken, Unknown) as e:
            got = type(e)
        ok = got is expect
        cases.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {name}")

    page = f'<a class="js-idp" href="{html.escape(good).replace("/", "&#x2F;").replace("=", "&#x3D;")}">ZITADEL</a>'
    case("an escaped IdP link on the login page is found",
         lambda: None if idp_links(page, t.authorize_url) == [good] else (_ for _ in ()).throw(Broken("not found")),
         None)
    case("a matching link is healthy", lambda: judge_link(good, "42"), None)
    case("a different client id is broken", lambda: judge_link(good, "43"), Broken)
    case("a link with no PKCE challenge is broken",
         lambda: judge_link(good.replace("code_challenge=abc&", ""), "42"), Broken)
    case("plain PKCE is broken", lambda: judge_link(good.replace("S256", "plain"), "42"), Broken)
    case("a redirect to the login UI is healthy",
         lambda: judge_authorize(302, "https://auth.mctl.ai/ui/v2/login/login?authRequest=V2_1", "", t), None)
    case("an unknown client (400) is broken",
         lambda: judge_authorize(400, "", '{"error":"invalid_request","error_description":"Errors.App.NotFound"}', t),
         Broken)
    case("an error redirect is broken",
         lambda: judge_authorize(302, f"{CALLBACK}?error=invalid_client&state=s", "", t), Broken)
    case("a 5xx is unknown, not healthy", lambda: judge_authorize(502, "", "", t), Unknown)
    case("an unexpected redirect is unknown",
         lambda: judge_authorize(302, "https://auth.mctl.ai/somewhere", "", t), Unknown)
    case("a missing client id default is unknown",
         lambda: parse_client_id_default('variable "zitadel_access_client_id" {\n  type = string\n}', "x"),
         Unknown)
    case("the client id default is parsed",
         lambda: None if parse_client_id_default(
             'variable "zitadel_access_client_id" {\n  default = "123"\n}', "x") == "123"
         else (_ for _ in ()).throw(Broken("wrong")), None)

    def outcome(*kinds):
        def check(target, _root):
            kind = kinds[TARGETS_UNDER_TEST.index(target)]
            if kind:
                raise kind("x")
        return check

    TARGETS_UNDER_TEST[:] = [Target(f"t{i}", "", "", "", "") for i in range(2)]
    for kinds, want in [((Unknown, Broken), 1), ((Broken, Unknown), 1),
                        ((None, Unknown), 2), ((None, KeyError), 2), ((None, None), 0)]:
        got = run(".", TARGETS_UNDER_TEST, outcome(*kinds))
        ok = got == want
        cases.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} run() with {[k.__name__ if k else 'ok' for k in kinds]} exits {want}")
    return 0 if all(cases) else 1


TARGETS_UNDER_TEST: list[Target] = []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--repo-root", default=os.getcwd())
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    return selftest() if a.selftest else run(a.repo_root)


if __name__ == "__main__":
    sys.exit(main())
