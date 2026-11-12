#!/usr/bin/env python3
"""
Media library scraper for the Favorites web showcase.

Scrapes both music albums and movies, enriches metadata and artwork,
and exports datasets to docs/albums.csv and docs/movies.csv.
"""

from src.__main__ import main
from src.stages import AlbumScraper, MovieScraper, MoviesStage, MusicStage

__all__ = ["main", "MusicStage", "MoviesStage", "AlbumScraper", "MovieScraper"]

if __name__ == "__main__":
    main()
