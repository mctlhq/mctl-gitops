package auth

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"

	"golang.org/x/oauth2"
)

// fakeAPI is the mctl API's authorization server as the CLI sees it:
// metadata, dynamic registration, authorize, token (with PKCE and refresh
// rotation) and revocation.
type fakeAPI struct {
	t   *testing.T
	srv *httptest.Server

	mu         sync.Mutex
	meta       func(base string) map[string]any
	clients    map[string][]string // client id -> redirect URIs
	challenges map[string]string   // code -> code_challenge
	codeClient map[string]string   // code -> client id
	refresh    string              // the one live refresh token
	issued     int
	refreshes  int
	revoked    []string
	expiresIn  int
}

func newFakeAPI(t *testing.T) *fakeAPI {
	t.Helper()
	f := &fakeAPI{
		t:          t,
		clients:    map[string][]string{},
		challenges: map[string]string{},
		codeClient: map[string]string{},
		expiresIn:  3600,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/.well-known/oauth-authorization-server", f.metadata)
	mux.HandleFunc("/oauth/register", f.register)
	mux.HandleFunc("/oauth/authorize", f.authorize)
	mux.HandleFunc("/oauth/token", f.token)
	mux.HandleFunc("/oauth/revoke", f.revoke)
	f.srv = httptest.NewServer(mux)
	t.Cleanup(f.srv.Close)
	return f
}

func (f *fakeAPI) metadata(w http.ResponseWriter, _ *http.Request) {
	f.mu.Lock()
	meta := f.meta
	f.mu.Unlock()
	doc := map[string]any{
		"issuer":                           f.srv.URL,
		"authorization_endpoint":           f.srv.URL + "/oauth/authorize",
		"token_endpoint":                   f.srv.URL + "/oauth/token",
		"registration_endpoint":            f.srv.URL + "/oauth/register",
		"revocation_endpoint":              f.srv.URL + "/oauth/revoke",
		"code_challenge_methods_supported": []string{"S256"},
	}
	if meta != nil {
		doc = meta(f.srv.URL)
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(doc)
}

func (f *fakeAPI) register(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RedirectURIs []string `json:"redirect_uris"`
		AuthMethod   string   `json:"token_endpoint_auth_method"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || len(req.RedirectURIs) != 1 || req.AuthMethod != "none" {
		http.Error(w, `{"error":"invalid_client_metadata"}`, http.StatusBadRequest)
		return
	}
	f.mu.Lock()
	id := fmt.Sprintf("dcr_%d", len(f.clients)+1)
	f.clients[id] = req.RedirectURIs
	f.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(map[string]any{"client_id": id})
}

func (f *fakeAPI) authorize(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	f.mu.Lock()
	defer f.mu.Unlock()
	uris, ok := f.clients[q.Get("client_id")]
	if !ok || uris[0] != q.Get("redirect_uri") {
		http.Error(w, "invalid redirect_uri", http.StatusBadRequest)
		return
	}
	if q.Get("response_type") != "code" || q.Get("code_challenge_method") != "S256" || q.Get("code_challenge") == "" || q.Get("state") == "" {
		http.Error(w, "invalid_request", http.StatusBadRequest)
		return
	}
	code := fmt.Sprintf("code-%d", len(f.challenges)+1)
	f.challenges[code] = q.Get("code_challenge")
	f.codeClient[code] = q.Get("client_id")
	target, _ := url.Parse(q.Get("redirect_uri"))
	tq := target.Query()
	tq.Set("code", code)
	tq.Set("state", q.Get("state"))
	target.RawQuery = tq.Encode()
	http.Redirect(w, r, target.String(), http.StatusFound)
}

func (f *fakeAPI) token(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		http.Error(w, `{"error":"invalid_request"}`, http.StatusBadRequest)
		return
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	fail := func() {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":"invalid_grant","error_description":"invalid or expired token"}`))
	}
	switch r.FormValue("grant_type") {
	case "authorization_code":
		code := r.FormValue("code")
		sum := sha256.Sum256([]byte(r.FormValue("code_verifier")))
		challenge, ok := f.challenges[code]
		if !ok || challenge != base64.RawURLEncoding.EncodeToString(sum[:]) ||
			f.codeClient[code] != r.FormValue("client_id") ||
			f.clients[r.FormValue("client_id")][0] != r.FormValue("redirect_uri") {
			fail()
			return
		}
		delete(f.challenges, code)
	case "refresh_token":
		if r.FormValue("refresh_token") != f.refresh || f.refresh == "" || r.FormValue("client_id") == "" {
			fail()
			return
		}
		f.refreshes++
	default:
		fail()
		return
	}
	f.issued++
	f.refresh = fmt.Sprintf("refresh-%d", f.issued)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"access_token":  fmt.Sprintf("access-%d", f.issued),
		"refresh_token": f.refresh,
		"token_type":    "Bearer",
		"expires_in":    f.expiresIn,
		"scope":         "mctl",
	})
}

