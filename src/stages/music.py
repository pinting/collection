import csv
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.api.cover import CoverResolver
from src.api.discogs import DiscogsClient
from src.api.tidal import TidalClient
from src.audio import read_audio_tags
from src.config import Config
from src.genres import normalize_music_genres
from src.matching import (
    VA_NAMES,
    artists_match,
    clean_title,
    parse_album_folder,
    title_similarity,
)
from src.models import MusicAlbum
from src.utils import fold_string, is_progress

# Ground-truth overrides for albums with known historical ambiguities or duplicate seed mappings
KNOWN_OVERRIDES: Dict[tuple, Dict[str, Any]] = {
    # The Beatles
    ("the beatles", "rubber soul"): {
        "spotify_url": "https://open.spotify.com/album/50o7kf2wLwVmOTVYJOTplm",
        "tidal_url": "https://tidal.com/browse/album/55163273",
        "cover": "https://i.scdn.co/image/ab67616d00001e02ed801e58a9ababdea6ac7ce4",
        "seed_rank": 20,
    },
    ("the beatles", "the beatles"): {
        "spotify_url": "https://open.spotify.com/album/1klALx0u4AavZNEvC4LrTL",
        "tidal_url": "https://tidal.com/browse/album/55163302",
        "cover": "https://i.scdn.co/image/ab67616d00001e024ce8b4e42588bf18182a1ad2",
        "seed_rank": 21,
    },
    ("the beatles", "please please me"): {
        "spotify_url": "https://open.spotify.com/album/3KzAvEXcqJKBF97HrXwlgf",
        "tidal_url": "https://tidal.com/browse/album/55163243",
        "cover": "https://i.scdn.co/image/ab67616d00001e02dbeec63ad914c973e75c24df",
        "seed_rank": 464,
    },
    ("the beatles", "yellow submarine"): {
        "spotify_url": "https://open.spotify.com/album/47bcKzmKgmMPHXNVOWpLiu",
        "tidal_url": "https://tidal.com/browse/album/55130781",
        "cover": "https://i.scdn.co/image/ab67616d00001e0217cacba12e60416c7f1aebce",
        "seed_rank": 465,
    },
    ("the beatles", "let it be"): {
        "spotify_url": "https://open.spotify.com/album/0jTGHV5xqHPvEcwL8f6YU5",
        "tidal_url": "https://tidal.com/browse/album/55130733",
        "cover": "https://i.scdn.co/image/ab67616d00001e0284243a01af3c77b56fe01ab1",
        "seed_rank": 466,
    },
    # Tamás Cseh
    ("tamas cseh", "level noveremnek"): {
        "spotify_url": "https://open.spotify.com/album/6aU4aXARwn61sIcOAHVFsd",
        "tidal_url": "https://tidal.com/browse/album/543318933",
        "cover": "https://cdn-images.dzcdn.net/images/cover/3cf81c5d01211100572d4cf6065538e3/500x500-000000-80-0-0.jpg",
        "seed_rank": 29,
    },
    ("tamas cseh", "level noveremnek vol 2"): {
        "spotify_url": "https://open.spotify.com/album/6Eyin4SyKgOY5FUwuKskZ9",
        "tidal_url": "https://tidal.com/browse/album/283274468",
        "cover": "https://i.scdn.co/image/ab67616d00001e0206b0c5607151fe9bff09aac2",
        "seed_rank": 30,
    },
    # Trabant
    ("trabant", "trabant"): {
        "spotify_url": "https://open.spotify.com/album/72MFBFxb95qaT5eZzTDlO5",
        "tidal_url": "https://tidal.com/browse/album/391283308",
        "cover": "https://i.scdn.co/image/ab67616d00001e02febd085f41e38ce9afb0a4b7",
        "seed_rank": 116,
    },
    ("trabant", "trabant ii"): {
        "spotify_url": "https://open.spotify.com/album/6BiDDlhwEmb3uC0GtV4OjC",
        "tidal_url": "https://tidal.com/browse/album/455753268",
        "cover": "https://i.scdn.co/image/ab67616d00001e021f5cc580d5016215b102937a",
        "seed_rank": 117,
    },
    # DrumTalk (differentiated by year)
    ("drumtalk", "drumtalk", "2012"): {
        "spotify_url": "https://open.spotify.com/album/6308zkyIfMGilSefN5kuMG",
        "tidal_url": "https://tidal.com/browse/album/218287218",
        "cover": "https://i.scdn.co/image/ab67616d00001e02e2e384538dba52d2a283e281",
        "seed_rank": 186,
    },
    ("drumtalk", "drumtalk", "2015"): {
        "spotify_url": "https://open.spotify.com/album/1vQp5f3TMwtPWrZzMUs6yz",
        "tidal_url": "https://tidal.com/browse/album/42628756",
        "cover": "https://i.scdn.co/image/ab67616d00001e023845a019b13548a503316b07",
        "seed_rank": 187,
    },
    # Pye Corner Audio
    ("pye corner audio", "where things are hollow"): {
        "spotify_url": "https://open.spotify.com/album/5KSXjSOkwjwhXd4i3i34Xa",
        "tidal_url": "https://tidal.com/browse/album/185031823",
        "cover": "https://i.scdn.co/image/ab67616d00001e021f5bbcb3827ee78cb71329a2",
        "seed_rank": 204,
    },
    ("pye corner audio", "where things are hollow 2"): {
        "spotify_url": "https://open.spotify.com/album/52c2tceuuykVy7e15d4JNA",
        "tidal_url": "https://tidal.com/browse/album/184826257",
        "cover": "https://i.scdn.co/image/ab67616d00001e02174632bee9a5edff8459e739",
        "seed_rank": 205,
    },
    # Stan Getz
    ("stan getz & joao gilberto", "getz gilberto 76"): {
        "spotify_url": "https://open.spotify.com/album/08HyQbnGbDvcZmEM5hPRrr",
        "tidal_url": "",
        "cover": "https://i.scdn.co/image/ab67616d00001e0290b5036a09ba1508e5edd19f",
        "seed_rank": 463,
    },
    # Pajtás Daloljunk
    ("various artists", "pajtas daloljunk x"): {
        "spotify_url": "",
        "tidal_url": "https://tidal.com/browse/album/70287186",
        "cover": "https://cdn-images.dzcdn.net/images/cover/563d7442ea9f1f4c60ea4fef2264fc25/500x500-000000-80-0-0.jpg",
        "seed_rank": 13,
    },
    ("various artists", "pajtas daloljunk y"): {
        "spotify_url": "https://open.spotify.com/album/3ZO3KV0MZ4H1cWux6vBFUs",
        "tidal_url": "https://tidal.com/browse/album/75232568",
        "cover": "https://i.scdn.co/image/ab67616d00001e028c955851e3022c3b79daae4b",
        "seed_rank": 14,
    },
}


