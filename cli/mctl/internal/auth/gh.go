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
	// ModeDefault: the stored mctl sign-in (api.go). Without one there is
	// no credential: the GitHub token is never picked implicitly.
	ModeDefault Mode = iota
	// ModeZitadel: the raw ZITADEL token (zitadel.go).
	ModeZitadel
	// ModeGitHub: the GitHub token, even when a mctl sign-in is stored.
	// Deprecated (mctlhq/mctl-api#525): the API will stop accepting it.
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

// legacyNotice is where the deprecation warning for MCTL_AUTH=github goes;
// tests replace it.
var (
	legacyNotice     io.Writer = os.Stderr
	legacyNoticeOnce sync.Once
)

// GetToken returns the bearer token for the mctl API.
// Resolution order: MCTL_TOKEN; then what MCTL_AUTH selects (zitadel: the
// stored ZITADEL login, github: the GitHub token, deprecated); otherwise the
// stored mctl sign-in (`mctl auth login`). Without one it is an error: the
// GitHub token (GITHUB_TOKEN, gh auth token) is sent only when MCTL_AUTH=github
// asks for it.
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
		tok, err := githubToken()
		if err != nil {
			return "", err
		}
		legacyNoticeOnce.Do(func() {
			fmt.Fprintln(legacyNotice, "mctl: MCTL_AUTH=github is deprecated and will stop working (mctlhq/mctl-api#525); run 'mctl auth login' to sign in with your MCTL account.")
		})
		return tok, nil
	}

	tok, err := APIToken()
	if err == nil {
		return tok, nil
	}
	// No sign-in is an error with the way to get one. There is no implicit
	// GitHub fallback (mctlhq/mctl-api#525): sending a credential the user
	// did not choose hides which identity a command runs as.
	if errors.Is(err, ErrNoAPILogin) {
		// err says why there is no sign-in, which matters when one exists
		// for another API URL.
		return "", fmt.Errorf("%w\n\nRun:\n  mctl auth login\n\nor set MCTL_TOKEN=<token>", err)
	}
	return "", err
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
