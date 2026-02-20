package vault

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// Client wraps Vault HTTP API calls.
type Client struct {
	Addr       string
	Token      string
	HTTPClient *http.Client
}

// NewClientFromEnv creates a Vault client from VAULT_ADDR and VAULT_TOKEN env vars.
func NewClientFromEnv() (*Client, error) {
	addr := os.Getenv("VAULT_ADDR")
	if addr == "" {
		return nil, fmt.Errorf("VAULT_ADDR environment variable is not set")
	}
	token := os.Getenv("VAULT_TOKEN")
	if token == "" {
		return nil, fmt.Errorf("VAULT_TOKEN environment variable is not set")
	}
	return &Client{
		Addr:       addr,
		Token:      token,
		HTTPClient: &http.Client{Timeout: 15 * time.Second},
	}, nil
}

// SaveRepoPAT stores a repository PAT in Vault at teams/{team}/{service}/repo-pat.
func (c *Client) SaveRepoPAT(team, service, pat string) error {
	url := fmt.Sprintf("%s/v1/secret/data/teams/%s/%s/repo-pat", c.Addr, team, service)

	body := map[string]interface{}{
		"data": map[string]string{
			"pat": pat,
		},
	}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewReader(jsonBody))
	if err != nil {
		return err
	}
	req.Header.Set("X-Vault-Token", c.Token)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("vault request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("vault write failed (HTTP %d): %s", resp.StatusCode, string(respBody))
	}

	return nil
}