func (f *fakeAPI) revoke(w http.ResponseWriter, r *http.Request) {
	_ = r.ParseForm()
	f.mu.Lock()
	f.revoked = append(f.revoked, r.FormValue("token"))
	f.mu.Unlock()
	w.WriteHeader(http.StatusOK)
}

func (f *fakeAPI) counts() (refreshes int, revoked []string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.refreshes, append([]string(nil), f.revoked...)
}

// useFakeAPI points the CLI at f with an empty credential directory and no
// other credential in the environment.
func useFakeAPI(t *testing.T, f *fakeAPI) string {
	t.Helper()
	tokenFile := filepath.Join(t.TempDir(), "mctl", "api-token.json")
	t.Setenv("MCTL_API_URL", f.srv.URL)
	t.Setenv("MCTL_API_TOKEN_FILE", tokenFile)
	t.Setenv("MCTL_ZITADEL_TOKEN_FILE", filepath.Join(t.TempDir(), "mctl", "zitadel-token.json"))
	t.Setenv("MCTL_TOKEN", "")
	t.Setenv("MCTL_AUTH", "")
	t.Setenv("GITHUB_TOKEN", "")
	// No gh on PATH: the GitHub fallback must come from GITHUB_TOKEN alone.
	t.Setenv("PATH", t.TempDir())
	legacyNoticeOnce = sync.Once{}
	prev := legacyNotice
	legacyNotice = &bytes.Buffer{}
	t.Cleanup(func() { legacyNotice = prev })
	return tokenFile
}

func apiLogin(t *testing.T) error {
	t.Helper()
	b := &browser{t: t, done: make(chan struct{})}
	err := APILogin(context.Background(), b, false)
	select {
	case <-b.done:
	case <-time.After(5 * time.Second):
		t.Cleanup(func() { <-b.done })
	}
	return err
}

// expire makes the stored access token look expired, keeping the rest.
func expire(t *testing.T) {
	t.Helper()
	st, err := readAPIToken()
	if err != nil {
		t.Fatal(err)
	}
	st.Token.Expiry = time.Now().Add(-time.Minute)
	if err := writeAPIToken(st); err != nil {
		t.Fatal(err)
	}
}

func TestAPILoginStoresTokensOwnerOnly(t *testing.T) {
	f := newFakeAPI(t)
	tokenFile := useFakeAPI(t, f)
	// The fake refuses the exchange unless the verifier matches the
	// challenge sent to authorize, so a passing login proves PKCE ran.
	if err := apiLogin(t); err != nil {
		t.Fatalf("login: %v", err)
	}
	st, err := readAPIToken()
	if err != nil {
		t.Fatal(err)
	}
	if st.APIURL != f.srv.URL || st.ClientID != "dcr_1" || st.Token.AccessToken != "access-1" || st.Token.RefreshToken != "refresh-1" {
		t.Errorf("stored = %+v token %+v", st, st.Token)
	}
	if runtime.GOOS != "windows" {
		info, err := os.Stat(tokenFile)
		if err != nil {
			t.Fatal(err)
		}
		if info.Mode().Perm() != 0o600 {
			t.Errorf("token file mode = %v, want 0600", info.Mode().Perm())
		}
	}
	if tok, err := GetToken(); err != nil || tok != "access-1" {
		t.Errorf("GetToken = %q %v, want access-1", tok, err)
	}
}

