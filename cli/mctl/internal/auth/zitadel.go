package auth

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
	"golang.org/x/oauth2"
)

// ZITADEL sign-in for the mctl API (mctlhq/mctl-api#434). Opt-in: nothing
// here runs unless MCTL_AUTH=zitadel, or `mctl auth login --zitadel` is
// invoked; the GitHub token path in gh.go stays the default.
//
// The client is the native application `mctl-cli` in the ZITADEL project
// "MCTL API" (mctl-gitops platform-gitops/helm-charts/zitadel-iac/iac/
// mctl-api.tf): public, PKCE, no secret. Its access tokens are JWTs whose
// audience mctl-api enforces.

const (
	defaultZitadelIssuer = "https://auth.mctl.ai"
	// The client id of `mctl-cli`. Public by nature (a native app has no
	// secret); the zitadel-iac Job publishes it as MCTL_CLI_ZITADEL_CLIENT_ID
	// in mctl-api/mctl-api-oidc-zitadel.
	defaultZitadelClientID = "393609398217344725"

	// ZITADEL matches a native app's loopback redirect on path only, so the
	// port is free; the path must match the registered one.
	zitadelCallbackPath = "/callback"
	zitadelLoginTimeout = 5 * time.Minute
)

// zitadelScopes: offline_access for a refresh token; profile/email so the
// ID token names the user in `mctl auth status`.
var zitadelScopes = []string{oidc.ScopeOpenID, "profile", "email", oidc.ScopeOfflineAccess}

// ErrNoZitadelLogin: no ZITADEL login is stored.
var ErrNoZitadelLogin = errors.New("not logged in to ZITADEL: run 'mctl auth login --zitadel'")

// UseZitadel reports whether the ZITADEL token was chosen for API calls.
func UseZitadel() bool {
	return strings.EqualFold(strings.TrimSpace(os.Getenv("MCTL_AUTH")), "zitadel")
}

type zitadelSettings struct {
	issuer   string
	clientID string
}

func loadZitadelSettings() (zitadelSettings, error) {
	s := zitadelSettings{issuer: defaultZitadelIssuer, clientID: defaultZitadelClientID}
	if v := strings.TrimSpace(os.Getenv("MCTL_ZITADEL_ISSUER")); v != "" {
		s.issuer = v
	}
	if v := strings.TrimSpace(os.Getenv("MCTL_ZITADEL_CLIENT_ID")); v != "" {
		s.clientID = v
	}
	if s.clientID == "" {
		return s, errors.New("no ZITADEL client id: set MCTL_ZITADEL_CLIENT_ID")
	}
	return s, nil
}

// storedZitadelToken is the credential file. The issuer and client id are
// kept so a token is never sent after either was changed underneath it.
type storedZitadelToken struct {
	Issuer   string        `json:"issuer"`
	ClientID string        `json:"client_id"`
	Subject  string        `json:"sub"`
	Username string        `json:"preferred_username,omitempty"`
	Token    *oauth2.Token `json:"token"`
}

// zitadelTokenPath is <user config dir>/mctl/zitadel-token.json, or
// MCTL_ZITADEL_TOKEN_FILE.
func zitadelTokenPath() (string, error) {
	if p := os.Getenv("MCTL_ZITADEL_TOKEN_FILE"); p != "" {
		return p, nil
	}
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", fmt.Errorf("locating the user config directory: %w", err)
	}
	return filepath.Join(dir, "mctl", "zitadel-token.json"), nil
}

func readZitadelToken() (*storedZitadelToken, error) {
	p, err := zitadelTokenPath()
	if err != nil {
		return nil, err
	}
	b, err := os.ReadFile(p)
	if errors.Is(err, os.ErrNotExist) {
		return nil, ErrNoZitadelLogin
	}
	if err != nil {
		return nil, fmt.Errorf("reading %s: %w", p, err)
	}
	var st storedZitadelToken
	if err := json.Unmarshal(b, &st); err != nil {
		return nil, fmt.Errorf("reading %s: %w", p, err)
	}
	if st.Token == nil || st.Token.AccessToken == "" {
		return nil, fmt.Errorf("%s holds no access token: %w", p, ErrNoZitadelLogin)
	}
	return &st, nil
}

