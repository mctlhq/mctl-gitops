package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"time"

	"golang.org/x/oauth2"
)

// Sign-in to the mctl API itself (mctlhq/mctl-gitops#1500, phase 5.3): the
// default since this file. The CLI is an OAuth public client of the API's own
// authorization server, the same one MCP clients use: it discovers the
// endpoints (RFC 8414), registers a loopback redirect (RFC 7591), runs the
// authorization code flow with PKCE (S256) and stores the tokens the API
// issues.
//
// Who the person is gets decided on the API's sign-in page, which sends them
// to ZITADEL (auth.mctl.ai) or, while OAUTH_UPSTREAM allows it, to GitHub.
// Either way the token is the API's own and carries the caller's teams, which
// a raw ZITADEL token (zitadel.go) does not: the API withholds groups from it.

const (
	defaultAPIURL   = "https://api.mctl.ai"
	apiCallbackPath = "/callback"
	apiClientName   = "mctl CLI"
	apiScope        = "mctl"
	apiLoginTimeout = 5 * time.Minute
	apiHTTPTimeout  = 30 * time.Second
	// Generous for a metadata or registration document, small enough that a
	// misbehaving endpoint cannot fill memory.
	apiMaxBody = 1 << 20
)

// ErrNoAPILogin: no sign-in is stored for the API in use.
var ErrNoAPILogin = errors.New("not signed in: run 'mctl auth login'")

// APIBaseURL is the API the CLI talks to: MCTL_API_URL, or the default.
func APIBaseURL() string {
	if v := strings.TrimRight(strings.TrimSpace(os.Getenv("MCTL_API_URL")), "/"); v != "" {
		return v
	}
	return defaultAPIURL
}

// storedAPIToken is the credential file. The API URL is kept so a token is
// never sent to an API other than the one that issued it.
type storedAPIToken struct {
	APIURL   string        `json:"api_url"`
	ClientID string        `json:"client_id"`
	Token    *oauth2.Token `json:"token"`
}

// apiTokenPath is <user config dir>/mctl/api-token.json, or
// MCTL_API_TOKEN_FILE.
func apiTokenPath() (string, error) {
	if p := os.Getenv("MCTL_API_TOKEN_FILE"); p != "" {
		return p, nil
	}
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", fmt.Errorf("locating the user config directory: %w", err)
	}
	return filepath.Join(dir, "mctl", "api-token.json"), nil
}

// readAPIToken returns the stored sign-in. ErrNoAPILogin means there is none;
// any other error means the file could not be read, which is not the same
// thing and must not be treated as "signed out".
func readAPIToken() (*storedAPIToken, error) {
	p, err := apiTokenPath()
	if err != nil {
		return nil, err
	}
	b, err := os.ReadFile(p)
	if errors.Is(err, os.ErrNotExist) {
		return nil, ErrNoAPILogin
	}
	if err != nil {
		return nil, fmt.Errorf("reading %s: %w", p, err)
	}
	var st storedAPIToken
	if err := json.Unmarshal(b, &st); err != nil {
		return nil, fmt.Errorf("reading %s: %w", p, err)
	}
	if st.Token == nil || st.Token.AccessToken == "" || st.ClientID == "" || st.APIURL == "" {
		return nil, fmt.Errorf("%s is incomplete: run 'mctl auth login' again", p)
	}
	return &st, nil
}

func writeAPIToken(st *storedAPIToken) error {
	p, err := apiTokenPath()
	if err != nil {
		return err
	}
	return writeOwnerOnly(p, st)
}

// readAPITokenFor returns the stored sign-in when it belongs to base. A
// sign-in for another API is reported as ErrNoAPILogin: for this API there
// is none.
func readAPITokenFor(base string) (*storedAPIToken, error) {
	st, err := readAPIToken()
	if err != nil {
		return nil, err
	}
	if st.APIURL != base {
		return nil, fmt.Errorf("the stored sign-in is for %s, not %s: %w", st.APIURL, base, ErrNoAPILogin)
	}
	return st, nil
}