func TestGetTokenOrder(t *testing.T) {
	f := newFakeAPI(t)
	useFakeAPI(t, f)
	notice := legacyNotice.(*bytes.Buffer)

	if _, err := GetToken(); err == nil || !strings.Contains(err.Error(), "mctl auth login") {
		t.Errorf("no credential at all: err = %v, want a pointer to 'mctl auth login'", err)
	}

	t.Setenv("GITHUB_TOKEN", "gh-token")
	if tok, err := GetToken(); err != nil || tok != "gh-token" {
		t.Errorf("no sign-in: token = %q %v, want the GitHub token", tok, err)
	}
	if !strings.Contains(notice.String(), "mctl auth login") {
		t.Errorf("the GitHub fallback must say how to sign in; notice = %q", notice.String())
	}
	if _, err := GetToken(); err != nil || strings.Count(notice.String(), "\n") != 1 {
		t.Errorf("the notice must be printed once per process; notice = %q", notice.String())
	}

	if err := writeAPIToken(&storedAPIToken{
		APIURL: f.srv.URL, ClientID: "dcr_1",
		Token: &oauth2.Token{AccessToken: "api-token", Expiry: time.Now().Add(time.Hour)},
	}); err != nil {
		t.Fatal(err)
	}
	if tok, err := GetToken(); err != nil || tok != "api-token" {
		t.Errorf("signed in: token = %q %v, want the mctl sign-in ahead of GITHUB_TOKEN", tok, err)
	}

	notice.Reset()
	legacyNoticeOnce = sync.Once{}
	t.Setenv("MCTL_AUTH", "github")
	if tok, err := GetToken(); err != nil || tok != "gh-token" {
		t.Errorf("MCTL_AUTH=github: token = %q %v, want the GitHub token", tok, err)
	}
	if notice.Len() != 0 {
		t.Errorf("MCTL_AUTH=github is a choice and must not be nagged; notice = %q", notice.String())
	}

	t.Setenv("MCTL_AUTH", "zitdel")
	if tok, err := GetToken(); err == nil || !strings.Contains(err.Error(), "MCTL_AUTH") {
		t.Errorf("unknown MCTL_AUTH: token = %q err = %v, want an error naming MCTL_AUTH", tok, err)
	}

	t.Setenv("MCTL_TOKEN", "explicit")
	if tok, err := GetToken(); err != nil || tok != "explicit" {
		t.Errorf("MCTL_TOKEN must win over everything: token = %q %v", tok, err)
	}
}

// A token is only ever sent to the API that issued it.
func TestAPITokenIsNotSentToAnotherAPI(t *testing.T) {
	f := newFakeAPI(t)
	useFakeAPI(t, f)
	if err := writeAPIToken(&storedAPIToken{
		APIURL: "https://api.other.example", ClientID: "dcr_1",
		Token: &oauth2.Token{AccessToken: "other-api-token", Expiry: time.Now().Add(time.Hour)},
	}); err != nil {
		t.Fatal(err)
	}
	if tok, err := APIToken(); !errors.Is(err, ErrNoAPILogin) {
		t.Errorf("APIToken = %q %v, want ErrNoAPILogin", tok, err)
	}
	if tok, err := GetToken(); err == nil {
		t.Errorf("GetToken = %q, want an error: the only credential belongs to another API", tok)
	}
	t.Setenv("GITHUB_TOKEN", "gh-token")
	if tok, err := GetToken(); err != nil || tok != "gh-token" {
		t.Errorf("GetToken = %q %v, want the GitHub token and never the other API's", tok, err)
	}
}