// writeZitadelToken stores the ZITADEL credential (see writeOwnerOnly).
func writeZitadelToken(st *storedZitadelToken) error {
	p, err := zitadelTokenPath()
	if err != nil {
		return err
	}
	return writeOwnerOnly(p, st)
}

// writeOwnerOnly writes v as JSON to p, owner-only (mode 600 on Unix; on
// Windows the user profile's ACLs apply), through a temp file and a rename
// so a crash never leaves half a credential behind.
func writeOwnerOnly(p string, v any) error {
	if err := os.MkdirAll(filepath.Dir(p), 0o700); err != nil {
		return fmt.Errorf("creating %s: %w", filepath.Dir(p), err)
	}
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(p), "."+filepath.Base(p)+"-*")
	if err != nil {
		return fmt.Errorf("writing %s: %w", p, err)
	}
	defer os.Remove(tmp.Name()) //nolint:errcheck
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close() //nolint:errcheck
		return err
	}
	if _, err := tmp.Write(b); err != nil {
		tmp.Close() //nolint:errcheck
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), p)
}

// ZitadelLogout removes the stored ZITADEL credential, if any.
func ZitadelLogout() error {
	p, err := zitadelTokenPath()
	if err != nil {
		return err
	}
	if err := os.Remove(p); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return nil
}

func zitadelOAuthConfig(ctx context.Context, s zitadelSettings) (*oidc.Provider, *oauth2.Config, error) {
	provider, err := oidc.NewProvider(ctx, s.issuer)
	if err != nil {
		return nil, nil, fmt.Errorf("ZITADEL discovery at %s: %w", s.issuer, err)
	}
	return provider, &oauth2.Config{
		ClientID: s.clientID,
		Endpoint: provider.Endpoint(),
		Scopes:   zitadelScopes,
	}, nil
}

// ZitadelToken returns a valid ZITADEL access token, refreshing and storing
// it when it has expired.
func ZitadelToken() (string, error) {
	s, err := loadZitadelSettings()
	if err != nil {
		return "", err
	}
	st, err := readZitadelToken()
	if err != nil {
		return "", err
	}
	if st.Issuer != s.issuer || st.ClientID != s.clientID {
		return "", fmt.Errorf("stored ZITADEL login is for %s (client %s): %w", st.Issuer, st.ClientID, ErrNoZitadelLogin)
	}
	if st.Token.Valid() {
		return st.Token.AccessToken, nil
	}
	return refreshZitadelToken(s)
}

