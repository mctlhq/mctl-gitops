# Isolated media-engine evaluation harness (X0-X3) under experiments/media-engine-evaluation/

## Context
Issue #128 is a child of #127 revision 2. The parent proposal is `platform-gitops/agents-state/seerrsense/proposals/issue-127-spike-media-competitive-landscape-and-mc/`, with design blob `b0bbb7448c29c5a0c880cf8ffef8c38ee5c234d4` and tasks blob `f73fefa988d192f52b78172640a877ea91ac4f4d`. This investigation re-checked both blobs with `git hash-object`, and both match. #127 scores a decision matrix over Baseline/A/B/C/D/H and defines gates G1-G6 and experiments X1 and X2. The pivotal inputs to that matrix are all unmeasured: engine safety, footprint on a matched host, and parser quality. The owner authorises only the construction of an isolated, opt-in research harness that can produce that evidence. #127 stays proposed/HOLD. This proposal does not approve F1-F6, does not select an engine, and does not adopt one.

The harness is a new directory, `experiments/media-engine-evaluation/`, in the seerrsense repo. It has no runtime dependency on the SeerrSense application and changes nothing in it. It delivers four parts:
- X0: an owner-run, read-only baseline inventory.
- X1: a fail-closed, egress-denied benchmark and capability/security probe runner for four configurations.
- X2: an executable parser comparison over a synthetic corpus with independently authored labels.
- X3: a reproducible decision-matrix report generator.

Wherever native execution is not safely possible, the harness records BLOCKED, NOT RUN or NOT COMPARABLE with evidence. It never fabricates a number.

## User stories
- AS the owner I WANT a read-only local inventory script SO THAT I can supply host baseline data myself, without anyone getting access to my Mac or NAS.
- AS a reviewer I WANT every candidate pinned by tag, full commit and image digest, and verified by a separate preflight SO THAT results are attributable and nothing is guessed.
- AS the owner I WANT candidates to run only in disposable, egress-denied compose projects with synthetic fixtures SO THAT no real tracker, downloader, metadata service or household data is touched.
- AS a reviewer I WANT parser output scored against an independently authored expected-label manifest SO THAT all four upstream parsers are compared on the same ground truth.
- AS the decision maker I WANT the #127 matrix recomputed from machine-readable results, with unknowns kept visible SO THAT no winner is forced on missing evidence.
- AS a seerrsense maintainer I WANT the harness fully separated from the app's build, tests and release SO THAT `npm test`, `npm run typecheck`, the Docker image and release-please are unaffected.

## Acceptance criteria (EARS)

### Isolation from the application
- WHILE the harness exists THE SYSTEM SHALL keep every added or changed file under `experiments/media-engine-evaluation/`. It SHALL NOT modify `src/`, `tests/`, `public/`, `scripts/`, `docs/`, `Dockerfile`, `package.json`, `package-lock.json`, `tsconfig.json`, `.github/`, `.gitignore`, `release-please-config.json` or `.release-please-manifest.json`.
- WHILE the harness exists THE SYSTEM SHALL implement its own code with the Node.js 22 standard library only. There SHALL be no `package.json` dependency, no `npm install` and no lockfile in the experiment directory. Upstream code SHALL run only inside pinned toolchain or candidate containers.
- WHEN `npm test` runs at the repository root THE SYSTEM SHALL collect no harness file. Harness tests SHALL be named `*.harness-test.mjs`, which does not match vitest's default include `**/*.{test,spec}.?(c|m)[jt]s?(x)`. The root suite SHALL pass unchanged.
- WHEN the SeerrSense image is built from `Dockerfile` THE SYSTEM SHALL include no harness file.
- WHEN harness commits are made THE SYSTEM SHALL use the `chore(experiments)` or `test(experiments)` commit types, so release-please (package `.`, `release-type: node`) cuts no SeerrSense release.

### X0 baseline inventory
- WHEN the owner runs `bin/inventory.sh` THE SYSTEM SHALL record the following and write JSON that validates against `schema/inventory.schema.json`, using local read-only commands only:
  - host OS, architecture, total RAM and swap;
  - container runtime and its VM CPU and memory size;
  - running container names, image references and repo digests;
  - per-container RSS and CPU.
- IF a value cannot be read THEN THE SYSTEM SHALL record it as `{"status":"not_observed","reason":"..."}`, never as zero or an empty string.
- WHILE the inventory runs THE SYSTEM SHALL NOT:
  - open network connections;
  - inspect container environments, mounts, volumes or configuration files;
  - read credentials, home directories or media paths.

  It SHALL print the result to stdout for owner review before anything is shared.
- WHILE the harness is developed and tested THE SYSTEM SHALL NOT depend on any inventory from the owner's host. X3 SHALL treat inventory input as optional.

