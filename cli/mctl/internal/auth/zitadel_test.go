package auth

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
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
		// Slow enough that concurrent refreshes would overlap.
		time.Sleep(50 * time.Millisecond)
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

func (f *fakeZitadel) setNonceOverride(v string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.nonceOverride = v
}

func (f *fakeZitadel) refreshCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.refreshes
}

func useFake(t *testing.T, f *fakeZitadel) string {
	t.Helper()
	tokenFile := filepath.Join(t.TempDir(), "mctl", "zitadel-token.json")
	t.Setenv("MCTL_ZITADEL_ISSUER", f.srv.URL)
	t.Setenv("MCTL_ZITADEL_CLIENT_ID", testClientID)
	t.Setenv("MCTL_ZITADEL_TOKEN_FILE", tokenFile)
	// Keep the default path away from the developer's own mctl sign-in.
	t.Setenv("MCTL_API_TOKEN_FILE", filepath.Join(t.TempDir(), "mctl", "api-token.json"))
	return tokenFile
}

// browser stands in for the user: it follows the sign-in URL the login
// prints, the way a browser would after the user signs in. before, if set,
// runs first with the redirect URI the login is listening on.
type browser struct {
	t      *testing.T
	done   chan struct{}
	once   sync.Once
	before func(redirectURI string)
}

var authURLPattern = regexp.MustCompile(`https?://\S+/authorize\?\S+`)

