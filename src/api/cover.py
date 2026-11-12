import os
from typing import Optional

import requests

from src.api.base import APIClient
from src.api.discogs import DiscogsClient
from src.config import Config
from src.matching import VA_NAMES, artists_match, clean_title, title_similarity
from src.utils import fold_string


class CatboxUploader:
    """Handles upload of local album artwork to the Catbox CDN service."""

    def __init__(self, config: Config):
        self.config = config

    def upload_file(self, file_path: str) -> Optional[str]:
        """Uploads a local image file to Catbox and returns its public CDN URL."""
        if not os.path.isfile(file_path) or os.path.getsize(file_path) == 0:
            return None

        try:
            data = {"reqtype": "fileupload"}
            if self.config.catbox_userhash:
                data["userhash"] = self.config.catbox_userhash

            with open(file_path, "rb") as f:
                resp = requests.post(
                    self.config.catbox_url,
                    data=data,
                    files={"fileToUpload": f},
                    timeout=self.config.timeout,
                )
            if resp.ok and resp.text.strip().startswith("https://"):
                return resp.text.strip()
        except Exception as e:
            print(f"[CDN] Catbox upload error for {file_path}: {e}")

        return None

    @staticmethod
    def find_local_image(folder: str) -> Optional[str]:
        """Finds primary cover image in a directory."""
        if not os.path.isdir(folder):
            return None

        for fname in ("cover.jpg", "cover.png", "folder.jpg", "front.jpg"):
            path = os.path.join(folder, fname)
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return path

        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                path = os.path.join(folder, fname)
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    return path

        return None


class CoverResolver(APIClient):
    """Resolves remote CDN URLs for album covers using multiple providers."""

    def __init__(self, config: Config, discogs: DiscogsClient):
        super().__init__(config, delay=0.0)
        self.discogs = discogs
        self.catbox = CatboxUploader(config)

    def _headers(self) -> dict:
        return {"User-Agent": "FavoritesScraper/1.0 (Mozilla/5.0 compatible)"}

    def resolve(self, artist: str, album: str, local_folder: str, existing_cover: str = "") -> str:
        """Finds or validates a remote CDN cover URL. Never returns a local path."""
        # 1. Existing remote cover if already a valid URL
        if existing_cover and existing_cover.startswith("http"):
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

        # 5. Local image upload to Catbox CDN
        local_cover = self.catbox.find_local_image(local_folder)
        if local_cover:
            uploaded = self.catbox.upload_file(local_cover)
            if uploaded:
                return uploaded

        # Fallback placeholder CDN
        return self.config.fallback_cover_music

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
