# Favorites: Music & Movies

A personal media showcase hosted on GitHub Pages displaying favorite music albums and movies on virtual wooden shelves.

The website at `docs/` features responsive grids, genre navigation filters, and direct links to streaming platforms and databases (Spotify, Tidal, IMDb, Letterboxd).

- **Music**: displaying album sleeves (1:1 ratio) with Spotify & Tidal links.
- **Films**: displaying movie posters (2:3 ratio) with IMDb & Letterboxd links.

## How It Works

1. **Music Collection**:
   - Source: Configured via `MUSIC_DIR` in `.env` or `--music-dir`
   - Metadata extracted from folder naming and embedded audio tags (FLAC Vorbis, ID3, MP4).
   - Enriched via Tidal OpenAPI and Discogs API.
   - Remote CDN artwork fetched from Deezer, Apple Music, Discogs, Spotify, or Catbox.
   - Preserves curated rankings and Spotify URLs from `docs/albums.csv`.
   - Exported to `docs/albums.csv`.

2. **Movie Collection**:
   - Source: Configured via `MOVIES_DIR` / `MOVIES_TXT` in `.env` or `--movies-dir` / `--movies-txt`
   - Metadata and high-resolution posters fetched via IMDb Suggestion and Cinemeta APIs.
   - Enriched with IMDb and Letterboxd direct links.
   - Remote CDN poster artwork hosted on Amazon CloudFront and Metahub.
   - Exported to `docs/movies.csv`.

> **Note on Artwork:** All covers and posters are hosted on remote CDNs. Local image files are not stored in the repository to maintain high performance and GitHub Pages compatibility.

## Architecture

Following the design principles of `musicd`, the pipeline is split into modular components:

```
src/
├── __init__.py
├── __main__.py          # Pipeline entrypoint (python -m src)
├── config.py            # Dataclass-driven CLI configuration & .env loader
├── utils.py             # Environment, string folding, progress helpers
├── matching.py          # Fuzzy matching, clutter stripping, slug generators
├── models.py            # Domain dataclasses (MusicAlbum, MovieEntry, etc.)
├── genres.py            # Canonical music & movie genre taxonomies
├── audio.py             # Audio tag reader (mutagen + pure Python FLAC Vorbis)
├── api/
│   ├── base.py          # APIClient (retries, backoff, 429) & OAuthClient
│   ├── tidal.py         # Tidal OpenAPI v2 client
│   ├── discogs.py       # Discogs database search client
│   ├── imdb.py          # IMDb suggestion search client
│   ├── cinemeta.py      # Cinemeta metadata client
│   └── cover.py         # CDN cover resolver (Deezer, iTunes, Discogs, Catbox)
└── stages/
    ├── music.py         # Music album ingestion & enrichment stage
    └── movies.py        # Movie catalog ingestion & enrichment stage
```

## Setup

Install dependencies with `uv` or `pip`:

```bash
uv pip install -e .
```

Copy `.env.template` to `.env` and fill in media paths and API credentials:

```bash
cp .env.template .env
```

Example `.env`:

```env
# Media Library Paths
MUSIC_DIR=/home/user/Music/Albums
MOVIES_DIR=/home/user/repos/movies
MOVIES_TXT=/home/user/repos/movies/Movies.txt

# Spotify API
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=

# Tidal API
TIDAL_CLIENT_ID=
TIDAL_CLIENT_SECRET=
TIDAL_COUNTRY_CODE=HU

# Discogs API
DISCOGS_API_KEY=
```

## Running the Scraper

```bash
# Scrape both music and movies (default)
python scraper.py
# or
favorites
# or
python -m src

# Scrape only music albums
python scraper.py --music
# or
favorites --music

# Scrape only movies
python scraper.py --movies
# or
favorites --movies

# Limit items for dry-run testing
python scraper.py --limit 5
```

## Previewing Locally

Start a local HTTP server in the `docs` directory:

```bash
python -m http.server --directory docs 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser:
- [http://localhost:8000/#/music](http://localhost:8000/#/music) for music albums
- [http://localhost:8000/#/films](http://localhost:8000/#/films) or [http://localhost:8000/movies.html](http://localhost:8000/movies.html) for films
