# The ERPact copy's Frappe sign-in (project, OIDC application, verified e-mail
# actions, grants, the two Secrets in namespace erpact) was removed when the
# copy left this cluster (ERPact runs on its own CLO cluster). The tenant
# organization `erpact` and its users stay: git.mctl.ai (Forgejo) signs in
# through ZITADEL and its accounts are linked to those users (forgejo.tf).
#
# The user grants are forgotten, not destroyed. Their for_each keys carry user
# names, which allowedDeletes would have to list in this public repository;
# destroying the project (zitadel_project.erpact_frappe, listed there) takes
# them with it in ZITADEL.
#
# Delete this file once the Job has applied it.
removed {
  from = zitadel_user_grant.erpact_frappe_tenant
  lifecycle {
    destroy = false
  }
}

removed {
  from = zitadel_user_grant.erpact_frappe_admin
  lifecycle {
    destroy = false
  }
}
