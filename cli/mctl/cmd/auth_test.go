package cmd

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
)

// whoamiAPI answers /api/v1/whoami with the bearer token it was sent as the
// identity, so a test sees which credential the status check really used.
func whoamiAPI(t *testing.T) {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		if r.URL.Path != "/api/v1/whoami" || token == "" || token == "refused" {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"id": "id-of-" + token, "groups": []string{"labs"}})
	}))
	t.Cleanup(srv.Close)
	prev := apiURL
	apiURL = ""
	t.Cleanup(func() { apiURL = prev })
	t.Setenv("MCTL_API_URL", srv.URL)
	t.Setenv("MCTL_API_TOKEN_FILE", filepath.Join(t.TempDir(), "api-token.json"))
	t.Setenv("MCTL_ZITADEL_TOKEN_FILE", filepath.Join(t.TempDir(), "zitadel-token.json"))
	t.Setenv("MCTL_TOKEN", "")
	t.Setenv("MCTL_AUTH", "")
	t.Setenv("GITHUB_TOKEN", "")
	// No gh binary: status must not need one, nor report its identity.
	t.Setenv("PATH", t.TempDir())
}

func status(t *testing.T) (string, error) {
	t.Helper()
	var out bytes.Buffer
	err := authStatus(&out)
	return out.String(), err
}

func TestAuthStatusReportsTheCredentialInUse(t *testing.T) {
	t.Run("MCTL_TOKEN", func(t *testing.T) {
		whoamiAPI(t)
		t.Setenv("MCTL_TOKEN", "explicit")
		t.Setenv("GITHUB_TOKEN", "gh-token")
		out, err := status(t)
		if err != nil || !strings.Contains(out, "id-of-explicit") || !strings.Contains(out, "MCTL_TOKEN") {
			t.Errorf("out = %q err = %v, want the MCTL_TOKEN identity", out, err)
		}
		if strings.Contains(out, "mctl auth login") {
			t.Errorf("an explicit token is a choice and gets no sign-in hint: %q", out)
		}
	})
	t.Run("MCTL_AUTH=github without gh", func(t *testing.T) {
		whoamiAPI(t)
		t.Setenv("MCTL_AUTH", "github")
		t.Setenv("GITHUB_TOKEN", "gh-token")
		out, err := status(t)
		if err != nil || !strings.Contains(out, "id-of-gh-token") || !strings.Contains(out, "MCTL_AUTH=github") {
			t.Errorf("out = %q err = %v, want the GitHub token identity", out, err)
		}
	})
	t.Run("no sign-in ignores the GitHub token", func(t *testing.T) {
		whoamiAPI(t)
		t.Setenv("GITHUB_TOKEN", "gh-token")
		out, err := status(t)
		if err == nil || !strings.Contains(out, "Not signed in") || !strings.Contains(out, "mctl auth login") {
			t.Errorf("out = %q err = %v, want not signed in and the sign-in hint", out, err)
		}
		if strings.Contains(out, "id-of-gh-token") {
			t.Errorf("status used the GitHub token without MCTL_AUTH=github: %q", out)
		}
	})
	t.Run("nothing", func(t *testing.T) {
		whoamiAPI(t)
		out, err := status(t)
		if err == nil || !strings.Contains(out, "Not signed in") {
			t.Errorf("out = %q err = %v, want not signed in", out, err)
		}
	})
	t.Run("refused", func(t *testing.T) {
		whoamiAPI(t)
		t.Setenv("MCTL_TOKEN", "refused")
		out, err := status(t)
		if err == nil || !strings.Contains(out, "refused the credential in use (MCTL_TOKEN)") {
			t.Errorf("out = %q err = %v, want a refusal naming MCTL_TOKEN", out, err)
		}
	})
	t.Run("unknown MCTL_AUTH", func(t *testing.T) {
		whoamiAPI(t)
		t.Setenv("MCTL_AUTH", "zitdel")
		t.Setenv("GITHUB_TOKEN", "gh-token")
		if out, err := status(t); err == nil {
			t.Errorf("out = %q, want an error", out)
		}
	})
}