// refreshZitadelToken refreshes under a lock file. ZITADEL rotates refresh
// tokens and treats a reused one as theft, revoking the whole family, so two
// mctl processes must never present the same one: the second waits, re-reads
// the file, and uses what the first stored.
func refreshZitadelToken(s zitadelSettings) (string, error) {
	unlock, err := lockZitadelToken()
	if err != nil {
		return "", err
	}
	defer unlock()

	st, err := readZitadelToken()
	if err != nil {
		return "", err
	}
	if st.Issuer != s.issuer || st.ClientID != s.clientID {
		return "", fmt.Errorf("stored ZITADEL login is for %s (client %s): %w", st.Issuer, st.ClientID, ErrNoZitadelLogin)
	}
	if st.Token.Valid() {
		return st.Token.AccessToken, nil
	}
	if st.Token.RefreshToken == "" {
		return "", errors.New("ZITADEL access token expired and no refresh token is stored: run 'mctl auth login --zitadel'")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	_, cfg, err := zitadelOAuthConfig(ctx, s)
	if err != nil {
		return "", err
	}
	tok, err := cfg.TokenSource(ctx, st.Token).Token()
	if err != nil {
		return "", fmt.Errorf("refreshing the ZITADEL token failed (run 'mctl auth login --zitadel'): %w", err)
	}
	// ZITADEL rotates refresh tokens; the new one must be stored or the
	// next refresh fails.
	st.Token = tok
	if err := writeZitadelToken(st); err != nil {
		return "", fmt.Errorf("storing the refreshed ZITADEL token: %w", err)
	}
	return tok.AccessToken, nil
}

const (
	// Longer than a refresh may take (its context allows 30 s), so a waiter
	// never gives up on a healthy holder; shorter than zitadelLockStale.
	zitadelLockWait  = 45 * time.Second
	zitadelLockStale = time.Minute
)

// lockZitadelToken locks the ZITADEL credential file (see lockTokenFile).
func lockZitadelToken() (func(), error) {
	p, err := zitadelTokenPath()
	if err != nil {
		return nil, err
	}
	return lockTokenFile(p)
}

// lockTokenFile takes <token file>.lock with O_EXCL. A lock older than
// zitadelLockStale is left over from a killed process and is taken over.
func lockTokenFile(p string) (func(), error) {
	lock := p + ".lock"
	if err := os.MkdirAll(filepath.Dir(p), 0o700); err != nil {
		return nil, fmt.Errorf("creating %s: %w", filepath.Dir(p), err)
	}
	owner, err := randomToken()
	if err != nil {
		return nil, err
	}
	deadline := time.Now().Add(zitadelLockWait)
	for {
		f, err := os.OpenFile(lock, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		if err == nil {
			_, werr := f.WriteString(owner)
			f.Close() //nolint:errcheck
			if werr != nil {
				os.Remove(lock) //nolint:errcheck
				return nil, fmt.Errorf("locking %s: %w", p, werr)
			}
			// Remove only our own lock: after a stale takeover the path may
			// hold another process's lock by the time we unlock.
			return func() {
				if b, err := os.ReadFile(lock); err == nil && string(b) == owner {
					os.Remove(lock) //nolint:errcheck
				}
			}, nil
		}
		if !errors.Is(err, os.ErrExist) {
			return nil, fmt.Errorf("locking %s: %w", p, err)
		}
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("another mctl process holds %s; remove it if no mctl is running", lock)
		}
		if info, statErr := os.Stat(lock); statErr == nil && time.Since(info.ModTime()) > zitadelLockStale {
			// Take a stale lock over by renaming it away: a rename succeeds
			// for one process only, where remove-then-create could hand the
			// lock to two. The loser simply retries.
			stale := fmt.Sprintf("%s.stale.%d", lock, os.Getpid())
			if os.Rename(lock, stale) == nil {
				os.Remove(stale) //nolint:errcheck
			}
		}
		time.Sleep(100 * time.Millisecond)
	}
}

// ZitadelIdentity returns who the stored ZITADEL login belongs to.
func ZitadelIdentity() (subject, username string, expiry time.Time, err error) {
	st, err := readZitadelToken()
	if err != nil {
		return "", "", time.Time{}, err
	}
	return st.Subject, st.Username, st.Token.Expiry, nil
}

// ZitadelLogin runs the authorization code flow with PKCE (S256) through a
// loopback listener (RFC 8252), checks state and the ID token's nonce, and
// stores the tokens.
func ZitadelLogin(ctx context.Context, out io.Writer, openBrowser bool) error {
	s, err := loadZitadelSettings()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(ctx, zitadelLoginTimeout)
	defer cancel()

	provider, cfg, err := zitadelOAuthConfig(ctx, s)
	if err != nil {
		return err
	}

	// 127.0.0.1 rather than localhost: an IP literal cannot be redirected
	// elsewhere by a resolver (RFC 8252 8.3).
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return fmt.Errorf("opening the loopback listener: %w", err)
	}
	cfg.RedirectURL = fmt.Sprintf("http://%s%s", ln.Addr().String(), zitadelCallbackPath)

	state, err := randomToken()
	if err != nil {
		return err
	}
	nonce, err := randomToken()
	if err != nil {
		return err
	}
	verifier := oauth2.GenerateVerifier()
	authURL := cfg.AuthCodeURL(state, oauth2.S256ChallengeOption(verifier), oidc.Nonce(nonce))

	code, err := awaitLoopbackCode(ctx, ln, zitadelCallbackPath, state, out, "ZITADEL", authURL, openBrowser)
	if err != nil {
		return err
	}

	tok, err := cfg.Exchange(ctx, code, oauth2.VerifierOption(verifier))
	if err != nil {
		return fmt.Errorf("exchanging the authorization code: %w", err)
	}
	rawID, ok := tok.Extra("id_token").(string)
	if !ok || rawID == "" {
		return errors.New("ZITADEL returned no ID token")
	}
	idToken, err := provider.Verifier(&oidc.Config{ClientID: s.clientID}).Verify(ctx, rawID)
	if err != nil {
		return fmt.Errorf("verifying the ID token: %w", err)
	}
	if subtle.ConstantTimeCompare([]byte(idToken.Nonce), []byte(nonce)) != 1 {
		return errors.New("ID token nonce does not match this sign-in")
	}
	var claims struct {
		PreferredUsername string `json:"preferred_username"`
	}
	_ = idToken.Claims(&claims)

	if err := writeZitadelToken(&storedZitadelToken{
		Issuer:   s.issuer,
		ClientID: s.clientID,
		Subject:  idToken.Subject,
		Username: claims.PreferredUsername,
		Token:    tok,
	}); err != nil {
		return fmt.Errorf("storing the ZITADEL token: %w", err)
	}
	return nil
}

