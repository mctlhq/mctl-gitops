# Tasks: issue-128-spike-media-isolated-engine-evaluation-h

Paths are relative to `experiments/media-engine-evaluation/` unless they start with the repo root. No file outside that directory may change. Commit types are `chore(experiments)` and `test(experiments)` only.

- [ ] 1. Scaffold the directory. Add:
  - `README.md`, covering scope, the authorisation boundary (quote #128, with parent #127 on HOLD), the licence boundary, commands and the "run vs specified" table;
  - `.gitignore`, covering `runs/`, `out/` and `.cache/`;
  - the empty directories from the design layout.

  — DoD: `git diff --name-only origin/main` lists only paths under `experiments/media-engine-evaluation/`. The README states that running on owner hardware, adopting an engine, creating mctl-media, and F1-F6 each need a separate owner decision.
- [ ] 2. Write the pure shared libs: `lib/prng.mjs` (seeded mulberry32), `lib/schema-validate.mjs`, `lib/redact.mjs`, `lib/stats.mjs` and `lib/docker.mjs` (injectable executor). (depends on 1) — DoD: T1-T3 pass with `node --test`.
- [ ] 3. Add the schemas: `schema/inventory`, `candidate-manifest`, `result`, `parser-result` and `report` (`.schema.json`). The result schema requires:
  - host/arch;
  - candidate id, version, commit and digest;
  - timestamp, workload_hash and repetition;
  - `mode` (`smoke|full`) and `synthetic`;
  - metric_source, interval_s, units and raw samples;
  - an isolation evidence block;
  - gates[] with a status enum of `pass|fail|blocked|not_applicable|not_run`.

  (depends on 2) — DoD: T4 passes.
- [ ] 4. Write `candidates.json` with the pins verified in design.md:
  - HolyArrs 1.2.0 `d63e43f3...`, Streamline v3.4.0 `6d6d255e...`, Mediarium v4.1.0 `9ff49c21...` and Reelix v0.8.7 `606fa714...`, with SPDX ids, primary-source URLs at each commit, image refs without the `v` prefix and the observed index digests;
  - the reference baseline Seerr v3.5.2, Radarr v7.0.3.10918, Sonarr v4.0.20.3014 and Prowlarr v3.0.2.5780, with digests `null` and `status: unverified`;
  - an `upgrade_from` pin per engine (the preceding release), resolved and reviewed.

  Write `bin/preflight.mjs` as described in the design: anonymous GitHub and OCI resolution, a revision-label provenance check, `docker pull ref@digest`, source tarballs, offline vendoring in pinned toolchain images, compressed size, and output to `out/preflight.json`. It blocks on drift and never writes the manifest. (depends on 3) — DoD: the manifest validates and T5 passes. If network access is available, preflight runs once, and its output plus any reviewed pin edits go in the PR. Otherwise it is recorded as NOT RUN.
- [ ] 5. Write the X0 script `bin/inventory.sh`: POSIX sh with macOS and Linux branches, `--dry-run`, `not_observed` fallbacks, no network, no container `inspect` or `exec`, and no reads of home, volume or config paths. (depends on 3) — DoD: T6 passes. Output from the implementer's own machine (never the owner's) validates against the schema.
- [ ] 6. Write the fixtures: `bin/gen-fixtures.mjs` (500 movies and 50 series, seeded, payloads of 4 KiB or less, reserved ids) and `fixtures/services/{torznab,qbittorrent,jellyfin,metadata-stub,egress-sink}.mjs`, using only the stdlib `http` and `dgram` modules. (depends on 2) — DoD: T7 and T8 pass, and the fixture hash is stable per seed.
- [ ] 7. Set up compose and isolation:
  - `compose/base.yml`: an internal network with IPv6 off, the sink as DNS, labels, and no ports;
  - an overlay per candidate, using documented config only, via `adapters/x1/<id>/`;
  - `lib/compose-lint.mjs`;
  - `bin/isolation-check.mjs`: the lint plus the live busybox probe, exiting with code 3 on any reachability.

  (depends on 6) — DoD: T9 passes on good and deliberately bad compose files. A run with no passing probe aborts before the candidate starts (T10).
