package auth

import (
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"sync"
)

// Mode is what MCTL_AUTH selects.
type Mode int

const (
	// ModeDefault: the stored mctl sign-in (api.go); without one, the GitHub
	// token, as before the sign-in existed.
	ModeDefault Mode = iota
	// ModeZitadel: the raw ZITADEL token (zitadel.go).
	ModeZitadel
	// ModeGitHub: the GitHub token, even when a mctl sign-in is stored.
	ModeGitHub
)

// AuthMode reads MCTL_AUTH. A value it does not know is an error, not the
// default: a typo must not silently pick a different credential.
func AuthMode() (Mode, error) {
	switch v := strings.ToLower(strings.TrimSpace(os.Getenv("MCTL_AUTH"))); v {
	case "":
		return ModeDefault, nil
	case "zitadel":
		return ModeZitadel, nil
	case "github":
		return ModeGitHub, nil
	default:
		return ModeDefault, fmt.Errorf("unknown MCTL_AUTH %q: use zitadel or github, or leave it unset", v)
	}
}

// legacyNotice is where the reminder that the GitHub token is the old way
// goes; tests replace it.
var (
	legacyNotice     io.Writer = os.Stderr
	legacyNoticeOnce sync.Once
)

// GetToken returns the bearer token for the mctl API.
// Resolution order: MCTL_TOKEN; then what MCTL_AUTH selects (zitadel: the
// stored ZITADEL login, github: the GitHub token); otherwise the stored mctl
// sign-in (`mctl auth login`), and only when there is none, the GitHub token
// (GITHUB_TOKEN, gh auth token).
func GetToken() (string, error) {
	if t := os.Getenv("MCTL_TOKEN"); t != "" {
		return t, nil
	}
	mode, err := AuthMode()
	if err != nil {
		return "", err
	}
	switch mode {
	case ModeZitadel:
		return ZitadelToken()
	case ModeGitHub:
		return githubToken()
	}

	tok, err := APIToken()
	if err == nil {
		return tok, nil
	}
	// Only "there is no sign-in" falls through to the GitHub token. A
	// sign-in that exists but cannot be read or refreshed is an error: the
	// user chose it, and quietly sending a different credential would hide
	// that it stopped working.
	if !errors.Is(err, ErrNoAPILogin) {
		return "", err
	}
	tok, ghErr := githubToken()
	if ghErr != nil {
		// err says why there is no sign-in, which matters when one exists
		// for another API URL.
		return "", fmt.Errorf("%w\n\nRun:\n  mctl auth login\n\nor set MCTL_TOKEN=<token>", err)
	}
	legacyNoticeOnce.Do(func() {
		fmt.Fprintln(legacyNotice, "mctl: using your GitHub token. Run 'mctl auth login' to sign in with your MCTL account; set MCTL_AUTH=github to keep the GitHub token and silence this.")
	})
	return tok, nil
}

// githubToken is the legacy credential: GITHUB_TOKEN, then gh auth token.
func githubToken() (string, error) {
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
	return "", fmt.Errorf("no GitHub token found\n\nSet one of:\n  export GITHUB_TOKEN=<token>\n  gh auth login")
}

// GetUser returns the current authenticated GitHub username.
func GetUser() (string, error) {
	out, err := exec.Command("gh", "api", "/user", "--jq", ".login").Output()
	if err != nil {
		return "", fmt.Errorf("failed to get GitHub user: %w", err)
	}
	return strings.TrimSpace(string(out)), nil
}
