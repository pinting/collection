import argparse
import os
from dataclasses import dataclass, field, fields
from typing import Optional, Tuple

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")
load_dotenv(ENV_FILE)

STAGES = ("music", "movies")
STAGE_CHOICES = STAGES + ("all",)


def option(default, help: str, **kwargs):
    return field(default=default, metadata={"help": help, **kwargs})


@dataclass(frozen=True)
class Config:
    """Application configuration with CLI flag generation and environment variable support."""

    # Execution
    stages: tuple = option(STAGES, "Stages to run (music, movies, all)", choices=STAGE_CHOICES)
    limit: int = option(0, "Max items to process per stage (0 means no limit)")
    workers: int = option(4, "Concurrent worker threads")
    progress_every: int = option(25, "Print progress after every N processed items")

    # Library Paths (configured via .env or CLI)
    music_dir: str = option("", "Path to music albums directory (MUSIC_DIR in .env)")
    movies_dir: str = option("", "Path to movies directory (MOVIES_DIR in .env)")
    movies_txt: str = option("", "Path to Movies.txt file (MOVIES_TXT in .env)")
    export_music_csv: str = option(os.path.join(ROOT, "docs", "albums.csv"), "Export CSV for music albums")
    export_movies_csv: str = option(os.path.join(ROOT, "docs", "movies.csv"), "Export CSV for movies")
    seed_csv: str = option(os.path.join(ROOT, "docs", "albums.csv"), "Seed CSV to preserve rankings & Spotify URLs")
    db_path: str = option(os.path.join(ROOT, "..", "musicd", "database.db"), "Path to musicd database.db for metadata reference")
    env_file: str = option(ENV_FILE, "Path to .env file")

    # Network & Retries
    retries: int = option(3, "Attempts per API request")
    retry_backoff: float = option(1.5, "Linear backoff step between failed attempts, in seconds")
    retry_after: int = option(5, "Wait after a 429 without a Retry-After header, in seconds")
    timeout: float = option(10.0, "Request timeout in seconds")
    token_margin: int = option(60, "Refresh OAuth tokens this many seconds before they expire")

    # Tidal API
    tidal_auth_url: str = option("https://auth.tidal.com/v1/oauth2/token", "Tidal token endpoint")
    tidal_base_url: str = option("https://openapi.tidal.com/v2", "Tidal OpenAPI v2 base URL")
    tidal_country: str = option("HU", "Primary Tidal catalog region (TIDAL_COUNTRY_CODE in .env)")
    tidal_delay: float = option(0.2, "Delay before each Tidal request, in seconds")

    # Discogs API
    discogs_base_url: str = option("https://api.discogs.com", "Discogs API base URL")
    discogs_delay: float = option(0.5, "Delay before each Discogs request, in seconds")
    discogs_user_agent: str = option("FavoritesScraper/1.0", "Discogs User-Agent")
    discogs_per_page: int = option(5, "Results per Discogs search")
    discogs_min_title_similarity: float = option(0.65, "Minimum title similarity of a searched release")

    # Deezer API
    deezer_base_url: str = option("https://api.deezer.com", "Deezer API base URL")
    deezer_delay: float = option(0.1, "Delay before each Deezer request, in seconds")

    # Apple Music / iTunes Search API
    itunes_base_url: str = option("https://itunes.apple.com", "iTunes Search API base URL")
    itunes_delay: float = option(0.1, "Delay before each iTunes request, in seconds")

    # Catbox CDN Upload
    catbox_url: str = option("https://catbox.moe/user/api.php", "Catbox upload endpoint")
    catbox_userhash: str = option("", "Optional Catbox userhash (CATBOX_USERHASH in .env)")

    # IMDb Suggestion API
    imdb_suggestion_url: str = option("https://v3.sg.media-imdb.com/suggestion", "IMDb suggestion API base URL")
    imdb_delay: float = option(0.1, "Delay before each IMDb request, in seconds")
    imdb_year_tolerance: int = option(1, "Release year tolerance for IMDb matching (+- years)")

    # Cinemeta API
    cinemeta_base_url: str = option("https://v3-cinemeta.strem.io/meta/movie", "Cinemeta API base URL")
    cinemeta_delay: float = option(0.1, "Delay before each Cinemeta request, in seconds")

    # Fallbacks & Placeholders
    fallback_cover_music: str = option(
        "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=600&q=80",
        "Fallback music cover URL",
    )
    fallback_cover_movie: str = option(
        "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=600&q=80",
        "Fallback movie poster URL",
    )
    metahub_poster_url: str = option("https://images.metahub.space/poster/medium", "Metahub poster base URL")