### X1 preflight and acquisition
- WHEN `bin/preflight.mjs` runs THE SYSTEM SHALL, for every entry in `candidates.json`, resolve the following through anonymous public APIs only and compare each value with the pin:
  - the tag to a full commit SHA;
  - each image reference to its registry index digest;
  - where the image declares it, the `org.opencontainers.image.revision` label.

  The entries are the reference baseline (Seerr, Radarr, Sonarr, Prowlarr), HolyArrs 1.2.0, Streamline v3.4.0, Mediarium v4.1.0, and Reelix v0.8.7 (X2 only).
- IF a resolved commit or digest differs from the pin, or cannot be resolved THEN THE SYSTEM SHALL mark that candidate BLOCKED with the observed values. It SHALL NOT substitute another tag, `latest` or a mutable reference.
- IF an image's revision label is absent or differs from the pinned commit THEN THE SYSTEM SHALL record `provenance: "unverified"` or `"mismatch"`, never `"verified"`.
- WHEN preflight acquires images and source archives THE SYSTEM SHALL use no credentials and SHALL record the compressed registry size per platform. Acquisition SHALL be a separate command from any execution. No run step SHALL pull an image or fetch source.

### X1 runtime isolation
- WHEN `bin/run-x1.mjs` is about to start a candidate THE SYSTEM SHALL first pass a static compose lint and a live isolation probe, and SHALL refuse to start (fail closed, exit code 3) unless all of the following are demonstrated:
  - every network is `internal: true` with IPv6 disabled;
  - no service uses `network_mode`, `privileged`, `cap_add`, `devices`, host `pid` or `ipc`, published ports, or a Docker socket mount;
  - every bind mount source resolves under the freshly created run root;
  - a probe container on the candidate network fails to reach an external IPv4 address, an external IPv6 address, `host.docker.internal` and the host gateway, and fails to resolve a public name to a public address.
- WHILE a candidate runs THE SYSTEM SHALL provide only local fixture services: synthetic Torznab, a mock qBittorrent WebAPI v2, a mock Jellyfin, a local metadata stub and an egress sink. It SHALL record every DNS query and connection attempt that reaches the sink as an attempted-egress record.
- WHEN a run ends, fails or is interrupted THE SYSTEM SHALL remove only resources labelled `io.mctl.experiment=media-engine-evaluation` together with that run's `io.mctl.run=<id>`, and the run root it created. It SHALL never call `docker system prune` or any unfiltered prune.
- IF a candidate cannot initialise offline through a supported API, documented configuration or a documented fixture adapter THEN THE SYSTEM SHALL record BLOCKED with the failing step and logs. It SHALL NOT patch the candidate, bypass isolation, or report a mock-only result as native engine performance.

### X1 measurement and gate probes
- WHEN a full run executes THE SYSTEM SHALL:
  - sample per-container RSS and CPU every 5 s for 10 min of idle after warm-up, and for 30 min of the matched workload (500 synthetic movies, 50 synthetic series);
  - report container RSS and VM overhead as separate series, never summed together;
  - report p50/p95 latency, fixture success, errors and recovery times.
- WHEN smoke mode is selected THE SYSTEM SHALL label every result `mode: "smoke"`, and X3 SHALL NOT use smoke results for any scored cell.
- WHEN a result file is written THE SYSTEM SHALL include:
  - host OS/arch;
  - candidate id, version, commit and digest;
  - timestamp, workload hash and repetition index;
  - metric source, sampling interval and units;
  - `mode` and `synthetic`;
  - raw samples.

  The file SHALL validate against `schema/result.schema.json`.
- WHEN gates G1-G6 are probed THE SYSTEM SHALL record each as `pass`, `fail`, `blocked`, `not_applicable` (with a non-empty rationale) or `not_run`. It SHALL never collapse `not_run` or `blocked` into `pass` or `fail`.
- WHILE G3 probes run THE SYSTEM SHALL use only the candidate's supported OAuth, API-key or confirmation mechanisms against its disposable instance. It SHALL redact tokens, codes, verifiers, client secrets and keys from all output.

### X2 parser comparison
- WHEN `bin/gen-corpus.mjs --seed <n>` runs THE SYSTEM SHALL emit at least 150 release names, byte-identical for the same seed, covering:
  - Cyrillic, Latin and transliterated titles;
  - audio markers DUB/MVO/DVO/AVO/Rus+Eng;
  - resolution, codec and edition;
  - season/episode and packs;
  - ambiguous and negative cases.
