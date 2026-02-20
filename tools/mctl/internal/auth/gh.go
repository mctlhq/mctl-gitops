package auth

import (
	"fmt"
	"os/exec"
	"strings"
)

// GetToken returns a GitHub token by running `gh auth token`.
func GetToken() (string, error) {
	out, err := exec.Command("gh", "auth", "token").Output()
	if err != nil {
		return "", fmt.Errorf("failed to get GitHub token (is gh CLI installed and authenticated?): %w", err)
	}
	token := strings.TrimSpace(string(out))
	if token == "" {
		return "", fmt.Errorf("gh auth token returned empty — run 'gh auth login' first")
	}
	return token, nil
}

// GetUser returns the current authenticated GitHub username.
func GetUser() (string, error) {
	out, err := exec.Command("gh", "api", "/user", "--jq", ".login").Output()
	if err != nil {
		return "", fmt.Errorf("failed to get GitHub user: %w", err)
	}
	return strings.TrimSpace(string(out)), nil
}
