# Design: issue-128-spike-media-isolated-engine-evaluation-h

## Current state

### Repository layout (clone at da0c5a3, seerrsense 1.14.4)
- Top level: `src/`, `tests/`, `public/`, `scripts/sync-tokens.mjs`, `docs/portal-allowlist.json`, `Dockerfile`, `package.json`, `tsconfig.json`, `release-please-config.json`, `.release-please-manifest.json`. There is no `experiments/` directory today, so the harness path is new and collides with nothing.
- `package.json` `"test"` is `vitest run` with no vitest config file in the repo. Vitest's default include (`**/*.{test,spec}.?(c|m)[jt]s?(x)`, excluding `node_modules`) therefore applies to the whole tree: any `*.test.mjs` placed under `experiments/` would be silently collected by `npm test` and by `.github/workflows/ci.yml` ("Test" step). The harness must avoid that naming pattern, because adding a vitest config would be a change outside the experiment directory.
- `tsconfig.json` has `"rootDir": "./src"`, `"include": ["src/**/*"]`, so `npm run typecheck` ignores `experiments/`. The harness is plain `.mjs` so it needs no TypeScript build.
- `Dockerfile` copies only `package.json`, `package-lock.json*`, `tsconfig.json`, `src/` (builder) and `dist`, `public/` (runtime). There is no `.dockerignore`, but no `COPY .`, so harness files never enter the image.
- `tests/source-hygiene.test.ts` scans only `src/` and `tests/` for control characters; it does not see the harness. The harness gets its own equivalent check (Cyrillic corpus files make this relevant).
- `tests/bake-off.ts` is an existing precedent for an opt-in, not-in-suite research script (named without `.test.`, run manually, calls an external LLM). The harness follows the same "not collected by vitest" convention but, unlike bake-off, makes no network call in tests.
- `release-please-config.json` uses `release-type: node` on package `.`; commits typed `feat`/`fix` anywhere bump the app version. Harness commits must use `chore(experiments):`/`test(experiments):` so no SeerrSense release is cut.
- `.gitignore` ignores `node_modules` and `dist/`; run outputs need their own ignore file inside the experiment directory.
- CI (`.github/workflows/ci.yml`) runs `check:tokens`, typecheck, `npm test` with Postgres, and `docker build`. None of these touches the harness when the naming rule above holds.

