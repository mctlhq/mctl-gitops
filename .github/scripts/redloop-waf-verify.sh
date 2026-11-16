#!/usr/bin/env bash
# =============================================================================
# RedLoop Phase P2 Gate 3 — Read-Only Cloudflare Ruleset Contract Verification
#
# Issues exactly one read-only GET request against the zone ruleset endpoint
# using CF_APPLY_TOKEN_MCTL_AI to assert:
# 1. Credentials successfully authenticate against the Cloudflare Rulesets API.
# 2. Zone ruleset 4bdd5c0da7004933b40aae8fd0d5ce78 contains target rule.
# 3. Exactly one rule matches ID d8b4ea76eabc420e99146cafd9596801.
# 4. Target rule attributes match invariants:
#    - enabled == false (strictly inert kill switch)
#    - ref == "block_staging_redloop_emergency"
#    - action == "block"
#    - expression == '(http.host eq "staging-redloop.mctl.ai")'
#
# ZERO MUTATION GUARANTEE:
# - Strictly HTTP GET; zero POST, PATCH, PUT, or DELETE calls.
# - Never logs the API token or the full ruleset JSON.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Self-Test Mock Suite (Runs when REDLOOP_VERIFY_SELF_TEST=1)
# ---------------------------------------------------------------------------
if [ "${REDLOOP_VERIFY_SELF_TEST:-}" = "1" ] || [ "${1:-}" = "--self-test" ]; then
  echo "=== Running RedLoop WAF Verify Self-Test Suite ==="

  mock_port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
  tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/redloop-verify-test.XXXXXX")

  # shellcheck disable=SC2329
  cleanup_mock() {
    if [ -n "${mock_pid:-}" ] && kill -0 "$mock_pid" 2>/dev/null; then
      kill "$mock_pid" 2>/dev/null || true
      wait "$mock_pid" 2>/dev/null || true
    fi
    rm -rf "$tmp_dir"
  }
  trap cleanup_mock EXIT

  python3 - <<PYEOF > "$tmp_dir/mock.log" 2>&1 &
import http.server
import json
import sys

