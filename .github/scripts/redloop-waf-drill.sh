#!/usr/bin/env bash
# RedLoop P2 Gate 3 — Production-Safe WAF Drill Harness (404 -> 403 -> 404)
# Target: staging-redloop.mctl.ai
# Zone: 86a90fe2fdfe87b9702842218b607f60 (mctl.ai)
# Ruleset: 4bdd5c0da7004933b40aae8fd0d5ce78 (http_request_firewall_custom)
# Rule ID: d8b4ea76eabc420e99146cafd9596801 (block_staging_redloop_emergency)
#
# Safety invariants:
# 1. Strictly bounded blast radius: modifies exclusively Rule ID d8b4ea76eabc420e99146cafd9596801.
# 2. Comprehensive production controls: continuous checks on 6 production endpoints with latency & status limits.
# 3. Fail-closed rollback: traps EXIT, ERR, INT, TERM with bounded retries and API read-back verification.
# 4. Strict activation guard: rollback never modifies rule if activation was not attempted (preserves active incidents).
# 5. Fail-safe state tracking: activation state transitions to "activating" BEFORE dispatch, guaranteeing rollback on network drop.
# 6. Independent recovery verification: produces machine-readable summary and audit correlation.

set -euo pipefail

# ---------------------------------------------------------------------------
# Self-Test Mode (Mock Server Verification)
# ---------------------------------------------------------------------------
if [ "${REDLOOP_DRILL_SELF_TEST:-}" = "1" ]; then
  echo "=== Running RedLoop WAF Drill Harness Self-Test Suite ==="
  tmp_dir="$(mktemp -d)"

  # Python mock server simulating Cloudflare API and endpoints
  mock_port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
  mock_py="$tmp_dir/mock_server.py"

  cat << 'PYEOF' > "$mock_py"
import sys
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

rule_state = {
    "enabled": False,
    "patch_count": 0,
    "fail_activation_patch": False,
    "trigger_null_on_rollback": False,
    "null_on_next_get": False,
    "probe_fail_count": 0
}

class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if "/ruleset" in self.path:
            if rule_state["null_on_next_get"]:
                rule_state["null_on_next_get"] = False
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "errors": [{"message": "transient backend error"}], "result": None}).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "success": True,
                "errors": [],
                "result": {
                    "id": "d8b4ea76eabc420e99146cafd9596801",
                    "ref": "block_staging_redloop_emergency",
                    "enabled": rule_state["enabled"],
                    "action": "block",
                    "expression": '(http.host eq "staging-redloop.mctl.ai")'
                }
            }
            self.wfile.write(json.dumps(resp).encode())
        elif self.path == "/staging":
            if rule_state["probe_fail_count"] > 0:
                rule_state["probe_fail_count"] -= 1
                self.send_response(500)
                self.end_headers()
                return
            if rule_state["enabled"]:
                self.send_response(403)
                self.send_header("cf-ray", "mockray403-TEST")
                self.send_header("server", "cloudflare")
                self.end_headers()
                self.wfile.write(b"error code: 1020 access denied")
            else:
                self.send_response(404)
                self.send_header("cf-ray", "mockray404-TEST")
                self.send_header("server", "cloudflare")
                self.end_headers()
                self.wfile.write(b"404 page not found")
        elif self.path in ["/prod/mctl", "/prod/app", "/prod/api/healthz", "/prod/ops", "/prod/tg"]:
            self.send_response(200)
            self.send_header("cf-ray", "mockray200-TEST")
            self.send_header("server", "cloudflare")
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path == "/prod/api/apex":
            self.send_response(404)
            self.send_header("cf-ray", "mockray404-TEST")
            self.send_header("server", "cloudflare")
            self.end_headers()
            self.wfile.write(b"404 Not Found")
        elif self.path == "/control/set_enabled_true":
            rule_state["enabled"] = True
            self.send_response(200)
            self.end_headers()
        elif self.path == "/control/set_enabled_false":
            rule_state["enabled"] = False
            self.send_response(200)
            self.end_headers()
        elif self.path == "/control/set_fail_activation":
            rule_state["fail_activation_patch"] = True
            self.send_response(200)
            self.end_headers()
        elif self.path == "/control/clear_fail_activation":
            rule_state["fail_activation_patch"] = False
            self.send_response(200)
            self.end_headers()
        elif self.path == "/control/arm_null_readback_on_rollback":
            rule_state["trigger_null_on_rollback"] = True
            self.send_response(200)
            self.end_headers()
        elif self.path == "/control/get_patch_count":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"patch_count": rule_state["patch_count"], "enabled": rule_state["enabled"]}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_PATCH(self):
        rule_state["patch_count"] += 1
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        payload = json.loads(body.decode()) if body else {}

        if payload.get("enabled", False) and rule_state["fail_activation_patch"]:
            rule_state["enabled"] = True
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "errors": [{"message": "simulated activation failure"}]}).encode())
            return

        rule_state["enabled"] = payload.get("enabled", False)

        # Trigger null read-back on the subsequent GET if armed
        if not rule_state["enabled"] and rule_state["trigger_null_on_rollback"]:
            rule_state["null_on_next_get"] = True
            rule_state["trigger_null_on_rollback"] = False

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "success": True,
            "errors": [],
            "result": {
                "id": "d8b4ea76eabc420e99146cafd9596801",
                "ref": "block_staging_redloop_emergency",
                "enabled": rule_state["enabled"],
                "action": "block"
            }
        }
        self.wfile.write(json.dumps(resp).encode())

