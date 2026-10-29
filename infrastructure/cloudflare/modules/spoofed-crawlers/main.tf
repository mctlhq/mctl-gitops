# One WAF expression, shared by every zone root: block requests whose
# User-Agent claims to be a well-known crawler while Cloudflare's verified-bot
# check says otherwise. Real Googlebot, bingbot, ClaudeBot and the rest are in
# Cloudflare's verified-bot list, matched by source network, which a header
# cannot fake; a request with the name but without the verification is a
# scanner in disguise.
#
# Observed 2026-10-22 on *.mctl.me (mctl-landing-form Workers Logs): one
# scanner on Google Cloud (AS396982, 35.231.0.0/16) sent 189k requests in a
# day, rotating evenly through ~30 crawler User-Agents (Googlebot, bingbot,
# Applebot, Claude-User, ChatGPT-User, PerplexityBot, KimiBot, GrokBot, ...)
# while requesting /.env, /.git/config, /.terraform/terraform.tfstate and the
# like on a wordlist of subdomains. `verifiedBotCategory` was empty on every
# one of them. The same traffic then follows the worker's 301 to *.mctl.ai, so
# mctl.ai carries the rule too.
#
# A module with no resources and no provider: it exists so the three zone
# rulesets cannot drift apart on the list. Regex (`matches`) is not available
# on these plans, hence one `contains` clause per fragment; `lower()` and
# `cf.bot_management.verified_bot` are available on every plan.

locals {
  fragments = [
    "googlebot", "bingbot", "applebot", "yandexbot", "duckduckbot", "duckassistbot",
    "claudebot", "claude-user", "claude-searchbot", "anthropic-ai",
    "gptbot", "chatgpt-user", "oai-searchbot",
    "perplexitybot", "perplexity-user", "kimibot", "kimi-searchbot", "grokbot",
    "bravebot", "meta-webindexer", "meta-externalagent", "facebookexternalhit",
    "qwenbot", "hunyuan", "chatglm-spider", "bytespider", "amazonbot", "petalbot",
  ]
}

output "expression" {
  description = "Rules-language expression matching a spoofed crawler: a listed User-Agent fragment on a request that is not a verified bot."
  value = format(
    "(not cf.bot_management.verified_bot and (%s))",
    join(" or ", [for f in local.fragments : format("lower(http.user_agent) contains \"%s\"", f)]),
  )
}

output "description" {
  description = "Rule description to use with the expression, so the three zones read the same in the dashboard."
  value       = "block crawler User-Agents that are not verified bots (spoofed-crawlers module)"
}