state = {
    "auth_error": False,
    "method_not_allowed": False,
    "server_error": False,
    "malformed_null": False,
    "malformed_rules_type": False,
    "missing_rule": False,
    "duplicate_rule": False,
    "enabled_true": False,
    "bad_ref": False,
    "bad_action": False,
    "bad_expr": False,
    "write_count": 0,
}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        state["write_count"] += 1
        self.send_response(405)
        self.end_headers()

    def do_PATCH(self):
        state["write_count"] += 1
        self.send_response(405)
        self.end_headers()

    def do_PUT(self):
        state["write_count"] += 1
        self.send_response(405)
        self.end_headers()

    def do_DELETE(self):
        state["write_count"] += 1
        self.send_response(405)
        self.end_headers()

    def do_GET(self):
        # Control endpoints for test manipulation
        if self.path.startswith("/control/"):
            action = self.path[len("/control/"):]
            if action == "get_write_count":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"write_count": state["write_count"]}).encode())
                return
            elif action.startswith("set_"):
                key = action[4:]
                if key in state:
                    state[key] = True
            elif action.startswith("clear_"):
                key = action[6:]
                if key in state:
                    state[key] = False
            self.send_response(200)
            self.end_headers()
            return

        # Cloudflare ruleset mock endpoint
        if state["method_not_allowed"] or "/rules/" in self.path:
            self.send_response(405)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "errors": [{"code": 10405, "message": "Method not allowed for this authentication scheme"}],
                "result": None
            }).encode())
            return

        if state["auth_error"]:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "errors": [{"code": 10000, "message": "Authentication error"}],
                "result": None
            }).encode())
            return

        if state["server_error"]:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "errors": [{"code": 500, "message": "Internal server error"}],
                "result": None
            }).encode())
            return

        if state["malformed_null"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "errors": [],
                "result": None
            }).encode())
            return

        if state["malformed_rules_type"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "errors": [],
                "result": {"id": "4bdd5c0da7004933b40aae8fd0d5ce78", "rules": "not-an-array"}
            }).encode())
            return

        rules = [
            {
                "id": "1493169d2b0947769321b3375a153715",
                "action": "skip",
                "description": "seerr",
                "enabled": True,
                "expression": "(ip.src.asnum eq 24940)",
                "ref": "1493169d2b0947769321b3375a153715"
            },
            {
                "id": "2a3535af952d46be832c9bccbe0add17",
                "action": "block",
                "description": "block archive probes",
                "enabled": True,
                "expression": '(http.request.uri.path contains ".zip")',
                "ref": "block_archive_probes_apex"
            },
            {
                "id": "2fe2992c8fbb4848aae84a4648d4f1cb",
                "action": "block",
                "description": "block spoofed crawlers",
                "enabled": True,
                "expression": "(not cf.client.bot)",
                "ref": "block_spoofed_crawlers"
            }
        ]

        target_rule = {
            "id": "d8b4ea76eabc420e99146cafd9596801",
            "ref": "block_staging_redloop_emergency" if not state["bad_ref"] else "wrong_ref",
            "enabled": False if not state["enabled_true"] else True,
            "action": "block" if not state["bad_action"] else "log",
            "expression": '(http.host eq "staging-redloop.mctl.ai")' if not state["bad_expr"] else '(http.host eq "other.mctl.ai")'
        }

        if not state["missing_rule"]:
            rules.append(target_rule)
            if state["duplicate_rule"]:
                rules.append(dict(target_rule))

        resp = {
            "success": True,
            "errors": [],
            "messages": [],
            "result": {
                "id": "4bdd5c0da7004933b40aae8fd0d5ce78",
                "name": "default",
                "phase": "http_request_firewall_custom",
                "rules": rules
            }
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

server = http.server.HTTPServer(("127.0.0.1", int("$mock_port")), Handler)
server.serve_forever()
PYEOF
  mock_pid=$!

  # Wait for mock server readiness
  for _ in $(seq 1 30); do
    if curl -s "http://127.0.0.1:$mock_port/control/ping" > /dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done

  echo "[+] Test Case 1: Standard valid contract verification (all assertions pass)"
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  EVIDENCE_FILE="$tmp_dir/evidence1.json" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test1.log" 2>&1

  if ! grep -q "SUCCESS: Read-only Cloudflare Ruleset contract verified" "$tmp_dir/test1.log"; then
    echo "[-] FAIL: Test 1 expected contract verification success!"
    cat "$tmp_dir/test1.log"
    exit 1
  fi
  if [ ! -f "$tmp_dir/evidence1.json" ]; then
    echo "[-] FAIL: Test 1 did not generate evidence file!"
    exit 1
  fi
  if ! jq -e . "$tmp_dir/evidence1.json" > /dev/null 2>&1; then
    echo "[-] FAIL: Test 1 generated invalid JSON in evidence file!"
    cat "$tmp_dir/evidence1.json"
    exit 1
  fi
  ev_expr=$(jq -r '.expression' "$tmp_dir/evidence1.json")
  if [ "$ev_expr" != '(http.host eq "staging-redloop.mctl.ai")' ]; then
    echo "[-] FAIL: Test 1 evidence expression mismatch: got '$ev_expr'"
    exit 1
  fi
  echo "[+] Test Case 1 PASSED: Valid contract verified and safe evidence emitted."

  echo "[+] Test Case 2: HTTP 405 Method Not Allowed (reproduce 10405 error) fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_method_not_allowed" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test2.log" 2>&1
  rc2=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_method_not_allowed" > /dev/null
  if [ "$rc2" -eq 0 ]; then
    echo "[-] FAIL: Test 2 expected failure on HTTP 405, got 0"
    exit 1
  fi
  if ! grep -q "10405" "$tmp_dir/test2.log"; then
    echo "[-] FAIL: Test 2 did not log expected 10405 error code!"
    cat "$tmp_dir/test2.log"
    exit 1
  fi
  echo "[+] Test Case 2 PASSED: HTTP 405 / 10405 correctly failed closed."

  echo "[+] Test Case 3: HTTP 401 Unauthorized fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_auth_error" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test3.log" 2>&1
  rc3=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_auth_error" > /dev/null
  if [ "$rc3" -eq 0 ]; then
    echo "[-] FAIL: Test 3 expected failure on HTTP 401, got 0"
    exit 1
  fi
  if ! grep -q "Ruleset API returned HTTP 401" "$tmp_dir/test3.log"; then
    echo "[-] FAIL: Test 3 did not log expected 401 error!"
    cat "$tmp_dir/test3.log"
    exit 1
  fi
  echo "[+] Test Case 3 PASSED: HTTP 401 correctly failed closed."

  echo "[+] Test Case 4: HTTP 500 Internal Server Error fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_server_error" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test4.log" 2>&1
  rc4=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_server_error" > /dev/null
  if [ "$rc4" -eq 0 ]; then
    echo "[-] FAIL: Test 4 expected failure on HTTP 500, got 0"
    exit 1
  fi
  if ! grep -q "Ruleset API returned HTTP 500" "$tmp_dir/test4.log"; then
    echo "[-] FAIL: Test 4 did not log expected 500 error!"
    cat "$tmp_dir/test4.log"
    exit 1
  fi
  echo "[+] Test Case 4 PASSED: HTTP 500 correctly failed closed."

  echo "[+] Test Case 5: Malformed payload (.result is null) fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_malformed_null" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test5.log" 2>&1
  rc5=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_malformed_null" > /dev/null
  if [ "$rc5" -eq 0 ]; then
    echo "[-] FAIL: Test 5 expected failure on null result, got 0"
    exit 1
  fi
  if ! grep -q "Malformed ruleset payload: .result is not an object" "$tmp_dir/test5.log"; then
    echo "[-] FAIL: Test 5 did not log expected null result error!"
    cat "$tmp_dir/test5.log"
    exit 1
  fi
  echo "[+] Test Case 5 PASSED: Null result correctly failed closed."

  echo "[+] Test Case 6: Malformed payload (.result.rules is not an array) fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_malformed_rules_type" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test6.log" 2>&1
  rc6=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_malformed_rules_type" > /dev/null
  if [ "$rc6" -eq 0 ]; then
    echo "[-] FAIL: Test 6 expected failure on non-array rules, got 0"
    exit 1
  fi
  if ! grep -q "Malformed ruleset payload: .result.rules is not an array" "$tmp_dir/test6.log"; then
    echo "[-] FAIL: Test 6 did not log expected rules type error!"
    cat "$tmp_dir/test6.log"
    exit 1
  fi
  echo "[+] Test Case 6 PASSED: Non-array rules correctly failed closed."

  echo "[+] Test Case 7: Missing target rule fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_missing_rule" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test7.log" 2>&1
  rc7=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_missing_rule" > /dev/null
  if [ "$rc7" -eq 0 ]; then
    echo "[-] FAIL: Test 7 expected failure on missing rule, got 0"
    exit 1
  fi
  if ! grep -q "Expected exactly 1 rule matching ID" "$tmp_dir/test7.log"; then
    echo "[-] FAIL: Test 7 did not log expected missing rule error!"
    cat "$tmp_dir/test7.log"
    exit 1
  fi
  echo "[+] Test Case 7 PASSED: Missing target rule correctly failed closed."

  echo "[+] Test Case 8: Duplicate target rule fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_duplicate_rule" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test8.log" 2>&1
  rc8=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_duplicate_rule" > /dev/null
  if [ "$rc8" -eq 0 ]; then
    echo "[-] FAIL: Test 8 expected failure on duplicate rule, got 0"
    exit 1
  fi
  if ! grep -q "Expected exactly 1 rule matching ID 'd8b4ea76eabc420e99146cafd9596801', found 2" "$tmp_dir/test8.log"; then
    echo "[-] FAIL: Test 8 did not log expected duplicate rule error!"
    cat "$tmp_dir/test8.log"
    exit 1
  fi
  echo "[+] Test Case 8 PASSED: Duplicate target rule correctly failed closed."

  echo "[+] Test Case 9: Safety invariant violation (rule enabled is true) fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_enabled_true" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test9.log" 2>&1
  rc9=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_enabled_true" > /dev/null
  if [ "$rc9" -eq 0 ]; then
    echo "[-] FAIL: Test 9 expected failure on enabled=true, got 0"
    exit 1
  fi
  if ! grep -q "Security invariant violation: rule enabled is 'true', expected 'false'" "$tmp_dir/test9.log"; then
    echo "[-] FAIL: Test 9 did not log expected enabled=true violation!"
    cat "$tmp_dir/test9.log"
    exit 1
  fi
  echo "[+] Test Case 9 PASSED: Active rule (enabled=true) correctly failed closed."

  echo "[+] Test Case 10: Rule ref mismatch fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_bad_ref" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test10.log" 2>&1
  rc10=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_bad_ref" > /dev/null
  if [ "$rc10" -eq 0 ]; then
    echo "[-] FAIL: Test 10 expected failure on ref mismatch, got 0"
    exit 1
  fi
  if ! grep -q "Rule ref mismatch" "$tmp_dir/test10.log"; then
    echo "[-] FAIL: Test 10 did not log expected ref mismatch!"
    cat "$tmp_dir/test10.log"
    exit 1
  fi
  echo "[+] Test Case 10 PASSED: Ref mismatch correctly failed closed."

  echo "[+] Test Case 11: Rule action mismatch fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_bad_action" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test11.log" 2>&1
  rc11=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_bad_action" > /dev/null
  if [ "$rc11" -eq 0 ]; then
    echo "[-] FAIL: Test 11 expected failure on action mismatch, got 0"
    exit 1
  fi
  if ! grep -q "Rule action mismatch" "$tmp_dir/test11.log"; then
    echo "[-] FAIL: Test 11 did not log expected action mismatch!"
    cat "$tmp_dir/test11.log"
    exit 1
  fi
  echo "[+] Test Case 11 PASSED: Action mismatch correctly failed closed."

  echo "[+] Test Case 12: Rule expression mismatch fails closed"
  curl -s "http://127.0.0.1:$mock_port/control/set_bad_expr" > /dev/null
  set +e
  CF_RULESET_API_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  REDLOOP_VERIFY_SELF_TEST="" \
  "$0" > "$tmp_dir/test12.log" 2>&1
  rc12=$?
  set -e
  curl -s "http://127.0.0.1:$mock_port/control/clear_bad_expr" > /dev/null
  if [ "$rc12" -eq 0 ]; then
    echo "[-] FAIL: Test 12 expected failure on expression mismatch, got 0"
    exit 1
  fi
  if ! grep -q "Rule expression mismatch" "$tmp_dir/test12.log"; then
    echo "[-] FAIL: Test 12 did not log expected expression mismatch!"
    cat "$tmp_dir/test12.log"
    exit 1
  fi
  echo "[+] Test Case 12 PASSED: Expression mismatch correctly failed closed."

  echo "[+] Test Case 13: Zero mutation guarantee (0 writes across all test runs)"
  total_writes=$(curl -s "http://127.0.0.1:$mock_port/control/get_write_count" | jq -r '.write_count')
  if [ "$total_writes" -ne 0 ]; then
    echo "[-] FAIL: Test 13 detected $total_writes write mutations during verification tests!"
    exit 1
  fi
  echo "[+] Test Case 13 PASSED: Zero mutations confirmed (write_count == 0)."

  echo "=== All 13 Verification Self-Test Scenarios PASSED ==="
  exit 0
fi

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------
CF_TOKEN="${CLOUDFLARE_API_TOKEN:-${CF_TOKEN:-}}"

if [ -z "$CF_TOKEN" ]; then
  echo "[-] ERROR: Cloudflare API token not provided via CLOUDFLARE_API_TOKEN or CF_TOKEN." >&2
  exit 1
fi

ZONE_ID="86a90fe2fdfe87b9702842218b607f60"
RULESET_ID="4bdd5c0da7004933b40aae8fd0d5ce78"
RULE_ID="d8b4ea76eabc420e99146cafd9596801"
EXPECTED_REF="block_staging_redloop_emergency"
EXPECTED_ACTION="block"
EXPECTED_EXPR='(http.host eq "staging-redloop.mctl.ai")'

DEFAULT_API_URL="https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/${RULESET_ID}"
API_URL="${CF_RULESET_API_OVERRIDE:-$DEFAULT_API_URL}"

# Regression guard: assert target URL stays at the ruleset level, not individual rule path
if [[ "$API_URL" == *"/rules/"* ]]; then
  echo "[-] ERROR: Invariant violation: Target URL must query the ruleset level, not /rules/ ($API_URL)." >&2
  exit 1
fi

echo "[*] Querying Cloudflare Ruleset API (Read-Only GET)..."
echo "[*] Zone ID: $ZONE_ID"
echo "[*] Ruleset ID: $RULESET_ID"
echo "[*] Target Rule ID: $RULE_ID"

# ---------------------------------------------------------------------------
# Single Read-Only GET Operation
# ---------------------------------------------------------------------------
http_resp=$(curl -sS --max-time 15 --connect-timeout 5 -w "\n%{http_code}" -X GET "$API_URL" \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$CF_TOKEN") 2>&1 || true)

http_code=$(echo "$http_resp" | tail -n 1)
body=$(echo "$http_resp" | sed '$d')

# Fail closed on HTTP != 200
if [ "$http_code" != "200" ]; then
  echo "[-] ERROR: Ruleset API returned HTTP $http_code (expected 200)." >&2
  errors_snippet=$(echo "$body" | jq -c 'try .errors catch []' 2>/dev/null || echo "[]")
  echo "[-] Cloudflare error details: $errors_snippet" >&2
  exit 1
fi

# Fail closed on .success != true
api_success=$(echo "$body" | jq -r 'try (.success // false) catch false' 2>/dev/null || echo "false")
if [ "$api_success" != "true" ]; then
  echo "[-] ERROR: Cloudflare API returned success: $api_success (expected true)." >&2
  exit 1
fi

# Fail closed on .result null or non-object
result_type=$(echo "$body" | jq -r 'try (.result | type) catch "null"' 2>/dev/null || echo "null")
if [ "$result_type" != "object" ]; then
  echo "[-] ERROR: Malformed ruleset payload: .result is not an object (type: '$result_type')." >&2
  exit 1
fi

# Fail closed on .result.rules non-array
rules_type=$(echo "$body" | jq -r 'try (.result.rules | type) catch "null"' 2>/dev/null || echo "null")
if [ "$rules_type" != "array" ]; then
  echo "[-] ERROR: Malformed ruleset payload: .result.rules is not an array (type: '$rules_type')." >&2
  exit 1
fi

# Cardinality assertion
matching_rules=$(echo "$body" | jq -c --arg id "$RULE_ID" 'try ([.result.rules[]? | select(.id == $id)]) catch []' 2>/dev/null || echo "[]")
rule_count=$(echo "$matching_rules" | jq 'length' 2>/dev/null || echo 0)

if [ "$rule_count" -ne 1 ]; then
  echo "[-] ERROR: Expected exactly 1 rule matching ID '$RULE_ID', found $rule_count." >&2
  exit 1
fi

# Extract and assert rule attributes
target_rule=$(echo "$matching_rules" | jq '.[0]')
rule_enabled=$(echo "$target_rule" | jq -r 'try (.enabled | tostring) catch "unknown"')
rule_ref=$(echo "$target_rule" | jq -r 'try (.ref // "") catch ""')
rule_action=$(echo "$target_rule" | jq -r 'try (.action // "") catch ""')
rule_expr=$(echo "$target_rule" | jq -r 'try (.expression // "") catch ""')

if [ "$rule_enabled" != "false" ]; then
  echo "[-] ERROR: Security invariant violation: rule enabled is '$rule_enabled', expected 'false'." >&2
  exit 1
fi

if [ "$rule_ref" != "$EXPECTED_REF" ]; then
  echo "[-] ERROR: Rule ref mismatch: got '$rule_ref', expected '$EXPECTED_REF'." >&2
  exit 1
fi

if [ "$rule_action" != "$EXPECTED_ACTION" ]; then
  echo "[-] ERROR: Rule action mismatch: got '$rule_action', expected '$EXPECTED_ACTION'." >&2
  exit 1
fi

if [ "$rule_expr" != "$EXPECTED_EXPR" ]; then
  echo "[-] ERROR: Rule expression mismatch: got '$rule_expr', expected '$EXPECTED_EXPR'." >&2
  exit 1
fi

total_rules=$(echo "$body" | jq 'try (.result.rules | length) catch 0' 2>/dev/null || echo 0)
timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "[+] SUCCESS: Read-only Cloudflare Ruleset contract verified."
echo "[+] Rule ID: $RULE_ID"
echo "[+] Ref: $rule_ref"
echo "[+] Action: $rule_action"
echo "[+] Expression: $rule_expr"
echo "[+] Enabled: $rule_enabled (INERT)"
echo "[+] Total rules in ruleset: $total_rules"

# ---------------------------------------------------------------------------
# Safe Evidence Generation
# ---------------------------------------------------------------------------
if [ -n "${EVIDENCE_FILE:-}" ]; then
  jq -n \
    --arg run_id "${GITHUB_RUN_ID:-local}" \
    --arg run_attempt "${GITHUB_RUN_ATTEMPT:-1}" \
    --arg ts "$timestamp" \
    --arg zone_id "$ZONE_ID" \
    --arg ruleset_id "$RULESET_ID" \
    --arg rule_id "$RULE_ID" \
    --arg ref "$rule_ref" \
    --arg action "$rule_action" \
    --arg expr "$rule_expr" \
    --argjson total_rules "$total_rules" \
    '{
      workflow_run_id: $run_id,
      workflow_run_attempt: $run_attempt,
      timestamp_utc: $ts,
      http_status: 200,
      api_success: true,
      zone_id: $zone_id,
      ruleset_id: $ruleset_id,
      rule_id: $rule_id,
      ref: $ref,
      action: $action,
      expression: $expr,
      enabled: false,
      total_rules: $total_rules,
      verdict: "PASS"
    }' > "$EVIDENCE_FILE"
  echo "[+] Evidence recorded in $EVIDENCE_FILE"
fi

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  cat >> "$GITHUB_STEP_SUMMARY" <<MDEOF
### RedLoop Gate 3 — Read-Only Cloudflare Ruleset Contract Verification

- **Timestamp (UTC):** \`$timestamp\`
- **HTTP Status:** \`200 OK\`
- **API Success:** \`true\`
- **Zone ID:** \`$ZONE_ID\` (\`mctl.ai\`)
- **Ruleset ID:** \`$RULESET_ID\`
- **Target Rule ID:** \`$RULE_ID\`
- **Rule Ref:** \`$rule_ref\`
- **Rule Action:** \`$rule_action\`
- **Rule Expression:** \`$rule_expr\`
- **Rule Enabled:** \`$rule_enabled\` (INERT)
- **Total Rules in Ruleset:** \`$total_rules\`
- **Contract Verification Verdict:** **PASS (Read-Only Contract Verified)**
MDEOF
fi
