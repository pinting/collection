import difflib
import re
from typing import List, Optional, Tuple

from src.utils import fold_string, to_ascii

CLUTTER_PATTERN = re.compile(
    r"\s*[\(\[](?:remaster|deluxe|expanded|anniversary|version|edition|mono|stereo|bonus|live|collector|digital|soundtrack|score|\d{4})[^\)\]]*[\)\]]",
    re.IGNORECASE,
)

ROMAN_NUMS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
VOL_RE = re.compile(r"\b(?:vol(?:ume)?\.?\s*([0-9ivx]+)|part\s*([0-9ivx]+)|#\s*([0-9]+)|(ii|iii|iv|vi|vii|viii|ix|x|\d+))\b", re.IGNORECASE)


def extract_vols(text: str) -> set:
    """Extracts normalized sequence or volume numbers from text."""
    res = set()
    for m in VOL_RE.finditer(text):
        val = next(g for g in m.groups() if g is not None).lower()
        res.add(ROMAN_NUMS.get(val, val))
    return res

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

    # If sequence or volume numbers differ (e.g. Vol 1 vs Vol 2, Trabant vs Trabant II), do not match
    vols_a = extract_vols(fa)
    vols_b = extract_vols(fb)
    if vols_a != vols_b:
        return 0.0

    # If one title contains the other exactly and covers >= 85% of length
    if f" {fa} " in f" {fb} " or f" {fb} " in f" {fa} ":
        shorter, longer = (fa, fb) if len(fa) < len(fb) else (fb, fa)
        if len(shorter) / len(longer) >= 0.85:
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


def _single_person_matches(dir_a: str, dir_b: str) -> bool:
    fa = fold_string(dir_a)
    fb = fold_string(dir_b)
    if not fa or not fb:
        return False
    if fa == fb:
        return True

    fa_clean = re.sub(r"^the\s+", "", fa)
    fb_clean = re.sub(r"^the\s+", "", fb)
    if fa_clean == fb_clean:
        return True

    parts_a = [p for p in fa_clean.split() if len(p) >= 2]
    parts_b = [p for p in fb_clean.split() if len(p) >= 2]
    set_a, set_b = set(parts_a), set(parts_b)

    # Permutation (e.g. Bacsó Péter vs Péter Bacsó, Hu Bo vs Bo Hu)
    if set_a == set_b:
        return True

    # Subset when both names have 2+ parts (e.g. Francis Ford Coppola vs Francis Coppola)
    if len(set_a) >= 2 and len(set_b) >= 2:
        if set_a.issubset(set_b) or set_b.issubset(set_a):
            return True
        stems_a = {p.rstrip("s") for p in parts_a}
        stems_b = {p.rstrip("s") for p in parts_b}
        if stems_a == stems_b or (len(stems_a) >= 2 and stems_a.issubset(stems_b)):
            return True

    # Single-word name or collective (e.g. "The Wachowskis" -> parts_a = ["wachowskis"])
    if len(parts_a) == 1:
        stem_a = parts_a[0].rstrip("s")
        stems_b = {p.rstrip("s") for p in parts_b}
        if stem_a in stems_b or any(stem_a in p for p in stems_b if len(stem_a) >= 5):
            return True

    if len(parts_b) == 1:
        stem_b = parts_b[0].rstrip("s")
        stems_a = {p.rstrip("s") for p in parts_a}
        if stem_b in stems_a or any(stem_b in p for p in stems_a if len(stem_b) >= 5):
            return True

    return False


def director_matches(dir_a: str, dir_b: str) -> bool:
    """Checks whether two director names match, handling Western vs Eastern name ordering."""
    if not dir_a or not dir_b:
        return False
    people_a = [p.strip() for p in re.split(r"[,/;&]|\band\b", dir_a) if p.strip()]
    people_b = [p.strip() for p in re.split(r"[,/;&]|\band\b", dir_b) if p.strip()]
    return any(_single_person_matches(pa, pb) for pa in people_a for pb in people_b)


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
        slugs.append(p_slug)
        slugs.append(f"{s_clean}_{p_slug}")
        slugs.append(f"{p_slug}_{year}")
        slugs.append(f"{s_clean}_{p_slug}_{year}")

    # Clean title without year first, then with year
    if s_full and len(s_full) > 1:
        slugs.append(s_full)
        slugs.append(f"{s_full}_{year}")

    # Clean title (without parens) with and without year
    if s_clean and len(s_clean) > 1 and s_clean != s_full:
        slugs.append(s_clean)
        slugs.append(f"{s_clean}_{year}")

    # Parenthetical candidates (e.g. English title or subtitle)
    for par in parens:
        sp = to_slug(par)
        if len(sp) > 1:
            slugs.append(sp)
            slugs.append(f"{sp}_{year}")

    # Subtitles split by dash or colon
    parts = [p.strip() for p in re.split(r"[-:]", clean) if len(p.strip()) > 2]
    for p in parts:
        sp = to_slug(p)
        if len(sp) > 2:
            slugs.append(sp)
            slugs.append(f"{sp}_{year}")

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
