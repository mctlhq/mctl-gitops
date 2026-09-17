# valkey — the ACL file, and how to change it without an outage

**Use this when** you are about to change the Valkey ACL template, or when
`valkey-0` is crash-looping after one was changed.

**On this deployment, a `#` line inside the rendered `aclfile` is not ignored —
it aborts server startup.** Scope of that claim: it is what was observed on the
cluster's own image (`valkey/valkey:8.1.10-alpine`, file mounted from the
`valkey-acl` secret) on 2026-09-17, where it turned a documentation change into
a four-minute outage of `platform-events`, and reproduced on a local 7.2.4 with
the same file. It has not been measured across other versions or against
`user` directives in `valkey.conf`, so treat it as a property of *this*
Valkey and config-generation path, not as a general statement about Valkey.
That is enough: this path is the only one that renders the file here.

Source of the file:
`platform-gitops/infra-components/data/valkey/externalsecret.yaml` — an
ExternalSecret that templates `users.acl` from individual passwords in Vault
(`secret/platform/valkey`). The StatefulSet mounts it at
`/etc/valkey/acl/users.acl`.

## Why a bad line is an outage, not a warning

Two properties compose badly:

1. **Valkey reads `aclfile` only at process start.** A changed secret does
   nothing until the pod restarts, which is why the StatefulSet carries
   `mctl.ai/config-revision` — bumping it is the deliberate rollout trigger.
2. **A malformed line is fatal.** Not skipped, not logged-and-continued:

   ```
   # Aborting Valkey startup because of ACL errors: /etc/valkey/acl/users.acl:6
   # ... should start with user keyword followed by the username
   ```

So a comment added to the ACL template plus a `config-revision` bump in the
same commit is a crash-loop the moment Argo syncs it. There is no state in
which the bad file is merely present and harmless.

## The rule

**Notes about the ACL go in the YAML, above the block scalar. Never inside it.**

```yaml
data:
  # users.acl is parsed by Valkey itself and accepts no comments: a '#'
  # line aborts startup with "should start with user keyword". Keep notes
  # here, above the block, never inside it.
  #
  # events-observer is a read-only observer of the audit stream: ...
  users.acl: |
    user default off
    user claude-remote on >{{ .claudeRemote }} ...
```

Everything after `users.acl: |` is handed to Valkey verbatim. Each line must
start with `user`.

## Before merging an ACL change

Render the template and count what comes out — the check is cheap and catches
the whole class:

```sh
# Every line of the block must start with 'user'. The ten leading spaces are
# the block's own indentation -- they are what ends the block, so do not
# reflow them away.
awk '/users\.acl: \|/{f=1;next} f{ if ($0 !~ /^          /) {f=0; next} print $1 }' \
  platform-gitops/infra-components/data/valkey/externalsecret.yaml \
  | sort | uniq -c
#    7 user
```

Anything other than a single `user` row means the block has something in it
that Valkey will refuse. The check is worth trusting only because it fails on
the real defect — inserting `          # note` into the block makes it print a
`#` row next to the `user` row.

## If valkey-0 is crash-looping after an ACL change

```sh
kubectl -n platform-events logs valkey-0 -c valkey --tail=20
```

`Aborting Valkey startup because of ACL errors: .../users.acl:<line>` names the
offending line number in the *rendered* file. To see the structure of what was
actually rendered without printing any password:

```sh
kubectl -n platform-events get secret valkey-acl -o jsonpath='{.data.users\.acl}' \
  | base64 -d | awk '{print NR, $1, NF, length($0)}'
```

First token, field count and line length are enough to find a stray line; the
values never reach the terminal.

Fix forward by correcting the ExternalSecret and merging — ESO re-renders
within its refresh interval (or immediately on a forced refresh), and the pod
recovers on its next restart attempt.

**Rolling back the `config-revision` does not repair the file.** The two live
in different places: `config-revision` is an annotation on the StatefulSet pod
template whose only job is to make a pod restart, while the ACL text is
rendered by ESO from the ExternalSecret into the `valkey-acl` Secret and mounted
from there. Reverting the annotation reverts the *trigger*, not the *content* —
the Secret still holds the broken file, and the restarted pod mounts and parses
exactly the same bytes. Only a corrected ExternalSecret, re-synced by ESO,
changes what the pod reads.

## The ACL users, and what each is for

| User | Purpose |
|---|---|
| `default` | off — nothing authenticates as default |
| `claude-remote` | the inbound events adapter: consumer-group reads, `XACK`, `XCLAIM`/`XAUTOCLAIM`, `XADD` on the audit stream, and the `mctl:events:state:*` keyspace |
| `events-observer` | read-only observer of `mctl:events:audit` — `XRANGE`/`XREVRANGE`/`XLEN`/`XINFO` and nothing else, for verification without write access |
| `exporter` | metrics scraping |
| `github-producer`, `telegram-producer`, `synthetic-producer` | publish into their own streams |

Passwords live in Vault at `secret/platform/valkey`, one field per user. Adding
a user is two changes in one commit: the field in Vault (written with
`vault kv patch`, value never printed) and the template line plus its `data:`
entry here. Rotating one is a Vault write plus a `config-revision` bump.

Operating the events channel on top of these users — reading the audit trail,
reading group state, what `pending` and `lag` mean — is documented in
`mctlhq/mctl-claude-remote`, `docs/events-operations.md`.