class MusicStage:
    """Stage for scanning local music albums, enriching metadata and CDN artwork, and exporting CSV."""

    def __init__(
        self,
        config: Config,
        tidal: Optional[TidalClient] = None,
        discogs: Optional[DiscogsClient] = None,
        cover_resolver: Optional[CoverResolver] = None,
    ):
        self.config = config
        self.tidal = tidal or TidalClient(config)
        self.discogs = discogs or DiscogsClient(config)
        self.cover_resolver = cover_resolver or CoverResolver(config, self.discogs)
        self.musicd_albums = self._load_musicd_database(self.config.db_path)

    @staticmethod
    def _load_musicd_database(db_path: str) -> Dict[str, List[Dict[str, Any]]]:
        """Loads album metadata from musicd SQLite database if present."""
        if not db_path or not os.path.isfile(db_path):
            return {}

        indexed: Dict[str, List[Dict[str, Any]]] = {}
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.artists, a.album_name, a.release_date, a.external_url, a.images, f.tidal_album_uri, f.genres
                FROM albums a
                LEFT JOIN favorite_albums f ON f.spotify_album_uri = a.album_uri
            """)
            for row in cursor.fetchall():
                artist_name = row[0] or ""
                album_name = row[1] or ""
                release_date = row[2] or ""
                spotify_url = row[3] or ""
                images_json = row[4] or ""
                tidal_uri = row[5] or ""
                genres_json = row[6] or ""

                cover_url = ""
                if images_json:
                    try:
                        imgs = json.loads(images_json)
                        cover_url = imgs[1]["url"] if len(imgs) > 1 else imgs[0]["url"]
                    except Exception:
                        pass

                tidal_url = ""
                if tidal_uri:
                    item_id = tidal_uri.split(":")[-1]
                    if item_id:
                        tidal_url = f"https://tidal.com/browse/album/{item_id}"

                genre_str = ""
                if genres_json:
                    try:
                        g_list = json.loads(genres_json)
                        if isinstance(g_list, list):
                            genre_str = "|".join(g_list)
                    except Exception:
                        pass

                fa = fold_string(artist_name)
                record = {
                    "artists": artist_name,
                    "album": album_name,
                    "year": release_date[:4],
                    "spotify_url": spotify_url,
                    "tidal_url": tidal_url,
                    "cover": cover_url,
                    "genres": genre_str,
                }
                indexed.setdefault(fa, []).append(record)

            conn.close()
            print(f"[Music] Loaded {sum(len(v) for v in indexed.values())} reference albums from {db_path}")
        except Exception as e:
            print(f"[Music] Could not load musicd database from {db_path}: {e}")

        return indexed

    def load_seed_csv(self, path: str) -> Dict[str, Dict[str, str]]:
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

    def match_seed_row(
        self, artist: str, album: str, seed_data: Dict[str, Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """Finds best matching row in seed data with strict title similarity."""
        fa = fold_string(artist)
        fb = fold_string(album)
        direct_key = f"{fa}___{fb}"
        if direct_key in seed_data:
            return seed_data[direct_key]

        clean_alb = clean_title(album)
        for key, row in seed_data.items():
            seed_art, _, seed_alb = key.partition("___")
            if artists_match(artist, row.get("artists", "")) or artists_match(fa, seed_art):
                if title_similarity(clean_alb, seed_alb) >= 0.88 or title_similarity(album, seed_alb) >= 0.88:
                    return row
        return None

    def match_musicd_album(self, artist: str, album: str) -> Optional[Dict[str, Any]]:
        """Finds matching album in musicd database index."""
        fa = fold_string(artist)
        clean_alb = clean_title(album)
        candidates = self.musicd_albums.get(fa, [])
        for cand in candidates:
            cand_name = cand["album"]
            if title_similarity(clean_alb, cand_name) >= 0.88 or title_similarity(album, cand_name) >= 0.88:
                return cand
        return None

    def parse_directory(self, dir_name: str, full_path: str) -> Dict[str, Any]:
        """Parses artist, year, album, and embedded audio tags from folder and media files."""
        folder_artist, folder_year, folder_album = parse_album_folder(dir_name)
        tags = read_audio_tags(full_path)

        artist = tags.artist or folder_artist
        if fold_string(folder_artist) in VA_NAMES:
            artist = "Various Artists"

        album = tags.album or folder_album
        year = tags.year or folder_year

        return {
            "folder": dir_name,
            "path": full_path,
            "artist": artist.strip(),
            "year": year.strip()[:4],
            "album": album.strip(),
            "embedded_genre": tags.genre,
        }

    def _enrich_single_album(
        self, album_meta: Dict[str, Any], seed_data: Dict[str, Dict[str, str]]
    ) -> MusicAlbum:
        artist = album_meta["artist"]
        album = album_meta["album"]
        year = album_meta["year"]
        path = album_meta["path"]
        folder = album_meta["folder"]
        embedded_genre = album_meta["embedded_genre"]

        fa = fold_string(artist)
        clean_alb = clean_title(album)
        fc = fold_string(clean_alb)

        seed_rank: Optional[int] = None
        spotify_url = ""
        tidal_url = ""
        cover_url = ""
        genre_list: List[str] = []

        if embedded_genre:
            genre_list.append(embedded_genre)

        # 1. Check ground-truth override table first
        ov = KNOWN_OVERRIDES.get((fa, fc, year)) or KNOWN_OVERRIDES.get((fa, fc))
        has_override = bool(ov)
        if ov:
            spotify_url = ov.get("spotify_url", "")
            tidal_url = ov.get("tidal_url", "")
            cover_url = ov.get("cover", "")
            if "seed_rank" in ov:
                seed_rank = ov["seed_rank"]

        # 2. Check seed CSV
        seed = self.match_seed_row(artist, album, seed_data)
        if seed:
            if seed_rank is None:
                try:
                    seed_rank = int(seed.get("rank", 0))
                except (ValueError, TypeError):
                    seed_rank = None
            if not has_override:
                if not spotify_url and seed.get("spotify_url"):
                    spotify_url = seed["spotify_url"]
                if not tidal_url and seed.get("tidal_url"):
                    tidal_url = seed["tidal_url"]
                if not cover_url:
                    cov = seed.get("cover", "")
                    if cov and "catbox.moe" not in cov and "unsplash.com" not in cov:
                        cover_url = cov
            if seed.get("genres"):
                genre_list.append(seed["genres"])

        # 3. Check musicd database reference
        if not has_override:
            musicd_row = self.match_musicd_album(artist, album)
            if musicd_row:
                if not spotify_url and musicd_row.get("spotify_url"):
                    spotify_url = musicd_row["spotify_url"]
                if not tidal_url and musicd_row.get("tidal_url"):
                    tidal_url = musicd_row["tidal_url"]
                if not cover_url and musicd_row.get("cover"):
                    cover_url = musicd_row["cover"]
                if musicd_row.get("genres"):
                    genre_list.append(musicd_row["genres"])

        # 4. Query Tidal for album link if still missing
        if not tidal_url and self.tidal.is_configured():
            tidal_res = self.tidal.search_album(artist, album)
            if tidal_res:
                _, tidal_url = tidal_res

        # 5. Query Discogs for genre tags if needed
        if not genre_list and self.discogs.is_configured():
            discogs_data = self.discogs.search(artist, album)
            if discogs_data.genres:
                genre_list.extend(discogs_data.genres)

        # 6. Resolve remote CDN cover URL (never returns local file path or catbox URL)
        cover_url = self.cover_resolver.resolve(artist, album, path, cover_url)

        final_genres = normalize_music_genres(genre_list)

        return MusicAlbum(
            rank=0,
            artists=artist,
            album=album,
            year=year,
            cover=cover_url,
            spotify_url=spotify_url,
            tidal_url=tidal_url,
            genres=final_genres,
            folder=folder,
            path=path,
            seed_rank=seed_rank,
        )

    def run(self, limit: Optional[int] = None) -> List[MusicAlbum]:
        """Executes the music album scraper pipeline."""
        music_dir = self.config.music_dir
        if not music_dir or not os.path.isdir(music_dir):
            raise FileNotFoundError(
                f"Music directory not configured or not found: '{music_dir}'. "
                f"Set MUSIC_DIR in .env or pass --music-dir."
            )

        entries = sorted(os.listdir(music_dir))
        album_dirs = [d for d in entries if os.path.isdir(os.path.join(music_dir, d))]

        eff_limit = limit if limit is not None else self.config.limit
        if eff_limit > 0:
            album_dirs = album_dirs[:eff_limit]

        print(f"[Music] Found {len(album_dirs)} album directories in {music_dir}")
        seed_data = self.load_seed_csv(self.config.seed_csv)
        print(f"[Music] Loaded {len(seed_data)} seed records from {self.config.seed_csv}")

        # Step 1: Parse metadata
        parsed_albums = [
            self.parse_directory(d, os.path.join(music_dir, d)) for d in album_dirs
        ]

        # Step 2: Concurrent enrichment
        print(f"[Music] Enriching {len(parsed_albums)} albums with {self.config.workers} workers...")
        enriched: List[MusicAlbum] = []

        with ThreadPoolExecutor(max_workers=self.config.workers) as executor:
            future_to_album = {
                executor.submit(self._enrich_single_album, alb, seed_data): alb for alb in parsed_albums
            }
            completed = 0
            for future in as_completed(future_to_album):
                completed += 1
                result = future.result()
                enriched.append(result)
                if is_progress(completed, len(parsed_albums), self.config.progress_every):
                    print(f"[Music] Progress: {completed}/{len(parsed_albums)} albums processed")

        # Step 3: Sort albums preserving seed rankings
        def sort_key(item: MusicAlbum):
            prev = item.seed_rank
            return (
                prev if prev is not None else 999999,
                item.artists.lower(),
                item.year,
                item.album.lower(),
            )

        enriched.sort(key=sort_key)

        # Step 4: Deduplicate streaming URLs and filter out unfindable albums
        seen_spotify = set()
        seen_tidal = set()
        kept: List[MusicAlbum] = []
        dropped_count = 0

        for item in enriched:
            # Dedup Spotify URL
            if item.spotify_url:
                if item.spotify_url in seen_spotify:
                    item.spotify_url = ""
                else:
                    seen_spotify.add(item.spotify_url)

            # Dedup Tidal URL
            if item.tidal_url:
                if item.tidal_url in seen_tidal:
                    item.tidal_url = ""
                else:
                    seen_tidal.add(item.tidal_url)

            # Drop albums not on popular streaming services
            if not item.spotify_url and not item.tidal_url:
                dropped_count += 1
                continue

            # Drop albums with catbox or invalid covers
            if "catbox.moe" in item.cover:
                dropped_count += 1
                continue

            if not item.cover or not item.cover.startswith("http"):
                item.cover = self.config.fallback_cover_music

            kept.append(item)

        print(f"[Music] Dropped {dropped_count} albums not available on popular streaming services or without valid CDN cover.")

        # Step 5: Assign continuous 1..N ranks
        for idx, item in enumerate(kept, start=1):
            item.rank = idx

        # Step 6: Export CSV
        out_csv = self.config.export_music_csv
        os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=MusicAlbum.CSV_FIELDS)
            writer.writeheader()
            for item in kept:
                writer.writerow(item.to_csv_dict())

        print(f"[Music] Successfully wrote {len(kept)} albums to {out_csv}!")
        return kept
