package auth

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/go-jose/go-jose/v4"
	"golang.org/x/oauth2"
)

const testClientID = "mctl-cli-test"

// fakeZitadel is a minimal OIDC provider: discovery, JWKS, an authorize
// endpoint that redirects straight back, and a token endpoint that enforces
// PKCE S256 and serves refresh grants.
type fakeZitadel struct {
	t      *testing.T
	srv    *httptest.Server
	signer jose.Signer
	jwk    jose.JSONWebKey

	mu        sync.Mutex
	challenge string
	nonce     string
	// nonceOverride, when set, is put in the ID token instead of the nonce
	// the client sent.
	nonceOverride string
	refreshes     int
}

func newFakeZitadel(t *testing.T) *fakeZitadel {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	f := &fakeZitadel{t: t, jwk: jose.JSONWebKey{Key: &key.PublicKey, KeyID: "k1", Algorithm: "RS256", Use: "sig"}}
	f.signer, err = jose.NewSigner(jose.SigningKey{Algorithm: jose.RS256, Key: jose.JSONWebKey{Key: key, KeyID: "k1"}}, nil)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{ //nolint:errcheck
			"issuer":                                f.srv.URL,
			"authorization_endpoint":                f.srv.URL + "/authorize",
			"token_endpoint":                        f.srv.URL + "/token",
			"jwks_uri":                              f.srv.URL + "/keys",
			"id_token_signing_alg_values_supported": []string{"RS256"},
		})
	})
	mux.HandleFunc("/keys", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(jose.JSONWebKeySet{Keys: []jose.JSONWebKey{f.jwk}}) //nolint:errcheck
	})
	mux.HandleFunc("/authorize", f.authorize)
	mux.HandleFunc("/token", f.token)
	f.srv = httptest.NewServer(mux)
	t.Cleanup(f.srv.Close)
	return f
}

func (f *fakeZitadel) authorize(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	if q.Get("client_id") != testClientID || q.Get("response_type") != "code" {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if q.Get("code_challenge_method") != "S256" || q.Get("code_challenge") == "" {
		http.Error(w, "PKCE S256 required", http.StatusBadRequest)
		return
	}
	if !strings.Contains(" "+q.Get("scope")+" ", " offline_access ") {
		http.Error(w, "offline_access missing", http.StatusBadRequest)
		return
	}
	redirect, err := url.Parse(q.Get("redirect_uri"))
	if err != nil || redirect.Hostname() != "127.0.0.1" || redirect.Path != "/callback" {
		http.Error(w, "redirect_uri must be the loopback /callback", http.StatusBadRequest)
		return
	}
	f.mu.Lock()
	f.challenge, f.nonce = q.Get("code_challenge"), q.Get("nonce")
	f.mu.Unlock()
	v := redirect.Query()
	v.Set("code", "the-code")
	v.Set("state", q.Get("state"))
	redirect.RawQuery = v.Encode()
	http.Redirect(w, r, redirect.String(), http.StatusFound)
}

func (f *fakeZitadel) token(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	switch r.Form.Get("grant_type") {
	case "authorization_code":
		sum := sha256.Sum256([]byte(r.Form.Get("code_verifier")))
		if r.Form.Get("code") != "the-code" || base64.RawURLEncoding.EncodeToString(sum[:]) != f.challenge {
			http.Error(w, `{"error":"invalid_grant"}`, http.StatusBadRequest)
			return
		}
		nonce := f.nonce
		if f.nonceOverride != "" {
			nonce = f.nonceOverride
		}
		f.writeTokens(w, "access-1", "refresh-1", nonce)
	case "refresh_token":
		if r.Form.Get("refresh_token") != "refresh-1" {
			http.Error(w, `{"error":"invalid_grant"}`, http.StatusBadRequest)
			return
		}
		f.refreshes++
		f.writeTokens(w, "access-2", "refresh-2", "")
	default:
		http.Error(w, `{"error":"unsupported_grant_type"}`, http.StatusBadRequest)
	}
}

func (f *fakeZitadel) writeTokens(w http.ResponseWriter, access, refresh, nonce string) {
	now := time.Now()
	claims := map[string]any{
		"iss": f.srv.URL, "sub": "user-1", "aud": testClientID,
		"iat": now.Unix(), "exp": now.Add(time.Hour).Unix(),
		"preferred_username": "alice",
	}
	if nonce != "" {
		claims["nonce"] = nonce
	}
	payload, _ := json.Marshal(claims)
	sig, err := f.signer.Sign(payload)
	if err != nil {
		f.t.Error(err)
		return
	}
	idToken, _ := sig.CompactSerialize()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{ //nolint:errcheck
		"access_token": access, "token_type": "Bearer", "expires_in": 3600,
		"refresh_token": refresh, "id_token": idToken,
	})
}

func useFake(t *testing.T, f *fakeZitadel) string {
	t.Helper()
	tokenFile := filepath.Join(t.TempDir(), "mctl", "zitadel-token.json")
	t.Setenv("MCTL_ZITADEL_ISSUER", f.srv.URL)
	t.Setenv("MCTL_ZITADEL_CLIENT_ID", testClientID)
	t.Setenv("MCTL_ZITADEL_TOKEN_FILE", tokenFile)
	return tokenFile
}

// browser stands in for the user: it follows the sign-in URL the login
// prints, the way a browser would after the user signs in.
type browser struct {
	t    *testing.T
	done chan struct{}
	once sync.Once
}

var authURLPattern = regexp.MustCompile(`https?://\S+/authorize\?\S+`)

