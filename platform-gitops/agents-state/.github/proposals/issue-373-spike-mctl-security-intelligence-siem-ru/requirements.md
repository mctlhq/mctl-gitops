# MCTL Security Intelligence spike (#373): offline egress detection slice and evidence-based SIEM decision package

## Context

mctlhq/.github#373 asks whether MCTL can materially improve security detection and
cross-source correlation with its existing stack (Loki/Promtail, VictoriaMetrics
VMRules, Incident Management, SecurityFinding v1, governed proposals), or whether a
bounded SIEM or runtime-security pilot (Falco, Wazuh, OpenSearch Security Analytics,
Splunk interop) is justified. The owner priority decision of 2026-11-22 makes the
research P1, keeps DEFER for live ingestion, new external SIEM/sensor and incident
integration, and asks for one concrete offline vertical slice: synthetic Squid egress
fixtures (mctlhq/mctl-gitops#2232), one deterministic rule, isolated DetectionResult
and replay semantics, trusted attribution, positive/negative/missing/forged tests,
measured results and an exit-from-DEFER matrix. No live probe, write, remediation,
intake, implementer or deployment is authorized by the issue.

The repository already holds `docs/spikes/security-intelligence.md` ("Proposal
Revision 2") and three frozen fixture files under
`docs/spikes/security-intelligence/fixtures/` (`normalized.jsonl`, `allowset.json`,
`expected.json`) that specify rule EG373-R1 revision 1 and a 12-case answer key, with
the harness explicitly "NOT IMPLEMENTED". This proposal (Revision 3) turns that
specification into a stdlib-only offline evaluator with tests, adds the missing D1-D6
research sections around it, registers the spike in the roadmap, and stops at
`proposed`. Building it still requires the owner's separate GO through the normal
DevLoop decide page; approving this proposal is that GO and nothing more.

## User stories

- AS the platform owner I WANT a measured, reproducible offline result for one
  egress rule SO THAT the DEFER / EXTEND_NATIVE_DETECTION decision rests on evidence,
  not on tool lists.
- AS a security reviewer I WANT every source in a pinned current-state matrix with
  observed / UNKNOWN status SO THAT absent signal is never read as "no threat".
- AS the Incident Management / SecurityFinding owner I WANT detection results kept
  separate from incidents and findings SO THAT an alert cannot create a vulnerability
  or authorize remediation.
- AS the #2232 egress source owner I WANT the parser-readiness gap stated as a
  blocking UNKNOWN SO THAT normalized-case conformance is not mistaken for raw-log or
  live coverage.
- AS an independent reviewer I WANT deliberately weak baselines that must fail SO
  THAT the answer key is proven discriminating.

## Acceptance criteria (EARS)

Harness behaviour
- WHEN `python3 -I offline_eval.py --fixtures fixtures/normalized.jsonl --allowset fixtures/allowset.json --expected fixtures/expected.json --out results.json` is run THE SYSTEM SHALL emit, for each of E1-E12, exactly the five fields `case_id, disposition, rule_revision, allowset_revision, evidence_ref`, and every observed row SHALL equal the corresponding row of the frozen `expected.json`.
- WHEN every mandatory expectation and isolation assertion holds THE SYSTEM SHALL exit 0; IF any observed output mismatches or a boundary assertion fails THEN THE SYSTEM SHALL exit 1; IF a fixture file, its pinned SHA-256 or another precondition is missing THEN THE SYSTEM SHALL exit 2 and report overall readiness UNKNOWN.
- WHEN a CONNECT event with status 200 has a normalized `host:port` not exactly in the allowset THE SYSTEM SHALL return MATCH_REFERENCE; WHEN it is exactly in the allowset THE SYSTEM SHALL return NO_MATCH.
- WHEN a valid CONNECT event has a non-200 status THE SYSTEM SHALL return NO_MATCH and SHALL NOT assert a successful tunnel.
- THE SYSTEM SHALL normalize hosts only by ASCII lowercase and removal of one terminal dot, and SHALL NOT perform suffix matching, DNS resolution, IP attribution or tenant inference.
- WHEN a (source, id) pair repeats with an identical canonical source-content digest THE SYSTEM SHALL return REPLAY with no additional MATCH; WHEN it repeats with a different digest THE SYSTEM SHALL return CONFLICT and retain the first observation.
- IF an event's source is not `fixture-squid` THEN THE SYSTEM SHALL return REJECT and produce no detection.
- IF the method or destination syntax is unsupported (non-CONNECT, absolute URL, IP literal, IPv6) or a required field is missing or mistyped THEN THE SYSTEM SHALL return UNKNOWN, never a clean negative.
- WHEN the input is `{"coverage": "missing-source"}` THE SYSTEM SHALL return COVERAGE_UNKNOWN.
- WHILE the harness runs THE SYSTEM SHALL use only the standard library and the three local files, with no network, environment credentials, subprocess or API client imports, and replay state SHALL be in memory only and discarded at exit.
- THE SYSTEM SHALL produce byte-identical canonical JSON on repeated runs over the same inputs.
- THE SYSTEM SHALL NOT include destination, client, user, tenant, URL or raw-source text in any output row (forbidden-field scan), and SHALL NOT emit incident, finding, proposal or approval fields.

Baselines
- WHEN the null baseline, substring allow-check baseline and ignore-port baseline are run on the same key THE SYSTEM SHALL record that null fails E2/E7/E9, substring fails E9 and ignore-port fails E7; IF any designated baseline passes its designated case THEN the key SHALL be reported non-discriminating and the run SHALL FAIL.

Report (D1-D7)
- THE SYSTEM SHALL record a source-pinned current-state matrix (repo SHA/path, read date, owner, schema, tenant attribution, retention, detector silence handling, observed / UNKNOWN) for Kubernetes API audit, Vault audit, ZITADEL, mctl-api/MCP audit, GitHub/CI, Cloudflare and Squid egress/runtime.
- IF a source could not be read THEN the report SHALL record it as UNKNOWN (not observed), never as absent.
- THE SYSTEM SHALL define security event, detection result, incident, SecurityFinding and Occurrence, and SHALL state that a detection result never creates an incident, finding or remediation by itself.
- THE SYSTEM SHALL compare native Loki/VMRule rules, Falco, Wazuh, OpenSearch Security Analytics and Splunk interop with each version/license claim marked as source-pinned or unverified.
- THE SYSTEM SHALL state exactly one primary verdict from the issue's outcome set, with any secondary candidate marked as not authorized.
- WHILE the spike lifecycle is `proposed` THE SYSTEM SHALL NOT add `agents:intake`, start a DevLoop for follow-ups, or create follow-up issues.

## Out of scope

- Live ingestion, Loki queries, Promtail/Alloy stages, new VMRules or any gitops change.
- Deploying or registering Falco, Wazuh, OpenSearch, Splunk or OBI (#2286/#2303 own OBI).
- Raw Squid log parser fixtures and parser readiness (blocked on the #2232 source owner's pinned format proof; stays UNKNOWN).
- Incident Management or SecurityFinding writes, incident routing, token revocation, blocking, remediation or any user-facing action.
- Production replay/dedup keys and retention (owned by the source and API owners).
- Changing the frozen eval1 fixtures or answer key; adding new cases needs a new revision.
- Cross-tenant, auth+Vault/K8s correlation and runtime-process scenarios as executable cases (documented as future SEC373 integration coverage only).
- Editing issue #373 labels, creating an epic or follow-up issues.

## Open questions

- Accountable owner for "existing detection/API owner TBD" in the exit-from-DEFER matrix is not appointed; recorded as UNKNOWN.
- Whether `/proc`-level runtime detection (Falco) is ever acceptable on the k3s nodes given the privileged-PSA posture already provisional for OBI (#2303); left to the owner decision.
- The squid `access_log ... squid` native format layout is not defined in the gitops checkout; the #2232 owner must supply versioned upstream proof before any parser run.
- ZITADEL, mctl-api MCP decision audit, GitHub/CI and Cloudflare event schemas and retention were not read from source in this run; the implementer must pin them or mark UNKNOWN.
- Whether the spike should carry a `timebox.decisionBy`; this proposal assumes 2026-12-31 and the owner may change it.
