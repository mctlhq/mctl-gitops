# Tasks: issue-1409-feat-usage-versioned-price-catalog-for-t

- [ ] 1. Add the catalog document
      `platform-gitops/bootstrap/files/usage-pricing/claude-firstparty.json` — a
      JSON array of three `Pricing` entries (`claude-opus-5`, `claude-sonnet-5`,
      `claude-haiku-4-5`), each with `provider: firstParty`,
      `effective_from: "2026-09-01T00:00:00Z"`,
      `version: "2026-09-01-firstparty-1"`, and the rates from design.md's table
      (5.00/25.00/6.25/0.50, 2.00/10.00/2.50/0.20, 1.00/5.00/1.25/0.10; all three
      `web_search_per_call: 0.01`). Inside the bootstrap chart directory because
      `.Files.Get` cannot read outside the chart.
      DoD: `python3 -c "import json;json.load(open(...))"` returns a 3-element
      list; every entry has `version`, `canonical_model`, `effective_from`; field
      names match `internal/usage/pricing.go`'s JSON tags exactly.

- [ ] 2. Add `platform-gitops/bootstrap/files/usage-pricing/README.md`
      (depends on 1) — one line per rate naming the source
      (`https://platform.claude.com/docs/en/about-claude/pricing`), the table it
      was read from ("Model pricing"; "Specific tool pricing -> Web search tool"
      for $10/1,000 searches = 0.01 per call) and the retrieval date 2026-09-26;
      the `effective_from` rationale (footnote 3: Sonnet 5's $2/$10 became
      standard on 2026-09-01); the 5-minute cache-write assumption and what to
      change if a 1-hour cache is ever enabled; the append-only rule (new card +
      new `version`, never edit a card — ADR-012 invariant 7); and the
      `ROLLOUT_MARKER` requirement for any content change.
      DoD: a reviewer can verify all 12 numbers against the cited page without
      arithmetic; no rate appears in the README without a source.

- [ ] 3. Add the ConfigMap template
      `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-usage-pricing.yaml`
      (depends on 1) — `ConfigMap` `mctl-api-usage-pricing` in namespace
      `mctl-api`, single key `catalog.json` filled with
      `{{ .Files.Get "files/usage-pricing/claude-firstparty.json" | nindent 4 }}`.
      No second copy of the JSON in the template. Header comment explaining why
      it is a root-app raw manifest (external chart, no `extraObjects`), citing
      `mctl-api-netpol.yaml`.
      DoD: `helm template test platform-gitops/bootstrap -f platform-gitops/bootstrap/values.yaml`
      emits the ConfigMap; the extracted `catalog.json` value is byte-identical to
      the committed file; `kubeconform -strict` passes.

- [ ] 4. Companion chart change on mctlhq/mctl-api (cross-repo, blocking for 5) —
      open an issue/PR adding the optional `usagePricingCatalog`
      (`configMapName: ""`, `key: catalog.json`) value to `helm/values.yaml` and,
      in `helm/templates/deployment.yaml`, a `configMap` volume with
      `defaultMode: 0444`, a read-only `volumeMount` at
      `/etc/mctl-api/usage-pricing` (whole-directory, not `subPath`) and
      `USAGE_PRICING_CATALOG: /etc/mctl-api/usage-pricing/catalog.json`, all gated
      on `configMapName` being non-empty.
      DoD: merged to `mctl-api` `main` (which is the Application's
      `targetRevision`, so no `image.tag` bump); rendering the chart with the value
      unset produces a diff-free manifest versus today.

- [ ] 5. Wire it up in `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`
      (depends on 3 and 4) — add `usagePricingCatalog.configMapName:
      mctl-api-usage-pricing` to the inline Helm values and bump `ROLLOUT_MARKER`
      in the same commit, with a comment stating why (catalog read once at
      startup; no ConfigMap checksum annotation in the external chart). Do NOT set
      `USAGE_PRICING_CATALOG` under `env:` — the chart owns the path.
      DoD: `helm template` of bootstrap shows both the ConfigMap and the new value;
      this commit lands only after task 3 is on `main` and root-app has synced the
      ConfigMap (a pod restarting against a missing ConfigMap cannot mount it).

