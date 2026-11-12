import time
from typing import Any, Dict, Optional

import requests

from src.config import Config


class APIClient:
    """Base API client with automated retry, backoff, and rate-limit handling."""

    def __init__(self, config: Config, delay: float = 0.0):
        self.config = config
        self.delay = delay
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        return {}

    def _on_unauthorized(self) -> None:
        pass

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self._send("GET", url, params=params)
        return {} if response.status_code == 404 else response.json()

    def _post(
        self,
        url: str,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        files: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        response = self._send("POST", url, json=json_body, data=data, files=files, headers=headers)
        response.raise_for_status()
        return response

    def _send(self, method: str, url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> requests.Response:
        """Sends an HTTP request with retries, 429 rate limit backoff, and timeouts."""
        retries = self.config.retries

        for attempt in range(1, retries + 1):
            if self.delay > 0:
                time.sleep(self.delay)

            try:
                combined_headers = {**self._headers(), **(headers or {})}
                response = self.session.request(
                    method,
                    url,
                    headers=combined_headers,
                    timeout=self.config.timeout,
                    **kwargs,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt == retries:
                    raise
                print(f"Request failed: {e}. Retrying ({attempt}/{retries})...")
                self._backoff(attempt)
                continue

            if response.ok or response.status_code == 404:
                return response

            if attempt == retries:
                response.raise_for_status()

            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", self.config.retry_after))
                print(f"Rate limited, waiting {wait}s ({attempt}/{retries})...")
                time.sleep(wait)
            elif response.status_code == 401:
                self._on_unauthorized()
            elif response.status_code >= 500:
                self._backoff(attempt)
            else:
                response.raise_for_status()

        return response

    def _backoff(self, attempt: int) -> None:
        time.sleep(self.config.retry_backoff * attempt)


class OAuthClient(APIClient):
    """OAuth2 Client Credentials client with automatic token refreshing and margin."""

    def __init__(self, config: Config, delay: float, auth_url: str, client_id: str, client_secret: str):
        super().__init__(config, delay)
        self.auth_url = auth_url
        self.credentials = (client_id, client_secret)
        self.token: Optional[str] = None
        self.token_expires_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(self.credentials[0] and self.credentials[1])

    def _headers(self) -> Dict[str, str]:
        if not self.is_configured():
            return {}

        if self.token is None or time.time() >= self.token_expires_at:
            self._authenticate()

        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _on_unauthorized(self) -> None:
        self.token = None

    def _authenticate(self) -> None:
        retries = self.config.retries

        for attempt in range(1, retries + 1):
            try:
                response = self.session.post(
                    self.auth_url,
                    data={"grant_type": "client_credentials"},
                    auth=self.credentials,
                    timeout=self.config.timeout,
                )
                response.raise_for_status()
                data = response.json()

                self.token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                self.token_expires_at = time.time() + expires_in - self.config.token_margin
                return
            except requests.exceptions.RequestException as e:
                if attempt == retries:
                    print(f"OAuth authentication failed at {self.auth_url}: {e}")
                    self.token = None
                    return
                self._backoff(attempt)
