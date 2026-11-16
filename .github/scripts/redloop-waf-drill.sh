#!/usr/bin/env bash
# RedLoop P2 Gate 3 — Production-Safe WAF Drill Harness (404 -> 403 -> 404)
# Target: staging-redloop.mctl.ai
# Zone: 86a90fe2fdfe87b9702842218b607f60 (mctl.ai)
# Ruleset: 4bdd5c0da7004933b40aae8fd0d5ce78 (http_request_firewall_custom)
# Rule ID: d8b4ea76eabc420e99146cafd9596801 (block_staging_redloop_emergency)
#
# Safety invariants:
# 1. Strictly bounded blast radius: modifies exclusively Rule ID d8b4ea76eabc420e99146cafd9596801.
# 2. Server-side pre-validation: runs ?dry_run=true before live modification.
# 3. Comprehensive production controls: continuous checks on 6 production endpoints with latency & status limits.
# 4. Fail-closed rollback: traps EXIT, ERR, INT, TERM with bounded retries and API read-back verification.
# 5. Independent recovery verification: produces machine-readable summary and audit correlation.

set -euo pipefail

# ---------------------------------------------------------------------------
# Self-Test Mode (Mock Server Verification)
# ---------------------------------------------------------------------------
if [ "${REDLOOP_DRILL_SELF_TEST:-}" = "1" ]; then
  echo "=== Running RedLoop WAF Drill Harness Self-Test ==="
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT

  # Python mock server simulating Cloudflare API and endpoints
  mock_port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
  mock_py="$tmp_dir/mock_server.py"

  cat << 'PYEOF' > "$mock_py"
import sys
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

rule_state = {"enabled": False}
probe_count = 0

class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        global probe_count
        if "/ruleset" in self.path:
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
            probe_count += 1
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
        else:
            self.send_response(404)
            self.end_headers()

    def do_PATCH(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        payload = json.loads(body.decode()) if body else {}

        if "dry_run=true" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "errors": [], "result": payload}).encode())
            return

        rule_state["enabled"] = payload.get("enabled", False)
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
  sleep 0.5

  cleanup_mock() {
    kill "$mock_pid" 2>/dev/null || true
    wait "$mock_pid" 2>/dev/null || true
  }
  trap cleanup_mock EXIT

  # Run self-test invocation against mock
  CF_API_BASE_OVERRIDE="http://127.0.0.1:$mock_port/rulesets" \
  MOCK_STAGING_URL="http://127.0.0.1:$mock_port/staging" \
  MOCK_PROD_MCTL="http://127.0.0.1:$mock_port/prod/mctl" \
  MOCK_PROD_APP="http://127.0.0.1:$mock_port/prod/app" \
  MOCK_PROD_API_HEALTH="http://127.0.0.1:$mock_port/prod/api/healthz" \
  MOCK_PROD_API_APEX="http://127.0.0.1:$mock_port/prod/api/apex" \
  MOCK_PROD_OPS="http://127.0.0.1:$mock_port/prod/ops" \
  MOCK_PROD_TG="http://127.0.0.1:$mock_port/prod/tg" \
  CF_TOKEN="mock-token" \
  REDLOOP_DRILL_SELF_TEST="" \
  "$0"

  echo "self-test PASSED successfully."
  exit 0
fi

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------
CF_TOKEN="${CLOUDFLARE_API_TOKEN:-${CF_TOKEN:-${1:-}}}"

if [ -z "$CF_TOKEN" ]; then
  echo "[-] ERROR: Cloudflare API token not provided."
  echo "    Usage: CF_TOKEN=<token> $0  OR  $0 <token>"
  exit 1
fi

ZONE_ID="86a90fe2fdfe87b9702842218b607f60"
RULESET_ID="4bdd5c0da7004933b40aae8fd0d5ce78"
RULE_ID="d8b4ea76eabc420e99146cafd9596801"
TARGET_HOST="staging-redloop.mctl.ai"

TARGET_URL="${MOCK_STAGING_URL:-https://${TARGET_HOST}/}"
API_URL="${CF_API_BASE_OVERRIDE:-https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/${RULESET_ID}/rules/${RULE_ID}}"

# Latency and Timeout Thresholds
MAX_PROD_LATENCY_SECONDS="${MAX_PROD_LATENCY_SECONDS:-1.000}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-60}"
PROBE_INTERVAL_SECONDS="${PROBE_INTERVAL_SECONDS:-1}"

# State Tracking
CURRENT_STATE="initial" # initial -> active -> rolling_back -> inert
SUMMARY_FILE="${GITHUB_STEP_SUMMARY:-/tmp/redloop_waf_drill_summary.md}"
TIMINGS_FILE="${TIMINGS_FILE:-/tmp/redloop_waf_drill_timings.json}"

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
  # Disable traps during rollback to avoid recursion
  trap - EXIT INT TERM ERR

  if [ "$CURRENT_STATE" = "inert" ]; then
    log "[+] State is already INERT (enabled=false confirmed). No rollback required."
    exit "$exit_code"
  fi

  log "[!] ================================================================="
  log "[!] EMERGENCY / RECOVERY ROLLBACK TRIGGERED (Exit code: $exit_code, State: $CURRENT_STATE)"
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
    http_resp=$(curl -sS -w "\n%{http_code}" -X PATCH "$API_URL" \
      -H "Authorization: Bearer $CF_TOKEN" \
      -H "Content-Type: application/json" \
      -d "$deact_payload" || true)

    local http_code
    http_code=$(echo "$http_resp" | tail -n 1)
    local body
    body=$(echo "$http_resp" | sed '$d')

    if [ "$http_code" = "200" ] && [ "$(echo "$body" | jq -r '.success // false')" = "true" ]; then
      log "[+] Rollback PATCH succeeded. Verifying via Cloudflare API read-back..."
      
      # Read-back verification
      local verify_resp
      verify_resp=$(curl -sS -X GET "$API_URL" -H "Authorization: Bearer $CF_TOKEN" || true)
      local verify_enabled
      verify_enabled=$(echo "$verify_resp" | jq -r 'if (.result | has("enabled")) then (.result.enabled | tostring) else "unknown" end')

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
    sleep "$((attempt * 2))"
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
    probe_out=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" "$url" || echo "000 99.999")
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

