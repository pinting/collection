import difflib
import re
from typing import Optional

from src.api.base import APIClient
from src.config import Config
from src.matching import director_matches, make_slugs
from src.models import ImdbMovie
from src.utils import fold_string


class ImdbClient(APIClient):
    """Client for IMDb suggestion API with high-confidence candidate verification."""

    def __init__(self, config: Config):
        super().__init__(config, config.imdb_delay)

    def _headers(self) -> dict:
        return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FavoritesApp/1.0"}

    def find_movie(self, title: str, year: int, director: str = "") -> Optional[ImdbMovie]:
        """Queries IMDb suggestion API and returns candidate if high-confidence match is verified."""
        slugs = make_slugs(title, year, director)
        ft = fold_string(title)
        clean_t = fold_string(re.sub(r"[\(\[].*?[\)\]]", "", title))
        parens = [fold_string(m.group(1)) for m in re.finditer(r"[\(\[](.*?)[\)\]]", title)]

        for slug in slugs:
            if not slug:
                continue
            first_char = slug[0]
            url = f"{self.config.imdb_suggestion_url}/{first_char}/{slug}.json"
            try:
                data = self._get(url)
                items = data.get("d", [])

                for item in items:
                    qid = item.get("qid")
                    q = item.get("q")
                    if qid not in ("movie", "short", "tvMovie") and q not in ("feature", "movie", "TV movie", "short"):
                        continue

                    cand_year = item.get("y")
                    if not cand_year or abs(cand_year - year) > self.config.imdb_year_tolerance:
                        continue

                    cand_img = (item.get("i") or {}).get("imageUrl", "")
                    if not cand_img or not cand_img.startswith("https://"):
                        continue

                    imdb_t = item.get("l", "")
                    fit = fold_string(imdb_t)
                    credits = item.get("s", "")

                    sim = difflib.SequenceMatcher(None, ft, fit).ratio()
                    sim_clean = difflib.SequenceMatcher(None, clean_t, fit).ratio()
                    sim_paren = max([difflib.SequenceMatcher(None, p, fit).ratio() for p in parens] or [0])

                    contain = (
                        (ft and ft in fit)
                        or (fit and fit in ft)
                        or (clean_t and len(clean_t) > 2 and (clean_t in fit or fit in clean_t))
                        or any(p and len(p) > 2 and (p in fit or fit in p) for p in parens)
                    )

                    dir_match = director_matches(director, credits) if director else False

                    # Verified high-confidence match
                    if max(sim, sim_clean, sim_paren) >= 0.55 or contain or dir_match:
                        return ImdbMovie(
                            id=item.get("id", ""),
                            title=imdb_t,
                            year=cand_year,
                            image_url=cand_img,
                            credits=credits,
                        )
            except Exception:
                pass

        return None
