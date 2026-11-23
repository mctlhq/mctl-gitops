#!/usr/bin/env bash
# Web contract preview assurance: isolated browser run + fail-closed report.
# Preview assurance only; not production conformance (mctlhq/mctl-gitops#2929).
#
#   assurance/web-contracts/run.sh                    full run
#   assurance/web-contracts/run.sh --consumer-plan-only   print the docker commands, run nothing
#
# Order matters (nothing is fetched after the network is isolated):
#   1. pin check and catalogue check (no browser, no docker)
#   2. BEFORE isolation: git archive of mctl-design at the pin, npm ci against the lockfile into a
#      directory outside the repo, images present locally (pulled here if missing)
#   3. docker network create --internal; fixture origin; mode:image consumers (dummy env, 60 s wait)
#   4. Playwright in the pinned image: runner UID, read-only rootfs, cap-drop ALL, no-new-privileges,
#      tmpfs, repo mounted read-only; no egress
#   5. report; guard counters; ALWAYS remove what this run created, by name (trap)
#
# Environment:
#   WCA_PREFIX       container/network name prefix (default wca-run); every name is <prefix>-<role>
#   WCA_OUT          output directory (default <repo>/assurance-out)
#   WCA_WORK         staging directory (default: a fresh mktemp -d, removed on exit)
#   WCA_DESIGN_REPO  a local mctl-design checkout holding the pinned commit; if unset the commit is
#                    fetched from the public GitHub repository before isolation
#   WCA_PINS         pins.json override (used only for the documented dry path)
#   WCA_CAPTURE_HTML 1 = also save each healthy consumer's landing page to <out>/consumer-html/<name>.html
#                    (evidence for choosing selectors; off by default)
#   WCA_PW_ARGS      extra Playwright CLI arguments, e.g. a --grep filter for debugging (the report
#                    then lists every unselected case as NOT-RUN; such a run proves nothing)
#
# Exit codes: the report's (0 ok, 1 a case FAILed, 2 a negative control did not FAIL, 3 unreadable
# input or rejected pin), plus 4 = the guard saw an unexpected request or its log does not account
# for every executed test, 5 = setup failed, the Playwright runner crashed, or a fixture case that
# should have run is NOT-RUN.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
PINS=${WCA_PINS:-$HERE/pins.json}
REPORT=$HERE/report/build_report.py
PREFIX=${WCA_PREFIX:-wca-run}
OUT=${WCA_OUT:-$REPO/assurance-out}
RUN_UID=$(id -u)
RUN_GID=$(id -g)
DRY=0
[ "${1:-}" = "--consumer-plan-only" ] && DRY=1

NET=$PREFIX-net
ORIGIN=$PREFIX-origin
RUNNER=$PREFIX-runner
RUN_ID=$$-$(date +%s)   # every container carries label wca.run=$RUN_ID; cleanup removes only those
CREATED_CONTAINERS=()
CREATED_NET=0
OWN_WORK=0

