"""Read title/artist/album/duration from MP3 ID3 tags via mutagen."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError


@dataclass
class TrackInfo:
    title: str
    artist: str
    album: str | None
    duration: float | None
    source: str = "tags"  # "tags" or "filename" — for reporting only


class TagReadError(Exception):
    """Raised when a track's tags can't be read AND its filename doesn't
    look like "Title - Artist" either."""


def read_track_info(mp3_path: Path) -> TrackInfo:
    duration: float | None = None
    tags = None

    try:
        audio = MP3(mp3_path)
        duration = getattr(audio.info, "length", None)
        tags = audio.tags
    except ID3NoHeaderError:
        pass  # valid audio, just no ID3 header — fall through to filename fallback
    except Exception:
        pass  # unparseable/corrupt audio — still worth trying the filename fallback

    title = artist = album = None
    if tags is not None:
        title = _first_frame(tags, "TIT2")
        artist = _first_frame(tags, "TPE1")
        album = _first_frame(tags, "TALB")

    if title and artist:
        return TrackInfo(title=title, artist=artist, album=album, duration=duration, source="tags")

    # Fallback: many downloaders (including Sunnify) name files
    # "Title - Artist.mp3" even when the embedded tags are missing.
    from_name = _parse_filename(mp3_path)
    if from_name is not None:
        fallback_title, fallback_artist = from_name
        return TrackInfo(
            title=title or fallback_title,
            artist=artist or fallback_artist,
            album=album,
            duration=duration,
            source="filename",
        )

    raise TagReadError(
        f"{mp3_path.name} has no usable title/artist tag, and its filename "
        "doesn't look like 'Title - Artist.mp3' either"
    )


def _parse_filename(mp3_path: Path) -> tuple[str, str] | None:
    """Best-effort "Title - Artist" parse from a filename.

    Strips a trailing " [spotify-id]" suffix some downloaders (Sunnify
    included) append to disambiguate duplicate titles, e.g.
    "Song - Artist [6rPO02ozF3bM7NnOV4h6s2].mp3".
    """
    stem = mp3_path.stem
    stem = re.sub(r"\s*\[[A-Za-z0-9]{15,25}\]\s*$", "", stem).strip()

    if " - " not in stem:
        return None

    title, _, artist = stem.partition(" - ")
    title, artist = title.strip(), artist.strip()
    if not title or not artist:
        return None
    return title, artist


def _first_frame(tags, frame_id: str) -> str | None:
    frame = tags.get(frame_id)
    if frame is None:
        return None
    values = getattr(frame, "text", None)
    if not values:
        return None
    return str(values[0]).strip() or None