func (b *browser) Write(p []byte) (int, error) {
	if u := authURLPattern.FindString(string(p)); u != "" {
		b.once.Do(func() {
			go func() {
				defer close(b.done)
				if b.before != nil {
					parsed, err := url.Parse(u)
					if err != nil {
						b.t.Errorf("browser: %v", err)
						return
					}
					b.before(parsed.Query().Get("redirect_uri"))
				}
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
	return loginWith(t, nil)
}

func loginWith(t *testing.T, before func(string)) error {
	t.Helper()
	b := &browser{t: t, done: make(chan struct{}), before: before}
	err := ZitadelLogin(context.Background(), b, false)
	// The browser only starts once the login printed its URL; a login that
	// failed before that has nothing to wait for.
	select {
	case <-b.done:
	case <-time.After(5 * time.Second):
		// Do not let the browser goroutine report into a finished test.
		t.Cleanup(func() { <-b.done })
	}
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
	if perm := info.Mode().Perm(); runtime.GOOS != "windows" && perm != 0o600 {
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
	f.setNonceOverride("someone-elses-nonce")

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
	if _, err := ZitadelToken(); err != nil || f.refreshCount() != 1 {
		t.Errorf("refreshes = %d (%v), want 1", f.refreshCount(), err)
	}
}

// Parallel mctl commands after expiry must present the refresh token once:
// ZITADEL revokes the whole token family on reuse.
func TestZitadelTokenRefreshesOnceUnderConcurrency(t *testing.T) {
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

	var wg sync.WaitGroup
	errs := make(chan error, 5)
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			tok, err := ZitadelToken()
			if err == nil && tok != "access-2" {
				err = errors.New("got " + tok)
			}
			errs <- err
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Errorf("concurrent ZitadelToken: %v", err)
		}
	}
	if n := f.refreshCount(); n != 1 {
		t.Errorf("refreshes = %d, want 1", n)
	}
}

// A request on the callback path that is not this sign-in's redirect must
// not end the login.
func TestZitadelLoginIgnoresForeignCallback(t *testing.T) {
	f := newFakeZitadel(t)
	useFake(t, f)

	err := loginWith(t, func(redirectURI string) {
		resp, err := http.Get(redirectURI + "?state=not-ours&code=stolen")
		if err != nil {
			t.Errorf("stray request: %v", err)
			return
		}
		resp.Body.Close() //nolint:errcheck
		if resp.StatusCode != http.StatusBadRequest {
			t.Errorf("stray request status = %d, want 400", resp.StatusCode)
		}
	})
	if err != nil {
		t.Fatalf("login after a stray callback: %v", err)
	}
	if tok, err := ZitadelToken(); err != nil || tok != "access-1" {
		t.Errorf("token = %q %v, want access-1", tok, err)
	}
}

func TestStaleLockIsTakenOver(t *testing.T) {
	f := newFakeZitadel(t)
	tokenFile := useFake(t, f)
	lock := tokenFile + ".lock"
	if err := os.MkdirAll(filepath.Dir(lock), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(lock, nil, 0o600); err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-2 * zitadelLockStale)
	if err := os.Chtimes(lock, old, old); err != nil {
		t.Fatal(err)
	}
	// Several acquirers race for one leftover lock: the takeover must hand
	// it to one of them at a time.
	var held, maxHeld, acquired int32
	var wg sync.WaitGroup
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			unlock, err := lockZitadelToken()
			if err != nil {
				t.Errorf("stale lock not taken over: %v", err)
				return
			}
			atomic.AddInt32(&acquired, 1)
			n := atomic.AddInt32(&held, 1)
			for {
				m := atomic.LoadInt32(&maxHeld)
				if n <= m || atomic.CompareAndSwapInt32(&maxHeld, m, n) {
					break
				}
			}
			time.Sleep(20 * time.Millisecond)
			atomic.AddInt32(&held, -1)
			unlock()
		}()
	}
	wg.Wait()
	if acquired != 5 || maxHeld != 1 {
		t.Errorf("acquired = %d, max simultaneous holders = %d; want 5 and 1", acquired, maxHeld)
	}
	if _, err := os.Stat(lock); !os.IsNotExist(err) {
		t.Errorf("lock left behind after unlock: %v", err)
	}
}

// Unlocking must not delete a lock another process took over meanwhile.
func TestUnlockLeavesAnotherHoldersLock(t *testing.T) {
	f := newFakeZitadel(t)
	tokenFile := useFake(t, f)
	if err := os.MkdirAll(filepath.Dir(tokenFile), 0o700); err != nil {
		t.Fatal(err)
	}
	unlock, err := lockZitadelToken()
	if err != nil {
		t.Fatal(err)
	}
	// Simulate a takeover: the path now holds someone else's lock.
	if err := os.WriteFile(tokenFile+".lock", []byte("someone-else"), 0o600); err != nil {
		t.Fatal(err)
	}
	unlock()
	if _, err := os.Stat(tokenFile + ".lock"); err != nil {
		t.Errorf("unlock removed another holder's lock: %v", err)
	}
}

func TestZitadelLogoutRemovesLoginAndIsIdempotent(t *testing.T) {
	f := newFakeZitadel(t)
	tokenFile := useFake(t, f)
	if err := login(t); err != nil {
		t.Fatalf("login: %v", err)
	}
	if err := ZitadelLogout(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(tokenFile); !os.IsNotExist(err) {
		t.Errorf("token file still present after logout: %v", err)
	}
	if err := ZitadelLogout(); err != nil {
		t.Errorf("second logout: %v", err)
	}
	if _, err := ZitadelToken(); err == nil {
		t.Error("ZitadelToken after logout must fail")
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
		wantForeign                  bool
	}{
		{name: "ok", state: "s", code: "c", wantCode: "c"},
		{name: "foreign state", state: "x", code: "c", wantErr: "state", wantForeign: true},
		{name: "missing state", code: "c", wantErr: "state", wantForeign: true},
		{name: "provider error", state: "s", errCode: "access_denied", errMsg: "no", wantErr: "access_denied"},
		{name: "no code", state: "s", wantErr: "no authorization code"},
		{name: "provider error without state", errCode: "access_denied", wantErr: "state", wantForeign: true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := callbackResult(c.state, "s", c.code, c.errCode, c.errMsg)
			if got.foreign != c.wantForeign {
				t.Fatalf("foreign = %v, want %v", got.foreign, c.wantForeign)
			}
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