- [ ] 6. Extend `.github/workflows/validate-manifests.yml` (depends on 1 and 3) —
      a step modelled on "Render and validate the usage-writer overlay
      (.github#50)": render bootstrap, `grep -qF` for
      `name: mctl-api-usage-pricing` and
      `usagePricingCatalog`/`configMapName: mctl-api-usage-pricing`, run
      kubeconform over the render, and validate the committed JSON (array; required
      fields present; no duplicate (canonical_model, provider, effective_from)
      triple; every rate a non-negative number) — the local mirror of
      `usage.NewCatalog`.
      DoD: the step fails on a deliberately broken copy of the catalog (duplicate
      triple and a missing `effective_from`, tested locally) and passes on the real
      one.

- [ ] 7. Post the rate table for owner review on the issue before merge
      (depends on 1, 2) — the three models, five figures each, with the source URL
      and retrieval date, and the two recorded assumptions (5m cache write;
      `firstParty` only).
      DoD: owner has acknowledged the rates on mctlhq/mctl-gitops#1409; the PR is
      not merged before that.

- [ ] 8. Post-deploy verification (depends on 5) — confirm the pod restarted, the
      catalog loaded, and new rows are priced.
      DoD: `mctl_get_service_logs`/pod logs for `mctl-api` contain no
      `usage pricing catalog failed to load` after the rollout; a usage row
      recorded after it carries a non-null `calculated_cost` and
      `pricing_version: 2026-09-01-firstparty-1`; a row recorded before it still
      has `calculated_cost = NULL`.

- [ ] 9. (Optional, only if observed) Add alias cards for dated `model_key`s —
      if post-rollout rows show `calculated_cost IS NULL` because
      `canonical_model` was absent and `model_key` was dated (e.g.
      `claude-opus-5-20260401`), add entries for those exact keys with the same
      rates and a new `version`.
      DoD: the specific unpriced `model_key` is named in the commit message with
      the row count that motivated it; existing cards untouched.

## Tests

- [ ] T1. `helm lint platform-gitops/bootstrap` and
      `helm template test platform-gitops/bootstrap -f platform-gitops/bootstrap/values.yaml | kubeconform -strict -summary -schema-location default -schema-location "$CRD_SCHEMA_LOCATION" -`
      both pass with the new template in place.
- [ ] T2. Round-trip fidelity: extract `data["catalog.json"]` from the rendered
      ConfigMap, `json.load` it, and assert it equals `json.load` of
      `platform-gitops/bootstrap/files/usage-pricing/claude-firstparty.json`
      (guards the `nindent` indentation of the embedded document).
- [ ] T3. Arithmetic spot-check, by hand against the card: 1,000,000 input +
      200,000 output on `claude-opus-5/firstParty` must price to
      `5.00 + 0.2*25.00 = 10.00`; one web search adds `0.01`. Confirms the
      per-million unit and `web_search_per_call` are not off by 1000.
- [ ] T4. Negative case: a copy of the catalog with two cards sharing
      (`claude-opus-5`, `firstParty`, `2026-09-01T00:00:00Z`) is rejected by the
      CI validator from task 6 (matching `NewCatalog`'s duplicate rule).
- [ ] T5. Inert-by-default: rendering the mctl-api chart with
      `usagePricingCatalog.configMapName` unset yields a manifest with no new
      volume, no new mount and no `USAGE_PRICING_CATALOG` — i.e. the chart change
      alone cannot affect the running pod.
- [ ] T6. `yamllint` (relaxed, repo config) passes over `platform-gitops` with the
      new template; the `.json` file is outside yamllint's default file patterns
      and needs no ignore entry.

## Rollback

Ordered least- to most-invasive; every step is a revert, no data is involved.

1. **Pricing is wrong or suspect:** revert the task 5 commit (drop
   `usagePricingCatalog.configMapName`, keep the `ROLLOUT_MARKER` bump or bump it
   again). The pod restarts without `USAGE_PRICING_CATALOG` and returns to
   recording usage with no derived cost — today's behaviour. Rows already priced
   keep their `calculated_cost` and `pricing_version`, which is correct: they were
   priced by a named catalog version and stay auditable.
2. **A rate was wrong:** do not edit the card. Add a corrected card with a later
   `effective_from` and a new `version`, bump `ROLLOUT_MARKER`, and record the
   mispriced window in the README — rows priced by the old `version` remain
   identifiable by exactly that field.
3. **The pod cannot mount the ConfigMap (CrashLoop):** revert task 5 first (that
   removes the volume); then, if needed, revert task 3. ArgoCD self-heals both
   within its normal sync window; `mctl_get_service_status admins mctl-api` should
   report Healthy again.
4. **Full withdrawal:** revert tasks 1, 2, 3, 5 and 6 in this repo. The mctl-api
   chart value (task 4) can stay — it is inert when unset — or be reverted
   separately; nothing else consumes it.