def parse_args(argv=None) -> Config:
    """Parses command-line arguments and loads configuration with .env defaults."""
    # Pre-parse env argument if provided
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env", default=ENV_FILE, help="Path to .env file")
    pre_args, _ = pre_parser.parse_known_args(argv)

    if os.path.isfile(pre_args.env):
        load_dotenv(pre_args.env)
    elif os.path.isfile(ENV_FILE):
        load_dotenv(ENV_FILE)

    parser = argparse.ArgumentParser(
        prog="python -m src",
        description="Favorites media library scraper and showcase pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False,
    )

    for f in fields(Config):
        kwargs = {"default": f.default, "help": f.metadata["help"]}

        if "choices" in f.metadata:
            kwargs["choices"] = f.metadata["choices"]

        if isinstance(f.default, tuple):
            kwargs["nargs"] = "+"
        else:
            kwargs["type"] = type(f.default)

        parser.add_argument(f"--{f.name.replace('_', '-')}", **kwargs)

    # Convenience and backward-compatibility aliases
    parser.add_argument("--music", action="store_true", help="Scrape music albums only")
    parser.add_argument("--movies", action="store_true", help="Scrape movies only")
    parser.add_argument("--all", action="store_true", help="Scrape both music albums and movies")
    parser.add_argument("--output", default=None, help="Output CSV path (overrides export CSV for the stage)")
    parser.add_argument("--env", default=pre_args.env, help="Path to .env file")

    # Set defaults from environment variables
    env_music_dir = os.getenv("MUSIC_DIR", "")
    env_movies_dir = os.getenv("MOVIES_DIR", "")
    env_movies_txt = os.getenv("MOVIES_TXT", "")
    env_tidal_country = os.getenv("TIDAL_COUNTRY_CODE", "HU")
    env_catbox_userhash = os.getenv("CATBOX_USERHASH", "")

    parser.set_defaults(
        music_dir=env_music_dir,
        movies_dir=env_movies_dir,
        movies_txt=env_movies_txt,
        tidal_country=env_tidal_country,
        catbox_userhash=env_catbox_userhash,
    )

    args = parser.parse_args(argv)
    args_dict = vars(args)

    # Resolve stages from shortcuts
    if args.movies and not args.music and not args.all:
        selected_stages = ("movies",)
    elif args.music and not args.movies and not args.all:
        selected_stages = ("music",)
    elif args.all:
        selected_stages = ("music", "movies")
    else:
        raw_stages = args.stages
        if isinstance(raw_stages, str):
            raw_stages = (raw_stages,)
        stages_list = []
        for s in raw_stages:
            if s == "all":
                for st in ("music", "movies"):
                    if st not in stages_list:
                        stages_list.append(st)
            elif s in STAGES and s not in stages_list:
                stages_list.append(s)
        selected_stages = tuple(stages_list) if stages_list else STAGES

    args_dict["stages"] = selected_stages

    # Handle output redirect alias
    if args.output:
        if "movies" in selected_stages and "music" not in selected_stages:
            args_dict["export_movies_csv"] = args.output
        elif "music" in selected_stages and "movies" not in selected_stages:
            args_dict["export_music_csv"] = args.output

    # Resolve default movies_txt if movies_dir is given and movies_txt is empty
    if not args_dict.get("movies_txt") and args_dict.get("movies_dir"):
        candidate_txt = os.path.join(args_dict["movies_dir"], "Movies.txt")
        if os.path.isfile(candidate_txt):
            args_dict["movies_txt"] = candidate_txt

    # Clean up non-dataclass convenience flags
    for extra in ("music", "movies", "all", "output", "env"):
        args_dict.pop(extra, None)

    return Config(**args_dict)
