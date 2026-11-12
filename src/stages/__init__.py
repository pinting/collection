"""Pipeline stages for scraping music albums and movies."""

from src.stages.movies import MoviesStage
from src.stages.music import MusicStage

AlbumScraper = MusicStage
MovieScraper = MoviesStage

__all__ = ["MusicStage", "MoviesStage", "AlbumScraper", "MovieScraper"]