// A sign-in that exists but cannot be read is an error, not "signed out":
// falling back would send a different credential than the user chose.
func TestUnreadableSignInDoesNotFallBackToGitHub(t *testing.T) {
	f := newFakeAPI(t)
	tokenFile := useFakeAPI(t, f)
	t.Setenv("GITHUB_TOKEN", "gh-token")
	if err := os.MkdirAll(filepath.Dir(tokenFile), 0o700); err != nil {
		t.Fatal(err)
	}
	for name, content := range map[string]string{
		"not JSON":   "{",
		"no token":   `{"api_url":"` + f.srv.URL + `","client_id":"dcr_1"}`,
		"no client":  `{"api_url":"` + f.srv.URL + `","token":{"access_token":"a"}}`,
		"no API URL": `{"client_id":"dcr_1","token":{"access_token":"a"}}`,
	} {
		if err := os.WriteFile(tokenFile, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
		tok, err := GetToken()
		if err == nil || errors.Is(err, ErrNoAPILogin) {
			t.Errorf("%s: GetToken = %q %v, want a read error", name, tok, err)
		}
	}
}

func TestAPITokenRefreshesAndStoresRotatedToken(t *testing.T) {
	f := newFakeAPI(t)
	useFakeAPI(t, f)
	if err := apiLogin(t); err != nil {
		t.Fatal(err)
	}
	expire(t)
	if tok, err := APIToken(); err != nil || tok != "access-2" {
		t.Fatalf("after expiry: token = %q %v, want access-2", tok, err)
	}
	st, err := readAPIToken()
	if err != nil {
		t.Fatal(err)
	}
	if st.Token.RefreshToken != "refresh-2" {
		t.Errorf("stored refresh token = %q, want the rotated refresh-2", st.Token.RefreshToken)
	}
	// The rotated token must be the one presented next: the fake accepts
	// only the live one.
	expire(t)
	if tok, err := APIToken(); err != nil || tok != "access-3" {
		t.Errorf("second refresh: token = %q %v, want access-3", tok, err)
	}
}

func TestAPITokenRefreshesOnceUnderConcurrency(t *testing.T) {
	f := newFakeAPI(t)
	useFakeAPI(t, f)
	if err := apiLogin(t); err != nil {
		t.Fatal(err)
	}
	expire(t)
	var wg sync.WaitGroup
	errs := make(chan error, 8)
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if tok, err := APIToken(); err != nil || tok != "access-2" {
				errs <- fmt.Errorf("token = %q %v", tok, err)
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Error(err)
	}
	if n, _ := f.counts(); n != 1 {
		t.Errorf("refreshes = %d, want exactly 1: a reused refresh token revokes the sign-in", n)
	}
}

func TestExpiredSignInThatCannotRefreshIsAnError(t *testing.T) {
	f := newFakeAPI(t)
	useFakeAPI(t, f)
	t.Setenv("GITHUB_TOKEN", "gh-token")
	if err := writeAPIToken(&storedAPIToken{
		APIURL: f.srv.URL, ClientID: "dcr_1",
		Token: &oauth2.Token{AccessToken: "old", RefreshToken: "revoked", Expiry: time.Now().Add(-time.Minute)},
	}); err != nil {
		t.Fatal(err)
	}
	tok, err := GetToken()
	if err == nil || !strings.Contains(err.Error(), "mctl auth login") {
		t.Errorf("GetToken = %q %v, want an error asking to sign in again, not the GitHub token", tok, err)
	}
}

func TestDiscoveryRefusesUntrustedMetadata(t *testing.T) {
	ok := func(base string) map[string]any {
		return map[string]any{
			"issuer":                           base,
			"authorization_endpoint":           base + "/oauth/authorize",
			"token_endpoint":                   base + "/oauth/token",
			"registration_endpoint":            base + "/oauth/register",
			"revocation_endpoint":              base + "/oauth/revoke",
			"code_challenge_methods_supported": []string{"S256"},
		}
	}
	cases := []struct {
		name    string
		mutate  func(doc map[string]any)
		wantErr string
	}{
		{"as served", func(map[string]any) {}, ""},
		{"another issuer", func(d map[string]any) { d["issuer"] = "https://evil.example" }, "issuer"},
		{"token endpoint elsewhere", func(d map[string]any) { d["token_endpoint"] = "https://evil.example/oauth/token" }, "token_endpoint"},
		{"authorize endpoint elsewhere", func(d map[string]any) { d["authorization_endpoint"] = "https://evil.example/a" }, "authorization_endpoint"},
		{"registration endpoint elsewhere", func(d map[string]any) { d["registration_endpoint"] = "https://evil.example/r" }, "registration_endpoint"},
		{"revocation endpoint elsewhere", func(d map[string]any) { d["revocation_endpoint"] = "https://evil.example/r" }, "revocation_endpoint"},
		{"no token endpoint", func(d map[string]any) { delete(d, "token_endpoint") }, "token_endpoint"},
		{"no S256", func(d map[string]any) { d["code_challenge_methods_supported"] = []string{"plain"} }, "S256"},
		{"no revocation endpoint", func(d map[string]any) { delete(d, "revocation_endpoint") }, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			f := newFakeAPI(t)
			useFakeAPI(t, f)
			f.meta = func(base string) map[string]any {
				doc := ok(base)
				c.mutate(doc)
				return doc
			}
			_, err := discoverAPI(context.Background(), f.srv.URL)
			if c.wantErr == "" {
				if err != nil {
					t.Fatalf("err = %v, want none", err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), c.wantErr) {
				t.Fatalf("err = %v, want one naming %q", err, c.wantErr)
			}
			// And the login as a whole stops there: nothing is stored.
			if err := APILogin(context.Background(), &bytes.Buffer{}, false); err == nil {
				t.Error("login succeeded against metadata discovery refuses")
			}
			if _, err := readAPIToken(); !errors.Is(err, ErrNoAPILogin) {
				t.Errorf("a refused login left a credential behind: %v", err)
			}
		})
	}
}

func TestAPIBaseMustBeHTTPSOffLoopback(t *testing.T) {
	for base, wantOK := range map[string]bool{
		"https://api.mctl.ai":    true,
		"http://127.0.0.1:8080":  true,
		"http://localhost:8080":  true,
		"http://[::1]:8080":      true,
		"http://api.mctl.ai":     false,
		"http://127.0.0.1.evil":  false,
		"ftp://api.mctl.ai":      false,
		"api.mctl.ai":            false,
		"http://localhost.evil/": false,
	} {
		_, err := checkAPIBase(base)
		if (err == nil) != wantOK {
			t.Errorf("checkAPIBase(%q) err = %v, want ok=%v", base, err, wantOK)
		}
	}
}

func TestAPILogoutRevokesAndRemoves(t *testing.T) {
	f := newFakeAPI(t)
	tokenFile := useFakeAPI(t, f)
	if err := apiLogin(t); err != nil {
		t.Fatal(err)
	}
	revokeErr, err := APILogout(context.Background())
	if err != nil || revokeErr != nil {
		t.Fatalf("logout: %v, revoke: %v", err, revokeErr)
	}
	if _, revoked := f.counts(); len(revoked) != 1 || revoked[0] != "refresh-1" {
		t.Errorf("revoked = %v, want the stored refresh token", revoked)
	}
	if _, err := os.Stat(tokenFile); !os.IsNotExist(err) {
		t.Errorf("token file still there: %v", err)
	}
	if revokeErr, err := APILogout(context.Background()); err != nil || revokeErr != nil {
		t.Errorf("second logout: %v, revoke: %v; want a no-op", err, revokeErr)
	}
}

// The file goes even when the API cannot be reached, and the caller is told
// the token may still be live.
func TestAPILogoutRemovesTheFileWhenRevocationFails(t *testing.T) {
	f := newFakeAPI(t)
	tokenFile := useFakeAPI(t, f)
	if err := apiLogin(t); err != nil {
		t.Fatal(err)
	}
	f.srv.Close()
	revokeErr, err := APILogout(context.Background())
	if err != nil {
		t.Fatalf("logout: %v", err)
	}
	if revokeErr == nil {
		t.Error("revocation against a dead API reported success")
	}
	if _, err := os.Stat(tokenFile); !os.IsNotExist(err) {
		t.Errorf("token file still there: %v", err)
	}
}
