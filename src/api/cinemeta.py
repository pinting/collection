from typing import Any, Dict

from src.api.base import APIClient
from src.config import Config


class CinemetaClient(APIClient):
    """Client for Cinemeta movie metadata and genres API."""

    def __init__(self, config: Config):
        super().__init__(config, config.cinemeta_delay)

    def _headers(self) -> dict:
        return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FavoritesApp/1.0"}

    def fetch_meta(self, imdb_id: str) -> Dict[str, Any]:
        """Fetches detailed metadata, genre list, and poster from Cinemeta."""
        if not imdb_id:
            return {}

        url = f"{self.config.cinemeta_base_url}/{imdb_id}.json"
        try:
            data = self._get(url)
            return data.get("meta", {})
        except Exception:
            return {}
