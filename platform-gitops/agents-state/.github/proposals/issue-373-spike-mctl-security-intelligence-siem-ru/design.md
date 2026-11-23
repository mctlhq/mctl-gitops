# Design: issue-373-spike-mctl-security-intelligence-siem-ru

## Current state

The spike already exists in this repository as a specification only:

- `docs/spikes/security-intelligence.md` (at `mctlhq/.github@60e9db522f18299e73dac23fffedfe5b4ce81930`)
  is "Proposal Revision 2". It defines rule EG373-R1 revision 1 (CONNECT + status 200,
  normalized `host:port` compared by exact equality to a versioned allowset), a 12-case
  answer key E1-E12, the dispositions MATCH_REFERENCE / NO_MATCH / REPLAY / CONFLICT /
  REJECT / UNKNOWN / COVERAGE_UNKNOWN, replay key `(source,id)` plus canonical content
  digest, a five-field output schema, three weak baselines (null, substring, ignore-port),
  exit codes 0/1/2, and an exit-from-DEFER matrix. Its "Runnable harness specification"
  is marked NOT IMPLEMENTED; raw parser fixtures are NOT CREATED.
- `docs/spikes/security-intelligence/fixtures/normalized.jsonl` (12 rows, E12 is
  `{"coverage":"missing-source"}`), `allowset.json` (`revision: eval1`,
  `["allowed.invalid:443"]`) and `expected.json` (12 rows, `rule_revision: EG373-R1/1`,
  `evidence_ref: fixture:<id>`; E3/E4 reuse `fixture:e2`).
- The spike is not registered: there is no `roadmap/spikes/security-intelligence.yaml`
  and no entry under `# Spikes` in `AGENTS.md`, unlike sibling spikes
  (`roadmap/spikes/cve-advisory-impact.yaml`, schema
  `roadmap/schemas/spike-definition.schema.json`, lifecycle enum
  proposed|parked|active|decided|archived, validated by `roadmap/scripts/validate.py`
  in `.github/workflows/roadmap-validate.yml`).
- Sibling reference models follow one convention: `docs/spikes/<name>/model.py`
  stdlib-only plus `tests/test_*.py`, and each is listed in the `paths:` filters and a
  `python3 -I -m unittest discover -s docs/spikes/<name>/tests -v` step of
  `.github/workflows/workflow-tests.yml` (e.g. finance-assistant, cve-advisory-impact).
  `docs/spikes/cve-advisory-impact/model.py` reuses the #209 model by path import,
  the precedent for reusing SecurityFinding semantics without a second schema.