- [ ] 8. Write the X1 runner and probes:
  - `bin/run-x1.mjs`: run id, mkdtemp run root, the warm-up/idle 600 s/active 1800 s phases at 5 s, smoke mode, a separate VM-overhead series, compressed vs unpacked image size, p50/p95, and the egress log;
  - `lib/probes/g1..g6.mjs`;
  - `bin/cleanup.mjs`, with a signal trap.

  (depends on 4, 7) — DoD: T11-T13 pass, and a run against a stub candidate (a tiny fixture-only container) produces a schema-valid result. For every real configuration (baseline, HolyArrs, Streamline, Mediarium), the README records one of: smoke run (with the raw output path), BLOCKED (with logs), or NOT RUN (with the reason).
- [ ] 9. Write the X2 corpus: `bin/gen-corpus.mjs`, which produces `corpus/names.json` with at least 150 entries across all classes, each class at least 5 times; a hand-authored `corpus/expected-labels.json`; and `corpus/fixture-sizes.json`. (depends on 2) — DoD: T14 and T15 pass, and the labels file is authored separately from the generator code and called out for review in the PR.
- [ ] 10. Write the X2 adapters and runner:
  - `adapters/x2/{holyarrs,streamline,mediarium,reelix}/`: adapter source, `field-map.json` and `Dockerfile.adapter`, building in a `.cache/build/` scratch copy with `--network none` and `-mod=vendor` or `--offline`;
  - an entrypoint check against the paths and symbols in design.md;
  - `bin/run-x2.mjs`;
  - `lib/labels.mjs` scoring.

  (depends on 4, 9) — DoD: T16 passes using a stub adapter. Each real candidate has either scored results or `not_comparable`/`not_run` with evidence. T20 passes.
- [ ] 11. Write X3:
  - `priors/rev2-matrix.json`, `lib/score.mjs`, `lib/sensitivity.mjs` and `lib/evidence-map.mjs`;
  - `bin/report.mjs`, which produces markdown and JSON: deltas vs rev 2, reversals, a leader only on non-overlapping ranges, a gate table, separate engine/implementation/integration sections, and experiment GO vs adoption GO;
  - `examples/synthetic-results/` and the generated `examples/sample-report.md`, with SYNTHETIC banners.

  (depends on 3, 8, 10) — DoD: T17-T19 pass, and the parent's s0-s3 totals are reproduced exactly.
- [ ] 12. Write the documentation. The README gets exact commands for preflight, X0, X1 smoke and full, X2, the report and cleanup; the license and metadata limitations per candidate; and the run vs specified table, filled in. (depends on 4-11) — DoD: every command in the README has been executed in the PR, or is marked NOT RUN with a reason.
- [ ] 13. Verify isolation from the app and open the PR. (depends on all) — DoD:
  - At the repo root, `npx vitest list` shows no file under `experiments/`.
  - `npm run check:tokens`, `npm run typecheck`, `npm test` (as in `.github/workflows/ci.yml`) and `docker build -t seerrsense:test .` pass unchanged, where they can be run.
  - `node --test experiments/media-engine-evaluation/test/` passes.
  - The PR body lists the exact commands, test output, what was run vs only specified, and the limitations. It states no auto-merge and no release.

## Tests
All harness tests are named `test/*.harness-test.mjs` and run with `node --test experiments/media-engine-evaluation/test/`, with no network and no Docker. Docker interaction is tested through the `lib/docker.mjs` recording shim.
- [ ] T1. PRNG: the same seed gives an identical sequence, and different seeds differ.
- [ ] T2. Redaction removes Bearer tokens, `code=`, `code_verifier`, `client_secret`, `confirm_token` and API-key-shaped strings from nested objects and from free text.
- [ ] T3. Stats: p50/p95 on known arrays; the idle/active phase split; VM overhead is never summed into container RSS; units are preserved.
- [ ] T4. Each schema accepts its valid fixture and rejects each of: a missing `mode`, a missing `synthetic`, an unknown gate status, `not_applicable` without a rationale, and `0` where `not_observed` is required.
- [ ] T5. Preflight against recorded HTTP responses:
  - a matching pin gives `pinned`;
  - a drifted commit or digest gives BLOCKED, with both values recorded;
  - a `v`-prefixed image tag with a 404 gives BLOCKED, with no fallback attempted;
  - a missing revision label gives `provenance: unverified`;
  - `candidates.json` is byte-unchanged afterwards.
