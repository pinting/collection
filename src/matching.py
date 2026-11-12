import difflib
import re
from typing import List, Optional, Tuple

from src.utils import fold_string, to_ascii

CLUTTER_PATTERN = re.compile(
    r"\s*[\(\[](?:remaster|deluxe|expanded|anniversary|version|edition|mono|stereo|bonus|live|collector|\d{4})[^\)\]]*[\)\]]",
    re.IGNORECASE,
)

MOVIE_LINE_PATTERN = re.compile(r"^(.+?)\s*-\s*(\d{4})\s*-\s*(.+)$")
ALBUM_FOLDER_PATTERN = re.compile(r"^(.+?)\s+-\s+(\d{4})\s+-\s+(.+)$")

VA_NAMES = {"va", "various", "various artists", "v.a."}


def clean_title(title: str) -> str:
    """Strips common edition and clutter keywords from a title."""
    return CLUTTER_PATTERN.sub("", title).strip()


def title_similarity(a: str, b: str) -> float:
    """Calculates fuzzy similarity between two album or movie titles."""
    fa = fold_string(clean_title(a))
    fb = fold_string(clean_title(b))

    if not fa or not fb:
        return 0.0
    if fa == fb:
        return 1.0

    # If one title contains the other and covers >= 70% of the length
    if fa in fb or fb in fa:
        shorter, longer = (fa, fb) if len(fa) < len(fb) else (fb, fa)
        if len(shorter) / len(longer) >= 0.7:
            return 0.95

    return difflib.SequenceMatcher(None, fa, fb).ratio()


def artists_match(a: str, b: str) -> bool:
    """Checks whether two artist names or credits match."""
    fa = fold_string(a)
    fb = fold_string(b)

    if not fa or not fb:
        return False

    if fa in VA_NAMES and fb in VA_NAMES:
        return True

    if fa == fb or fa in fb or fb in fa:
        return True

    # Split compound credits: "Artist A & Artist B", "Artist A feat. Artist B", etc.
    set_a = {x.strip() for x in re.split(r"[,/&]|\band\b|\bwith\b|\bfeat\b|\bfeaturing\b|\bft\b", fa) if x.strip()}
    set_b = {x.strip() for x in re.split(r"[,/&]|\band\b|\bwith\b|\bfeat\b|\bfeaturing\b|\bft\b", fb) if x.strip()}

    return bool(set_a & set_b)


def director_matches(dir_a: str, dir_b: str) -> bool:
    """Checks whether two director names match, handling Western vs Eastern name ordering."""
    fa = fold_string(dir_a)
    fb = fold_string(dir_b)
    if not fa or not fb:
        return False
    if fa == fb or fa in fb or fb in fa:
        return True

    parts_a = {p for p in fa.split() if len(p) > 2}
    parts_b = {p for p in fb.split() if len(p) > 2}
    return bool(parts_a & parts_b)


def make_slugs(title: str, year: int, director: str = "") -> List[str]:
    """Generates candidate search slugs for IMDb suggestion API."""
    slugs: List[str] = []

    clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", title).strip()
    full_clean = re.sub(r"[\(\[\{\)\]\}]", " ", title).strip()

    def to_slug(text: str) -> str:
        s = re.sub(r"[^a-z0-9\s]", " ", to_ascii(text).lower())
        return re.sub(r"\s+", "_", s).strip("_")

    s_full = to_slug(full_clean)
    s_clean = to_slug(clean)
    parens = [m.group(1).strip() for m in re.finditer(r"[\(\[](.*?)[\)\]]", title)]

    # Short titles special handling (e.g. "K" or "K2" or "Moebius")
    if len(s_clean) <= 3 and parens:
        p_slug = to_slug(parens[0])
        slugs.append(f"{s_clean}_{p_slug}_{year}")
        slugs.append(f"{s_clean}_{p_slug}")
        slugs.append(f"{p_slug}_{year}")
        slugs.append(p_slug)

    # Full clean title with and without year
    if s_full and len(s_full) > 1:
        slugs.append(f"{s_full}_{year}")
        slugs.append(s_full)

    # Clean title (without parens) with and without year
    if s_clean and len(s_clean) > 1 and s_clean != s_full:
        slugs.append(f"{s_clean}_{year}")
        slugs.append(s_clean)

    # Parenthetical candidates (e.g. English title or subtitle)
    for par in parens:
        sp = to_slug(par)
        if len(sp) > 1:
            slugs.append(f"{sp}_{year}")
            slugs.append(sp)

    # Subtitles split by dash or colon
    parts = [p.strip() for p in re.split(r"[-:]", clean) if len(p.strip()) > 2]
    for p in parts:
        sp = to_slug(p)
        if len(sp) > 2:
            slugs.append(f"{sp}_{year}")
            slugs.append(sp)

    if len(s_clean) <= 3 and director:
        dir_slug = to_slug(director)
        slugs.append(f"{dir_slug}_{s_clean}")

    return list(dict.fromkeys([s for s in slugs if s]))


def parse_movie_line(line: str) -> Optional[Tuple[str, str, str]]:
    """Extracts (director, year, title) from a movie entry line or directory name."""
    m = MOVIE_LINE_PATTERN.match(line.strip())
    if m:
        director, year_str, title = m.groups()
        return director.strip(), year_str.strip()[:4], title.strip()
    return None


def parse_album_folder(dir_name: str) -> Tuple[str, str, str]:
    """Extracts (artist, year, album) from an album folder name."""
    m = ALBUM_FOLDER_PATTERN.match(dir_name)
    if m:
        artist, year, album = m.groups()
        return artist.strip(), year.strip(), album.strip()

    parts = dir_name.split(" - ")
    if len(parts) >= 3:
        artist = parts[0]
        year = parts[1] if parts[1].isdigit() and len(parts[1]) == 4 else ""
        album = " - ".join(parts[2:])
        return artist.strip(), year.strip(), album.strip()
    elif len(parts) == 2:
        return parts[0].strip(), "", parts[1].strip()

    return "", "", dir_name.strip()
