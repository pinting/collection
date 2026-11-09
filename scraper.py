#!/usr/bin/env python3
"""
Music library scraper for the Favorites web showcase.

Scans the local album directory (/home/pinting/Music/Albums), extracts metadata
from folder names and audio tags, enriches with Tidal and Discogs API tokens from .env,
fetches high-resolution album artwork from remote CDNs (Deezer, Apple, Discogs, Catbox),
and exports the dataset to docs/albums.csv.
"""

import argparse
import csv
import difflib
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import mutagen
except ImportError:
    mutagen = None

import requests

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MUSIC_DIR = "/home/pinting/Music/Albums"
DEFAULT_OUTPUT_CSV = os.path.join(ROOT_DIR, "docs", "albums.csv")
DEFAULT_SEED_CSV = os.path.join(ROOT_DIR, "docs", "albums.csv")
DEFAULT_ENV_PATH = os.path.join(ROOT_DIR, ".env")

CSV_FIELDS = ("rank", "artists", "album", "year", "cover", "spotify_url", "tidal_url", "genres")

CANONICAL_GENRES = {
    "rock": "Rock",
    "punk": "Punk",
    "post-punk": "Post-Punk",
    "post punk": "Post-Punk",
    "new wave": "New-Wave",
    "new-wave": "New-Wave",
    "electronic": "Electronic",
    "electronica": "Electronic",
    "pop": "Pop",
    "hip-hop": "Hip-Hop",
    "hip hop": "Hip-Hop",
    "rap": "Hip-Hop",
    "jazz": "Jazz",
    "soul": "Soul",
    "funk": "Funk",
    "folk": "Folk",
    "experimental": "Experimental",
    "psychedelic": "Psychedelic",
    "psych": "Psychedelic",
    "minimal": "Minimal",
    "minimalism": "Minimal",
    "house": "House",
    "techno": "Techno",
    "fusion": "Fusion",
    "jazz-fusion": "Fusion",
    "industrial": "Industrial",
    "classical": "Classical",
    "bossa nova": "Bossa Nova",
    "metal": "Metal",
    "heavy metal": "Metal",
    "ambient": "Ambient",
    "reggae": "Reggae",
    "dub": "Dub",
    "disco": "Disco",
    "blues": "Blues",
    "hardcore": "Hardcore",
    "indie": "Indie",
    "indie rock": "Rock",
    "krautrock": "Krautrock",
    "alternative": "Alternative",
    "soundtrack": "Soundtrack",
}

FOLDER_PATTERN = re.compile(r"^(.+?)\s+-\s+(\d{4})\s+-\s+(.+)$")
CLUTTER_PATTERN = re.compile(
    r"\s*[\(\[](?:remaster|deluxe|expanded|anniversary|version|edition|mono|stereo|bonus|live|collector|\d{4})[^\)\]]*[\)\]]",
    re.IGNORECASE,
)


def fold_string(s: str) -> str:
    """Normalize string by removing diacritics, punctuation and lowercase."""
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFKD", s)
    filtered = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^\w\s]", "", filtered.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def title_similarity(a: str, b: str) -> float:
    """Calculates fuzzy similarity between two titles."""
    fa = fold_string(CLUTTER_PATTERN.sub("", a))
    fb = fold_string(CLUTTER_PATTERN.sub("", b))
    if not fa or not fb:
        return 0.0
    if fa == fb:
        return 1.0
    if fa in fb or fb in fa:
        shorter, longer = (fa, fb) if len(fa) < len(fb) else (fb, fa)
        if len(shorter) / len(longer) >= 0.7:
            return 0.95
    return difflib.SequenceMatcher(None, fa, fb).ratio()


def artists_match(a: str, b: str) -> bool:
    """Checks if two artist strings match."""
    fa = fold_string(a)
    fb = fold_string(b)
    if not fa or not fb:
        return False
    if fa in ("va", "various", "various artists") and fb in ("va", "various", "various artists"):
        return True
    if fa == fb or fa in fb or fb in fa:
        return True
    set_a = set(re.split(r"[,/&]|\band\b|\bwith\b|\bfeat\b", fa))
    set_b = set(re.split(r"[,/&]|\band\b|\bwith\b|\bfeat\b", fb))
    set_a = {x.strip() for x in set_a if x.strip()}
    set_b = {x.strip() for x in set_b if x.strip()}
    return bool(set_a & set_b)


