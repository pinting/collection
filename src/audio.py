import os
from typing import Optional

try:
    import mutagen
except ImportError:
    mutagen = None

from src.models import AudioTags

AUDIO_EXTENSIONS = (".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav")


def read_audio_tags(folder_path: str) -> AudioTags:
    """Reads embedded artist, album, date, and genre tags from audio files in the folder."""
    tags = AudioTags()
    if not os.path.isdir(folder_path):
        return tags

    audio_file: Optional[str] = None
    for root, _, files in os.walk(folder_path):
        for f in sorted(files):
            if f.lower().endswith(AUDIO_EXTENSIONS):
                audio_file = os.path.join(root, f)
                break
        if audio_file:
            break

    if not audio_file:
        return tags

    # Try mutagen first
    if mutagen is not None:
        try:
            m = mutagen.File(audio_file, easy=True)
            if m:
                if "artist" in m and m["artist"]:
                    tags.artist = m["artist"][0]
                if "albumartist" in m and m["albumartist"] and not tags.artist:
                    tags.artist = m["albumartist"][0]
                if "album" in m and m["album"]:
                    tags.album = m["album"][0]
                if "date" in m and m["date"]:
                    tags.year = m["date"][0][:4]
                if "genre" in m and m["genre"]:
                    tags.genre = ";".join(m["genre"])
                return tags
        except Exception:
            pass

    # Pure Python FLAC Vorbis Comment fallback
    if audio_file.lower().endswith(".flac"):
        try:
            with open(audio_file, "rb") as f:
                if f.read(4) == b"fLaC":
                    while True:
                        hdr = f.read(4)
                        if len(hdr) < 4:
                            break
                        is_last = bool(hdr[0] & 0x80)
                        block_type = hdr[0] & 0x7F
                        length = int.from_bytes(hdr[1:4], "big")
                        if block_type == 4:
                            data = f.read(length)
                            vlen = int.from_bytes(data[0:4], "little")
                            offset = 4 + vlen
                            num = int.from_bytes(data[offset : offset + 4], "little")
                            offset += 4
                            for _ in range(num):
                                if offset + 4 > len(data):
                                    break
                                clen = int.from_bytes(data[offset : offset + 4], "little")
                                offset += 4
                                comment = data[offset : offset + clen].decode("utf-8", errors="ignore")
                                offset += clen
                                if "=" in comment:
                                    k, v = comment.split("=", 1)
                                    ku = k.upper()
                                    if ku in ("ARTIST", "ALBUMARTIST") and not tags.artist:
                                        tags.artist = v
                                    elif ku == "ALBUM" and not tags.album:
                                        tags.album = v
                                    elif ku in ("DATE", "YEAR") and not tags.year:
                                        tags.year = v[:4]
                                    elif ku == "GENRE":
                                        tags.genre = (tags.genre + ";" + v).strip(";")
                            break
                        else:
                            f.seek(length, 1)
                        if is_last:
                            break
        except Exception:
            pass

    return tags
