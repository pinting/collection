import re
from typing import List, Set

CANONICAL_MUSIC_GENRES = {
    "rock": "Rock",
    "punk": "Punk",
    "post-punk": "Post-Punk",
    "post punk": "Post-Punk",
    "new wave": "New-Wave",
    "new-wave": "New-Wave",
    "electronic": "Electronic",
    "electronica": "Electronic",
    "pop": "Pop",
    "hip-hop": "Hip-Hop",
    "hip hop": "Hip-Hop",
    "rap": "Hip-Hop",
    "jazz": "Jazz",
    "soul": "Soul",
    "funk": "Funk",
    "folk": "Folk",
    "experimental": "Experimental",
    "psychedelic": "Psychedelic",
    "psych": "Psychedelic",
    "minimal": "Minimal",
    "minimalism": "Minimal",
    "house": "House",
    "techno": "Techno",
    "fusion": "Fusion",
    "jazz-fusion": "Fusion",
    "industrial": "Industrial",
    "classical": "Classical",
    "bossa nova": "Bossa Nova",
    "metal": "Metal",
    "heavy metal": "Metal",
    "ambient": "Ambient",
    "reggae": "Reggae",
    "dub": "Dub",
    "disco": "Disco",
    "blues": "Blues",
    "hardcore": "Hardcore",
    "indie": "Indie",
    "indie rock": "Rock",
    "krautrock": "Krautrock",
    "alternative": "Alternative",
    "soundtrack": "Soundtrack",
}

CANONICAL_MOVIE_GENRES = {
    "action": "Action",
    "adventure": "Adventure",
    "animation": "Animation",
    "biography": "Biography",
    "comedy": "Comedy",
    "crime": "Crime",
    "documentary": "Documentary",
    "drama": "Drama",
    "family": "Family",
    "fantasy": "Fantasy",
    "film-noir": "Film-Noir",
    "film noir": "Film-Noir",
    "history": "History",
    "horror": "Horror",
    "music": "Music",
    "musical": "Musical",
    "mystery": "Mystery",
    "romance": "Romance",
    "romantic": "Romance",
    "sci-fi": "Sci-Fi",
    "science fiction": "Sci-Fi",
    "short": "Short",
    "sport": "Sport",
    "thriller": "Thriller",
    "war": "War",
    "western": "Western",
}


def _split_and_clean_tokens(raw_genres: List[str]) -> List[str]:
    tokens: List[str] = []
    for g in raw_genres:
        if not g:
            continue
        parts = re.split(r"[;/|,]", g)
        for p in parts:
            p = p.strip()
            if p:
                tokens.append(p)
    return tokens


def normalize_music_genres(raw_genres: List[str]) -> str:
    """Standardizes music genre strings into a pipe-delimited list of canonical genres."""
    tokens = _split_and_clean_tokens(raw_genres)
    normalized: List[str] = []
    seen: Set[str] = set()

    for token in tokens:
        low = token.lower()
        canon = CANONICAL_MUSIC_GENRES.get(low) or token.strip().title()
        if canon.lower() not in seen:
            seen.add(canon.lower())
            normalized.append(canon)

    return "|".join(normalized)


def normalize_movie_genres(raw_genres: List[str]) -> str:
    """Standardizes movie genre strings into a pipe-delimited list of canonical genres."""
    tokens = _split_and_clean_tokens(raw_genres)
    normalized: List[str] = []
    seen: Set[str] = set()

    for token in tokens:
        low = token.lower()
        canon = CANONICAL_MOVIE_GENRES.get(low) or token.strip().title()
        if canon.lower() not in seen:
            seen.add(canon.lower())
            normalized.append(canon)

    return "|".join(normalized)
