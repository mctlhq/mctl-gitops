#!/usr/bin/env bash
# Reconcile the AI Gateway custom providers of one Cloudflare account against a
# declaration file in this repository.
#
#   cloudflare-ai-gateway-custom-providers.sh plan  <declaration.json>
#   cloudflare-ai-gateway-custom-providers.sh apply <declaration.json>
#
# Why a script and not a resource: Nebius and Hetzner are not native AI Gateway
# providers, so the gateway reaches them only through "custom providers", and
# the cloudflare/cloudflare Terraform provider has no resource for those
# (checked at 5.28.1, 2026-10-20; spike #2262). The generic REST provider was
# tried on paper and rejected: Cloudflare wraps every response in an envelope
# the provider compares the declared object against, and its search-based read
# treats a failed listing as "object gone", which is exactly the "could not
# observe" turned into "observed absent" that this repository forbids. Until a
# native resource exists, this script is the declaration's apply path, under
# the same discipline as the OpenTofu roots: plan with a read credential,
# approve, re-plan under the write credential, refuse if the plan moved, apply,
# read back.
#
# Declaration shape (infrastructure/cloudflare/account/ai-gateway-custom-providers.json):
#
#   { "account_id": "<32 hex>",
#     "providers": [ { "slug": "nebius", "name": "...", "base_url": "https://...", "enable": true } ] }
#
# The slug is the identity: the gateway route is <gateway>/custom-<slug>/...,
# so renaming a slug is a delete plus a create, and the plan says so.
#
# Fail-closed everywhere a read can fail: a non-200 listing, a body without
# success=true, a result that is not an array, or a result_info.total_count
# that differs from the number of rows returned (a second page this script does
# not fetch) are all errors, never an empty account. A plan that cannot read
# reports nothing; it does not report "no changes".
#
# Outputs (when GITHUB_OUTPUT is set): digest (sha256 of the canonical change
# set), changes, destroy. The digest is what crosses the plan/apply job
# boundary in cloudflare-apply.yml. With DETAILED_EXITCODE=1 a plan exits 2
# when the change set is not empty, so cloudflare-drift.yml can fail on it the
# way `tofu plan -detailed-exitcode` does. Deletes in apply need ALLOW_DESTROY=1.
#
# Self-test: CLOUDFLARE_GUARD_SELF_TEST=1 cloudflare-ai-gateway-custom-providers.sh
# runs the suite against a throwaway fake of the Cloudflare endpoint (python3
# http.server on localhost). Environment-gated like the sibling guards: $1 is a
# mode and $2 a path, and neither may double as a flag. The suite proves the
# detector both ways: no changes on a converged account, the right changes on
# a mutated one, and an error (not zero changes) when the listing fails.
set -euo pipefail

API_BASE="${CF_API_BASE:-https://api.cloudflare.com/client/v4}"
FIELDS='{slug: .slug, name: .name, base_url: .base_url, enable: .enable}'

