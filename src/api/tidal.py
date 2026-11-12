import os
from typing import Optional, Tuple

from src.api.base import OAuthClient
from src.config import Config
from src.matching import VA_NAMES, clean_title, title_similarity
from src.utils import fold_string


class TidalClient(OAuthClient):
    """Tidal OpenAPI v2 client using Client Credentials OAuth flow."""

    def __init__(self, config: Config):
        client_id = os.getenv("TIDAL_CLIENT_ID", "")
        client_secret = os.getenv("TIDAL_CLIENT_SECRET", "")
        super().__init__(config, config.tidal_delay, config.tidal_auth_url, client_id, client_secret)

    @staticmethod
    def is_available() -> bool:
        return bool(os.getenv("TIDAL_CLIENT_ID") and os.getenv("TIDAL_CLIENT_SECRET"))

    def _headers(self) -> dict:
        headers = super()._headers()
        if headers:
            headers["Accept"] = "application/vnd.api+json"
        return headers

    def search_album(self, artist: str, album: str) -> Optional[Tuple[str, str]]:
        """Searches for an album on Tidal. Returns (album_id, sharing_url) or None."""
        if not self.is_configured():
            return None

        clean_alb = clean_title(album)
        fa = fold_string(artist)
        query = clean_alb if fa in VA_NAMES else f"{artist} {clean_alb}".strip()

        try:
            data = self._get(
                f"{self.config.tidal_base_url}/searchResults",
                params={
                    "filter[query]": query,
                    "include": "albums",
                    "countryCode": self.config.tidal_country,
                },
            )
            results = data.get("data", [])
            refs = results[0].get("relationships", {}).get("albums", {}).get("data", []) if results else []
            ordered_ids = [r["id"] for r in refs if r.get("id")]
            included = {item["id"]: item for item in data.get("included", []) if item.get("type") == "albums"}

            for aid in ordered_ids:
                cand = included.get(aid)
                if not cand:
                    continue
                cand_title = cand.get("attributes", {}).get("title", "")
                if title_similarity(clean_alb, cand_title) >= 0.82 or title_similarity(album, cand_title) >= 0.82:
                    url = f"https://tidal.com/browse/album/{aid}"
                    for link in cand.get("attributes", {}).get("externalLinks", []):
                        if link.get("meta", {}).get("type") == "TIDAL_SHARING":
                            url = link.get("href")
                            break
                    return str(aid), url
        except Exception:
            # Non-fatal search exception
            pass

        return None