class TidalClient:
    """Client for Tidal OpenAPI v2 with client credentials OAuth."""

    def __init__(self, client_id: str, client_secret: str, country: str = "HU"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.country = country
        self.token = None
        self.token_expiry = 0.0
        self.session = requests.Session()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> Optional[str]:
        if self.token and time.time() < self.token_expiry:
            return self.token
        try:
            resp = self.session.post(
                "https://auth.tidal.com/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                self.token = data.get("access_token")
                self.token_expiry = time.time() + data.get("expires_in", 3600) - 60
                return self.token
        except Exception as e:
            print(f"[Tidal] Token authentication failed: {e}")
        return None

    def search_album(self, artist: str, album: str) -> Optional[Tuple[str, str]]:
        """Returns (album_id, album_url) if a match is found."""
        token = self._get_token()
        if not token:
            return None

        clean_alb = CLUTTER_PATTERN.sub("", album).strip()
        query = f"{artist} {clean_alb}".strip()
        if fold_string(artist) in ("va", "various", "various artists"):
            query = clean_alb

        try:
            resp = self.session.get(
                "https://openapi.tidal.com/v2/searchResults",
                params={"filter[query]": query, "include": "albums", "countryCode": self.country},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.api+json"},
                timeout=10,
            )
            if not resp.ok:
                return None
            data = resp.json()
            included = [x for x in data.get("included", []) if x.get("type") == "albums"]
            for cand in included[:5]:
                cand_title = cand.get("attributes", {}).get("title", "")
                if title_similarity(clean_alb, cand_title) >= 0.70:
                    album_id = cand.get("id")
                    ext_links = cand.get("attributes", {}).get("externalLinks", [])
                    url = f"https://tidal.com/browse/album/{album_id}"
                    for link in ext_links:
                        if link.get("meta", {}).get("type") == "TIDAL_SHARING":
                            url = link.get("href")
                            break
                    return album_id, url
        except Exception:
            pass
        return None


class DiscogsClient:
    """Client for Discogs API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search(self, artist: str, album: str) -> Dict[str, Any]:
        """Returns release information: cover_image, genres, styles."""
        if not self.is_configured():
            return {}

        clean_alb = CLUTTER_PATTERN.sub("", album).strip()
        query = f"{artist} {clean_alb}".strip()
        if fold_string(artist) in ("va", "various", "various artists"):
            query = clean_alb

        try:
            resp = self.session.get(
                "https://api.discogs.com/database/search",
                params={"q": query, "type": "release", "per_page": 5},
                headers={"Authorization": f"Discogs token={self.api_key}", "User-Agent": "FavoritesScraper/1.0"},
                timeout=10,
            )
            if not resp.ok:
                return {}
            data = resp.json()
            results = data.get("results", [])
            for r in results:
                title = r.get("title", "")
                # Format is usually 'Artist - Album'
                cand_artist, _, cand_title = title.partition(" - ")
                if not cand_title:
                    cand_title = title
                if title_similarity(clean_alb, cand_title) >= 0.65 or title_similarity(album, title) >= 0.65:
                    cover = r.get("cover_image", "")
                    if cover.endswith("spacer.gif"):
                        cover = ""
                    genres = r.get("genre", []) + r.get("style", [])
                    return {"cover": cover, "genres": genres}
        except Exception:
            pass
        return {}


class CoverResolver:
    """Resolves remote CDN URLs for album covers using multiple providers."""

    def __init__(self, discogs: DiscogsClient):
        self.discogs = discogs
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FavoritesScraper/1.0 (Mozilla/5.0 compatible)"})

    def resolve(self, artist: str, album: str, local_folder: str, existing_cover: str = "") -> str:
        """Finds or validates a remote CDN cover URL. Never returns a local path."""
        # 1. Existing remote cover if still valid
        if existing_cover and existing_cover.startswith("http"):
            return existing_cover

        clean_alb = CLUTTER_PATTERN.sub("", album).strip()
        query = f"{artist} {clean_alb}".strip()
        if fold_string(artist) in ("va", "various", "various artists"):
            query = clean_alb

        # 2. Deezer API (high-res 500x500 CDN)
        try:
            resp = self.session.get(
                "https://api.deezer.com/search/album",
                params={"q": query, "limit": 4},
                timeout=6,
            )
            if resp.ok:
                items = resp.json().get("data", [])
                for item in items:
                    cand_title = item.get("title", "")
                    cand_artist = item.get("artist", {}).get("name", "")
                    if title_similarity(clean_alb, cand_title) >= 0.65 and (
                        artists_match(artist, cand_artist) or fold_string(artist) in ("va", "various", "various artists")
                    ):
                        cover = item.get("cover_big") or item.get("cover_medium")
                        if cover and cover.startswith("http"):
                            return cover
        except Exception:
            pass

        # 3. iTunes Search API (Apple CDN 600x600)
        try:
            resp = self.session.get(
                "https://itunes.apple.com/search",
                params={"term": query, "entity": "album", "limit": 4},
                timeout=6,
            )
            if resp.ok:
                items = resp.json().get("results", [])
                for item in items:
                    cand_title = item.get("collectionName", "")
                    cand_artist = item.get("artistName", "")
                    if title_similarity(clean_alb, cand_title) >= 0.65 and (
                        artists_match(artist, cand_artist) or fold_string(artist) in ("va", "various", "various artists")
                    ):
                        art = item.get("artworkUrl100")
                        if art and art.startswith("http"):
                            return art.replace("100x100bb.jpg", "600x600bb.jpg")
        except Exception:
            pass

        # 4. Discogs API
        if self.discogs.is_configured():
            discogs_data = self.discogs.search(artist, album)
            cover = discogs_data.get("cover", "")
            if cover and cover.startswith("http"):
                return cover

        # 5. Local image upload to Catbox CDN (for local mixtapes/personal compilations)
        # Guarantees no local files in repo, providing an external HTTPS CDN URL
        local_cover = self._find_local_image(local_folder)
        if local_cover:
            uploaded_url = self._upload_to_catbox(local_cover)
            if uploaded_url:
                return uploaded_url

        # Fallback placeholder CDN
        return "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=600&q=80"

    def _find_local_image(self, folder: str) -> Optional[str]:
        if not os.path.isdir(folder):
            return None
        for fname in ("cover.jpg", "cover.png", "folder.jpg", "front.jpg"):
            path = os.path.join(folder, fname)
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return path
        for fname in os.listdir(folder):
            if fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                path = os.path.join(folder, fname)
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    return path
        return None

    def _upload_to_catbox(self, file_path: str) -> Optional[str]:
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": f},
                    timeout=15,
                )
            if resp.ok and resp.text.strip().startswith("https://"):
                return resp.text.strip()
        except Exception as e:
            print(f"[CDN] Catbox upload error for {file_path}: {e}")
        return None


def read_audio_tags(folder_path: str) -> Dict[str, str]:
    """Reads embedded artist, album, date, and genre tags from audio files in the folder."""
    tags = {}
    if not os.path.isdir(folder_path):
        return tags

    audio_file = None
    for root, _, files in os.walk(folder_path):
        for f in sorted(files):
            if f.lower().endswith((".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav")):
                audio_file = os.path.join(root, f)
                break
        if audio_file:
            break

    if not audio_file:
        return tags

    if mutagen is not None:
        try:
            m = mutagen.File(audio_file, easy=True)
            if m:
                if "artist" in m:
                    tags["artist"] = m["artist"][0]
                if "albumartist" in m and not tags.get("artist"):
                    tags["artist"] = m["albumartist"][0]
                if "album" in m:
                    tags["album"] = m["album"][0]
                if "date" in m:
                    tags["year"] = m["date"][0][:4]
                if "genre" in m:
                    tags["genre"] = ";".join(m["genre"])
                return tags
        except Exception:
            pass

    # Pure Python FLAC Vorbis Comment fallback
    if audio_file.lower().endswith(".flac"):
        try:
            with open(audio_file, "rb") as f:
                if f.read(4) == b"fLaC":
                    while True:
                        hdr = f.read(4)
                        if len(hdr) < 4:
                            break
                        is_last = bool(hdr[0] & 0x80)
                        block_type = hdr[0] & 0x7F
                        length = int.from_bytes(hdr[1:4], "big")
                        if block_type == 4:
                            data = f.read(length)
                            vlen = int.from_bytes(data[0:4], "little")
                            offset = 4 + vlen
                            num = int.from_bytes(data[offset : offset + 4], "little")
                            offset += 4
                            for _ in range(num):
                                if offset + 4 > len(data):
                                    break
                                clen = int.from_bytes(data[offset : offset + 4], "little")
                                offset += 4
                                comment = data[offset : offset + clen].decode("utf-8", errors="ignore")
                                offset += clen
                                if "=" in comment:
                                    k, v = comment.split("=", 1)
                                    ku = k.upper()
                                    if ku in ("ARTIST", "ALBUMARTIST") and "artist" not in tags:
                                        tags["artist"] = v
                                    elif ku == "ALBUM":
                                        tags["album"] = v
                                    elif ku in ("DATE", "YEAR") and "year" not in tags:
                                        tags["year"] = v[:4]
                                    elif ku == "GENRE":
                                        tags["genre"] = tags.get("genre", "") + ";" + v
                            break
                        else:
                            f.seek(length, 1)
                        if is_last:
                            break
        except Exception:
            pass

    return tags


def normalize_genres(raw_genres: List[str]) -> str:
    """Standardizes genre strings into a pipe-delimited list of canonical genres."""
    tokens = []
    for g in raw_genres:
        if not g:
            continue
        parts = re.split(r"[;/|,]", g)
        for p in parts:
            p = p.strip()
            if p:
                tokens.append(p)

    normalized: List[str] = []
    seen: Set[str] = set()

    for token in tokens:
        low = token.lower()
        canon = CANONICAL_GENRES.get(low)
        if not canon:
            # Title-case word
            canon = token.strip().title()
        if canon.lower() not in seen:
            seen.add(canon.lower())
            normalized.append(canon)

    return "|".join(normalized)


def parse_album_directory(dir_name: str, full_path: str) -> Dict[str, Any]:
    """Extracts artist, year, and album title from folder name and audio metadata."""
    folder_artist, folder_year, folder_album = "", "", ""
    m = FOLDER_PATTERN.match(dir_name)
    if m:
        folder_artist, folder_year, folder_album = m.groups()
    else:
        parts = dir_name.split(" - ")
        if len(parts) >= 3:
            folder_artist = parts[0]
            folder_year = parts[1] if parts[1].isdigit() and len(parts[1]) == 4 else ""
            folder_album = " - ".join(parts[2:])
        elif len(parts) == 2:
            folder_artist, folder_album = parts
        else:
            folder_album = dir_name

    tags = read_audio_tags(full_path)
    artist = tags.get("artist") or folder_artist
    if folder_artist.lower() in ("va", "various"):
        artist = "Various Artists"

    album = tags.get("album") or folder_album
    year = tags.get("year") or folder_year

    return {
        "folder": dir_name,
        "path": full_path,
        "artist": artist.strip(),
        "year": year.strip()[:4],
        "album": album.strip(),
        "embedded_genre": tags.get("genre", ""),
    }


def load_seed_csv(path: str) -> Dict[str, Dict[str, str]]:
    """Loads existing CSV rows to preserve curated ranks, Spotify URLs, and CDN covers."""
    if not os.path.isfile(path):
        return {}
    indexed = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fa = fold_string(row.get("artists", ""))
            fb = fold_string(row.get("album", ""))
            key = f"{fa}___{fb}"
            indexed[key] = row
    return indexed


def match_seed_row(artist: str, album: str, seed_data: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Finds best matching row in the seed data."""
    fa = fold_string(artist)
    fb = fold_string(album)
    direct_key = f"{fa}___{fb}"
    if direct_key in seed_data:
        return seed_data[direct_key]

    clean_alb = fold_string(CLUTTER_PATTERN.sub("", album))
    for key, row in seed_data.items():
        seed_art, _, seed_alb = key.partition("___")
        if (artists_match(artist, row.get("artists", "")) or artists_match(fa, seed_art)) and (
            title_similarity(clean_alb, seed_alb) >= 0.70 or title_similarity(fb, seed_alb) >= 0.70
        ):
            return row
    return None


class AlbumScraper:
    def __init__(
        self,
        music_dir: str = DEFAULT_MUSIC_DIR,
        output_csv: str = DEFAULT_OUTPUT_CSV,
        seed_csv: str = DEFAULT_SEED_CSV,
        env_file: str = DEFAULT_ENV_PATH,
        max_workers: int = 4,
    ):
        self.music_dir = music_dir
        self.output_csv = output_csv
        self.seed_csv = seed_csv
        self.max_workers = max_workers

        if load_dotenv and os.path.isfile(env_file):
            load_dotenv(env_file)

        self.tidal = TidalClient(
            client_id=os.getenv("TIDAL_CLIENT_ID", ""),
            client_secret=os.getenv("TIDAL_CLIENT_SECRET", ""),
            country=os.getenv("TIDAL_COUNTRY_CODE", "HU"),
        )
        self.discogs = DiscogsClient(api_key=os.getenv("DISCOGS_API_KEY", ""))
        self.cover_resolver = CoverResolver(self.discogs)

    def run(self, limit: int = 0) -> None:
        if not os.path.isdir(self.music_dir):
            raise FileNotFoundError(f"Music directory not found: {self.music_dir}")

        entries = sorted(os.listdir(self.music_dir))
        album_dirs = [d for d in entries if os.path.isdir(os.path.join(self.music_dir, d))]
        if limit > 0:
            album_dirs = album_dirs[:limit]

        print(f"[Scraper] Found {len(album_dirs)} album directories in {self.music_dir}")
        seed_data = load_seed_csv(self.seed_csv)
        print(f"[Scraper] Loaded {len(seed_data)} seed records from {self.seed_csv}")

        # Step 1: Parse directories and metadata
        parsed_albums = []
        for d in album_dirs:
            full_path = os.path.join(self.music_dir, d)
            parsed_albums.append(parse_album_directory(d, full_path))

        # Step 2: Enrich concurrently
        print(f"[Scraper] Enriching {len(parsed_albums)} albums (workers={self.max_workers})...")
        enriched_albums = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_album = {
                executor.submit(self._enrich_single_album, alb, seed_data): alb for alb in parsed_albums
            }
            completed = 0
            for future in as_completed(future_to_album):
                completed += 1
                result = future.result()
                enriched_albums.append(result)
                if completed % 50 == 0 or completed == len(parsed_albums):
                    print(f"[Scraper] Progress: {completed}/{len(parsed_albums)} albums processed")

        # Step 3: Sort and assign ranks
        # Preserve original ranking order for known favorites; new albums are sorted after
        def sort_key(item: Dict[str, Any]):
            prev_rank = item.get("seed_rank")
            return (
                prev_rank if prev_rank is not None else 999999,
                item["artists"].lower(),
                item["year"],
                item["album"].lower(),
            )

        enriched_albums.sort(key=sort_key)

        for index, item in enumerate(enriched_albums, start=1):
            item["rank"] = index

        # Step 4: Write CSV
        os.makedirs(os.path.dirname(os.path.abspath(self.output_csv)), exist_ok=True)
        with open(self.output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for item in enriched_albums:
                row = {field: item.get(field, "") for field in CSV_FIELDS}
                writer.writerow(row)

        print(f"[Scraper] Successfully wrote {len(enriched_albums)} albums to {self.output_csv}!")

    def _enrich_single_album(self, album_meta: Dict[str, Any], seed_data: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        artist = album_meta["artist"]
        album = album_meta["album"]
        year = album_meta["year"]
        path = album_meta["path"]
        embedded_genre = album_meta["embedded_genre"]

        seed = match_seed_row(artist, album, seed_data)
        seed_rank = None
        spotify_url = ""
        tidal_url = ""
        existing_cover = ""
        genre_list = []

        if seed:
            try:
                seed_rank = int(seed.get("rank", 0))
            except (ValueError, TypeError):
                seed_rank = None
            spotify_url = seed.get("spotify_url", "")
            tidal_url = seed.get("tidal_url", "")
            existing_cover = seed.get("cover", "")
            if seed.get("genres"):
                genre_list.append(seed["genres"])

        if embedded_genre:
            genre_list.append(embedded_genre)

        # Query Tidal if missing
        if not tidal_url and self.tidal.is_configured():
            tidal_res = self.tidal.search_album(artist, album)
            if tidal_res:
                _, tidal_url = tidal_res

        # Query Discogs for additional genre tags if needed
        if not genre_list and self.discogs.is_configured():
            discogs_data = self.discogs.search(artist, album)
            if discogs_data.get("genres"):
                genre_list.extend(discogs_data["genres"])

        # Resolve remote CDN cover URL
        cover_url = self.cover_resolver.resolve(artist, album, path, existing_cover)
        if not cover_url.startswith("http"):
            cover_url = "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=600&q=80"

        final_genres = normalize_genres(genre_list)

        return {
            "seed_rank": seed_rank,
            "artists": artist,
            "album": album,
            "year": year,
            "cover": cover_url,
            "spotify_url": spotify_url,
            "tidal_url": tidal_url,
            "genres": final_genres,
        }


def main():
    parser = argparse.ArgumentParser(description="Scrape music library and build docs/albums.csv")
    parser.add_argument("--music-dir", default=DEFAULT_MUSIC_DIR, help="Path to albums directory")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_CSV, help="Output CSV path")
    parser.add_argument("--seed-csv", default=DEFAULT_SEED_CSV, help="Seed CSV to preserve rankings & Spotify URLs")
    parser.add_argument("--env", default=DEFAULT_ENV_PATH, help="Path to .env file")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent workers")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of albums to scrape (0 for all)")

    args = parser.parse_args()

    scraper = AlbumScraper(
        music_dir=args.music_dir,
        output_csv=args.output,
        seed_csv=args.seed_csv,
        env_file=args.env,
        max_workers=args.workers,
    )
    scraper.run(limit=args.limit)


if __name__ == "__main__":
    main()