### Parent design (#127 revision 2, blobs verified)
- `git hash-object` on the parent `design.md` and `tasks.md` returned `b0bbb7448c29c5a0c880cf8ffef8c38ee5c234d4` and `f73fefa988d192f52b78172640a877ea91ac4f4d`, matching the issue.
- Parent `.status.yaml`: `status: proposed`, `requires_human_approval: true`. Unchanged by this proposal.
- Inputs reused verbatim from parent section 2: the six options, the 1-5 cell scores with [low-high] ranges, weights 25/20/20/15/10/10, scenarios s0-s3 (s1 footprint 30/fit 20/effort 15/migration 5; s2 safety 30/fit 20/footprint 10; s3 effort 10/fit 30/footprint 20), point totals (Baseline 3.60, A 3.65, B 3.50, C 3.40, D 2.70, H 2.95), Monte Carlo uniform sampling with 20,000 draws, seed 127, and the gates G1-G6.
- Candidate pins from the parent evidence annex: HolyArrs 1.2.0 at `d63e43f36a3a2babf475624f61b0a11021fd98fc`; Streamline v3.4.0 at `6d6d255` (short SHA only); Mediarium v4.1.0 at `9ff49c2` (short); Reelix v0.8.7 prerelease at `606fa71` (short). Short SHAs must be expanded and re-verified by preflight; image digests are not recorded anywhere in the parent.
- Parser entrypoints named in the parent: HolyArrs `app/backend/internal/core/releasename/parse.go` (path prefix inferred from the parent's other `app/backend/internal/...` citations), Streamline `internal/library/parser.go`, Mediarium `internal/parser/parser.go` and `internal/parser/language.go`, Reelix `crates/reelix-parser`. Fixture designs: Streamline `e2e/fakes/torznab.go`, `e2e/fakes/qbittorrent.go`.
- HolyArrs metadata default `https://api.holyarrs.com`, replaceable by `HOLYARRS_METADATA_URL` / `HOLYARRS_TMDB_KEY` (parent E6) - this is the documented fixture adapter for a local metadata stub. HolyArrs MCP is gated by the `ai_apps` held feature (E3); Mediarium MCP is switched on from the signed-in web UI (E8).

### Deployed state checked
- `$MCTL_GITOPS_ROOT/services/labs/seerrsense/values.yaml` (read): image `ghcr.io/mctlhq/seerrsense` tag `1.14.4`, digest `sha256:e65663bf8f1aa5e6bc5999562c725f054717d8189b553398be5d585a5926e485`. The harness changes nothing here and adds no service.
- `mctl_get_service_status(team=labs, service=seerrsense)`: ArgoCD `labs-seerrsense` Healthy, Synced, imageTag 1.14.4, port 8787, `hasDatabase: true`.
- Not observed: the owner's Mac mini / NAS where the household Seerr/*arr/qBittorrent/Jellyfin stack runs. By design the harness never observes it; X0 is an owner-run input.
- Not observed: registry tags/digests and upstream trees for the four candidates. This run had no GitHub/registry network access, so all pins beyond the parent's annex are to be resolved by preflight (task 4). See Open questions in requirements.md.

## Proposed solution

### Directory layout (all new, under `experiments/media-engine-evaluation/`)
```
README.md                      scope, authorisation boundary, commands, "run vs specified" table
.gitignore                     runs/, out/, .cache/
candidates.json                pinned manifest (tag, full commit, image ref + digest, license, sources)
bin/
  inventory.sh                 X0 owner-run, read-only
  preflight.mjs                X1/X2 resolve + verify pins, acquire images/source (network step)
  isolation-check.mjs          static compose lint + live egress probe; exits non-zero to fail closed
  run-x1.mjs                   per-candidate disposable compose run, sampling, probes
  gen-corpus.mjs               X2 deterministic name generator
  run-x2.mjs                   runs each parser adapter in a --network none container
  report.mjs                   X3 matrix + per-candidate report (markdown + JSON)
  cleanup.mjs                  removes only labelled resources of a given run id
lib/                           shared pure modules (prng.mjs, schema-validate.mjs, score.mjs, sensitivity.mjs,
                               corpus.mjs, labels.mjs, stats.mjs, redact.mjs, compose-lint.mjs)
schema/                        inventory, candidate-manifest, result, parser-result, report JSON Schemas
fixtures/
  generator/                   gen-fixtures.mjs: 500 movies, 50 series metadata, tiny (<=4 KiB) payload files
  services/                    stdlib-Node servers: torznab.mjs, qbittorrent.mjs, jellyfin.mjs,
                               metadata-stub.mjs (TMDB-shaped subset), egress-sink.mjs (DNS + TCP logger)
compose/
  base.yml                     internal networks, fixture services, egress sink, labels
  baseline.yml holyarrs.yml streamline.yml mediarium.yml
adapters/
  x1/<candidate>/              documented-config fixture adapters (env/config only, no candidate patches)
  x2/holyarrs/ streamline/ mediarium/ reelix/   thin parser adapters + Dockerfile.adapter
corpus/
  expected-labels.json         independently authored labels (hand-written, reviewed)
  fixture-sizes.json           byte sizes by reproducer id (from fixture metadata)
priors/rev2-matrix.json        parent section 2 cells, ranges, weights, scenarios, totals (transcribed)
examples/synthetic-results/    SYNTHETIC tagged sample raw results
examples/sample-report.md      generated from the synthetic results, banner on every section
test/*.harness-test.mjs        node:test unit tests
```

### Language and dependencies
Node 22 standard library only (`node:test`, `node:crypto`, `node:http`, `node:dgram`, `node:child_process` to call `docker`). Rationale: the repo's toolchain is Node 22 (CI `setup-node` 22, `node:22-slim` image), no dependency is added to `package.json`, and the experiment needs no lockfile. JSON Schema validation is a small in-repo validator covering the subset used (type, required, enum, properties, items, additionalProperties), tested directly. Upstream Go/Rust code is never compiled on the host; it is built inside pinned `golang` / `rust` toolchain images with `--network none` after preflight vendors dependencies.

Tests are `test/*.harness-test.mjs`, run with `node --test experiments/media-engine-evaluation/test/`. That filename does not match vitest's default include, so root `npm test` is unchanged (verified by task 13 with `npx vitest list`).

### X0 inventory (`bin/inventory.sh`)
POSIX sh, read-only, no network. Collects `uname -sm`, RAM (`sysctl hw.memsize` on macOS, `/proc/meminfo` on Linux), swap (`sysctl vm.swapusage` / `/proc/meminfo`), runtime (`docker version --format`, `colima list --json` / `docker info --format '{{.MemTotal}} {{.NCPU}}'` for VM size), containers (`docker ps --format` name and image, `docker image inspect --format '{{index .RepoDigests 0}}'`), and `docker stats --no-stream --format` RSS/CPU. It never runs `docker inspect` on containers (that exposes env and mounts), never lists volumes, never reads files under home. Every missing value becomes `not_observed` with the failing command name. Output goes to stdout and `out/inventory-<ts>.json`; the README tells the owner to review it before sharing. A `--dry-run` prints the command list only.

### Candidate manifest and preflight
`candidates.json` entries: `id`, `role` (`x1`, `x2` or both), `repo`, `tag`, `commit` (40-hex, or `null` until verified), `images[]` (`ref`, `digest`, `platform`), `license` (SPDX), `sources[]` (primary URLs at the pinned commit), `parser` (`path`, `entry`, or `null`), `x1_adapter` (documented env/config used), `status` (`pinned`, `unverified`, `blocked`). Baseline is a composite entry with four images.

`preflight.mjs` is the only networked step. It uses the anonymous GitHub REST API (`/repos/{r}/git/ref/tags/{tag}`, dereferencing annotated tags) and the OCI distribution API with anonymous bearer tokens (ghcr.io, docker.io, lscr.io) to resolve each pin; `docker pull <ref>@<digest>`; and `git archive`-equivalent tarball download at the commit (`/repos/{r}/tarball/{sha}`) into `.cache/src/<id>-<sha>/`, verifying the tarball's top-level SHA. For X2 it then runs `go mod vendor` / `cargo vendor` inside the toolchain image (network allowed in this step only) so the later build is offline. It writes `out/preflight.json` with compressed size per image (sum of manifest layer sizes) and refuses to mutate `candidates.json`; any mismatch is printed and the candidate is marked BLOCKED in the output. A pin update is a reviewed manual edit.

### X1 runtime (`compose/`, `bin/run-x1.mjs`, `bin/isolation-check.mjs`)
- Each run gets a run id, a compose project `mee-<runid>-<candidate>`, and a run root `runs/<runid>/<candidate>/` created fresh (`fs.mkdtemp`). Labels `io.mctl.experiment=media-engine-evaluation` and `io.mctl.run=<runid>` on every container, network and volume.
- Networks: `fixture` with `internal: true` and `enable_ipv6: false`. No published ports; the runner reaches services with `docker compose exec` / a runner sidecar on the same network.
- `compose-lint.mjs` parses `docker compose config --format json` and rejects: `network_mode`, `privileged`, `cap_add`, `pid`/`ipc: host`, `devices`, `/var/run/docker.sock`, bind sources outside the run root, any non-internal network, `extra_hosts` other than the stub aliases.
- Live probe: before the candidate starts, a probe container (pinned `busybox` digest) on the network attempts TCP to 1.1.1.1:443, `[2606:4700:4700::1111]:443`, `host.docker.internal`, the default gateway, and DNS for `api.themoviedb.org`. Any success aborts the run with exit code 3 (fail closed). Results are stored in the result file as `isolation.evidence`.
- Egress capture: the fixture network's DNS for public names resolves (via `extra_hosts` / a stub resolver in `egress-sink.mjs`) to the sink, which logs hostname, port and the first bytes of each connection; real hostnames the candidate tries (e.g. `api.holyarrs.com`) appear as attempted egress. Documented overrides (HolyArrs `HOLYARRS_METADATA_URL`) point at `metadata-stub.mjs`. Where a candidate has no override, the attempt is recorded and the candidate's metadata-dependent steps become `blocked` with that evidence.
- Fixtures: `gen-fixtures.mjs` (seeded) produces 500 movie and 50 series metadata records with synthetic titles and ids in a reserved range, Torznab results referencing tiny payload files, a mock qBittorrent WebAPI v2 (login, add, torrents/info, delete) that "completes" a download by writing the tiny file into the run root, and a mock Jellyfin (System/Info, Items, Library/Refresh). Designs follow Streamline's `e2e/fakes/*` as cited by the parent, rewritten in Node (no code copied).
- Candidate configuration: only through documented env/config/API (`adapters/x1/<id>/`), applied via the candidate's own HTTP API after start. No image modification. Mediarium's web-UI-only MCP switch is driven through its HTTP endpoints if those are documented; otherwise MCP probes are `blocked`.
- Measurement (`lib/stats.mjs`): sampler polls `docker stats --no-stream --format json` every 5 s. Metric source recorded as `docker-stats` (cgroup memory usage minus inactive file, as reported by the engine), units bytes and percent of one CPU. Phases: warm-up (until health OK + 60 s), idle 600 s, active 1800 s (workload: add all 500 movies / 50 series, trigger searches, grabs, imports, Jellyfin refresh), recovery. VM overhead is a separate series from the inventory/host (`colima`/`docker info`), never summed into container RSS; G5 compares engine container RSS to the sum of replaced components' container RSS on the same host and run. Image size: compressed (registry manifest) and unpacked (`docker image inspect .Size`). Latency p50/p95 over the candidate's API calls made by the workload driver. Smoke mode: 30 s idle, 60 s active, 20 movies / 2 series, 3 repetitions of G1, labelled `smoke`.
- Probes (`lib/probes/*.mjs`, each returns `{gate, status, evidence, rationale}`):
  - G1: 50 fixture vertical-slice runs, pass if >=49 succeed, zero duplicate grabs (mock qBittorrent add-count per hash) and zero files outside the run root (walk + realpath check).
  - G2: `docker kill -s KILL` during download and during import (10 each) then reconcile check; disk-full via a size-limited tmpfs volume inside the run (no host disk); backup/restore via the candidate's documented backup API onto a fresh volume.
  - G3: OAuth/PKCE (plain PKCE refused, unregistered redirect refused, code single use, revoked key refused), confirm-token single use and user binding, DCR rate limit; only where the candidate exposes these at the tag (HolyArrs with `ai_apps`, Mediarium); others `not_applicable` with rationale. Secrets pass through `redact.mjs` before any write. Dependency advisory scan and signature/attestation verification are recorded as `not_run` unless an offline tool and data are available; the result says which.
  - G4: upgrade across two consecutive pinned tags on the fixture DB and documented rollback; requires extra pins in `candidates.json`, else `not_run`.
  - G5: computed from measured series only; smoke data never qualifies.
  - G6: licence/provenance fields from preflight plus observed egress versus documented egress.
- Cleanup: `cleanup.mjs --run <id>` runs `docker compose -p <project> down -v` for projects it created and then removes containers/networks/volumes filtered by both labels; it never uses `prune` or unlabelled names. A trap in `run-x1.mjs` calls it on SIGINT/SIGTERM.

### X2 parser comparison
- `gen-corpus.mjs` uses a seeded PRNG (`lib/prng.mjs`, mulberry32) over templates to emit `corpus/names.json` (>=150 entries, each `{id: "P###", name}`), deterministic per seed. Coverage classes: Cyrillic titles, Latin titles, transliterated titles, audio markers (DUB, MVO, DVO, AVO, Rus+Eng, studio tags), resolution, codec, source, edition, S/E single, season packs, multi-episode, ambiguous (year-like titles, numbers in titles), negative (non-media, sample, trailer).
- `corpus/expected-labels.json` is hand-authored per id (fields: title, year, languages[], dubbing_type `dub|mvo|dvo|avo|original|unknown`, resolution, codec, edition, season, episodes[], is_pack, is_negative) with `confidence: confirmed|unknown`. A test asserts the generator never writes this file and that every corpus id has a label. Size labels live in `corpus/fixture-sizes.json`; no field derives size from the name.
- Adapters (`adapters/x2/<id>/`): a small program reading names on stdin and writing normalised JSON per line. Because Go `internal/` packages cannot be imported from another module, the Go adapter file is copied at build time into a scratch copy of the vendored upstream tree under `.cache/build/` (never into the repo) as `cmd/mee-adapter/main.go`, and built with `go build -mod=vendor` in the pinned `golang` image with `--network none`. Reelix uses a scratch cargo workspace with a path dependency on `crates/reelix-parser` and `--offline`. Each adapter has a field mapping file documenting how upstream fields map to the label schema; unmapped fields are `unsupported` (coverage), not wrong.
- Task 9 first verifies the path and exported entrypoint at the pinned commit. If absent or not callable, the candidate is `not_comparable` with the checked path in evidence.
- Scoring (`lib/labels.mjs`): per field accuracy = correct / labelled-and-emitted; coverage = emitted / labelled; critical false positives: language or dubbing type asserted when label is `unknown` or different, wrong season/episode, any title emitted on a negative. Error taxonomy codes (`E-LANG`, `E-DUB`, `E-SE`, `E-RES`, `E-TITLE-TRANSLIT`, ...) each list reproducer ids.
- Licence boundary: upstream code is run, not copied; adapters and outputs are MCTL-authored. The README states the combined adapter binary is never distributed.

### X3 report (`bin/report.mjs`, `lib/score.mjs`, `lib/sensitivity.mjs`)
- Inputs: `priors/rev2-matrix.json` (transcribed from parent section 2, with a test that the point totals reproduce 3.60/3.65/3.50/3.40/2.70/2.95 and s0-s3 match the parent table), X1/X2 result files, optional X0 inventory.
- Evidence mapping rules (documented in README, each a pure function with tests): measured G5 replaces the footprint cell for B/C (and informs H via Radarr's share); G3/G2 outcomes adjust safety (e.g. a confirm-token replay = safety 2, as the parent's reversal analysis states); X2 critical-FP rate informs D/H fit. A cell without qualifying evidence keeps its prior and is tagged `provisional`.
- Output: point totals and [low-high] per scenario, Monte Carlo first-place shares (20,000 draws, seed 127, uniform within ranges), `leader` only if its low bound exceeds every other high bound, else `no leader (ranges overlap)`; deltas against revision 2 and rank reversals; per-candidate section separating engine selection from implementation choice (integrate unmodified / fork / clean-room) and integration choice (Seerr on top / backend adapter); a gate table with all six statuses; an explicit "experiment GO vs adoption GO" section, where adoption is always "requires separate owner decision".
- A `--synthetic` input path stamps the banner. `examples/sample-report.md` is generated from `examples/synthetic-results/` and checked in; a test regenerates it and compares bytes.

### What is run vs specified
The README carries a table updated by the implementer: unit tests and synthetic report (run in PR), X0 (specified, owner-run), preflight (run if network available, else NOT RUN), X1 smoke (run only in an approved isolated Docker environment, else NOT RUN), X1 full (NOT RUN by default), X2 adapters (run if preflight succeeded and toolchain images are available, else NOT RUN).

## Alternatives
- Put the harness in a new repo (`mctlhq/mctl-media-eval`). Dropped: the issue forbids a new repo, and the parent defers `mctl-media` to a later owner GO.
- Write the harness in TypeScript with vitest, reusing the app toolchain. Dropped: TS files under `experiments/` are outside `tsconfig.json` `rootDir`, and `*.test.ts` would be collected by the root `npm test` (no vitest config), so it would either change root config or pollute the app suite. Plain `.mjs` + `node:test` with a non-matching filename needs neither.
- Use the Python ecosystem (jsonschema, pytest) or Go for the harness. Dropped: adds a toolchain the repo does not use and third-party dependencies; Go only appears inside upstream adapter builds, where it is required.
- Reimplement each upstream parser's rules in a wrapper. Dropped: would be a fabricated result and would risk copying copyleft logic; the issue requires actual pinned upstream behaviour or `not_comparable`.
- Isolate with network namespaces / firewall rules on the host. Dropped: requires root and host changes; compose `internal: true` networks plus a live probe are demonstrable without host modification and fail closed.

## Platform impact
- Migrations: none. No schema, GitOps, tenant or service change; `labs/seerrsense` stays at 1.14.4.
- Backward compatibility: application code, tests, image and MCP tools are untouched. Root `npm test`, `npm run typecheck`, `check:tokens` and `docker build` behave identically (task 13 verifies).
- Release: commits must be `chore(experiments)` / `test(experiments)` so release-please (`release-type: node`, package `.`) does not bump the app version. No auto-merge.
- Resource impact: none in the cluster. Locally, full X1 runs need Docker and roughly the candidates' footprint plus fixtures; smoke mode is a few minutes.
- Risks and mitigations:
  - Accidental egress from a candidate: internal networks, live probe before start, egress sink logging, fail closed.
  - Cleanup removing unrelated resources: label filters on two labels plus project-name prefix; no prune.
  - Misreading smoke or synthetic data as evidence: `mode` and `synthetic` fields are required by the result schema, and `report.mjs` refuses to use them for scored cells.
  - Copyleft contamination: adapters built in `.cache/` scratch trees only; a test asserts no file under the experiment directory contains an upstream copyright header.
  - Stale pins (HolyArrs releases daily): preflight verifies and blocks on drift; pins change only by reviewed edit.
  - Cyrillic corpus files and control characters: harness-local hygiene test.
