import csv
import os
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
        """Finds best matching row in seed data."""
        fa = fold_string(artist)
        fb = fold_string(album)
        direct_key = f"{fa}___{fb}"
        if direct_key in seed_data:
            return seed_data[direct_key]

        clean_alb = fold_string(clean_title(album))
        for key, row in seed_data.items():
            seed_art, _, seed_alb = key.partition("___")
            if (artists_match(artist, row.get("artists", "")) or artists_match(fa, seed_art)) and (
                title_similarity(clean_alb, seed_alb) >= 0.70 or title_similarity(fb, seed_alb) >= 0.70
            ):
                return row
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

        seed = self.match_seed_row(artist, album, seed_data)
        seed_rank: Optional[int] = None
        spotify_url = ""
        tidal_url = ""
        existing_cover = ""
        genre_list: List[str] = []

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

        # Query Tidal for album link if missing
        if not tidal_url and self.tidal.is_configured():
            tidal_res = self.tidal.search_album(artist, album)
            if tidal_res:
                _, tidal_url = tidal_res

        # Query Discogs for genre tags if needed
        if not genre_list and self.discogs.is_configured():
            discogs_data = self.discogs.search(artist, album)
            if discogs_data.genres:
                genre_list.extend(discogs_data.genres)

        # Resolve remote CDN cover URL (never returns local file path)
        cover_url = self.cover_resolver.resolve(artist, album, path, existing_cover)
        if not cover_url.startswith("http"):
            cover_url = self.config.fallback_cover_music

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

        # Step 4: Assign continuous 1..N ranks
        for idx, item in enumerate(enriched, start=1):
            item.rank = idx

        # Step 5: Export CSV
        out_csv = self.config.export_music_csv
        os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=MusicAlbum.CSV_FIELDS)
            writer.writeheader()
            for item in enriched:
                writer.writerow(item.to_csv_dict())

        print(f"[Music] Successfully wrote {len(enriched)} albums to {out_csv}!")
        return enriched