- [ ] T6. `inventory.sh --dry-run` lists no network tool, no container `inspect` or `exec`, and no home or volume path. With `docker` stripped from PATH, a run yields `not_observed` fields and valid JSON.
- [ ] T7. The fixture generator produces 500 movies and 50 series, a stable hash per seed, every payload at 4 KiB or less, and ids in the reserved range.
- [ ] T8. The mock qBittorrent counts adds per hash and refuses a save path outside its root. The mock Torznab and Jellyfin return correctly shaped responses. The egress sink logs qname, host and port, and redacts.
- [ ] T9. The compose lint rejects each of: host network, privileged, cap_add, devices, ports, docker.sock, a bind outside the run root (including through a symlink), a non-internal network, IPv6 enabled. It accepts `compose/base.yml` and every overlay.
- [ ] T10. Fail closed: when the probe shim reports any reachable target, `run-x1.mjs` exits with code 3, and no candidate `up` is issued (asserted on recorded shim calls).
- [ ] T11. Cleanup acts only on resources carrying both labels and the run id. It never issues `prune`. It refuses a run root outside `runs/`.
- [ ] T12. Probe status: an unrun probe is `not_run`, and an unsupported one is `not_applicable` with a rationale. Neither counts toward the G1 arithmetic. 49 of 50 passes; 48 of 50 fails; a duplicate grab fails; a path outside the root fails.
- [ ] T13. Smoke results carry `mode: smoke`, and the X3 evidence map refuses them for footprint and every other scored cell.
- [ ] T14. The corpus has at least 150 entries, is byte-identical for a seed, has every class present at least 5 times, and has unique ids. The generator source never references `expected-labels.json` for writing.
- [ ] T15. Every corpus id has exactly one expected label, and size is read only from `fixture-sizes.json`. Harness hygiene holds: no control characters in any harness file (mirroring root `tests/source-hygiene.test.ts`), and all files are valid UTF-8.
- [ ] T16. Scoring:
  - accuracy and coverage are distinct;
  - an `unsupported` field is excluded;
  - asserting dubbing on an `unknown` label is a critical false positive;
  - the taxonomy lists reproducer ids;
  - a `not_comparable` adapter yields no accuracy number at all.
- [ ] T17. Matrix:
  - the s0-s3 weights each sum to 100;
  - the rev-2 totals 3.60/3.65/3.50/3.40/2.70/2.95 and the s1-s3 rows match the parent;
  - the Monte Carlo with seed 127 is deterministic;
  - missing evidence keeps the prior, tagged `provisional`;
  - overlapping ranges give "no leader";
  - a G3 fail for B sets B's safety to 2, and the report shows the reversal below Baseline.
- [ ] T18. When any gate is not `pass`, the report contains "no adoption recommendation" and Business/adoption GO = DEFERRED, and the engine, implementation and integration sections are all present.
- [ ] T19. `report.mjs` on `examples/synthetic-results/` regenerates `examples/sample-report.md` byte-identically, and every section carries the SYNTHETIC banner.
- [ ] T20. Repository guard: no committed file under the experiment directory carries an upstream AGPL or GPL copyright header or matches an upstream path, and `git diff --name-only origin/main` has no path outside `experiments/media-engine-evaluation/`.

## Rollback
The change is one new directory. Nothing in the application, CI or release config references it. To roll back, revert the PR, or run `git rm -r experiments/media-engine-evaluation`.

Local experiment resources are removed with `node experiments/media-engine-evaluation/bin/cleanup.mjs --run <id>`. It deletes only containers, networks and volumes labelled `io.mctl.experiment=media-engine-evaluation` with that run id, plus that run's own `runs/<id>/` root.

No deployed service, database, GitOps file or release is affected, so no platform rollback is needed.