server = HTTPServer(("127.0.0.1", int(sys.argv[1])), MockHandler)
server.serve_forever()
PYEOF

  python3 "$mock_py" "$mock_port" &
  mock_pid=$!

  cleanup_mock() {
    kill "$mock_pid" 2>/dev/null || true
    wait "$mock_pid" 2>/dev/null || true
    rm -rf "$tmp_dir"
  }
  trap cleanup_mock EXIT INT TERM

  # Wait for mock server port readiness
  for _ in $(seq 1 30); do
    if python3 -c "import socket; s=socket.socket(); s.connect(('127.0.0.1', $mock_port)); s.close()" 2>/dev/null; then
      break
    fi
    sleep 0.1
  done

  echo "[+] Test Case 1: Standard Happy Path (404 -> 403 -> 404)"
  CF_API_BASE_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  MOCK_STAGING_URL="http://127.0.0.1:$mock_port/staging" \
  MOCK_PROD_MCTL="http://127.0.0.1:$mock_port/prod/mctl" \
  MOCK_PROD_APP="http://127.0.0.1:$mock_port/prod/app" \
  MOCK_PROD_API_HEALTH="http://127.0.0.1:$mock_port/prod/api/healthz" \
  MOCK_PROD_API_APEX="http://127.0.0.1:$mock_port/prod/api/apex" \
  MOCK_PROD_OPS="http://127.0.0.1:$mock_port/prod/ops" \
  MOCK_PROD_TG="http://127.0.0.1:$mock_port/prod/tg" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  RUNNER_TEMP="$tmp_dir" \
  REDLOOP_DRILL_SELF_TEST="" \
  "$0"

  echo "[+] Test Case 2: Pre-flight abort when rule is already enabled (active incident guard)"
  curl -s "http://127.0.0.1:$mock_port/control/set_enabled_true" > /dev/null
  init_patches=$(curl -s "http://127.0.0.1:$mock_port/control/get_patch_count" | jq -r '.patch_count')

  set +e
  CF_API_BASE_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  MOCK_STAGING_URL="http://127.0.0.1:$mock_port/staging" \
  MOCK_PROD_MCTL="http://127.0.0.1:$mock_port/prod/mctl" \
  MOCK_PROD_APP="http://127.0.0.1:$mock_port/prod/app" \
  MOCK_PROD_API_HEALTH="http://127.0.0.1:$mock_port/prod/api/healthz" \
  MOCK_PROD_API_APEX="http://127.0.0.1:$mock_port/prod/api/apex" \
  MOCK_PROD_OPS="http://127.0.0.1:$mock_port/prod/ops" \
  MOCK_PROD_TG="http://127.0.0.1:$mock_port/prod/tg" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  RUNNER_TEMP="$tmp_dir" \
  REDLOOP_DRILL_SELF_TEST="" \
  "$0" > "$tmp_dir/test2.log" 2>&1
  test2_rc=$?
  set -e

  if [ "$test2_rc" -eq 0 ]; then
    echo "[-] FAIL: Test 2 expected non-zero exit code when rule is already enabled, got 0"
    exit 1
  fi

  post_patches=$(curl -s "http://127.0.0.1:$mock_port/control/get_patch_count" | jq -r '.patch_count')
  post_enabled=$(curl -s "http://127.0.0.1:$mock_port/control/get_patch_count" | jq -r '.enabled')

  if [ "$post_patches" -ne "$init_patches" ]; then
    echo "[-] FAIL: Test 2 sent PATCH during pre-flight failure! ($post_patches != $init_patches)"
    exit 1
  fi
  if [ "$post_enabled" != "true" ]; then
    echo "[-] FAIL: Test 2 modified rule enabled status! Expected rule to remain true, got $post_enabled"
    exit 1
  fi
  echo "[+] Test Case 2 PASSED: Rule remained untouched (enabled=true) and zero PATCHes were sent."

  echo "[+] Test Case 3: Activation PATCH failure triggers in-script rollback to inert"
  curl -s "http://127.0.0.1:$mock_port/control/set_enabled_false" > /dev/null
  curl -s "http://127.0.0.1:$mock_port/control/set_fail_activation" > /dev/null

  set +e
  CF_API_BASE_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  MOCK_STAGING_URL="http://127.0.0.1:$mock_port/staging" \
  MOCK_PROD_MCTL="http://127.0.0.1:$mock_port/prod/mctl" \
  MOCK_PROD_APP="http://127.0.0.1:$mock_port/prod/app" \
  MOCK_PROD_API_HEALTH="http://127.0.0.1:$mock_port/prod/api/healthz" \
  MOCK_PROD_API_APEX="http://127.0.0.1:$mock_port/prod/api/apex" \
  MOCK_PROD_OPS="http://127.0.0.1:$mock_port/prod/ops" \
  MOCK_PROD_TG="http://127.0.0.1:$mock_port/prod/tg" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  RUNNER_TEMP="$tmp_dir" \
  REDLOOP_DRILL_SELF_TEST="" \
  "$0" > "$tmp_dir/test3.log" 2>&1
  test3_rc=$?
  set -e

  curl -s "http://127.0.0.1:$mock_port/control/clear_fail_activation" > /dev/null

  if [ "$test3_rc" -eq 0 ]; then
    echo "[-] FAIL: Test 3 expected failure when activation PATCH failed, got 0"
    exit 1
  fi
  post_enabled=$(curl -s "http://127.0.0.1:$mock_port/control/get_patch_count" | jq -r '.enabled')
  if [ "$post_enabled" != "false" ]; then
    echo "[-] FAIL: Test 3 left rule enabled after activation PATCH failure!"
    exit 1
  fi
  if ! grep -q "EMERGENCY / RECOVERY ROLLBACK TRIGGERED" "$tmp_dir/test3.log"; then
    echo "[-] FAIL: Test 3 did not trigger rollback on activation failure!"
    exit 1
  fi
  echo "[+] Test Case 3 PASSED: In-script rollback triggered and verified rule inert."

  echo "[+] Test Case 4: Rollback resilience when read-back returns result:null on first retry"
  curl -s "http://127.0.0.1:$mock_port/control/set_enabled_false" > /dev/null
  curl -s "http://127.0.0.1:$mock_port/control/arm_null_readback_on_rollback" > /dev/null

  set +e
  CF_API_BASE_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  MOCK_STAGING_URL="http://127.0.0.1:$mock_port/staging" \
  MOCK_PROD_MCTL="http://127.0.0.1:$mock_port/prod/mctl" \
  MOCK_PROD_APP="http://127.0.0.1:$mock_port/prod/app" \
  MOCK_PROD_API_HEALTH="http://127.0.0.1:$mock_port/prod/api/healthz" \
  MOCK_PROD_API_APEX="http://127.0.0.1:$mock_port/prod/api/apex" \
  MOCK_PROD_OPS="http://127.0.0.1:$mock_port/prod/ops" \
  MOCK_PROD_TG="http://127.0.0.1:$mock_port/prod/tg" \
  CLOUDFLARE_API_TOKEN="mock-token" \
  RUNNER_TEMP="$tmp_dir" \
  MOCK_TRIGGER_ABORT_ON_403="1" \
  REDLOOP_DRILL_SELF_TEST="" \
  "$0" > "$tmp_dir/test4.log" 2>&1
  test4_rc=$?
  set -e

  if [ "$test4_rc" -eq 0 ]; then
    echo "[-] FAIL: Test 4 expected failure when drill was aborted, got 0"
    exit 1
  fi
  if grep -q "Cannot check whether null has a string key" "$tmp_dir/test4.log"; then
    echo "[-] FAIL: Test 4 caught jq null unhandled exception!"
    exit 1
  fi
  if ! grep -q "Read-back verification failed: rule enabled status is 'unknown'" "$tmp_dir/test4.log"; then
    echo "[-] FAIL: Test 4 did not log expected transient read-back failure!"
    exit 1
  fi
  if ! grep -q "Rollback CONFIRMED: Cloudflare API read-back reports enabled=false." "$tmp_dir/test4.log"; then
    echo "[-] FAIL: Test 4 rollback did not recover and confirm inert status!"
    exit 1
  fi
  echo "[+] Test Case 4 PASSED: Transient null read-back handled gracefully without jq exception and recovered on next attempt."

  echo "=== All Self-Test Scenarios PASSED ==="
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
TARGET_HOST="staging-redloop.mctl.ai"