die() { echo "::error::$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "$1 is required"; }

# ---------------------------------------------------------------- self-test
if [ "${CLOUDFLARE_GUARD_SELF_TEST:-}" = "1" ]; then
  need python3; need jq; need curl
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"; [ -n "${srv:-}" ] && kill "$srv" 2>/dev/null || true' EXIT
  acc="00000000000000000000000000000001"

  # A fake of /accounts/<acc>/ai-gateway/custom-providers with the envelope
  # Cloudflare uses. Its state and failure mode live in files so a test can
  # mutate the "account" behind the script's back. MODE file: ok | http500 |
  # short (total_count overstated) | garbage (non-JSON body).
  cat > "$tmp/fake.py" <<'PY'
import json, os, sys, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
STATE = sys.argv[2]; MODE = sys.argv[3]; PREFIX = sys.argv[4]
def load():
    with open(STATE) as f: return json.load(f)
def save(rows):
    with open(STATE, "w") as f: json.dump(rows, f)
def mode():
    with open(MODE) as f: return f.read().strip()
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def env(self, result, extra=None):
        body = {"success": True, "errors": [], "messages": [], "result": result}
        if extra: body.update(extra)
        return body
    def read_body(self):
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")
    def auth(self):
        if self.headers.get("authorization") != "Bearer fake-token":
            self.send(403, {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]}); return False
        return True
    def do_GET(self):
        if not self.auth(): return
        if not self.path.startswith(PREFIX): return self.send(404, {"success": False, "errors": [{"code": 7003}]})
        m = mode(); rows = load()
        if m == "http500": return self.send(500, {"success": False, "errors": [{"code": 1000, "message": "boom"}]})
        if m == "garbage": return self.send(200, b"<html>not json</html>")
        total = len(rows) + (1 if m == "short" else 0)
        self.send(200, self.env(rows, {"result_info": {"count": len(rows), "page": 1, "per_page": 50, "total_count": total}}))
    def do_POST(self):
        if not self.auth(): return
        if self.path.split("?")[0] != PREFIX: return self.send(404, {"success": False})
        b = self.read_body(); rows = load()
        if any(r["slug"] == b.get("slug") for r in rows):
            return self.send(400, {"success": False, "errors": [{"code": 2001, "message": "slug exists"}]})
        row = {"id": uuid.uuid4().hex, "slug": b["slug"], "name": b["name"], "base_url": b["base_url"], "enable": b.get("enable", True), "created_at": 1}
        rows.append(row); save(rows); self.send(200, self.env(row))
    def do_PUT(self):
        if not self.auth(): return
        pid = self.path.rsplit("/", 1)[-1]; b = self.read_body(); rows = load()
        for r in rows:
            if r["id"] == pid:
                r.update({k: b[k] for k in ("slug", "name", "base_url", "enable") if k in b}); save(rows); return self.send(200, self.env(r))
        self.send(404, {"success": False, "errors": [{"code": 7003}]})
    def do_DELETE(self):
        if not self.auth(): return
        pid = self.path.rsplit("/", 1)[-1]; rows = load()
        keep = [r for r in rows if r["id"] != pid]
        if len(keep) == len(rows): return self.send(404, {"success": False, "errors": [{"code": 7003}]})
        save(keep); self.send(200, self.env({"id": pid}))
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
  echo '[]' > "$tmp/state.json"; echo ok > "$tmp/mode"
  port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
  python3 -I "$tmp/fake.py" "$port" "$tmp/state.json" "$tmp/mode" "/accounts/$acc/ai-gateway/custom-providers" &
  srv=$!
  for _ in $(seq 1 50); do curl -s -o /dev/null "http://127.0.0.1:$port/" && break; sleep 0.1; done

  decl() { # decl <file> <slug:name:base_url:enable>...
    local f="$1"; shift
    { echo "{\"account_id\": \"$acc\", \"providers\": ["
      local first=1
      for p in "$@"; do IFS=: read -r s n u e <<< "$p"
        [ "$first" = 1 ] || echo ","; first=0
        printf '{"slug":"%s","name":"%s","base_url":"https://%s","enable":%s}' "$s" "$n" "$u" "$e"
      done
      echo "]}"; } > "$f"
  }
  fail=0
  run() { # run <mode> <decl> -> sets rc, out; env passes through
    rc=0; out=$(CLOUDFLARE_GUARD_SELF_TEST='' CF_API_BASE="http://127.0.0.1:$port" CLOUDFLARE_API_TOKEN=fake-token \
                GITHUB_OUTPUT="$tmp/out" GITHUB_STEP_SUMMARY=/dev/null "$self" "$1" "$2" 2>&1) || rc=$?
  }
  expect_rc() { [ "$rc" -eq "$1" ] || { echo "self-test FAILED: $2 — expected exit $1, got $rc"; echo "$out" | sed 's/^/    /'; fail=1; }; }
  expect_out() { grep -qx "$1" "$tmp/out" 2>/dev/null || { echo "self-test FAILED: $2 — wanted output '$1', outputs were:"; cat "$tmp/out" 2>/dev/null | sed 's/^/    /'; fail=1; }; }

  decl "$tmp/d.json" "nebius:Nebius:api.nebius.example:true" "hetzner:Hetzner:inference.hetzner.example/api:true"

  : > "$tmp/out"; run plan "$tmp/d.json"; expect_rc 0 "plan against an empty account"
  expect_out "changes=2" "plan against an empty account counts two creates"; expect_out "destroy=0" "no destroy on an empty account"
  : > "$tmp/out"; DETAILED_EXITCODE=1 run plan "$tmp/d.json"; expect_rc 2 "detailed exit code with pending changes"

  : > "$tmp/out"; run apply "$tmp/d.json"; expect_rc 0 "apply two creates"
  : > "$tmp/out"; run plan "$tmp/d.json"; expect_rc 0 "plan after apply"; expect_out "changes=0" "converged account plans no changes"
  : > "$tmp/out"; DETAILED_EXITCODE=1 run plan "$tmp/d.json"; expect_rc 0 "detailed exit code on a converged account"
  [ "$(jq 'length' "$tmp/state.json")" = 2 ] || { echo "self-test FAILED: fake account holds $(jq length "$tmp/state.json") rows after apply"; fail=1; }

  # Mutate the account behind the script's back: one field changed, one
  # provider nobody declared. The detector must go red, and the undeclared
  # one must count as a destroy that apply refuses without ALLOW_DESTROY.
  jq '(.[] | select(.slug=="nebius") | .base_url) = "https://elsewhere.example" | . + [{"id":"deadbeef","slug":"foreign","name":"Foreign","base_url":"https://foreign.example","enable":true}]' \
    "$tmp/state.json" > "$tmp/state2.json" && mv "$tmp/state2.json" "$tmp/state.json"
  : > "$tmp/out"; run plan "$tmp/d.json"; expect_rc 0 "plan on a mutated account"
  expect_out "changes=2" "mutation counts one update and one delete"; expect_out "destroy=1" "the undeclared provider is a destroy"
  : > "$tmp/out"; run apply "$tmp/d.json"; expect_rc 1 "apply with a pending destroy and no ALLOW_DESTROY"
  [ "$(jq 'map(select(.slug=="foreign")) | length' "$tmp/state.json")" = 1 ] || { echo "self-test FAILED: refused apply still deleted the undeclared provider"; fail=1; }
  : > "$tmp/out"; ALLOW_DESTROY=1 run apply "$tmp/d.json"; expect_rc 0 "apply with ALLOW_DESTROY converges"
  : > "$tmp/out"; run plan "$tmp/d.json"; expect_out "changes=0" "converged again after the destroy"
  [ "$(jq -r 'map(select(.slug=="nebius")) | .[0].base_url' "$tmp/state.json")" = "https://api.nebius.example" ] || { echo "self-test FAILED: update did not restore base_url"; fail=1; }

  # Reads that fail must be errors, not empty accounts: if any of these came
  # back exit 0 the plan would be "2 to create" against a full account.
  for m in http500 short garbage; do
    echo "$m" > "$tmp/mode"; : > "$tmp/out"; run plan "$tmp/d.json"
    expect_rc 1 "listing failure mode '$m' is an error"
    if grep -q '^changes=' "$tmp/out" 2>/dev/null; then echo "self-test FAILED: mode '$m' still reported a change count"; fail=1; fi
  done
  echo ok > "$tmp/mode"
  : > "$tmp/out"
  rc=0; out=$(CLOUDFLARE_GUARD_SELF_TEST='' CF_API_BASE="http://127.0.0.1:$port" CLOUDFLARE_API_TOKEN=wrong GITHUB_OUTPUT="$tmp/out" GITHUB_STEP_SUMMARY=/dev/null "$self" plan "$tmp/d.json" 2>&1) || rc=$?
  expect_rc 1 "a refused credential is an error"

  # Declarations that cannot mean one thing are refused before any request.
  decl "$tmp/dup.json" "nebius:A:a.example:true" "nebius:B:b.example:true"
  : > "$tmp/out"; run plan "$tmp/dup.json"; expect_rc 1 "duplicate slugs are refused"
  printf '{"account_id":"%s","providers":[{"slug":"Bad Slug","name":"x","base_url":"https://x.example","enable":true}]}' "$acc" > "$tmp/slug.json"
  : > "$tmp/out"; run plan "$tmp/slug.json"; expect_rc 1 "a slug outside [a-z0-9-] is refused"
  printf '{"account_id":"%s","providers":[{"slug":"ok","name":"x","base_url":"http://x.example","enable":true}]}' "$acc" > "$tmp/http.json"
  : > "$tmp/out"; run plan "$tmp/http.json"; expect_rc 1 "a non-https base_url is refused"
  : > "$tmp/out"; run plan "$tmp/missing.json"; expect_rc 1 "a missing declaration is an error"
  : > "$tmp/out"; run frobnicate "$tmp/d.json"; expect_rc 1 "an unknown mode is refused"

  [ "$fail" -eq 0 ] || exit 1
  echo "self-test OK"
  exit 0
