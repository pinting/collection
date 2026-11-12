import os
import re
import sys
import unicodedata
from typing import List, Optional


def require_env(*names: str) -> List[str]:
    """Ensures specified environment variables are configured, or halts with error."""
    values = [os.getenv(name) for name in names]
    missing = [name for name, value in zip(names, values) if not value]

    if missing:
        sys.exit(f"Error: {', '.join(missing)} must be configured in .env")

    return values


def get_env(name: str, default: str = "") -> str:
    """Gets an environment variable with a fallback default."""
    return os.getenv(name, default)


def is_progress(index: int, total: int, every: int) -> bool:
    """Checks whether the current index matches a progress reporting interval."""
    if every <= 0 or total <= 0:
        return index == total
    return index % every == 0 or index == total


def merge_distinct(existing: List[str], new: List[str]) -> List[str]:
    """Appends items from new missing from existing, comparing case-insensitively."""
    result = list(existing)
    seen = {item.strip().lower() for item in existing if item and item.strip()}

    for item in new:
        cleaned = item.strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            result.append(cleaned)

    return result


def to_ascii(text: str) -> str:
    """Normalizes string by stripping diacritics using Unicode NFKD decomposition."""
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def fold_string(text: str) -> str:
    """Normalizes a string for comparison: removes diacritics, punctuation, lowercases, trims."""
    if not text:
        return ""
    decomposed = to_ascii(text)
    cleaned = re.sub(r"[^\w\s]", "", decomposed.lower())
    return re.sub(r"\s+", " ", cleaned).strip()
