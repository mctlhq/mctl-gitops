package cmd

import (
	"fmt"
	"strings"
)

// joinKV joins repeated KEY=VALUE flag values into the newline-separated list
// the deploy-service workflow reads (env_vars / secret_env_vars). Each flag
// occurrence is one entry and is kept whole: a comma inside a value is data,
// not a separator. A newline is the separator the workflow splits on, so a
// value carrying one would silently turn into a second entry; it is refused
// instead.
func joinKV(flag string, entries []string) (string, error) {
	for _, e := range entries {
		key, _, ok := strings.Cut(e, "=")
		if !ok || strings.TrimSpace(key) == "" {
			// Never echo the entry: for --secret a malformed one is
			// usually the bare secret value itself.
			return "", fmt.Errorf("--%s: an entry has no key or no '=': want KEY=VALUE", flag)
		}
		if strings.ContainsAny(e, "\r\n") {
			return "", fmt.Errorf("--%s %s: a value cannot contain a newline", flag, key)
		}
	}
	return strings.Join(entries, "\n"), nil
}