fi

# ------------------------------------------------------------------- main
MODE="${1:?usage: $0 plan|apply <declaration.json>}"
DECL="${2:?usage: $0 plan|apply <declaration.json>}"
case "$MODE" in plan|apply) ;; *) die "mode must be plan or apply, got '$MODE'" ;; esac
need jq; need curl
[ -n "${CLOUDFLARE_API_TOKEN:-}" ] || die "CLOUDFLARE_API_TOKEN is not set"
[ -f "$DECL" ] || die "declaration not found: $DECL"

# Declaration: validated before the first request, so a malformed file never
# produces a plan that reads as "delete everything".
jq -e 'type == "object" and (.account_id | type == "string" and test("^[0-9a-f]{32}$")) and (.providers | type == "array")' "$DECL" >/dev/null \
  || die "$DECL: expected {account_id: <32 hex>, providers: [...]}"
jq -e '.providers | all(type == "object" and (.slug | type == "string" and test("^[a-z0-9-]+$")) and (.name | type == "string" and length > 0) and (.base_url | type == "string" and test("^https://")) and (.enable | type == "boolean"))' "$DECL" >/dev/null \
  || die "$DECL: every provider needs slug [a-z0-9-], name, https base_url and boolean enable"
dups=$(jq -r '[.providers[].slug] | group_by(.) | map(select(length > 1) | .[0]) | .[]' "$DECL")
[ -z "$dups" ] || die "$DECL: duplicate slug(s): $dups"
ACCOUNT=$(jq -r .account_id "$DECL")
LIST_URL="$API_BASE/accounts/$ACCOUNT/ai-gateway/custom-providers"