TARGET_URL="${MOCK_STAGING_URL:-https://${TARGET_HOST}/}"
API_URL="${CF_API_BASE_OVERRIDE:-https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/${RULESET_ID}/rules/${RULE_ID}}"

# Latency and Timeout Thresholds
MAX_PROD_LATENCY_SECONDS="${MAX_PROD_LATENCY_SECONDS:-2.500}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-60}"
PROBE_INTERVAL_SECONDS="${PROBE_INTERVAL_SECONDS:-1}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-10}"
CURL_CONNECT_TIMEOUT_SECONDS="${CURL_CONNECT_TIMEOUT_SECONDS:-5}"

# State Tracking & Incident Guards
ACTIVATION_ATTEMPTED=0
CURRENT_STATE="initial" # initial -> activating -> active -> rolling_back -> inert
ACTIVATION_MARKER_FILE="${RUNNER_TEMP:-/tmp}/redloop_waf_drill_activated"
SUMMARY_FILE="${GITHUB_STEP_SUMMARY:-/tmp/redloop_waf_drill_summary.md}"
TIMINGS_FILE="${TIMINGS_FILE:-/tmp/redloop_waf_drill_timings.json}"

# Ensure activation marker is absent initially
rm -f "$ACTIVATION_MARKER_FILE"

