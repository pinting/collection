from typing import Optional

from src.api.base import APIClient
from src.api.discogs import DiscogsClient
from src.config import Config
from src.matching import VA_NAMES, artists_match, clean_title, title_similarity
from src.utils import fold_string


class CoverResolver(APIClient):
    """Resolves remote CDN URLs for album covers using multiple providers (Deezer, iTunes, Discogs)."""

    def __init__(self, config: Config, discogs: DiscogsClient):
        super().__init__(config, delay=0.0)
        self.discogs = discogs

    def _headers(self) -> dict:
        return {"User-Agent": "FavoritesScraper/1.0 (Mozilla/5.0 compatible)"}

    def resolve(self, artist: str, album: str, local_folder: str = "", existing_cover: str = "") -> str:
        """Finds or validates a remote CDN cover URL. Never returns a local path or catbox URL."""
        # 1. Existing remote cover if already a valid CDN URL and not catbox or placeholder
        if existing_cover and existing_cover.startswith("http"):
            if "catbox.moe" not in existing_cover and "images.unsplash.com" not in existing_cover:
                return existing_cover

        clean_alb = clean_title(album)
        fa = fold_string(artist)
        query = clean_alb if fa in VA_NAMES else f"{artist} {clean_alb}".strip()

        # 2. Deezer API (high-res 500x500 CDN)
        cover = self._search_deezer(query, artist, clean_alb)
        if cover:
            return cover

        # 3. iTunes Search API (Apple CDN 600x600)
        cover = self._search_itunes(query, artist, clean_alb)
        if cover:
            return cover

        # 4. Discogs API
        if self.discogs.is_configured():
            discogs_data = self.discogs.search(artist, album)
            if discogs_data.cover and discogs_data.cover.startswith("http"):
                return discogs_data.cover

        # No remote CDN artwork found
        return ""

    def _search_deezer(self, query: str, artist: str, clean_alb: str) -> Optional[str]:
        try:
            data = self._get(f"{self.config.deezer_base_url}/search/album", params={"q": query, "limit": 4})
            items = data.get("data", [])
            for item in items:
                cand_title = item.get("title", "")
                cand_artist = item.get("artist", {}).get("name", "")
                if title_similarity(clean_alb, cand_title) >= self.config.discogs_min_title_similarity and (
                    artists_match(artist, cand_artist) or fold_string(artist) in VA_NAMES
                ):
                    cover = item.get("cover_big") or item.get("cover_medium")
                    if cover and cover.startswith("http"):
                        return cover
        except Exception:
            pass
        return None

    def _search_itunes(self, query: str, artist: str, clean_alb: str) -> Optional[str]:
        try:
            data = self._get(
                f"{self.config.itunes_base_url}/search",
                params={"term": query, "entity": "album", "limit": 4},
            )
            items = data.get("results", [])
            for item in items:
                cand_title = item.get("collectionName", "")
                cand_artist = item.get("artistName", "")
                if title_similarity(clean_alb, cand_title) >= self.config.discogs_min_title_similarity and (
                    artists_match(artist, cand_artist) or fold_string(artist) in VA_NAMES
                ):
                    art = item.get("artworkUrl100")
                    if art and art.startswith("http"):
                        return art.replace("100x100bb.jpg", "600x600bb.jpg")
        except Exception:
            pass
        return None
