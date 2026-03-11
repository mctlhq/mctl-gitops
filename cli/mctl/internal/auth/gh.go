package auth

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// GetToken returns a GitHub token from env vars or the gh CLI.
// Resolution order: MCTL_TOKEN, GITHUB_TOKEN, gh auth token.
func GetToken() (string, error) {
	if t := os.Getenv("MCTL_TOKEN"); t != "" {
		return t, nil
	}
	if t := os.Getenv("GITHUB_TOKEN"); t != "" {
		return t, nil
	}
	out, err := exec.Command("gh", "auth", "token").Output()
	if err == nil {
		token := strings.TrimSpace(string(out))
		if token != "" {
			return token, nil
		}
	}
	return "", fmt.Errorf("no authentication token found\n\nSet one of:\n  export MCTL_TOKEN=<token>\n  export GITHUB_TOKEN=<token>\n  gh auth login")
}

// GetUser returns the current authenticated GitHub username.
func GetUser() (string, error) {
	out, err := exec.Command("gh", "api", "/user", "--jq", ".login").Output()
	if err != nil {
		return "", fmt.Errorf("failed to get GitHub user: %w", err)
	}
	return strings.TrimSpace(string(out)), nil
}
