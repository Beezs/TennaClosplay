"""Supported media types and organized media-folder helpers."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


VIDEO_EXTENSIONS = frozenset({".avi", ".mkv", ".mov", ".mp4", ".mpeg", ".webm"})
IMAGE_EXTENSIONS = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav"})
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS


@dataclass(frozen=True)
class PlaylistItem:
    path: Path
    transition: Optional[str] = None
    transition_duration: float = 0.0
    stop_at_seconds: Optional[float] = None


def media_kind(path):
    extension = Path(path).suffix.lower()
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    return None


def is_talk_animation(path):
    path = Path(path)
    return path.is_dir() and path.name.casefold().endswith(".talk")


def is_playlist_file(path):
    path = Path(path)
    return path.is_file() and path.name.casefold().endswith(".list.json")


def load_playlist(path):
    """Load ordered media paths and transition directives from a playlist."""
    path = Path(path)
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} contains invalid JSON: {error}") from error

    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path.name} must contain a non-empty JSON array of paths")

    media_items = []
    next_transition = None
    next_stop_at = None
    for index, entry in enumerate(entries, start=1):
        if isinstance(entry, list):
            if len(entry) == 3 and isinstance(entry[0], str) and entry[0].casefold() == "stopat":
                if (
                    not isinstance(entry[1], str)
                    or entry[1].casefold() != "video"
                    or isinstance(entry[2], bool)
                    or not isinstance(entry[2], (int, float))
                    or not math.isfinite(entry[2])
                    or entry[2] < 0
                ):
                    raise ValueError(
                        f"Playlist entry {index} must be "
                        '["StopAt", "Video", seconds] with a non-negative time'
                    )
                if next_stop_at is not None:
                    raise ValueError(
                        f"Playlist entry {index} duplicates a StopAt directive"
                    )
                next_stop_at = float(entry[2])
                continue
            if len(entry) == 3 and isinstance(entry[0], str) and entry[0].casefold() == "effect":
                if next_transition is not None:
                    raise ValueError(
                        f"Playlist entry {index} duplicates a transition directive"
                    )
                if (
                    not isinstance(entry[1], str)
                    or entry[1].casefold() != "fade"
                    or isinstance(entry[2], bool)
                    or not isinstance(entry[2], (int, float))
                    or not math.isfinite(entry[2])
                    or not 0 < entry[2] <= 10
                ):
                    raise ValueError(
                        f"Playlist entry {index} must be "
                        '["Effect", "Fade", seconds] with seconds between 0 and 10'
                    )
                next_transition = ("fade", float(entry[2]))
                continue
            if next_transition is not None or next_stop_at is not None:
                raise ValueError(
                    f"Playlist entry {index} has an invalid directive"
                )
            raise ValueError(
                f"Playlist entry {index} must be a supported directive array"
            )

        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(
                f"Playlist entry {index} must be a path or transition directive"
            )
        media_path = Path(entry)
        if not media_path.is_absolute():
            media_path = path.parent / media_path
        media_path = media_path.resolve()
        if not media_path.exists():
            raise ValueError(
                f"Playlist entry {index} does not exist: {entry}"
            )
        if not is_talk_animation(media_path) and media_kind(media_path) is None:
            raise ValueError(
                f"Playlist entry {index} is not supported media: {entry}"
            )
        if next_stop_at is not None and media_kind(media_path) != "video":
            raise ValueError(
                f"Playlist entry {index} follows StopAt but is not a video"
            )
        transition, duration = next_transition or (None, 0.0)
        media_items.append(
            PlaylistItem(media_path, transition, duration, next_stop_at)
        )
        next_transition = None
        next_stop_at = None

    if next_transition is not None or next_stop_at is not None:
        raise ValueError("Playlist cannot end with a directive")

    return tuple(media_items)


def load_startup_playlist(entries, base_directory):
    """Resolve startup media paths and expand referenced playlist files."""
    if not isinstance(entries, list):
        raise ValueError("startup_playlist must be an array of file paths")

    base_directory = Path(base_directory)
    media_items = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(
                f"Startup playlist entry {index} must be a non-empty file path"
            )
        media_path = Path(entry)
        if not media_path.is_absolute():
            media_path = base_directory / media_path
        media_path = media_path.resolve()
        if not media_path.is_file():
            raise ValueError(
                f"Startup playlist entry {index} does not exist: {entry}"
            )
        if is_playlist_file(media_path):
            media_items.extend(load_playlist(media_path))
            continue
        if media_kind(media_path) not in {"video", "audio"}:
            raise ValueError(
                f"Startup playlist entry {index} must be a .list.json, video, "
                f"MP3, or WAV: {entry}"
            )
        media_items.append(PlaylistItem(media_path))
    return tuple(media_items)


def talk_animation_images(path):
    """Return the first sorted image in each required A/B animation folder."""
    frame_groups = talk_animation_frame_groups(path)
    if not frame_groups:
        return ()
    return tuple(frames[0] for frames in frame_groups)


def talk_animation_frame_groups(path):
    """Return sorted image paths from the required A and B folders."""
    path = Path(path)
    frame_groups = []
    for folder_name in ("A", "B"):
        folder = next(
            (
                child
                for child in path.iterdir()
                if child.is_dir() and child.name.casefold() == folder_name.casefold()
            ),
            None,
        )
        if folder is None:
            return ()
        frames = tuple(
            child
            for child in sorted(folder.iterdir(), key=lambda item: item.name.casefold())
            if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not frames:
            return ()
        frame_groups.append(frames)
    return tuple(frame_groups)


def media_entries(folder):
    """List supported files and child folders in a stable, display-friendly order."""
    folder = Path(folder)
    directories = sorted(
        (path for path in folder.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )
    files = sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file()
            and path.name.casefold() != "tennatalk.wav"
            and (media_kind(path) is not None or is_playlist_file(path))
        ),
        key=lambda path: path.name.casefold(),
    )
    return directories + files