// awaitLoopbackCode serves the loopback redirect of one sign-in on ln, prints
// authURL (opening a browser when asked) and returns the authorization code
// carried by the redirect whose state is this sign-in's. what names the
// sign-in page in messages.
func awaitLoopbackCode(ctx context.Context, ln net.Listener, callbackPath, state string, out io.Writer, what, authURL string, openBrowser bool) (string, error) {
	results := make(chan callbackOutcome, 1)
	mux := http.NewServeMux()
	mux.HandleFunc(callbackPath, func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		res := callbackResult(q.Get("state"), state, q.Get("code"), q.Get("error"), q.Get("error_description"))
		if res.foreign {
			// Not this sign-in's redirect (a prefetch, a scanner, another
			// local process): refuse it and keep waiting for the real one.
			http.Error(w, "mctl: unknown sign-in", http.StatusBadRequest)
			return
		}
		if res.err != nil {
			http.Error(w, "mctl: sign-in failed: "+res.err.Error(), http.StatusBadRequest)
		} else {
			fmt.Fprintln(w, "mctl: signed in. You can close this window.")
		}
		select {
		case results <- res:
		default:
		}
	})
	srv := &http.Server{Handler: mux, ReadHeaderTimeout: 10 * time.Second}
	go srv.Serve(ln) //nolint:errcheck
	defer func() {
		// Shutdown, not Close: let the page answering the browser finish,
		// above all the error page.
		sctx, scancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer scancel()
		srv.Shutdown(sctx) //nolint:errcheck
	}()

	if openBrowser {
		fmt.Fprintf(out, "Opening the %s sign-in page. If no browser opens, visit:\n\n  %s\n\n", what, authURL)
	} else {
		fmt.Fprintf(out, "To sign in to %s, visit:\n\n  %s\n\n", what, authURL)
	}
	if openBrowser {
		_ = launchBrowser(authURL)
	}

	select {
	case res := <-results:
		return res.code, res.err
	case <-ctx.Done():
		return "", fmt.Errorf("waiting for the %s sign-in: %w", what, ctx.Err())
	}
}

type callbackOutcome struct {
	code string
	err  error
	// foreign: the state is not this sign-in's, so the request is not the
	// redirect being waited for and must not end the login.
	foreign bool
}

// callbackResult validates one loopback callback: the state must be the one
// this login sent (constant-time), and an error from the sign-in page wins
// over a code.
func callbackResult(gotState, wantState, code, errCode, errDesc string) callbackOutcome {
	if subtle.ConstantTimeCompare([]byte(gotState), []byte(wantState)) != 1 {
		return callbackOutcome{err: errors.New("state does not match this sign-in"), foreign: true}
	}
	if errCode != "" {
		if errDesc != "" {
			return callbackOutcome{err: fmt.Errorf("the sign-in was refused: %s: %s", errCode, errDesc)}
		}
		return callbackOutcome{err: fmt.Errorf("the sign-in was refused: %s", errCode)}
	}
	if code == "" {
		return callbackOutcome{err: errors.New("callback carried no authorization code")}
	}
	return callbackOutcome{code: code}
}

func randomToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("generating a random value: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}

func launchBrowser(u string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", u)
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", u)
	default:
		cmd = exec.Command("xdg-open", u)
	}
	return cmd.Start()
}
