# Music Favorites

A personal music library showcase hosted on GitHub Pages.

The website at `docs/` displays favorite albums with high-resolution artwork, genres, and links to streaming platforms (Spotify and Tidal).

## How It Works

The library is built by scraping the local music collection in `/home/pinting/Music/Albums`. Metadata is extracted from directory naming patterns and embedded audio tags (FLAC Vorbis comments, ID3, MP4), enriched with external streaming links and high-resolution CDN artwork, and exported to `docs/albums.csv`.

> **Note on Artwork:** All album covers are hosted on remote CDNs (Deezer, Apple Music, Discogs, Spotify, or Catbox). Local album images are not stored in the repository to maintain high performance and GitHub Pages compatibility.

## Setup

Install dependencies with `uv` or `pip`:

```bash
uv pip install -e .
```

Copy `.env.template` to `.env` and fill in API credentials:

```bash
cp .env.template .env
```

Available API configurations:
- `TIDAL_CLIENT_ID` / `TIDAL_CLIENT_SECRET`: Tidal OpenAPI access for matching Tidal albums
- `TIDAL_COUNTRY_CODE`: Catalog region (default: `HU`)
- `DISCOGS_API_KEY`: Discogs API access for genres, styles, and release artwork
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`: Spotify Web API credentials

## Running the Scraper

Build or update `docs/albums.csv`:

```bash
python scraper.py
```

### Options

- `--music-dir`: Path to albums directory (default: `/home/pinting/Music/Albums`)
- `--output`: Destination CSV path (default: `docs/albums.csv`)
- `--seed-csv`: Seed CSV used to preserve curated rankings and existing Spotify links
- `--workers`: Number of concurrent requests (default: `4`)
- `--limit`: Limit number of albums to process (default: `0` for all)

## Previewing Locally

Start a local HTTP server in the `docs` directory:

```bash
python -m http.server --directory docs 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.