- `docs/spikes/security-finding-lifecycle.md` (#209) defines the finding lifecycle that
  D2 must reuse, not duplicate.

Deployed state checked:
- `$MCTL_GITOPS_ROOT` = mctl-gitops `platform-gitops/` at `d29edb4a39fac427518461c479e4cc349a014331` (2026-11-22).
- `infra-components/mctl-platform/mctl-agents-egress-proxy/proxy.yaml`: Squid
  `ubuntu/squid@sha256:8a3baed4...610963c`, `access_log stdio:/dev/stdout squid`,
  `http_access deny !Safe_ports`, `deny CONNECT !SSL_ports`, deny link-local/loopback,
  then `http_access allow all` (stage A allow-all). Matches Revision 2's pins. The native
  `squid` log field layout is not defined in this checkout.
- `bootstrap/templates/observability/loki.yaml`: Promtail ships the k3s Kubernetes API
  audit log (job `kube-apiserver-audit`, #871, metadata-level policy, control-plane only)
  and the Vault audit stream with a metrics stage `vault_audit_entries_total`; Loki
  retention 336h, Vault audit stream 720h. No Squid/egress-specific pipeline stage or
  counter was found (grep for squid/egress: no match), consistent with #2232 counters
  still open.
- `infra-components/observability/vm-rules/vault-audit-alerts.yaml`: VaultAuditLogSilent
  and VaultAuditLogAbsent kept separate ("could not observe" vs "observed quiet") - the
  existing native pattern for detector silence. `mctl-api-alerts.yaml` has
  MctlApiAuditWriteFailures. No egress, Falco, Wazuh or OpenSearch rule or component
  found (grep: no match in `platform-gitops/`).
- `bootstrap/templates/observability/obi-spike.yaml`: renders nothing while
  `obiSpike.enabled` is false; live gate is #2303. OBI is telemetry, not detection.
- `mctl_incident_summary`: total 0 active incidents at read time. This is "no active
  incident", not evidence of detector coverage.
- Not observed this run: ZITADEL event API/retention, mctl-api MCP actor/subject decision
  audit schema, GitHub/CI audit, Cloudflare logs, live Loki arrival for any stream,
  SecurityFinding v1 enablement (mctl-api#774) in production. All are UNKNOWN.

## Proposed solution

Revision 3 of the existing spike package. Everything stays under
`docs/spikes/security-intelligence*` plus roadmap/CI registration; no service, gitops or
runtime change.

1. `docs/spikes/security-intelligence/offline_eval.py` (stdlib only), implementing the
   Revision 2 harness exactly:
   - Preconditions: the three fixture paths exist and their SHA-256 values equal pins
     recorded in `fixtures/SHA256SUMS`; otherwise exit 2, readiness UNKNOWN.
   - Validation order (normative clarification in Revision 2): case envelope / coverage
     union -> field set exactly `{id,source,method,destination,status}` with types and
     bounds -> source trust (`fixture-squid` only, else REJECT) -> supported method and
     host syntax (CONNECT, DNS `host:port`; absolute URL, IP literal, IPv6 -> UNKNOWN) ->
     replay key `(source,id)` with `sha256(canonical_json(input))` (identical -> REPLAY,
     different -> CONFLICT, first retained) -> rule.
   - Rule `EG373-R1/1`: status != 200 -> NO_MATCH; normalize (ASCII lowercase, strip one
     terminal dot); exact membership in allowset -> NO_MATCH else MATCH_REFERENCE.
   - Output: list of five-field rows, `evidence_ref = "fixture:" + id` (E12:
     `fixture:missing-source`, as frozen in `expected.json`), canonical JSON
     (`sort_keys`, `separators=(",",":")`), plus a summary with per-disposition counts
     and per-case observed/expected; exit 0/1/2.
   - Isolation assertions: forbidden-field scan over outputs (no destination, host, URL,
     tenant, user, client or raw text; no incident/finding/proposal/approval keys);
     a self-check that `sys.modules` contains none of `socket`-using clients
     (`urllib.request`, `http.client`, `subprocess`, `ssl`) after import.
   - Baselines (`null`, `substring`, `ignore_port`) as alternate rule functions run on
     the same cases; the run FAILs if any designated baseline passes its designated case.
   - Descriptive wall time and `resource`/`tracemalloc` peak memory, labelled
     host-bound and not a performance claim.
2. `docs/spikes/security-intelligence/tests/test_offline_eval.py`: per-case conformance,
   exit codes (0 on frozen key, 1 on a mutated expected row, 2 on a missing file or
   hash mismatch), determinism (two runs byte-identical), baseline discrimination,
   forbidden-field and no-network assertions, plus extra robustness cases kept in the
   test file only (IP literal, double dot, empty host, port out of range, extra field)
   that must yield UNKNOWN/REJECT, without changing the frozen eval1 key.
3. `docs/spikes/security-intelligence.md` gains Revision 3 sections, preserving
   Revision 2 text verbatim below them:
   - D1 source-pinned matrix (table above, each row observed/UNKNOWN with SHA and path).
   - D2 definitions: security event (authenticated source observation) -> DetectionResult
     (EG373 output, no authority) -> incident (existing Incident Management only, by a
     separately authorized writer) -> SecurityFinding/Occurrence (#209 contract, only
     with confirmed evidence). A mere alert never creates a finding or authorizes
     remediation. OCSF/ECS: minimal mapping table only (Network Activity for CONNECT),
     no schema adoption. Sigma/ATT&CK: note T1071/T1041-style relevance as reference,
     no coverage claim from one rule.
   - D3 comparison table for native VMRule/Loki ruler, Falco, Wazuh, OpenSearch Security
     Analytics, Splunk interop: privilege (Falco needs eBPF/kernel access similar to the
     provisional OBI posture), tenancy, ops/HA, storage, rollback. Version and license
     cells are filled only from fetched sources with date; otherwise "unverified".
   - D4 offline scenario matrix: the 12 executed EG373 cases with measured results from
     the harness run; the remaining issue scenarios (auth+Vault/K8s, cross-tenant
     denial, runtime process, identity joins, benign release) listed as SEC373 future
     cases with status NOT RUN and the reason.
   - D5 trace event -> detection -> existing incident -> investigation -> optional
     finding -> governed proposal/approval -> mitigation verification, marking every
     arrow after "detection" as not implemented and requiring the consumer-isolation
     proof from the exit matrix first; reuse #342/#306 correlation ids
     (REUSE_WORK_ITEM_ID) rather than a new correlation key.
   - D6 verdict: primary **DEFER** (live ingestion, external SIEM/sensor and incident
     integration), with **EXTEND_NATIVE_DETECTION** as the secondary candidate, not
     authorized, gated by the exit-from-DEFER rows. Rationale: native Loki/VMRule already
     shows the required silence/absent pattern (Vault), the egress source lacks arrival
     counters and a parser contract (#2232), and no source today offers tenant
     attribution that a SIEM would add.
   - D7 independent review request and outstanding questions.
4. `roadmap/spikes/security-intelligence.yaml` SpikeDefinition: `lifecycle: proposed`,
   issue `mctlhq/.github#373`, the six outcomes from the issue, `timebox.decisionBy`,
   `evidence.report: docs/spikes/security-intelligence.md`, no `decision` block.
5. `AGENTS.md` `# Spikes` entry and `.github/workflows/workflow-tests.yml` path filter +
   `python3 -I -m unittest discover -s docs/spikes/security-intelligence/tests -v` step.

## Alternatives

- Keep Revision 2 as specification only and write prose D1-D6: rejected, the owner
  asked for measured results; without an executed harness there is nothing measured.
- Model the slice on the Kubernetes audit stream (#871), which already ships to Loki:
  rejected, Revision 2 explicitly supersedes the K8s minimal-slice candidate and the
  owner decision names Squid egress #2232 fixtures.
- Build the slice as a Loki ruler / VMRule unit test (`vm-rules/tests/*_test.yaml`) in
  mctl-gitops: rejected now, it requires a log pipeline counter that does not exist and
  a gitops change; it is the natural next slice if EXTEND_NATIVE_DETECTION is chosen.
- Evaluate Falco/Wazuh by running them locally on fixtures: rejected, D3 forbids live or
  external deployment and synthetic process fixtures cannot measure kernel-sensor value.

## Platform impact

- No migration, no runtime, gitops, tenant or deployed-service change; docs, fixtures,
  one stdlib script, tests, one roadmap manifest and CI filter only.
- CI cost: one additional sub-second unittest step in `workflow-tests.yml`.
- `roadmap-validate.yml` will validate the new SpikeDefinition; a schema error blocks
  the PR, so the manifest must match `spike-definition.schema.json`.
- Risk: PASS on 12 public cases is read as general accuracy or parser/live readiness.
  Mitigation: the summary prints "conformance to public key eval1; parser readiness
  UNKNOWN; live coverage UNKNOWN" and the report repeats it.
- Risk: frozen key drift. Mitigation: SHA-256 pins; any fixture change requires a new
  revision and exits 2 against old pins.
- Risk: authority creep (incident/finding writes). Mitigation: forbidden-field and
  no-client assertions in tests; D5 marks downstream arrows not implemented.
- Privacy: only `.invalid` synthetic domains; no customer or raw security payloads.
