# ZITADEL client for the basket approval page (text only, not applied)

The target files are reconciled and are NOT touched before activation:
`platform-gitops/helm-charts/zitadel-iac/` is applied to production ZITADEL
by the `zitadel` Application's PostSync Job and by the hourly CronJob
(`17 * * * *`), so landing this diff there is a production change with no
manual step. The leak guard refuses it in a reconciled path, and it belongs
to the activation phase (P2: OAuth), which needs its own GO.

What it does (mctlhq/mctl-api#1006, page in mctlhq/mctl-api#1007):

- `zitadel_application_oidc.mctl_api_glovo_basket` (`mctl-api-glovo-basket`):
  a confidential web client in the MCTL API project, the shape of
  `mctl-api-decide` (mctl-gitops#2521): client_secret_basic plus PKCE,
  authorization code only, one redirect
  `https://api.mctl.ai/glovo/basket/approvals/callback` (`SELF_URL` of
  `bootstrap/templates/mctl-platform/mctl-api.yaml` plus the page's callback
  path), opaque (BEARER) access token, userinfo assertion on, dev_mode off.
- `GLOVO_BASKET_UI_CLIENT_ID` / `GLOVO_BASKET_UI_CLIENT_SECRET` in
  `mctl-api/mctl-api-oidc-zitadel`, the Secret the Job already writes. The
  secret goes from the Terraform state into that Secret, as for the
  decide client; there is no Vault path or ExternalSecret.
- Not in `ZITADEL_HOOK_CLAIM_CLIENT_IDS` (customers.tf): the page resolves a
  linked identity by subject (`auth.UserForSignIn`) and reads no customer
  claim.

Why a client of its own rather than a second redirect on `mctl-api-decide`:
the page verifies the ID token with `aud` = its client id, so with a shared
client a code or ID token issued for the DevLoop decide page would be
accepted by the basket page and the reverse, and one secret would cover both
flows. A dedicated client is one resource in the existing pattern.

Activation order (each step its own PR and approval; runbook
`docs/runbooks/glovo-basket-canary.md`, step Z, which this diff is):

1. The chart slot `glovoBasketUISecret` (optional `secretKeyRef`s, mirroring
   `devLoopDecideSecret`) exists in mctl-api#1017 (which also carries the
   per-host ingress paths and `extraPaths`). #1007 has none.
2. A mctl-api release with #1007 and #1017, deployed after the release hold
   lifts. The chart source is pinned (mctlhq/mctl-gitops#2599), so #1017
   reaches production only in the release PR that moves the pin with the tag.
3. This diff into zitadel-iac, together with a change to the leak guard that
   admits it. Expected plan: no new action, one create plus an in-place
   update of the Secret data; `allowedActions` stays as is. It follows the
   database step (D2) and precedes B2.
4. B2 (`canary/env.patch.md`): `glovoBasketUISecret:
   mctl-api-oidc-zitadel`, `extraPaths: [/glovo]`, a `ROLLOUT_MARKER` bump and
   `GLOVO_BASKET_UI_ENABLED: "true"`, last, once the basket MCP (B1) is on.

Checked against the mctl-api code at #1014 (2026-11-11, read-only): the page
uses exactly this client shape (confidential, client_secret_basic, PKCE,
authorization code, `prompt=login`, ID-token audience = its own client id,
redirect `<SELF_URL>/glovo/basket/approvals/callback`). The MCP clients do not
use this client; they authenticate against the MCTL authorization server.

Verified against the tree this was staged from (`tofu` 1.12.6, mocked
providers): `tofu test` 100 passed with the diff applied; a mutation (an
extra redirect URI and the decide client's secret in the new key) failed the
two runs it targets (98 passed, 2 failed); `tofu fmt -check`, `tofu
validate` and `helm template` clean.

## Diff

```diff
diff --git a/platform-gitops/helm-charts/zitadel-iac/iac/mctl-api.tf b/platform-gitops/helm-charts/zitadel-iac/iac/mctl-api.tf
index dbae7a0ca..6cc02ba4b 100644
--- a/platform-gitops/helm-charts/zitadel-iac/iac/mctl-api.tf
+++ b/platform-gitops/helm-charts/zitadel-iac/iac/mctl-api.tf
@@ -227,6 +227,36 @@ resource "zitadel_application_oidc" "mctl_api_decide" {
   id_token_userinfo_assertion = true
 }
 
+# The Glovo basket approval page (mctl-api#1006): an MCP client shows the
+# basket owner a link to api.mctl.ai/glovo/basket/approvals/{id}, and the
+# owner signs in here, fresh, for that one decision (prompt=login,
+# max_age=0, PKCE, nonce). mctl-api reads the ID token only and resolves the
+# person to their linked principal; the decision handler's owner checks
+# decide, the page grants nothing by itself. It is the decide page's model,
+# with a client of its own rather than a second redirect on mctl-api-decide:
+# a code or ID token issued for one page is then never accepted by the
+# other (the ID token's aud is the client id), the secrets rotate apart, and
+# removing this client touches no DevLoop decision. Same shape as
+# mctl-api-decide: client secret plus PKCE, one redirect, opaque (BEARER)
+# access token, because a JWT access token of any app in this project would
+# pass mctl-api's JWT bearer check. Do not switch it to JWT. Not in
+# ZITADEL_HOOK_CLAIM_CLIENT_IDS (customers.tf): the page resolves a linked
+# identity by subject and reads no customer claim.
+resource "zitadel_application_oidc" "mctl_api_glovo_basket" {
+  org_id     = local.mctl_org_id
+  project_id = zitadel_project.mctl_api.id
+  name       = "mctl-api-glovo-basket"
+
+  app_type                    = "OIDC_APP_TYPE_WEB"
+  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_BASIC"
+  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
+  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
+  redirect_uris               = ["https://api.mctl.ai/glovo/basket/approvals/callback"]
+  access_token_type           = "OIDC_TOKEN_TYPE_BEARER"
+  dev_mode                    = false
+  id_token_userinfo_assertion = true
+}
+
 resource "kubernetes_secret_v1_data" "mctl_api_oidc" {
   metadata {
     name      = "mctl-api-oidc-zitadel"
@@ -275,6 +305,11 @@ resource "kubernetes_secret_v1_data" "mctl_api_oidc" {
     # is set in bootstrap/templates/mctl-platform/mctl-api.yaml.
     DEVLOOP_DECIDE_CLIENT_ID     = zitadel_application_oidc.mctl_api_decide.client_id
     DEVLOOP_DECIDE_CLIENT_SECRET = zitadel_application_oidc.mctl_api_decide.client_secret
+    # The Glovo basket approval page client (mctl-api#1006). Nothing reads
+    # these keys: the mctl-api chart has no slot for them yet, and the page
+    # stays unmounted unless GLOVO_BASKET_UI_ENABLED is "true" (it is unset).
+    GLOVO_BASKET_UI_CLIENT_ID     = zitadel_application_oidc.mctl_api_glovo_basket.client_id
+    GLOVO_BASKET_UI_CLIENT_SECRET = zitadel_application_oidc.mctl_api_glovo_basket.client_secret
     # The development client above, for an operator to copy into a local
     # run. Not read by mctl-api: the chart references keys by name, and these
     # names are none of them.
diff --git a/platform-gitops/helm-charts/zitadel-iac/iac/tests/mctl_api.tftest.hcl b/platform-gitops/helm-charts/zitadel-iac/iac/tests/mctl_api.tftest.hcl
index f1c6c04ee..25655be39 100644
--- a/platform-gitops/helm-charts/zitadel-iac/iac/tests/mctl_api.tftest.hcl
+++ b/platform-gitops/helm-charts/zitadel-iac/iac/tests/mctl_api.tftest.hcl
@@ -182,6 +182,53 @@ run "decide_client_is_a_confidential_pkce_web_client" {
   }
 }
 
+# The client of the Glovo basket approval page (mctl-api#1006). The same
+# attributes as mctl-api-decide, because the same things keep it closed.
+run "glovo_basket_client_is_a_confidential_pkce_web_client" {
+  command = plan
+  plan_options {
+    target = [zitadel_application_oidc.mctl_api_glovo_basket]
+  }
+
+  override_resource {
+    target = zitadel_project.mctl_api
+    values = { id = "mctl-api-project" }
+  }
+
+  assert {
+    condition     = zitadel_application_oidc.mctl_api_glovo_basket.name == "mctl-api-glovo-basket"
+    error_message = "The client is named mctl-api-glovo-basket."
+  }
+  assert {
+    condition     = zitadel_application_oidc.mctl_api_glovo_basket.project_id == "mctl-api-project" && zitadel_application_oidc.mctl_api_glovo_basket.org_id == "100000000000000001"
+    error_message = "The client must be in the MCTL API project of MCTL: has_project_check there is what limits who can sign in."
+  }
+  assert {
+    condition     = zitadel_application_oidc.mctl_api_glovo_basket.redirect_uris == tolist(["https://api.mctl.ai/glovo/basket/approvals/callback"])
+    error_message = "The only redirect URI must be https://api.mctl.ai/glovo/basket/approvals/callback."
+  }
+  assert {
+    condition     = zitadel_application_oidc.mctl_api_glovo_basket.app_type == "OIDC_APP_TYPE_WEB" && zitadel_application_oidc.mctl_api_glovo_basket.auth_method_type == "OIDC_AUTH_METHOD_TYPE_BASIC"
+    error_message = "The client must be a confidential web client authenticating with client_secret_basic."
+  }
+  assert {
+    condition     = zitadel_application_oidc.mctl_api_glovo_basket.grant_types == tolist(["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]) && zitadel_application_oidc.mctl_api_glovo_basket.response_types == tolist(["OIDC_RESPONSE_TYPE_CODE"])
+    error_message = "Authorization code only: no implicit, refresh token or device grant."
+  }
+  assert {
+    condition     = zitadel_application_oidc.mctl_api_glovo_basket.access_token_type == "OIDC_TOKEN_TYPE_BEARER"
+    error_message = "The access token must stay opaque (BEARER), never JWT."
+  }
+  assert {
+    condition     = zitadel_application_oidc.mctl_api_glovo_basket.id_token_userinfo_assertion == true
+    error_message = "id_token_userinfo_assertion must be on: mctl-api reads preferred_username from the ID token."
+  }
+  assert {
+    condition     = zitadel_application_oidc.mctl_api_glovo_basket.dev_mode == false
+    error_message = "dev_mode must stay off: on, ZITADEL accepts http redirects."
+  }
+}
+
 # The Job patches one Secret for three consumers. The new keys must carry the
 # new client's credentials, not the link client's, and the keys mctl-api and
 # the CLI already read must stay.
@@ -215,6 +262,10 @@ run "oauth_upstream_client_reaches_the_mctl_api_secret" {
     target = zitadel_application_oidc.mctl_api_decide
     values = { client_id = "decide-client-id", client_secret = "decide-client-secret" }
   }
+  override_resource {
+    target = zitadel_application_oidc.mctl_api_glovo_basket
+    values = { client_id = "glovo-basket-client-id", client_secret = "glovo-basket-client-secret" }
+  }
   override_resource {
     target = zitadel_org.customers
     values = { id = "customers-org-id" }
@@ -234,10 +285,12 @@ run "oauth_upstream_client_reaches_the_mctl_api_secret" {
       "OAUTH_ZITADEL_CLIENT_SECRET",
       "DEVLOOP_DECIDE_CLIENT_ID",
       "DEVLOOP_DECIDE_CLIENT_SECRET",
+      "GLOVO_BASKET_UI_CLIENT_ID",
+      "GLOVO_BASKET_UI_CLIENT_SECRET",
       "MCTL_API_DEV_ZITADEL_CLIENT_ID",
       "MCTL_API_DEV_ZITADEL_CLIENT_SECRET",
     ])
-    error_message = "mctl-api/mctl-api-oidc-zitadel must carry exactly the ten keys its consumers read."
+    error_message = "mctl-api/mctl-api-oidc-zitadel must carry exactly the twelve keys its consumers read."
   }
   assert {
     condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_API_DEV_ZITADEL_CLIENT_ID"]) == "dev-client-id" && nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_API_DEV_ZITADEL_CLIENT_SECRET"]) == "dev-client-secret"
@@ -259,6 +312,10 @@ run "oauth_upstream_client_reaches_the_mctl_api_secret" {
     condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["DEVLOOP_DECIDE_CLIENT_ID"]) == "decide-client-id" && nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["DEVLOOP_DECIDE_CLIENT_SECRET"]) == "decide-client-secret"
     error_message = "The decide keys must carry the mctl-api-decide client's credentials, never another flow's."
   }
+  assert {
+    condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["GLOVO_BASKET_UI_CLIENT_ID"]) == "glovo-basket-client-id" && nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["GLOVO_BASKET_UI_CLIENT_SECRET"]) == "glovo-basket-client-secret"
+    error_message = "The Glovo basket keys must carry the mctl-api-glovo-basket client's credentials, never another flow's."
+  }
   assert {
     condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_CLI_ZITADEL_CLIENT_ID"]) == "cli-client-id"
     error_message = "MCTL_CLI_ZITADEL_CLIENT_ID must still be the CLI's client id."
diff --git a/platform-gitops/helm-charts/zitadel-iac/values.yaml b/platform-gitops/helm-charts/zitadel-iac/values.yaml
index 9adb2af44..47519b745 100644
--- a/platform-gitops/helm-charts/zitadel-iac/values.yaml
+++ b/platform-gitops/helm-charts/zitadel-iac/values.yaml
@@ -73,6 +73,10 @@ image:
 #   /oauth/authorize's ZITADEL upstream, in the MCTL API project): no new
 #   action; a create, plus an in-place update of the data of
 #   mctl-api/mctl-api-oidc-zitadel (two keys added).
+#   mctl-api#1006 (mctl-api.tf: the mctl-api-glovo-basket web client of the
+#   Glovo basket approval page, in the MCTL API project): no new action; a
+#   create, plus an in-place update of the data of
+#   mctl-api/mctl-api-oidc-zitadel (two keys added).
 #   Labs apps sign-in (labs-apps.tf: a project and an OIDC application each
 #   for coolify-mcp and mctl-academy, one grant of each project per tenant
 #   organization with no role keys, the data of labs/coolify-mcp-oidc-zitadel
```
