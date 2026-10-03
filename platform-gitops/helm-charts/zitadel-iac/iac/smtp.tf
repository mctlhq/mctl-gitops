# Outgoing mail, so invited users get the code that lets them enrol a
# passkey. Resend is already verified for mctl.ai (DKIM resend._domainkey,
# infrastructure/cloudflare/zones/mctl-ai/dns.tf), and mctl-web sends from
# the same address. ZITADEL dials implicit TLS when tls = true (port 465).
resource "zitadel_email_provider_smtp" "resend" {
  sender_address   = "noreply@mctl.ai"
  sender_name      = "MCTL"
  reply_to_address = "support@mctl.ai"
  tls              = true
  host             = "smtp.resend.com:465"
  user             = "resend"
  password         = var.smtp_password
  set_active       = true
  description      = "Resend (managed by zitadel-iac)"
}