iso_ts() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log() {
  local ts
  ts=$(iso_ts)
  echo "[$ts] $*"
}

# ---------------------------------------------------------------------------
# Robust Rollback Logic (EXIT, ERR, INT, TERM)
# ---------------------------------------------------------------------------
rollback() {
  local exit_code=$?
  local reason="${1:-Emergency trap trigger}"
  if [ "$#" -ge 2 ]; then
    exit_code="$2"
  fi
  # If exit_code is 0 but rollback was explicitly triggered, ensure non-zero exit code
  if [ "$exit_code" -eq 0 ] && [ "$ACTIVATION_ATTEMPTED" -eq 1 ] && [ "$CURRENT_STATE" != "inert" ]; then
    exit_code=1
  fi

  # Disable traps during rollback to avoid recursion
  trap - EXIT INT TERM ERR
  set +e

  # P1 Guard: Never disable a rule that this drill did not attempt to activate
  if [ "$ACTIVATION_ATTEMPTED" -ne 1 ]; then
    log "[+] Activation was not attempted by this drill. Rollback will not modify Cloudflare state."
    exit "$exit_code"
  fi

  if [ "$CURRENT_STATE" = "inert" ]; then
    log "[+] State is already INERT (enabled=false confirmed). No rollback required."
    exit "$exit_code"
  fi

  log "[!] ================================================================="
  log "[!] EMERGENCY / RECOVERY ROLLBACK TRIGGERED"
  log "[!] Reason: $reason (Exit code: $exit_code, State: $CURRENT_STATE)"
  log "[!] ================================================================="

  CURRENT_STATE="rolling_back"
  local max_attempts=3
  local attempt=1
  local rollback_success=false

  local deact_payload='{
    "action": "block",
    "description": "staging-redloop: emergency kill switch / drill block",
    "enabled": false,
    "expression": "(http.host eq \"staging-redloop.mctl.ai\")"
  }'

  while [ "$attempt" -le "$max_attempts" ]; do
    log "[!] Rollback attempt $attempt of $max_attempts..."
    local http_resp
    http_resp=$(curl -sS --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
      -w "\n%{http_code}" -X PATCH "$API_URL" \
      -K <(printf 'header = "Authorization: Bearer %s"\n' "$CF_TOKEN") \
      -H "Content-Type: application/json" \
      -d "$deact_payload" 2>&1 || true)

    local http_code
    http_code=$(echo "$http_resp" | tail -n 1)
    local body
    body=$(echo "$http_resp" | sed '$d')

    local patch_success
    patch_success=$(echo "$body" | jq -r 'try (.success // false) catch false' 2>/dev/null || echo "false")

    if [ "$http_code" = "200" ] && [ "$patch_success" = "true" ]; then
      log "[+] Rollback PATCH succeeded. Verifying via Cloudflare API read-back..."
      
      # Read-back verification with safe jq handling
      local verify_resp
      verify_resp=$(curl -sS --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
        -X GET "$API_URL" \
        -K <(printf 'header = "Authorization: Bearer %s"\n' "$CF_TOKEN") 2>&1 || true)

      local verify_enabled
      verify_enabled=$(echo "$verify_resp" | jq -r 'try (.result | if (type == "object" and has("enabled")) then (.enabled | tostring) else "unknown" end) catch "unknown"' 2>/dev/null || echo "unknown")
      [ -z "$verify_enabled" ] && verify_enabled="unknown"

      if [ "$verify_enabled" = "false" ]; then
        log "[+] Rollback CONFIRMED: Cloudflare API read-back reports enabled=false."
        rollback_success=true
        CURRENT_STATE="inert"
        break
      else
        log "[-] Read-back verification failed: rule enabled status is '$verify_enabled'"
      fi
    else
      log "[-] Rollback PATCH failed with HTTP $http_code: $body"
    fi

    attempt=$((attempt + 1))
    if [ "$attempt" -le "$max_attempts" ]; then
      sleep "$((attempt * 2))"
    fi
  done

  if [ "$rollback_success" != "true" ]; then
    log "[!] CRITICAL: Automated rollback FAILED after $max_attempts attempts!"
    log "[!] ACTION REQUIRED: Manually disable rule $RULE_ID via Cloudflare Dashboard!"
    log "[!] URL: https://dash.cloudflare.com/${ZONE_ID}/security/waf/custom-rules"
    exit 2
  fi

  if [ "$exit_code" -ne 0 ]; then
    exit "$exit_code"
  fi
}

