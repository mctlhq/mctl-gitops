package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

const defaultBaseURL = "https://api.mctl.ai"

// Client calls the mctl REST API.
type Client struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

// NewClient creates an API client using the given GitHub token.
// The base URL is taken from MCTL_API_URL env var, defaulting to https://api.mctl.ai.
func NewClient(token string) *Client {
	base := os.Getenv("MCTL_API_URL")
	if base == "" {
		base = defaultBaseURL
	}
	return &Client{
		baseURL: base,
		token:   token,
		httpClient: &http.Client{Timeout: 15 * time.Second},
	}
}

// Get performs an authenticated GET request and decodes JSON into v.
func (c *Client) Get(path string, v interface{}) error {
	req, err := http.NewRequest("GET", c.baseURL+path, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("reading response: %w", err)
	}
	if resp.StatusCode >= 400 {
		var e struct {
			Error string `json:"error"`
		}
		if jsonErr := json.Unmarshal(body, &e); jsonErr == nil && e.Error != "" {
			return fmt.Errorf("API error (%d): %s", resp.StatusCode, e.Error)
		}
		return fmt.Errorf("API returned %d", resp.StatusCode)
	}
	if v != nil {
		return json.Unmarshal(body, v)
	}
	return nil
}

// GetRaw performs an authenticated GET and returns the raw response body.
func (c *Client) GetRaw(path string) ([]byte, int, error) {
	req, err := http.NewRequest("GET", c.baseURL+path, nil)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, 0, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	body, err := io.ReadAll(resp.Body)
	return body, resp.StatusCode, err
}
