# Tasks: issue-759-spike-runtime-746-slice-1-portable-runti

- [ ] 1. Create `experiments/portable-runtime-rs/` with `Cargo.toml` (package `mctl-runtime` 0.0.0, edition 2021, `publish = false`, no dependencies, empty `[workspace]`), hand-written v4 `Cargo.lock`, `rust-toolchain.toml` (pinned channel, clippy + rustfmt, minimal profile), `src/main.rs` (prints `mctl-runtime <version>`, one `#[cfg(test)]` test) — DoD: exactly these four files plus README exist; no other `.rs` files anywhere.
- [ ] 2. Write `experiments/portable-runtime-rs/README.md` (depends on 1) — DoD: starts with an EXPERIMENTAL / default-off banner, references #746 and #759, has run and delete instructions, states it is excluded from the image and guarded by the isolation test.
- [ ] 3. Append `experiments/**/target/` to `.gitignore` and `experiments/` to `.dockerignore`, each with a short comment — DoD: both lines present; no other ignore entries changed.
- [ ] 4. In `.github/workflows/pr-validation.yml` change `SHIPPING_PATHS` to `'^(tests/|docs/|\.github/|experiments/)'` and update the adjacent echo message to mention `experiments/` — DoD: only those two lines differ in that file.
- [ ] 5. Add `tests/test_portable_runtime_isolation.py` with the text-level helpers `dockerfile_copies_experiments` and `dockerignore_excludes_experiments` and the five tests described in design.md (skipif on missing experiment dir for all but the self-check; `os.walk` prunes `.git`, `.venv`, `venv`, `_gitops`, `target`, `node_modules`) (depends on 1, 3) — DoD: `uv run --locked pytest -q tests/test_portable_runtime_isolation.py` passes; `uv run --locked ruff check tests` clean.
- [ ] 6. Add `.github/workflows/portable-runtime-spike.yml` (paths filter on the experiment and the workflow file, `workflow_dispatch`, `permissions: contents: read`, `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`, matrix `ubuntu-latest` + `macos-14`, `rustup toolchain install`, `cargo build/test/clippy --locked`, `-D warnings`, pinned `cargo-audit` install + `cargo audit`) (depends on 1) — DoD: valid YAML; not referenced from any required-check config; runs on the PR.
- [ ] 7. Commit with a releasable conventional subject, e.g. `feat(experiments): portable-runtime spike scaffolding and isolation test (#759)`, body `Refs #746` (not `Closes`) — DoD: commit-lint passes; #746 stays open.

## Tests
- [ ] T1. `uv run --locked pytest -q` passes in full, with the isolation tests reported as passed (not skipped).
- [ ] T2. Negative self-check: `test_detector_flags_injected_copy` asserts the detector flags an appended `COPY experiments/ ./experiments/` line and returns nothing for the real Dockerfile.
- [ ] T3. Manual sanity (in the implementer sandbox): temporarily remove `experiments/` from `.dockerignore` and confirm `test_dockerignore_excludes_experiments` fails; temporarily add `# mctl-runtime` to `entrypoint.sh` and confirm `test_no_reference_in_shipped_paths` fails; revert both.
- [ ] T4. Skip behaviour: with `experiments/portable-runtime-rs` moved away, the four guarded tests are reported skipped and the self-check still passes.
- [ ] T5. `uv run --locked ruff check orchestrator config tests tools` and `uv run --locked mypy` stay clean.
- [ ] T6. On the PR: `portable-runtime spike (experimental)` is green on both ubuntu-latest and macos-14 (build, test, clippy, audit); `docker-build` in `PR validation` is green and unchanged.
- [ ] T7. `git diff --stat main` shows no change under `orchestrator/`, `config/`, `agents/`, nor to `Dockerfile`, `entrypoint.sh`, `pyproject.toml`, `uv.lock`.

## Rollback
Revert the single PR (`git revert <merge-sha>`). Everything added is inert: the crate is not built into the image, the workflow is not a required check, and the isolation test skips when `experiments/portable-runtime-rs/` is absent. Partial rollback is also safe: deleting `experiments/portable-runtime-rs/` and `.github/workflows/portable-runtime-spike.yml` alone leaves the test skipping and the ignore/commit-lint entries harmless.
