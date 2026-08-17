# Complementary user entity controls (CUECs)

Type I design assumes the following. If a user entity does not perform
them, the related criteria may not be met even when our controls are
designed as described.

## User entity (customer / operator of a tenant)

| CUEC | Why |
|---|---|
| Protect the GitHub account used to sign in (MFA on the user account, even while the org requirement is being enabled) | GitHub is the human IdP |
| Keep tenant secrets in Vault paths, not in git or chat | Isolation is path-based |
| Treat preview namespaces as non-production | Preview uses `teams/<team>/<svc>/preview/*`, not prod paths |
| Do not put regulated data (PHI, cardholder data) on this platform without a written agreement | Product scope is GitHub identity + platform ops; no BAA |
| Review MCP / OAuth clients they register | RFC 7591 DCR is open by product choice; redirect URIs are allowlisted but registration is public |
| Report suspected incidents to security@mctl.ai | Disclosure SLA is in SECURITY.md (48h ack / 5 business days) |

## Inherited / subservice (not operated by MCTL)

| Control | Provider | Our reliance |
|---|---|---|
| Physical access, power, cage | Hetzner Cloud | We have no datacenter access. Logical access only (hcloud API, SSH to nodes). |
| Edge DDoS / DNS / Worker isolation | Cloudflare | Landing OAuth Worker and R2 live here |
| Git hosting, Actions runners, OAuth app platform | GitHub | Branch protection and org MFA are configured on GitHub, not in this repo |
| Public TLS issuance | Let's Encrypt via cert-manager | We do not run a CA |
| Model inference for PR review and agents | Anthropic | Prompts may include repo diffs; no customer secrets by policy |

Collecting those vendors' SOC reports is still outstanding — see
[vendors.md](vendors.md).