RULE_INFO=$(curl -sS -X GET "$API_URL" -H "Authorization: Bearer $CF_TOKEN")
SUCCESS=$(echo "$RULE_INFO" | jq -r '.success // false')

if [ "$SUCCESS" != "true" ]; then
  log "[-] API Auth / Read failed: $(echo "$RULE_INFO" | jq -c '.errors')"
  exit 1
fi

INITIAL_ENABLED=$(echo "$RULE_INFO" | jq -r '.result.enabled')
INITIAL_REF=$(echo "$RULE_INFO" | jq -r '.result.ref')
INITIAL_EXPR=$(echo "$RULE_INFO" | jq -r '.result.expression')

log "[+] Target Rule verified: ref=$INITIAL_REF, enabled=$INITIAL_ENABLED"
log "[+] Target Expression: $INITIAL_EXPR"

if [ "$INITIAL_ENABLED" != "false" ]; then
  log "[-] Target rule is NOT inert before drill! (enabled=$INITIAL_ENABLED). Expected enabled=false."
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
STAGING_INIT=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" "$TARGET_URL")
STAGING_CODE=$(echo "$STAGING_INIT" | awk '{print $1}')
if [ "$STAGING_CODE" != "404" ]; then
  log "[-] Initial staging probe failed: expected HTTP 404, got $STAGING_CODE"
  exit 1
fi
log "[+] Initial staging probe confirmed: HTTP 404 (Unrouted Origin Passthrough)."

# ---------------------------------------------------------------------------
# Step 2: Server-Side Validation (dry_run=true)
# ---------------------------------------------------------------------------
log "=== Step 2: Server-Side Request Validation via dry_run=true ==="

ACTIVATE_PAYLOAD='{
  "action": "block",
  "description": "staging-redloop: emergency kill switch / drill block",
  "enabled": true,
  "expression": "(http.host eq \"staging-redloop.mctl.ai\")"
}'

DRY_RUN_RESP=$(curl -sS -X PATCH "${API_URL}?dry_run=true" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$ACTIVATE_PAYLOAD")

DRY_RUN_SUCCESS=$(echo "$DRY_RUN_RESP" | jq -r '.success // false')
if [ "$DRY_RUN_SUCCESS" != "true" ]; then
  log "[-] Server-side dry_run validation failed: $(echo "$DRY_RUN_RESP" | jq -c '.errors')"
  exit 1
fi
log "[+] Server-side dry_run validation PASSED: syntax, scope, and payload accepted."

# ---------------------------------------------------------------------------
# Step 3: Activation (T0) & Continuous Observation
# ---------------------------------------------------------------------------
log "=== Step 3: Activating WAF Rule d8b4ea76eabc420e99146cafd9596801 (T0) ==="

T0_TS=$(iso_ts)
T0_EPOCH=$(python3 -c "import time; print(time.time())")

ACT_RESP=$(curl -sS -X PATCH "$API_URL" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$ACTIVATE_PAYLOAD")

ACT_SUCCESS=$(echo "$ACT_RESP" | jq -r '.success // false')
if [ "$ACT_SUCCESS" != "true" ]; then
  log "[-] Rule activation PATCH failed: $(echo "$ACT_RESP" | jq -c '.errors')"
  exit 1
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
    log "[-] TIMEOUT: Rule propagation exceeded ${MAX_WAIT_SECONDS}s without HTTP 403!"
    rollback
    exit 1
  fi

  # Concurrently verify production stability
  if ! check_production_controls "drill-active"; then
    log "[-] ALERT: Production degradation detected during activation! Aborting."
    rollback
    exit 1
  fi

  # Probe staging
  PROBE_TMP=$(mktemp)
  PROBE_HEADER=$(curl -sD - -o "$PROBE_TMP" -w "%{http_code} %{time_total}" "$TARGET_URL")
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

DEACT_RESP=$(curl -sS -X PATCH "$API_URL" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$DEACT_PAYLOAD")

DEACT_SUCCESS=$(echo "$DEACT_RESP" | jq -r '.success // false')
if [ "$DEACT_SUCCESS" != "true" ]; then
  log "[-] Rule deactivation PATCH failed: $(echo "$DEACT_RESP" | jq -c '.errors')"
  rollback
  exit 1
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
    log "[-] TIMEOUT: Recovery propagation exceeded ${MAX_WAIT_SECONDS}s without HTTP 404!"
    rollback
    exit 1
  fi

  PROBE_TMP=$(mktemp)
  PROBE_HEADER=$(curl -sD - -o "$PROBE_TMP" -w "%{http_code} %{time_total}" "$TARGET_URL")
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

FINAL_RULE_INFO=$(curl -sS -X GET "$API_URL" -H "Authorization: Bearer $CF_TOKEN")
FINAL_ENABLED=$(echo "$FINAL_RULE_INFO" | jq -r '.result.enabled')

if [ "$FINAL_ENABLED" != "false" ]; then
  log "[-] CRITICAL: Post-drill rule state is enabled=${FINAL_ENABLED}! Expected false."
  rollback
  exit 1
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
