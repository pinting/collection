import csv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.api.cinemeta import CinemetaClient
from src.api.imdb import ImdbClient
from src.config import Config
from src.matching import director_matches, make_slugs, parse_movie_line
from src.models import MovieEntry
from src.utils import is_progress


class MoviesStage:
    """Stage for scanning movies, verifying online IMDb records/artwork, and exporting CSV."""

    def __init__(
        self,
        config: Config,
        imdb: Optional[ImdbClient] = None,
        cinemeta: Optional[CinemetaClient] = None,
    ):
        self.config = config
        self.imdb = imdb or ImdbClient(config)
        self.cinemeta = cinemeta or CinemetaClient(config)

    def get_movie_entries(self) -> List[Dict[str, Any]]:
        """Parses movie entries from Movies.txt or from the movies directory."""
        entries: List[Dict[str, Any]] = []

        movies_txt = self.config.movies_txt
        movies_dir = self.config.movies_dir

        if movies_txt and os.path.isfile(movies_txt):
            with open(movies_txt, "r", encoding="utf-8") as f:
                idx = 0
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parsed = parse_movie_line(line)
                    if parsed:
                        director, year, title = parsed
                        entries.append({
                            "director": director,
                            "year": year,
                            "title": title,
                            "raw": line,
                            "original_index": idx,
                        })
                        idx += 1
        elif movies_dir and os.path.isdir(movies_dir):
            idx = 0
            for d in sorted(os.listdir(movies_dir)):
                p = os.path.join(movies_dir, d)
                if not os.path.isdir(p):
                    continue
                parsed = parse_movie_line(d)
                if parsed:
                    director, year, title = parsed
                    entries.append({
                        "director": director,
                        "year": year,
                        "title": title,
                        "raw": d,
                        "original_index": idx,
                    })
                    idx += 1
        else:
            raise FileNotFoundError(
                f"Neither movies_txt ('{movies_txt}') nor movies_dir ('{movies_dir}') was found. "
                f"Configure MOVIES_DIR or MOVIES_TXT in .env or pass --movies-dir / --movies-txt."
            )

        return entries

    def _verify_online_record(
        self, director: str, year: int, title: str
    ) -> Optional[tuple[str, str]]:
        """Finds verified IMDb ID and cover poster URL. Returns (imdb_id, cover_url) or None."""
        # 1. Primary check via IMDb suggestion client
        match = self.imdb.find_movie(title, year, director)
        if match and match.image_url:
            return match.id, match.image_url

        # 2. Secondary check: for foreign films with translated titles, search by slugs and verify director via Cinemeta
        slugs = make_slugs(title, year, director)
        for slug in slugs:
            if not slug:
                continue
            first_char = slug[0]
            url = f"{self.config.imdb_suggestion_url}/{first_char}/{slug}.json"
            try:
                data = self.imdb._get(url)
                items = data.get("d", [])
                for item in items:
                    qid = item.get("qid")
                    q = item.get("q")
                    if qid not in ("movie", "short", "tvMovie") and q not in ("feature", "movie", "TV movie", "short"):
                        continue

                    cand_year = item.get("y")
                    if not cand_year or abs(cand_year - year) > self.config.imdb_year_tolerance:
                        continue

                    cand_id = item.get("id")
                    if not cand_id:
                        continue

                    # Verify director via Cinemeta
                    meta = self.cinemeta.fetch_meta(cand_id)
                    c_dirs = meta.get("director", [])
                    matched_dir = False
                    if isinstance(c_dirs, list):
                        matched_dir = any(director_matches(director, d) for d in c_dirs)
                    elif isinstance(c_dirs, str):
                        matched_dir = director_matches(director, c_dirs)

                    if matched_dir:
                        poster = (item.get("i") or {}).get("imageUrl") or meta.get("poster", "")
                        if poster and poster.startswith("https://"):
                            return cand_id, poster
            except Exception:
                pass

        return None

    def _enrich_single_movie(self, entry: Dict[str, Any]) -> Optional[MovieEntry]:
        director = entry["director"]
        year_str = entry["year"]
        year = int(year_str) if year_str.isdigit() else 0
        title = entry["title"]
        idx = entry.get("original_index", 0)

        if not year:
            return None

        verified = self._verify_online_record(director, year, title)
        if not verified:
            # Skip movie if not 100% confident
            print(f"[Movies] Skipping unverified record: {director} - {year} - {title}")
            return None

        imdb_id, cover_url = verified

        imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
        letterboxd_url = f"https://letterboxd.com/imdb/{imdb_id}/"

        return MovieEntry(
            rank=0,
            director=director,
            title=title,
            year=str(year),
            cover=cover_url,
            imdb_url=imdb_url,
            letterboxd_url=letterboxd_url,
            raw=entry.get("raw", ""),
            original_index=idx,
        )

    def run(self, limit: Optional[int] = None) -> List[MovieEntry]:
        """Executes the movie scraper pipeline, skipping unverified records."""
        entries = self.get_movie_entries()
        if not entries:
            raise RuntimeError("No movie entries found to process.")

        eff_limit = limit if limit is not None else self.config.limit
        if eff_limit > 0:
            entries = entries[:eff_limit]

        print(f"[Movies] Processing {len(entries)} movies with {self.config.workers} workers...")

        enriched: List[MovieEntry] = []
        with ThreadPoolExecutor(max_workers=self.config.workers) as executor:
            future_to_entry = {executor.submit(self._enrich_single_movie, e): e for e in entries}
            completed = 0
            for future in as_completed(future_to_entry):
                completed += 1
                result = future.result()
                if result is not None:
                    enriched.append(result)
                if is_progress(completed, len(entries), self.config.progress_every):
                    print(f"[Movies] Progress: {completed}/{len(entries)} movies processed")

        # Sort by original rank/index
        enriched.sort(key=lambda x: x.original_index)

        # Assign contiguous 1..N ranks
        for idx, item in enumerate(enriched, start=1):
            item.rank = idx

        # Export CSV (without genres)
        out_csv = self.config.export_movies_csv
        os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=MovieEntry.CSV_FIELDS)
            writer.writeheader()
            for item in enriched:
                writer.writerow(item.to_csv_dict())

        print(
            f"[Movies] Successfully verified and wrote {len(enriched)} movies "
            f"(skipped {len(entries) - len(enriched)}) to {out_csv}!"
        )
        return enriched
