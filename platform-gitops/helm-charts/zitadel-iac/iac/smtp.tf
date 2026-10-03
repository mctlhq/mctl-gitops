# Outgoing mail, so invited users get the code that lets them enrol a
# passkey. Resend is already verified for mctl.ai (DKIM resend._domainkey,
# infrastructure/cloudflare/zones/mctl-ai/dns.tf), and mctl-web sends from
# the same address. ZITADEL dials implicit TLS when tls = true.
#
# Port 2465, not 465: Hetzner Cloud blocks outgoing 25 and 465 by default,
# and the first apply timed out dialling smtp.resend.com:465 from the
# cluster. Resend serves implicit TLS on 2465 as well.
#
# NEVER CHANGE THIS RESOURCE IN PLACE. On ZITADEL v4.19.2 (and upstream main
# as of 2026-10-04) every SMTP update fails to project: the provider resends
# the password, the change event carries it as both Password and
# PlainAuth.Password, and reduceSMTPConfigChanged writes that one column
# twice ("multiple assignments to same column password"). The apply reports
# success, the event is skipped after five retries, and ZITADEL keeps sending
# with the old settings while every later plan shows the same diff.
# Creation projects fine, so a change is a new resource name (a delete plus a
# create), with "delete" allowed for that one PR. The resource name carries
# the port so the next change is a rename by construction.
resource "zitadel_email_provider_smtp" "resend_2465" {
  sender_address   = "noreply@mctl.ai"
  sender_name      = "MCTL"
  reply_to_address = "support@mctl.ai"
  tls              = true
  host             = "smtp.resend.com:2465"
  user             = "resend"
  password         = var.smtp_password
  set_active       = true
  description      = "Resend (managed by zitadel-iac)"
}