# api <method> <url> <out-file> [json-body] -> prints the HTTP status code and
# leaves the body in <out-file>. A function that set a variable would lose it
# to the $(...) subshell its callers run it in. Never echoes the token; -sS
# keeps curl's own errors visible.
api() {
  local method="$1" url="$2" out="$3" body="${4:-}"
  if [ -n "$body" ]; then
    curl -sS -o "$out" -w '%{http_code}' -X "$method" -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' --data "$body" "$url" \
      || die "curl failed: $method $url"
  else
    curl -sS -o "$out" -w '%{http_code}' -X "$method" -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "$url" \
      || die "curl failed: $method $url"
  fi
}

# The one read everything else rests on. Each check is a distinct way the
# listing can be wrong without being empty.
read_live() {
  local body code
  body=$(mktemp)
  code=$(api GET "$LIST_URL?per_page=50" "$body")
  [ "$code" = "200" ] || die "listing custom providers: HTTP $code ($(jq -r '.errors[0].message? // "no error message"' "$body" 2>/dev/null || echo 'unparseable body'))"
  jq -e . "$body" >/dev/null 2>&1 || die "listing custom providers: body is not JSON"
  jq -e '.success == true and (.result | type == "array")' "$body" >/dev/null || die "listing custom providers: success is not true or result is not an array"
  jq -e '(.result_info.total_count | type == "number") and .result_info.total_count == (.result | length)' "$body" >/dev/null \
    || die "listing custom providers: result_info.total_count ($(jq '.result_info.total_count' "$body")) differs from the $(jq '.result | length' "$body") rows returned; refusing to plan from a partial list"
  jq -c '.result' "$body"
  rm -f "$body"
}

# diff <live-json> -> canonical change set
#   {creates: [decl...], updates: [{id, slug, from, to}], deletes: [{id, slug, ...}]}
diff_sets() {
  jq -c --argjson live "$1" --slurpfile d "$DECL" -n "
    ([\$d[0].providers[] | $FIELDS] | sort_by(.slug)) as \$decl
    | ([\$live[] | {id: .id} + $FIELDS] | sort_by(.slug)) as \$cur
    | ([\$cur[].slug]) as \$cur_slugs
    | ([\$decl[].slug]) as \$decl_slugs
    | {creates: [\$decl[] | select(.slug as \$s | \$cur_slugs | index(\$s) | not)],
       updates: [\$decl[] as \$want | \$cur[] | select(.slug == \$want.slug) | select(($FIELDS) != \$want) | {id: .id, slug: .slug, from: ($FIELDS), to: \$want}],
       deletes: [\$cur[] | select(.slug as \$s | \$decl_slugs | index(\$s) | not)]}"
}

