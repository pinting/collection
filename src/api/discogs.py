import os
from typing import Any, Dict

from src.api.base import APIClient
from src.config import Config
from src.matching import clean_title, title_similarity
from src.models import DiscogsRelease
from src.utils import fold_string


class DiscogsClient(APIClient):
    """Client for Discogs API release search and artwork/genre retrieval."""

    def __init__(self, config: Config):
        super().__init__(config, config.discogs_delay)
        self.api_key = os.getenv("DISCOGS_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        if not self.is_configured():
            return {}
        return {
            "Authorization": f"Discogs token={self.api_key}",
            "User-Agent": self.config.discogs_user_agent,
            "Accept": "application/json",
        }

    def search(self, artist: str, album: str) -> DiscogsRelease:
        """Searches Discogs for release metadata, returning cover image and genre tags."""
        if not self.is_configured():
            return DiscogsRelease()

        clean_alb = clean_title(album)
        fa = fold_string(artist)
        query = clean_alb if fa in ("va", "various", "various artists") else f"{artist} {clean_alb}".strip()

        try:
            data = self._get(
                f"{self.config.discogs_base_url}/database/search",
                params={
                    "q": query,
                    "type": "release",
                    "per_page": self.config.discogs_per_page,
                },
            )
            results = data.get("results", [])
            for r in results:
                title = r.get("title", "")
                cand_artist, _, cand_title = title.partition(" - ")
                if not cand_title:
                    cand_title = title

                min_sim = self.config.discogs_min_title_similarity
                if title_similarity(clean_alb, cand_title) >= min_sim or title_similarity(album, title) >= min_sim:
                    cover = r.get("cover_image", "")
                    if cover.endswith("spacer.gif"):
                        cover = ""
                    genres = r.get("genre", []) + r.get("style", [])
                    return DiscogsRelease(cover=cover, genres=genres)
        except Exception:
            pass

        return DiscogsRelease()