// apiOAuthMeta is the part of the authorization server metadata (RFC 8414)
// the CLI uses.
type apiOAuthMeta struct {
	Issuer                        string   `json:"issuer"`
	AuthorizationEndpoint         string   `json:"authorization_endpoint"`
	TokenEndpoint                 string   `json:"token_endpoint"`
	RegistrationEndpoint          string   `json:"registration_endpoint"`
	RevocationEndpoint            string   `json:"revocation_endpoint"`
	CodeChallengeMethodsSupported []string `json:"code_challenge_methods_supported"`
}

// isLoopbackHost reports whether host is the local machine, where plain HTTP
// is acceptable (a development API, the tests).
func isLoopbackHost(host string) bool {
	if host == "localhost" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

// checkAPIBase refuses an API URL the sign-in must not run against: anything
// but https, except on the local machine.
func checkAPIBase(base string) (*url.URL, error) {
	u, err := url.Parse(base)
	if err != nil || u.Host == "" {
		return nil, fmt.Errorf("API URL %q is not a URL", base)
	}
	if u.Scheme != "https" && !(u.Scheme == "http" && isLoopbackHost(u.Hostname())) {
		return nil, fmt.Errorf("API URL %q must use https", base)
	}
	return u, nil
}

// discoverAPI fetches and checks the API's authorization server metadata.
// Every endpoint must live on the API's own origin: the document is fetched
// from the API, and an endpoint elsewhere would send the authorization code,
// the PKCE verifier or the refresh token to a host the user never named.
func discoverAPI(ctx context.Context, base string) (*apiOAuthMeta, error) {
	baseURL, err := checkAPIBase(base)
	if err != nil {
		return nil, err
	}
	metaURL := base + "/.well-known/oauth-authorization-server"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, metaURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	resp, err := apiHTTPClient().Do(req)
	if err != nil {
		return nil, fmt.Errorf("reading %s: %w", metaURL, err)
	}
	defer resp.Body.Close() //nolint:errcheck
	body, err := io.ReadAll(io.LimitReader(resp.Body, apiMaxBody))
	if err != nil {
		return nil, fmt.Errorf("reading %s: %w", metaURL, err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("reading %s: HTTP %d (does this API offer OAuth sign-in?)", metaURL, resp.StatusCode)
	}
	var meta apiOAuthMeta
	if err := json.Unmarshal(body, &meta); err != nil {
		return nil, fmt.Errorf("reading %s: %w", metaURL, err)
	}
	if strings.TrimRight(meta.Issuer, "/") != base {
		return nil, fmt.Errorf("%s names issuer %q, expected %q", metaURL, meta.Issuer, base)
	}
	for name, endpoint := range map[string]string{
		"authorization_endpoint": meta.AuthorizationEndpoint,
		"token_endpoint":         meta.TokenEndpoint,
		"registration_endpoint":  meta.RegistrationEndpoint,
	} {
		if err := sameOrigin(baseURL, endpoint); err != nil {
			return nil, fmt.Errorf("%s: %s: %w", metaURL, name, err)
		}
	}
	// Optional in RFC 8414; checked only when present.
	if meta.RevocationEndpoint != "" {
		if err := sameOrigin(baseURL, meta.RevocationEndpoint); err != nil {
			return nil, fmt.Errorf("%s: revocation_endpoint: %w", metaURL, err)
		}
	}
	if !slices.Contains(meta.CodeChallengeMethodsSupported, "S256") {
		return nil, fmt.Errorf("%s does not offer PKCE with S256", metaURL)
	}
	return &meta, nil
}

func sameOrigin(base *url.URL, endpoint string) error {
	if endpoint == "" {
		return errors.New("missing")
	}
	u, err := url.Parse(endpoint)
	if err != nil {
		return fmt.Errorf("%q is not a URL", endpoint)
	}
	if u.Scheme != base.Scheme || u.Host != base.Host {
		return fmt.Errorf("%q is not on %s://%s", endpoint, base.Scheme, base.Host)
	}
	return nil
}

func apiHTTPClient() *http.Client {
	return &http.Client{
		Timeout: apiHTTPTimeout,
		// The endpoints were checked to be on the API's origin; a redirect
		// would carry the request, and its credentials, somewhere unchecked.
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}
}

// registerAPIClient registers this sign-in's loopback redirect with the API
// (RFC 7591) and returns the client id.
func registerAPIClient(ctx context.Context, meta *apiOAuthMeta, redirectURI string) (string, error) {
	reqBody, err := json.Marshal(map[string]any{
		"client_name":                apiClientName,
		"redirect_uris":              []string{redirectURI},
		"grant_types":                []string{"authorization_code", "refresh_token"},
		"response_types":             []string{"code"},
		"token_endpoint_auth_method": "none",
	})
	if err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, meta.RegistrationEndpoint, bytes.NewReader(reqBody))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	resp, err := apiHTTPClient().Do(req)
	if err != nil {
		return "", fmt.Errorf("registering with the API: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck
	body, err := io.ReadAll(io.LimitReader(resp.Body, apiMaxBody))
	if err != nil {
		return "", fmt.Errorf("registering with the API: %w", err)
	}
	var out struct {
		ClientID         string `json:"client_id"`
		Error            string `json:"error"`
		ErrorDescription string `json:"error_description"`
	}
	// The body is decoded for either outcome: an error answer names its
	// reason there. A body that is not JSON leaves the fields empty.
	_ = json.Unmarshal(body, &out)
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		if out.Error != "" {
			return "", fmt.Errorf("registering with the API: HTTP %d: %s: %s", resp.StatusCode, out.Error, out.ErrorDescription)
		}
		return "", fmt.Errorf("registering with the API: HTTP %d", resp.StatusCode)
	}
	if out.ClientID == "" {
		return "", errors.New("registering with the API: the answer carries no client_id")
	}
	return out.ClientID, nil
}

func apiOAuthConfig(meta *apiOAuthMeta, clientID string) *oauth2.Config {
	return &oauth2.Config{
		ClientID: clientID,
		Scopes:   []string{apiScope},
		Endpoint: oauth2.Endpoint{
			AuthURL:  meta.AuthorizationEndpoint,
			TokenURL: meta.TokenEndpoint,
			// A public client: no secret, client_id travels in the form.
			AuthStyle: oauth2.AuthStyleInParams,
		},
	}
}

// APILogin signs in to the mctl API: authorization code flow with PKCE
// (S256) through a loopback listener (RFC 8252), and stores the tokens.
func APILogin(ctx context.Context, out io.Writer, openBrowser bool) error {
	base := APIBaseURL()
	ctx, cancel := context.WithTimeout(ctx, apiLoginTimeout)
	defer cancel()
	ctx = context.WithValue(ctx, oauth2.HTTPClient, apiHTTPClient())

	meta, err := discoverAPI(ctx, base)
	if err != nil {
		return err
	}

	// 127.0.0.1 rather than localhost: an IP literal cannot be redirected
	// elsewhere by a resolver (RFC 8252 8.3).
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return fmt.Errorf("opening the loopback listener: %w", err)
	}
	redirectURI := fmt.Sprintf("http://%s%s", ln.Addr().String(), apiCallbackPath)

	clientID, err := registerAPIClient(ctx, meta, redirectURI)
	if err != nil {
		ln.Close() //nolint:errcheck
		return err
	}
	cfg := apiOAuthConfig(meta, clientID)
	cfg.RedirectURL = redirectURI

	state, err := randomToken()
	if err != nil {
		ln.Close() //nolint:errcheck
		return err
	}
	verifier := oauth2.GenerateVerifier()
	authURL := cfg.AuthCodeURL(state, oauth2.S256ChallengeOption(verifier))

	code, err := awaitLoopbackCode(ctx, ln, apiCallbackPath, state, out, "mctl", authURL, openBrowser)
	if err != nil {
		return err
	}

	tok, err := cfg.Exchange(ctx, code, oauth2.VerifierOption(verifier))
	if err != nil {
		return fmt.Errorf("exchanging the authorization code: %w", err)
	}
	if tok.AccessToken == "" {
		return errors.New("the API returned no access token")
	}
	// Refuse at sign-in what would only fail later: without an expiry the
	// token is never renewed (a zero Expiry reads as "never expires"), and
	// without a refresh token it cannot be.
	if tok.RefreshToken == "" || tok.Expiry.IsZero() {
		return errors.New("the API returned a token that cannot be renewed (no refresh token or no expiry); nothing was stored")
	}
	if err := writeAPIToken(&storedAPIToken{APIURL: base, ClientID: clientID, Token: tok}); err != nil {
		return fmt.Errorf("storing the sign-in: %w", err)
	}
	return nil
}

// APIToken returns a valid access token for the API in use, refreshing and
// storing it when it has expired.
func APIToken() (string, error) {
	base := APIBaseURL()
	st, err := readAPITokenFor(base)
	if err != nil {
		return "", err
	}
	if st.Token.Valid() {
		return st.Token.AccessToken, nil
	}
	return refreshAPIToken(base)
}

// refreshAPIToken refreshes under a lock file. The API rotates refresh
// tokens and treats a reused one as theft, so two mctl processes must never
// present the same one: the second waits, re-reads the file, and uses what
// the first stored.
func refreshAPIToken(base string) (string, error) {
	p, err := apiTokenPath()
	if err != nil {
		return "", err
	}
	unlock, err := lockTokenFile(p)
	if err != nil {
		return "", err
	}
	defer unlock()

	st, err := readAPITokenFor(base)
	if err != nil {
		return "", err
	}
	if st.Token.Valid() {
		return st.Token.AccessToken, nil
	}
	if st.Token.RefreshToken == "" {
		return "", errors.New("the sign-in expired and no refresh token is stored: run 'mctl auth login'")
	}

	ctx, cancel := context.WithTimeout(context.Background(), apiHTTPTimeout)
	defer cancel()
	ctx = context.WithValue(ctx, oauth2.HTTPClient, apiHTTPClient())
	meta, err := discoverAPI(ctx, base)
	if err != nil {
		return "", err
	}
	tok, err := apiOAuthConfig(meta, st.ClientID).TokenSource(ctx, st.Token).Token()
	if err != nil {
		return "", fmt.Errorf("refreshing the sign-in failed (run 'mctl auth login'): %w", err)
	}
	// The API rotates refresh tokens; the new one must be stored or the next
	// refresh fails.
	st.Token = tok
	if err := writeAPIToken(st); err != nil {
		return "", fmt.Errorf("storing the refreshed sign-in: %w", err)
	}
	return tok.AccessToken, nil
}

// APILoginInfo describes the stored sign-in for the API in use.
func APILoginInfo() (apiURL string, expiry time.Time, err error) {
	st, err := readAPITokenFor(APIBaseURL())
	if err != nil {
		return "", time.Time{}, err
	}
	return st.APIURL, st.Token.Expiry, nil
}

// APILogout removes the stored sign-in, whichever API it is for, after
// asking that API to revoke its refresh token. The file is removed even when
// the revocation fails; revokeErr then says the token may still be live
// until it expires.
func APILogout(ctx context.Context) (revokeErr, err error) {
	p, err := apiTokenPath()
	if err != nil {
		return nil, err
	}
	st, readErr := readAPIToken()
	if errors.Is(readErr, ErrNoAPILogin) {
		return nil, nil
	}
	if readErr == nil && st.Token.RefreshToken != "" {
		revokeErr = revokeAPIToken(ctx, st)
	}
	// An unreadable file is still removed: logging out must not need a
	// credential that parses.
	if err := os.Remove(p); err != nil && !errors.Is(err, os.ErrNotExist) {
		return revokeErr, err
	}
	return revokeErr, nil
}

func revokeAPIToken(ctx context.Context, st *storedAPIToken) error {
	ctx, cancel := context.WithTimeout(ctx, apiHTTPTimeout)
	defer cancel()
	meta, err := discoverAPI(ctx, st.APIURL)
	if err != nil {
		return err
	}
	if meta.RevocationEndpoint == "" {
		return fmt.Errorf("%s offers no token revocation", st.APIURL)
	}
	form := url.Values{"token": {st.Token.RefreshToken}, "client_id": {st.ClientID}}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, meta.RevocationEndpoint, strings.NewReader(form.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := apiHTTPClient().Do(req)
	if err != nil {
		return fmt.Errorf("revoking the sign-in: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("revoking the sign-in: HTTP %d", resp.StatusCode)
	}
	return nil
}