trap rollback EXIT INT TERM ERR

# ---------------------------------------------------------------------------
# Production Endpoint Controls
# ---------------------------------------------------------------------------
check_production_controls() {
  local label="$1"
  local prod_endpoints=(
    "${MOCK_PROD_MCTL:-https://mctl.ai/}:200"
    "${MOCK_PROD_APP:-https://app.mctl.ai/}:200"
    "${MOCK_PROD_API_HEALTH:-https://api.mctl.ai/healthz}:200"
    "${MOCK_PROD_API_APEX:-https://api.mctl.ai/}:404"
    "${MOCK_PROD_OPS:-https://ops.mctl.ai/}:200"
    "${MOCK_PROD_TG:-https://tg.mctl.ai/}:200"
  )

  for item in "${prod_endpoints[@]}"; do
    local url="${item%:*}"
    local exp="${item##*:}"

    local probe_out
    probe_out=$(curl -s --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
      -o /dev/null -w "%{http_code} %{time_total}" "$url" || echo "000 99.999")
    local code
    code=$(echo "$probe_out" | awk '{print $1}')
    local latency
    latency=$(echo "$probe_out" | awk '{print $2}')

    # Validate HTTP status
    if [ "$code" != "$exp" ]; then
      log "[-] [$label] ALERT: Production status mismatch for $url: expected $exp, got $code"
      return 1
    fi

    # Validate Latency Threshold
    local exceeds_latency
    exceeds_latency=$(python3 -c "print(1 if float('$latency') > float('$MAX_PROD_LATENCY_SECONDS') else 0)")
    if [ "$exceeds_latency" -eq 1 ]; then
      log "[-] [$label] ALERT: Production latency threshold breached for $url: ${latency}s > ${MAX_PROD_LATENCY_SECONDS}s"
      return 1
    fi
  done
  return 0
}

# ---------------------------------------------------------------------------
# Step 1: Pre-flight Verification
# ---------------------------------------------------------------------------
log "=== Step 1: Pre-flight Cloudflare API & Environment Verification ==="

