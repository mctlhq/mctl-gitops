# Login V2 texts that name ZITADEL, rebranded as MCTL (owner decision
# 2026-10-04), in every locale Login V2 ships: it picks one from the
# browser's Accept-Language, so overriding English alone would leave
# "Войти с Zitadel" for a Russian browser.
#
# login_texts.json holds the overrides as literal text, one object per
# language, keyed like the hosted login locale files
# (apps/login/locales/<lang>.json in zitadel/zitadel). Each value is the
# built-in string of the deployed release with Zitadel replaced by MCTL, and
# a few grammar fixes (Hungarian article, Turkish suffix). Only those keys
# are set; every other key keeps its built-in text.
#
# Upgrade check: a ZITADEL release can add or move a key that names Zitadel.
# scripts/check-zitadel-login-texts.py (CI, zitadel-iac root) reads the
# locale files of the release the zitadel chart pin deploys and fails when
# one of their values names Zitadel and login_texts.json does not override
# it, when an override names Zitadel itself, or when it overrides a key that
# release does not have.
#
# The provider has no delete for these (ZITADEL has no API to remove
# translations): dropping a language here leaves its last texts in place.
resource "zitadel_default_hosted_login_translation" "mctl" {
  for_each = jsondecode(file("${path.module}/login_texts.json"))

  language     = each.key
  translations = jsonencode(each.value)
}
