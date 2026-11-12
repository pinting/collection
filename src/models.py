from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AudioTags:
    """Audio metadata tags extracted from local media files."""

    artist: str = ""
    album: str = ""
    year: str = ""
    genre: str = ""


@dataclass
class MusicAlbum:
    """Music album showcase record."""

    rank: int = 0
    artists: str = ""
    album: str = ""
    year: str = ""
    cover: str = ""
    spotify_url: str = ""
    tidal_url: str = ""
    genres: str = ""
    folder: str = ""
    path: str = ""
    seed_rank: Optional[int] = None

    CSV_FIELDS = ("rank", "artists", "album", "year", "cover", "spotify_url", "tidal_url", "genres")

    def to_csv_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "artists": self.artists,
            "album": self.album,
            "year": self.year,
            "cover": self.cover,
            "spotify_url": self.spotify_url,
            "tidal_url": self.tidal_url,
            "genres": self.genres,
        }

    @classmethod
    def from_seed_dict(cls, row: Dict[str, Any]) -> "MusicAlbum":
        try:
            seed_rank = int(row.get("rank", 0))
        except (ValueError, TypeError):
            seed_rank = None

        return cls(
            rank=seed_rank or 0,
            artists=row.get("artists", "").strip(),
            album=row.get("album", "").strip(),
            year=row.get("year", "").strip()[:4],
            cover=row.get("cover", "").strip(),
            spotify_url=row.get("spotify_url", "").strip(),
            tidal_url=row.get("tidal_url", "").strip(),
            genres=row.get("genres", "").strip(),
            seed_rank=seed_rank,
        )


@dataclass
class MovieEntry:
    """Movie showcase record (genres omitted)."""

    rank: int = 0
    director: str = ""
    title: str = ""
    year: str = ""
    cover: str = ""
    imdb_url: str = ""
    letterboxd_url: str = ""
    raw: str = ""
    original_index: int = 0

    CSV_FIELDS = ("rank", "director", "title", "year", "cover", "imdb_url", "letterboxd_url")

    def to_csv_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "director": self.director,
            "title": self.title,
            "year": self.year,
            "cover": self.cover,
            "imdb_url": self.imdb_url,
            "letterboxd_url": self.letterboxd_url,
        }


@dataclass
class DiscogsRelease:
    """Discogs release search candidate."""

    cover: str = ""
    genres: List[str] = field(default_factory=list)


@dataclass
class ImdbMovie:
    """IMDb movie search candidate."""

    id: str = ""
    title: str = ""
    year: Optional[int] = None
    image_url: str = ""
    credits: str = ""