func (b *browser) Write(p []byte) (int, error) {
	if u := authURLPattern.FindString(string(p)); u != "" {
		b.once.Do(func() {
			go func() {
				defer close(b.done)
				resp, err := http.Get(u)
				if err != nil {
					b.t.Errorf("browser: %v", err)
					return
				}
				resp.Body.Close() //nolint:errcheck
			}()
		})
	}
	return len(p), nil
}

func login(t *testing.T) error {
	t.Helper()
	b := &browser{t: t, done: make(chan struct{})}
	err := ZitadelLogin(context.Background(), b, false)
	<-b.done
	return err
}

func TestZitadelLoginStoresTokensOwnerOnly(t *testing.T) {
	f := newFakeZitadel(t)
	tokenFile := useFake(t, f)

	if err := login(t); err != nil {
		t.Fatalf("login: %v", err)
	}
	info, err := os.Stat(tokenFile)
	if err != nil {
		t.Fatal(err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Errorf("token file mode = %o, want 600", perm)
	}
	sub, user, _, err := ZitadelIdentity()
	if err != nil || sub != "user-1" || user != "alice" {
		t.Errorf("identity = %q %q %v, want user-1 alice", sub, user, err)
	}
	tok, err := ZitadelToken()
	if err != nil || tok != "access-1" {
		t.Errorf("token = %q %v, want access-1", tok, err)
	}
}

func TestZitadelLoginRefusesForeignNonce(t *testing.T) {
	f := newFakeZitadel(t)
	tokenFile := useFake(t, f)
	f.nonceOverride = "someone-elses-nonce"

	err := login(t)
	if err == nil || !strings.Contains(err.Error(), "nonce") {
		t.Fatalf("login err = %v, want a nonce refusal", err)
	}
	if _, statErr := os.Stat(tokenFile); !os.IsNotExist(statErr) {
		t.Error("a refused login must not store a token")
	}
}

func TestZitadelTokenRefreshesAndStoresRotatedToken(t *testing.T) {
	f := newFakeZitadel(t)
	useFake(t, f)
	if err := login(t); err != nil {
		t.Fatalf("login: %v", err)
	}
	st, err := readZitadelToken()
	if err != nil {
		t.Fatal(err)
	}
	st.Token.Expiry = time.Now().Add(-time.Minute)
	if err := writeZitadelToken(st); err != nil {
		t.Fatal(err)
	}

	tok, err := ZitadelToken()
	if err != nil || tok != "access-2" {
		t.Fatalf("token = %q %v, want the refreshed access-2", tok, err)
	}
	st, err = readZitadelToken()
	if err != nil {
		t.Fatal(err)
	}
	if st.Token.RefreshToken != "refresh-2" {
		t.Errorf("stored refresh token = %q, want the rotated refresh-2", st.Token.RefreshToken)
	}
	// The stored token is valid again: no second refresh.
	if _, err := ZitadelToken(); err != nil || f.refreshes != 1 {
		t.Errorf("refreshes = %d (%v), want 1", f.refreshes, err)
	}
}

func TestZitadelTokenRefusesLoginForAnotherClient(t *testing.T) {
	f := newFakeZitadel(t)
	useFake(t, f)
	if err := login(t); err != nil {
		t.Fatalf("login: %v", err)
	}
	t.Setenv("MCTL_ZITADEL_CLIENT_ID", "another-client")
	if _, err := ZitadelToken(); err == nil {
		t.Fatal("a token stored for another client id must not be sent")
	}
}

func TestCallbackResult(t *testing.T) {
	cases := []struct {
		name                         string
		state, code, errCode, errMsg string
		wantCode                     string
		wantErr                      string
	}{
		{name: "ok", state: "s", code: "c", wantCode: "c"},
		{name: "foreign state", state: "x", code: "c", wantErr: "state"},
		{name: "missing state", code: "c", wantErr: "state"},
		{name: "provider error", state: "s", errCode: "access_denied", errMsg: "no", wantErr: "access_denied"},
		{name: "no code", state: "s", wantErr: "no authorization code"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := callbackResult(c.state, "s", c.code, c.errCode, c.errMsg)
			if c.wantErr != "" {
				if got.err == nil || !strings.Contains(got.err.Error(), c.wantErr) {
					t.Fatalf("err = %v, want %q", got.err, c.wantErr)
				}
				return
			}
			if got.err != nil || got.code != c.wantCode {
				t.Fatalf("got %+v, want code %q", got, c.wantCode)
			}
		})
	}
}

func TestGetTokenUsesZitadelOnlyWhenOptedIn(t *testing.T) {
	f := newFakeZitadel(t)
	useFake(t, f)
	t.Setenv("MCTL_TOKEN", "")
	t.Setenv("GITHUB_TOKEN", "gh-token")
	if err := writeZitadelToken(&storedZitadelToken{
		Issuer: f.srv.URL, ClientID: testClientID,
		Token: &oauth2.Token{AccessToken: "zitadel-token", Expiry: time.Now().Add(time.Hour)},
	}); err != nil {
		t.Fatal(err)
	}

	t.Setenv("MCTL_AUTH", "")
	if tok, err := GetToken(); err != nil || tok != "gh-token" {
		t.Errorf("default: token = %q %v, want the GitHub token", tok, err)
	}
	t.Setenv("MCTL_AUTH", "zitadel")
	if tok, err := GetToken(); err != nil || tok != "zitadel-token" {
		t.Errorf("MCTL_AUTH=zitadel: token = %q %v, want the ZITADEL token", tok, err)
	}
	t.Setenv("MCTL_TOKEN", "explicit")
	if tok, err := GetToken(); err != nil || tok != "explicit" {
		t.Errorf("MCTL_TOKEN must still win: token = %q %v", tok, err)
	}
}