log() { printf 'run.sh: %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit "${2:-5}"; }

# One docker entry point so the dry path prints exactly what a real run would execute.
dk() {
  if [ "$DRY" = 1 ]; then printf 'DRY: docker %s\n' "$*" >&2; return 0; fi
  docker "$@"
}

# shellcheck disable=SC2329  # invoked through the EXIT trap
cleanup() {
  local rc=$?
  set +e
  [ "$DRY" = 1 ] && return "$rc"
  # Only what this run created, only by exact name: no pattern kill, no prune, no image removal.
  for c in "${CREATED_CONTAINERS[@]:-}"; do
    [ -n "$c" ] || continue
    # remove only a container this run labelled; a same-named foreign container is left alone
    [ "$(docker inspect -f '{{index .Config.Labels "wca.run"}}' "$c" 2>/dev/null)" = "$RUN_ID" ] \
      && docker rm -f "$c" >/dev/null 2>&1
  done
  if [ "$CREATED_NET" = 1 ]; then
    docker network rm "$NET" >/dev/null 2>&1 || log "WARNING: could not remove network $NET (an endpoint may still be attached): remove it by name"
  fi
  if [ "$OWN_WORK" = 1 ] && [ -n "${WORK:-}" ]; then rm -rf "$WORK"; fi
  return "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

pin() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$PINS" "$1"; }

# ------------------------------------------------------------------ 1. checks
log "1/5 pin check and catalogue check"
DESIGN_ARGS=()
if [ -n "${WCA_DESIGN_REPO:-}" ]; then DESIGN_ARGS=(--design-repo "$WCA_DESIGN_REPO"); fi
python3 "$REPORT" --check-pins --pins "$PINS" ${DESIGN_ARGS[@]+"${DESIGN_ARGS[@]}"} || exit 3
python3 "$HERE/report/gen_cases.py" --check || exit 3

PW_IMAGE=$(pin "d['playwright_image']")
NGINX_IMAGE=$(pin "d['nginx_image']")
COMMIT=$(pin "d['mctl_design']['commit']")
CONSUMER_LINES=$(pin "'\n'.join(s['name']+' '+s['image'] for s in d['sites'] if s['mode']=='image')")

# ------------------------------------------------------------------ 2. before isolation
if [ "$DRY" = 1 ]; then
  WORK=${WCA_WORK:-/nonexistent-dry-run}
else
  log "2/5 staging (network access is still allowed here)"
  if [ -n "${WCA_WORK:-}" ]; then WORK=$WCA_WORK; mkdir -p "$WORK"; else WORK=$(mktemp -d); OWN_WORK=1; fi
  mkdir -p "$OUT"
  rm -rf "$OUT/junit.xml" "$OUT/guard.jsonl" "$OUT/consumers.json" "$OUT/results.json" "$OUT/matrix.md" \
         "$OUT/network.txt" "$OUT/test-results" "$OUT/consumer-html"

  # pinned mctl-design bytes: a read-only git archive of the pinned commit
  ARCH=$WORK/arch
  rm -rf "$ARCH" "$WORK/design"; mkdir -p "$ARCH" "$WORK/design"
  if [ -n "${WCA_DESIGN_REPO:-}" ]; then
    SRC=$WCA_DESIGN_REPO
  else
    SRC=$WORK/design-src
    git init -q "$SRC"
    git -C "$SRC" fetch -q --depth 1 https://github.com/mctlhq/mctl-design.git "$COMMIT" || die "cannot fetch the pinned mctl-design commit"
  fi
  git -C "$SRC" archive "$COMMIT" apps/storybook/public/0.21.0 apps/storybook/public/0.20.2 | tar -x -C "$ARCH" \
    || die "git archive of the pinned commit failed"
  for v in 0.21.0 0.20.2; do cp -R "$ARCH/apps/storybook/public/$v" "$WORK/design/$v"; done
  # the floating sheets are the current version's bytes
  cp "$WORK"/design/0.21.0/*.css "$WORK/design/"
  chmod -R a+rX "$WORK/design"

  # Playwright dependencies, installed on the host from the lockfile BEFORE isolation
  mkdir -p "$WORK/npm"
  cp "$HERE/package.json" "$HERE/package-lock.json" "$WORK/npm/"
  (cd "$WORK/npm" && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm ci --ignore-scripts --no-audit --no-fund >/dev/null) \
    || die "npm ci failed"
  chmod -R a+rX "$WORK/npm"

  # every image must be local before the network exists; pull here, never afterwards
  ensure_image() { docker image inspect "$1" >/dev/null 2>&1 || docker pull -q "$1" >/dev/null || die "cannot get image $1"; }
  ensure_image "$PW_IMAGE"
  ensure_image "$NGINX_IMAGE"
  while read -r name image; do [ -n "${name:-}" ] && ensure_image "$image"; done <<<"$CONSUMER_LINES"
fi

# ------------------------------------------------------------------ 3. isolated network
HARDEN=(--pull=never --label "wca.run=$RUN_ID" --user "$RUN_UID:$RUN_GID" --read-only --cap-drop ALL --security-opt no-new-privileges
        --pids-limit 512 --tmpfs "/tmp:rw,nosuid,size=512m")

log "3/5 isolated network and fixture origin"
if [ "$DRY" = 0 ] && docker network inspect "$NET" >/dev/null 2>&1; then
  die "network $NET already exists; refusing to touch it (set WCA_PREFIX to a free prefix)"
fi
if [ "$DRY" = 0 ]; then
  # a pre-existing container with one of our names is never touched: refuse before creating anything
  names=("$ORIGIN" "$RUNNER" "$PREFIX-probe")
  while read -r name image; do [ -n "${name:-}" ] && names+=("$PREFIX-$name"); done <<<"$CONSUMER_LINES"
  for n in "${names[@]}"; do
    if docker container inspect "$n" >/dev/null 2>&1; then
      die "container $n already exists; refusing to touch it (set WCA_PREFIX to a free prefix)"
    fi
  done
  CREATED_NET=1
fi
dk network create --internal "$NET" >/dev/null
if [ "$DRY" = 0 ]; then
  internal=$(docker network inspect -f '{{.Internal}}' "$NET")
  printf 'network=%s Internal=%s\n' "$NET" "$internal" | tee "$OUT/network.txt" >&2
  [ "$internal" = "true" ] || die "network $NET is not Internal: refusing to run"
fi

FIX=$HERE/fixtures
CREATED_CONTAINERS+=("$ORIGIN")
dk run -d --name "$ORIGIN" --network "$NET" --network-alias ui.fixture.test --network-alias site.fixture.test \
  "${HARDEN[@]}" --memory 256m \
  -v "$FIX/origin/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$FIX/origin/security-headers.conf:/etc/nginx/snippets/security-headers.conf:ro" \
  -v "${WORK}/design:/srv/design:ro" -v "$FIX:/srv/fixtures:ro" "$NGINX_IMAGE" >/dev/null

probe_origin() {
  docker exec "$ORIGIN" wget -q -O- --header 'Host: site.fixture.test' http://127.0.0.1:8080/healthz >/dev/null 2>&1 \
    && docker exec "$ORIGIN" wget -q -O- --header 'Host: ui.fixture.test' http://127.0.0.1:8080/healthz >/dev/null 2>&1
}
if [ "$DRY" = 0 ]; then
  ok=0
  for _ in $(seq 1 60); do probe_origin && { ok=1; break; }; sleep 1; done
  [ "$ok" = 1 ] || { docker logs --tail 20 "$ORIGIN" >&2 || true; die "fixture origin not healthy within 60 s"; }
fi

# mode:image consumers: dummy env only, 60 s health wait; a failure is NOT-RUN with a sanitized reason.
ALLOW_HOSTS=""
CONSUMER_JSON='{}'
sanitize() { python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from build_report import sanitize_text; lines = sys.stdin.read().strip().splitlines(); print(sanitize_text(lines[-1] if lines else "")[:200])' "$HERE/report"; }
while read -r name image; do
  [ -n "${name:-}" ] || continue
  c=$PREFIX-$name
  alias=consumer-$name
  CREATED_CONTAINERS+=("$c" "$PREFIX-probe")
  dk run -d --name "$c" --network "$NET" --network-alias "$alias" "${HARDEN[@]}" --memory 384m \
    -e NODE_ENV=production -e PORT=8080 -e OAUTH_CLIENT_ID=dummy -e OAUTH_CLIENT_SECRET=dummy \
    -e TELEGRAM_BOT_TOKEN=dummy -e SESSION_SECRET=dummy "$image" >/dev/null || true
  healthy=false; reason="did not answer on port 8080 within 60 s"
  if [ "$DRY" = 0 ]; then
    for _ in $(seq 1 20); do
      if [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" != "true" ]; then reason="container exited"; break; fi
      if docker run --rm --name "$PREFIX-probe" --network "$NET" "${HARDEN[@]}" "$PW_IMAGE" node -e \
        "require('http').get('http://$alias:8080/',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))" >/dev/null 2>&1; then
        healthy=true; reason=""; break
      fi
      sleep 3
    done
    [ "$healthy" = true ] || reason="$(docker logs --tail 5 "$c" 2>&1 | sanitize || true) ($reason)"
    # Optional evidence for choosing consumer selectors from observation (WCA_CAPTURE_HTML=1): the landing
    # page exactly as the healthy image serves it, fetched from inside the isolated network by a hardened
    # container, capped at 2 MiB. It is the unauthenticated page of an app with dummy env; a failed capture
    # is a warning, never a verdict.
    if [ "$healthy" = true ] && [ "${WCA_CAPTURE_HTML:-0}" = 1 ]; then
      mkdir -p "$OUT/consumer-html"
      CREATED_CONTAINERS+=("$PREFIX-capture")
      docker run --rm --name "$PREFIX-capture" --network "$NET" "${HARDEN[@]}" "$PW_IMAGE" node -e \
        "require('http').get('http://$alias:8080/',r=>{process.stderr.write('status '+r.statusCode+'\n');r.pipe(process.stdout)}).on('error',e=>{process.stderr.write(String(e)+'\n');process.exit(1)})" \
        2>"$OUT/consumer-html/$name.status" | head -c 2097152 >"$OUT/consumer-html/$name.html" \
        || log "WARNING: could not capture the landing page of $name"
    fi
  fi
  ALLOW_HOSTS="${ALLOW_HOSTS:+$ALLOW_HOSTS,}$alias"
  CONSUMER_JSON=$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); d[sys.argv[2]]={"healthy": sys.argv[3]=="true","url":"http://"+sys.argv[4]+":8080/","reason":sys.argv[5]}; print(json.dumps(d))' \
    "$CONSUMER_JSON" "$name" "$healthy" "$alias" "$reason")
done <<<"$CONSUMER_LINES"

if [ "$DRY" = 1 ]; then
  dk run --name "$RUNNER" --network "$NET" "${HARDEN[@]}" --memory 1536m --shm-size 256m \
    -v "$REPO:/repo:ro" -v "<work>/npm/node_modules:/deps/node_modules:ro" -v "<work>/design:/design:ro" -v "<out>:/out" \
    -e WCA_OUT=/out -e WCA_DESIGN_DIR=/design -e "WCA_ALLOW_HOSTS=$ALLOW_HOSTS" -e NODE_PATH=/deps/node_modules \
    -w /repo/assurance/web-contracts "$PW_IMAGE" node /deps/node_modules/@playwright/test/cli.js test
  exit 0
fi
printf '%s\n' "$CONSUMER_JSON" > "$OUT/consumers.json"

# ------------------------------------------------------------------ 4. Playwright
log "4/5 Playwright in the pinned image on the internal network"
CREATED_CONTAINERS+=("$RUNNER")
docker run --name "$RUNNER" --network "$NET" "${HARDEN[@]}" --memory 1536m --shm-size 256m \
  -v "$REPO:/repo:ro" -v "$WORK/npm/node_modules:/deps/node_modules:ro" -v "$WORK/design:/design:ro" -v "$OUT:/out" \
  -e CI=1 -e HOME=/tmp/home -e WCA_OUT=/out -e WCA_DESIGN_DIR=/design -e "WCA_ALLOW_HOSTS=$ALLOW_HOSTS" \
  -e NODE_PATH=/deps/node_modules -w /repo/assurance/web-contracts "$PW_IMAGE" \
  node /deps/node_modules/@playwright/test/cli.js test --config /repo/assurance/web-contracts/playwright.config.ts ${WCA_PW_ARGS:-} \
  && PW_RC=0 || PW_RC=$?
log "playwright exit code $PW_RC (1 is expected while negative controls fail; the report decides)"
# 0 = all passed, 1 = some tests failed; anything else is a runner crash, not a verdict
case "$PW_RC" in 0|1) ;; *) die "Playwright runner crashed (exit $PW_RC): the results are not a verdict" 5 ;; esac

# ------------------------------------------------------------------ 5. report and guard counters
log "5/5 report"
ATTEMPT=${GITHUB_RUN_ID:+$GITHUB_RUN_ID-${GITHUB_RUN_ATTEMPT:-1}}
ATTEMPT=${ATTEMPT:-local-$(date +%s)}
BUNDLE=$WORK/assurance-out.tgz
tar -czf "$BUNDLE" -C "$OUT" --exclude=results.json --exclude=matrix.md . 2>/dev/null || true
set +e
python3 "$REPORT" --junit "$OUT/junit.xml" --cases "$HERE/cases.json" --pins "$PINS" \
  --out-dir "$OUT" --artifact "$BUNDLE" --attempt-id "$ATTEMPT"
REPORT_RC=$?
set -e

# guard counters: could not observe is never "zero"; a missing or unreadable log is an error
GUARD_RC=0
python3 - "$OUT/guard.jsonl" "$OUT/junit.xml" <<'PY' || GUARD_RC=$?
import json, sys
import xml.etree.ElementTree as ET
path, junit = sys.argv[1:3]
try:
    rows = [json.loads(l) for l in open(path) if l.strip()]
    executed = len(ET.parse(junit).getroot().findall(".//testcase"))
except (OSError, ValueError, ET.ParseError) as exc:
    print(f"guard: log or junit unreadable ({type(exc).__name__}): cannot claim zero unexpected requests", file=sys.stderr)
    sys.exit(4)
if not rows:
    print("guard: no records: cannot claim zero unexpected requests", file=sys.stderr)
    sys.exit(4)
if len(rows) != executed:
    # a test that bypassed the wca fixture (bare page or request) leaves no row: unknown, not zero
    print(f"guard: {len(rows)} records for {executed} executed tests: some test is not accounted for", file=sys.stderr)
    sys.exit(4)
unexpected = sum(r["unexpected_blocked"] for r in rows)
probes = sum(len(r["blocked"]) - r["unexpected_blocked"] for r in rows)
hosts = {}
for r in rows:
    for h, n in r["hosts"].items():
        hosts[h] = hosts.get(h, 0) + n
# Only requests the browser contexts issued through the route guard are counted here; the
# network itself (docker --internal) is the enforcement, this is an in-band tripwire.
print(f"guard: {len(rows)}/{executed} tests accounted for, requests per host {hosts}, expected probe aborts {probes}, "
      f"unexpected blocked {unexpected}", file=sys.stderr)
sys.exit(4 if unexpected else 0)
PY

# a fixture case that should have run but is NOT-RUN is an incomplete run, not a quiet gap
COMPLETE_RC=0
python3 - "$OUT/results.json" "$HERE/cases.json" <<'PY' || COMPLETE_RC=$?
import json, sys
try:
    res = json.load(open(sys.argv[1]))["results"]
    cases = {c["id"]: c for c in json.load(open(sys.argv[2]))["cases"]}
except (OSError, ValueError, KeyError) as exc:
    print(f"completeness: unreadable ({type(exc).__name__}): cannot claim the fixture cases ran", file=sys.stderr)
    sys.exit(5)
# documented NOT-RUN in fixture sites: the G4 placeholder and the catalogued known gaps
bad = [r["id"] for r in res
       if r["site"].startswith("fixture-") and r["kind"] == "case" and r["status"] == "NOT-RUN"
       and cases[r["id"]].get("gate") != "G4" and not cases[r["id"]].get("known_gap")]
if bad:
    print(f"completeness: {len(bad)} fixture case(s) NOT-RUN outside the documented allowlist: {bad[:5]}", file=sys.stderr)
    sys.exit(5)
PY

if [ "$REPORT_RC" != 0 ]; then exit "$REPORT_RC"; fi
if [ "$GUARD_RC" != 0 ]; then exit 4; fi
if [ "$COMPLETE_RC" != 0 ]; then exit 5; fi
exit 0