summarize() { # summarize <changeset> <heading>
  local cs="$1" heading="$2"
  {
    echo "### $heading"
    echo
    echo "| create | update | **destroy** |"
    echo "| --- | --- | --- |"
    echo "| $(jq '.creates | length' <<< "$cs") | $(jq '.updates | length' <<< "$cs") | **$(jq '.deletes | length' <<< "$cs")** |"
    echo
    jq -r '(.creates[] | "- create `\(.slug)`: \(.name), \(.base_url), enable=\(.enable)"),
           (.updates[] | "- update `\(.slug)`: \(.from | del(.slug)) -> \(.to | del(.slug))"),
           (.deletes[] | "- **destroy** `\(.slug)` (id \(.id)): \(.name), \(.base_url)")' <<< "$cs"
    if [ "$(jq '(.creates + .updates + .deletes) | length' <<< "$cs")" = "0" ]; then echo "- no changes"; fi
    echo
  } | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
}

live=$(read_live)
cs=$(diff_sets "$live")
changes=$(jq '(.creates + .updates + .deletes) | length' <<< "$cs")
destroy=$(jq '.deletes | length' <<< "$cs")
digest=$(jq -S -c . <<< "$cs" | sha256sum | cut -d' ' -f1)

if [ "$MODE" = "plan" ]; then
  summarize "$cs" "AI Gateway custom providers: plan (account $ACCOUNT)"
  echo "digest ${digest:0:16}, $changes change(s), $destroy destroy"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then { echo "digest=$digest"; echo "changes=$changes"; echo "destroy=$destroy"; } >> "$GITHUB_OUTPUT"; fi
  if [ "${DETAILED_EXITCODE:-}" = "1" ] && [ "$changes" != "0" ]; then exit 2; fi
  exit 0
fi

# ---- apply
summarize "$cs" "AI Gateway custom providers: apply (account $ACCOUNT)"
if [ "$destroy" != "0" ] && [ "${ALLOW_DESTROY:-}" != "1" ]; then
  die "this change set destroys $destroy custom provider(s) and ALLOW_DESTROY is not set; nothing was changed"
fi

write() { # write <method> <url> <body> <what>
  local out code
  out=$(mktemp)
  code=$(api "$1" "$2" "$out" "$3")
  case "$code" in 2*) ;; *) die "$4: HTTP $code $(jq -c '.errors? // .' "$out" 2>/dev/null || true)" ;; esac
  jq -e '.success == true' "$out" >/dev/null || die "$4: success is not true: $(jq -c '.errors? // .' "$out" 2>/dev/null || true)"
  rm -f "$out"
}
while IFS= read -r p; do
  [ -n "$p" ] || continue
  write POST "$LIST_URL" "$p" "create $(jq -r .slug <<< "$p")"
  echo "created $(jq -r .slug <<< "$p")"
done < <(jq -c '.creates[]' <<< "$cs")
while IFS= read -r u; do
  [ -n "$u" ] || continue
  write PUT "$LIST_URL/$(jq -r .id <<< "$u")" "$(jq -c .to <<< "$u")" "update $(jq -r .slug <<< "$u")"
  echo "updated $(jq -r .slug <<< "$u")"
done < <(jq -c '.updates[]' <<< "$cs")
while IFS= read -r d; do
  [ -n "$d" ] || continue
  write DELETE "$LIST_URL/$(jq -r .id <<< "$d")" "" "delete $(jq -r .slug <<< "$d")"
  echo "deleted $(jq -r .slug <<< "$d")"
done < <(jq -c '.deletes[]' <<< "$cs")

# Read back: the apply is done when the account matches the declaration, not
# when the last request returned 200.
after=$(diff_sets "$(read_live)")
remaining=$(jq '(.creates + .updates + .deletes) | length' <<< "$after")
if [ "$remaining" != "0" ]; then
  summarize "$after" "AI Gateway custom providers: STILL DIFFERENT after apply"
  die "after apply the account still differs from the declaration in $remaining place(s)"
fi
echo "applied: $changes change(s); the account now matches $DECL"