RULE_INFO=$(curl -sS --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
  -X GET "$API_URL" \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$CF_TOKEN") 2>&1 || true)

SUCCESS=$(echo "$RULE_INFO" | jq -r 'try (.success // false) catch false' 2>/dev/null || echo "false")

if [ "$SUCCESS" != "true" ]; then
  log "[-] API Auth / Read failed: $(echo "$RULE_INFO" | jq -c 'try .errors catch "error"')"
  exit 1
fi

INITIAL_ENABLED=$(echo "$RULE_INFO" | jq -r 'try (.result | if (type == "object" and has("enabled")) then (.enabled | tostring) else "unknown" end) catch "unknown"' 2>/dev/null || echo "unknown")
INITIAL_REF=$(echo "$RULE_INFO" | jq -r 'try .result.ref catch "unknown"' 2>/dev/null || echo "unknown")
INITIAL_EXPR=$(echo "$RULE_INFO" | jq -r 'try .result.expression catch "unknown"' 2>/dev/null || echo "unknown")

log "[+] Target Rule verified: ref=$INITIAL_REF, enabled=$INITIAL_ENABLED"
log "[+] Target Expression: $INITIAL_EXPR"

if [ "$INITIAL_ENABLED" != "false" ]; then
  log "[-] CRITICAL: Target rule is ALREADY ENABLED (enabled=$INITIAL_ENABLED) before drill!"
  log "[-] Active incident or manual override suspected. Refusing to run drill."
  exit 1
fi

# Initial Production Controls
log "[+] Verifying baseline for all 6 production endpoints..."
if ! check_production_controls "pre-flight"; then
  log "[-] Baseline production control verification failed! Aborting."
  exit 1
fi
log "[+] All 6 production endpoints match baseline status and latency thresholds."

# Initial Staging Probe
STAGING_INIT=$(curl -s --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
  -o /dev/null -w "%{http_code} %{time_total}" "$TARGET_URL" || echo "000 99.999")
STAGING_CODE=$(echo "$STAGING_INIT" | awk '{print $1}')
if [ "$STAGING_CODE" != "404" ]; then
  log "[-] Initial staging probe failed: expected HTTP 404, got $STAGING_CODE"
  exit 1
fi
log "[+] Initial staging probe confirmed: HTTP 404 (Unrouted Origin Passthrough)."

# ---------------------------------------------------------------------------
# Step 2: Local Schema & Scope Pre-validation
# ---------------------------------------------------------------------------
log "=== Step 2: Local Schema & Scope Pre-validation ==="

ACTIVATE_PAYLOAD='{
  "action": "block",
  "description": "staging-redloop: emergency kill switch / drill block",
  "enabled": true,
  "expression": "(http.host eq \"staging-redloop.mctl.ai\")"
}'

# Validate JSON payload locally
if ! echo "$ACTIVATE_PAYLOAD" | jq . > /dev/null 2>&1; then
  log "[-] Activation payload failed local JSON syntax validation!"
  exit 1
fi

if [ "$INITIAL_REF" != "block_staging_redloop_emergency" ]; then
  log "[-] Ref mismatch: expected block_staging_redloop_emergency, got $INITIAL_REF"
  exit 1
fi

if [ "$INITIAL_EXPR" != '(http.host eq "staging-redloop.mctl.ai")' ]; then
  log "[-] Expression mismatch: expected '(http.host eq \"staging-redloop.mctl.ai\")', got $INITIAL_EXPR"
  exit 1
fi
log "[+] Local validation PASSED: JSON payload valid, ref and expression verified."

# ---------------------------------------------------------------------------
# Step 3: Activation (T0) & Continuous Observation
# ---------------------------------------------------------------------------
log "=== Step 3: Activating WAF Rule d8b4ea76eabc420e99146cafd9596801 (T0) ==="

T0_TS=$(iso_ts)
T0_EPOCH=$(python3 -c "import time; print(time.time())")

# Mark activation state IMMEDIATELY before sending the activation PATCH
ACTIVATION_ATTEMPTED=1
CURRENT_STATE="activating"
touch "$ACTIVATION_MARKER_FILE"

