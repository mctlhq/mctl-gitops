# The mail a new tenant user receives (#1520 S3). ZITADEL sends its
# "verify email" message when a user is created with an unverified address;
# its stock text speaks of "a new email has been added", which reads as a
# mistake to someone who never had an account. These texts say what it is:
# an invitation to set up a passkey. Placeholders are ZITADEL's own
# ({{.DisplayName}}, {{.Code}}); the button carries the link.
#
# The same message also goes out when an existing user changes their e-mail,
# so the wording covers both.

resource "zitadel_default_verify_email_message_text" "en" {
  language    = "en"
  title       = "Your MCTL account"
  pre_header  = "Confirm your e-mail and set up a passkey"
  subject     = "MCTL: confirm your e-mail and set up sign-in"
  greeting    = "Hello {{.DisplayName}},"
  text        = "An MCTL account (auth.mctl.ai) has this e-mail address. Confirm it with the button below, or enter the code {{.Code}}. Then choose Passkeys: you sign in with your device's fingerprint, face or PIN, without a password. If you did not expect this e-mail, ignore it."
  button_text = "Confirm and set up sign-in"
  footer_text = "MCTL, auth.mctl.ai"
}

resource "zitadel_default_verify_email_message_text" "ru" {
  language    = "ru"
  title       = "Ваш аккаунт MCTL"
  pre_header  = "Подтвердите почту и настройте passkey"
  subject     = "MCTL: подтвердите почту и настройте вход"
  greeting    = "Здравствуйте, {{.DisplayName}}!"
  text        = "Этот адрес указан в аккаунте MCTL (auth.mctl.ai). Подтвердите его кнопкой ниже или введите код {{.Code}}. Затем выберите Passkeys: вход будет по отпечатку пальца, лицу или PIN-коду устройства, без пароля. Если вы не ждали этого письма, просто проигнорируйте его."
  button_text = "Подтвердить и настроить вход"
  footer_text = "MCTL, auth.mctl.ai"
}