- WHILE the corpus exists THE SYSTEM SHALL keep expected labels in a separately authored `corpus/expected-labels.json`, which the generator never writes. Labels SHALL distinguish audio language from dubbing type and `unknown` from `confirmed`. Byte size SHALL come only from `corpus/fixture-sizes.json`, never from name tokens.
- WHEN a parser is scored THE SYSTEM SHALL report per-field accuracy and coverage, critical false-positive counts, an error taxonomy and the reproducer id of every miss.
- WHEN an upstream parser is exercised THE SYSTEM SHALL build a thin adapter against the pinned upstream source in a scratch tree outside the repository, and run it with no network. IF no comparable entrypoint exists at the pinned commit THEN THE SYSTEM SHALL record `not_comparable` with the checked path, never zero accuracy.
- WHILE adapters exist THE SYSTEM SHALL NOT commit any upstream source file to the repository.

### X3 decision matrix and report
- WHEN `bin/report.mjs` runs THE SYSTEM SHALL recompute Baseline/A/B/C/D/H with weights fit 25, safety 20, effort 20, footprint 15, license 10 and migration 10, and scenarios s0-s3 from #127. It SHALL output point totals, [low-high] ranges and seeded Monte Carlo first-place shares, and SHALL list deltas and ranking reversals against revision 2.
- IF a criterion lacks qualifying measured evidence THEN THE SYSTEM SHALL keep the revision-2 prior, tagged `provisional`, and SHALL NOT name a leader while ranges overlap.
- IF any G1-G6 result for a candidate is `fail`, `blocked` or `not_run` THEN THE SYSTEM SHALL show it in the report. It SHALL state that the report is an experiment result only, with no adoption recommendation.
- WHEN the report is generated THE SYSTEM SHALL separate the experiment GO from the business/adoption GO. It SHALL also keep engine selection separate from the implementation choice (integrate unmodified, fork or clean-room) and from the integration choice (topology and SeerrSense adapter).
- WHEN the report is generated from `examples/synthetic-results/` THE SYSTEM SHALL label every section "SYNTHETIC EXAMPLE DATA - not measured".

## Out of scope
- Running anything on the owner's Mac mini or NAS, or reading any household system, volume, credential or media. X0 is only a script the owner may run.
- Selecting or adopting an engine, creating `mctl-media` or any new repo, and implementing #127 features F1-F6.
- Any change to the SeerrSense runtime, MCP tool registry, authentication, migrations, GitOps, release configuration or production workflows.
- A CI job for the harness, because adding one would edit `.github/workflows/`. Smoke checks are commands that the owner or a reviewer runs.
- Copying or vendoring upstream AGPL/GPL code into the repository.
- Engines beyond the four named for X1 and Reelix for X2.
- Fixing the `LICENSE` (MIT) vs `package.json` (ISC) mismatch noted in #127.
- Auto-merge, release or deployment.

## Open questions
- Reference baseline pins. #127 does not record which Seerr/Radarr/Sonarr/Prowlarr versions the household runs, because the owner host was never observed. This proposal pins the current upstream releases observed on 2026-11-22: Seerr v3.5.2, Radarr v7.0.3.10918, Sonarr v4.0.20.3014 and Prowlarr v3.0.2.5780. They are labelled "reference baseline, not owner baseline", and image digests are resolved by preflight. The owner can substitute their own digests from X0 later.
- Image-to-commit provenance. Index digests were observed for `docker.io/holyarrs/holyarrs:1.2.0`, `ghcr.io/datahearth/streamline:3.4.0`, `ghcr.io/rdborg/mediarium:4.1.0` and `ghcr.io/demonzoned/reelix:0.8.7` (see design). Whether each image was built from the pinned commit is not yet verified. Preflight checks the OCI revision label and records `unverified` when it is absent. Streamline's own `deploy/compose.yaml` builds from source. Building from the upstream Dockerfile at the pinned commit is therefore an allowed, labelled fallback (`built_from_source`). The reviewer should confirm that this fallback is acceptable.
- License boundary for the X2 adapters. The Go adapters for HolyArrs, Streamline and Mediarium, and the Rust adapter for Reelix, link copyleft packages. They are built and run only locally and are never distributed. The reviewer should confirm this boundary. If it is rejected, X2 falls back to each upstream's own test command where one can consume the corpus, and to `not_comparable` otherwise.
- G4 upgrade needs a second consecutive pinned tag per engine, which #127 does not pin. The proposal pins the immediately preceding release as a `from` version through preflight. Without that pin, G4 is `not_run`.
- MCP enablement. HolyArrs MCP sits behind the `ai_apps` held feature, and Mediarium MCP is enabled from its signed-in web UI. If the switch cannot be set through a documented API or configuration on a fixture instance, the G3 MCP probes are `blocked`, not bypassed.
- No approved isolated Docker runtime is known for this repository, and the investigation environment has no Docker. X1 smoke and full runs may remain NOT RUN, and the PR must say so.