ACT_RESP=$(curl -sS --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
  -X PATCH "$API_URL" \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$CF_TOKEN") \
  -H "Content-Type: application/json" \
  -d "$ACTIVATE_PAYLOAD" 2>&1 || true)

ACT_SUCCESS=$(echo "$ACT_RESP" | jq -r 'try (.success // false) catch false' 2>/dev/null || echo "false")
if [ "$ACT_SUCCESS" != "true" ]; then
  ACT_ERR=$(echo "$ACT_RESP" | jq -c 'try .errors catch empty' 2>/dev/null || true)
  rollback "Rule activation PATCH failed: ${ACT_ERR:-$ACT_RESP}" 1
fi

CURRENT_STATE="active"
log "[+] Rule activation PATCH succeeded. T0 = $T0_TS"

T1_TS=""
T1_EPOCH=""
FIRST_403_RAY=""
FIRST_403_SERVER=""
FIRST_403_SNIPPET=""

log "[+] Observing staging response once per second..."
OBS_START=$(python3 -c "import time; print(int(time.time()))")

while true; do
  NOW=$(python3 -c "import time; print(int(time.time()))")
  ELAPSED=$((NOW - OBS_START))

  if [ "$ELAPSED" -gt "$MAX_WAIT_SECONDS" ]; then
    rollback "TIMEOUT: Rule propagation exceeded ${MAX_WAIT_SECONDS}s without HTTP 403" 1
  fi

  # Concurrently verify production stability
  if ! check_production_controls "drill-active"; then
    rollback "ALERT: Production degradation detected during activation" 1
  fi

  # Probe staging
  PROBE_TMP=$(mktemp)
  PROBE_HEADER=$(curl -sD - --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
    -o "$PROBE_TMP" -w "%{http_code} %{time_total}" "$TARGET_URL" || echo "000 99.999")
  HTTP_CODE=$(echo "$PROBE_HEADER" | tail -n 1 | awk '{print $1}')
  PROBE_LAT=$(echo "$PROBE_HEADER" | tail -n 1 | awk '{print $2}')
  CF_RAY=$(echo "$PROBE_HEADER" | grep -i "^cf-ray:" | tr -d '\r' | awk '{print $2}' || echo "none")
  SERVER_HDR=$(echo "$PROBE_HEADER" | grep -i "^server:" | tr -d '\r' | awk '{print $2}' || echo "unknown")
  PROBE_TS=$(iso_ts)

  log "    [$PROBE_TS] elapsed=${ELAPSED}s -> HTTP $HTTP_CODE | Latency: ${PROBE_LAT}s | Ray: $CF_RAY"

  if [ "$HTTP_CODE" = "403" ]; then
    T1_TS="$PROBE_TS"
    T1_EPOCH=$(python3 -c "import time; print(time.time())")
    FIRST_403_RAY="$CF_RAY"
    FIRST_403_SERVER="$SERVER_HDR"
    FIRST_403_SNIPPET=$(head -c 120 "$PROBE_TMP" || true)
    rm -f "$PROBE_TMP"
    log "[+] HTTP 403 BLOCKED DETECTED! T1 = $T1_TS"
    log "    cf-ray: $FIRST_403_RAY | server: $FIRST_403_SERVER"

    # Self-test hook to verify rollback on abort
    if [ "${MOCK_TRIGGER_ABORT_ON_403:-}" = "1" ]; then
      rollback "Self-test simulated abort after 403" 1
    fi
    break
  fi
  rm -f "$PROBE_TMP"

  sleep "$PROBE_INTERVAL_SECONDS"
done

# ---------------------------------------------------------------------------
# Step 4: Immediate Deactivation / Recovery (T2)
# ---------------------------------------------------------------------------
log "=== Step 4: Immediate Recovery — Deactivating WAF Rule (T2) ==="

T2_TS=$(iso_ts)
T2_EPOCH=$(python3 -c "import time; print(time.time())")

DEACT_PAYLOAD='{
  "action": "block",
  "description": "staging-redloop: emergency kill switch / drill block",
  "enabled": false,
  "expression": "(http.host eq \"staging-redloop.mctl.ai\")"
}'

DEACT_RESP=$(curl -sS --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
  -X PATCH "$API_URL" \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$CF_TOKEN") \
  -H "Content-Type: application/json" \
  -d "$DEACT_PAYLOAD" 2>&1 || true)

DEACT_SUCCESS=$(echo "$DEACT_RESP" | jq -r 'try (.success // false) catch false' 2>/dev/null || echo "false")
if [ "$DEACT_SUCCESS" != "true" ]; then
  DEACT_ERR=$(echo "$DEACT_RESP" | jq -c 'try .errors catch empty' 2>/dev/null || true)
  rollback "Rule deactivation PATCH failed: ${DEACT_ERR:-$DEACT_RESP}" 1
fi
log "[+] Rule deactivation PATCH succeeded. T2 = $T2_TS"

T3_TS=""
T3_EPOCH=""
FIRST_404_RAY=""

log "[+] Observing recovery to HTTP 404 once per second..."
REC_START=$(python3 -c "import time; print(int(time.time()))")

while true; do
  NOW=$(python3 -c "import time; print(int(time.time()))")
  ELAPSED=$((NOW - REC_START))

  if [ "$ELAPSED" -gt "$MAX_WAIT_SECONDS" ]; then
    rollback "TIMEOUT: Recovery propagation exceeded ${MAX_WAIT_SECONDS}s without HTTP 404" 1
  fi

  PROBE_TMP=$(mktemp)
  PROBE_HEADER=$(curl -sD - --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
    -o "$PROBE_TMP" -w "%{http_code} %{time_total}" "$TARGET_URL" || echo "000 99.999")
  HTTP_CODE=$(echo "$PROBE_HEADER" | tail -n 1 | awk '{print $1}')
  PROBE_LAT=$(echo "$PROBE_HEADER" | tail -n 1 | awk '{print $2}')
  CF_RAY=$(echo "$PROBE_HEADER" | grep -i "^cf-ray:" | tr -d '\r' | awk '{print $2}' || echo "none")
  PROBE_TS=$(iso_ts)
  rm -f "$PROBE_TMP"

  log "    [$PROBE_TS] recovery elapsed=${ELAPSED}s -> HTTP $HTTP_CODE | Latency: ${PROBE_LAT}s | Ray: $CF_RAY"

  if [ "$HTTP_CODE" = "404" ]; then
    T3_TS="$PROBE_TS"
    T3_EPOCH=$(python3 -c "import time; print(time.time())")
    FIRST_404_RAY="$CF_RAY"
    log "[+] HTTP 404 RESTORED CONFIRMED! T3 = $T3_TS"
    log "    cf-ray: $FIRST_404_RAY"
    break
  fi

  sleep "$PROBE_INTERVAL_SECONDS"
done

# ---------------------------------------------------------------------------
# Step 5: Post-Drill Verification & State Confirmation
# ---------------------------------------------------------------------------
log "=== Step 5: Post-Drill API Verification & Production Health ==="

FINAL_RULE_INFO=$(curl -sS --max-time "$CURL_TIMEOUT_SECONDS" --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
  -X GET "$API_URL" \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$CF_TOKEN"))

FINAL_ENABLED=$(echo "$FINAL_RULE_INFO" | jq -r 'try (.result | if (type == "object" and has("enabled")) then (.enabled | tostring) else "unknown" end) catch "unknown"' 2>/dev/null || echo "unknown")

if [ "$FINAL_ENABLED" != "false" ]; then
  rollback "CRITICAL: Post-drill rule state is enabled=${FINAL_ENABLED}! Expected false." 1
fi
log "[+] Cloudflare API read-back confirmed rule is INERT (enabled=false)."

# Mark state as inert so trap exit is a clean no-op
CURRENT_STATE="inert"

# Final Production Controls
if ! check_production_controls "post-drill"; then
  log "[-] Final production control verification failed! Investigate production health."
  exit 1
fi
log "[+] All 6 production endpoints healthy and within latency limits."

# ---------------------------------------------------------------------------
# Step 6: Calculations & Evidence Summary
# ---------------------------------------------------------------------------
ACTIVATION_RTO=$(python3 -c "print(f'{$T1_EPOCH - $T0_EPOCH:.3f}')")
RECOVERY_RTO=$(python3 -c "print(f'{$T3_EPOCH - $T2_EPOCH:.3f}')")

log "=== Drill Results Summary ==="
log "  T0 (Activation Dispatch):    $T0_TS"
log "  T1 (First HTTP 403 Block):   $T1_TS (cf-ray: $FIRST_403_RAY)"
log "  T2 (Deactivation Dispatch):  $T2_TS"
log "  T3 (First HTTP 404 Restore): $T3_TS (cf-ray: $FIRST_404_RAY)"
log "  Measured Activation RTO:     ${ACTIVATION_RTO}s"
log "  Measured Recovery RTO:       ${RECOVERY_RTO}s"

# Record machine-readable timings
cat << JSONEOF > "$TIMINGS_FILE"
{
  "zone_id": "$ZONE_ID",
  "ruleset_id": "$RULESET_ID",
  "rule_id": "$RULE_ID",
  "target_host": "$TARGET_HOST",
  "t0_activation_dispatch": "$T0_TS",
  "t1_first_403_blocked": "$T1_TS",
  "t2_deactivation_dispatch": "$T2_TS",
  "t3_first_404_restored": "$T3_TS",
  "activation_rto_seconds": $ACTIVATION_RTO,
  "recovery_rto_seconds": $RECOVERY_RTO,
  "blocked_ray_id": "$FIRST_403_RAY",
  "restored_ray_id": "$FIRST_404_RAY",
  "final_rule_enabled": false
}
JSONEOF

log "[+] Timings written to $TIMINGS_FILE"
log "=== RedLoop Gate 3 Edge-Only WAF Drill Completed Successfully ==="
exit 0
