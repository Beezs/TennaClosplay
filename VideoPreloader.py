"""Warm video files into the OS cache or Linux memory-backed file descriptors."""

import os
import sys
import threading
from pathlib import Path

from MediaTypes import VIDEO_EXTENSIONS


CHUNK_SIZE = 1024 * 1024
MEMORY_RESERVE_BYTES = 128 * 1024 * 1024


class VideoPreloader:
    def __init__(self, video_directory, preload_to_cache, preload_to_memory):
        self.video_directory = Path(video_directory)
        self.preload_to_cache = preload_to_cache
        self.preload_to_memory = preload_to_memory
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._memory_files = {}
        self._thread = None

        if preload_to_memory and (
            sys.platform != "linux"
            or not hasattr(os, "memfd_create")
            or not Path("/proc/self/fd").is_dir()
        ):
            raise RuntimeError(
                "RAM video preloading requires Linux with /proc and memfd support."
            )

    def start(self):
        if not self.preload_to_cache and not self.preload_to_memory:
            return
        self._thread = threading.Thread(
            target=self._preload_videos,
            name="video-preloader",
            daemon=True,
        )
        self._thread.start()

    def media_path(self, media_path):
        media_path = Path(media_path).resolve()
        with self._lock:
            descriptor = self._memory_files.get(media_path)
        if descriptor is None:
            return str(media_path)
        return f"/proc/{os.getpid()}/fd/{descriptor}"

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        with self._lock:
            descriptors = tuple(self._memory_files.values())
            self._memory_files.clear()
        for descriptor in descriptors:
            os.close(descriptor)

    def _video_files(self):
        if not self.video_directory.is_dir():
            return ()
        return tuple(
            sorted(
                (
                    path
                    for path in self.video_directory.rglob("*")
                    if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
                ),
                key=lambda path: str(path).casefold(),
            )
        )

    @staticmethod
    def _available_memory():
        try:
            for line in Path("/proc/meminfo").read_text(
                encoding="utf-8"
            ).splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError):
            return None
        return None

    def _preload_videos(self):
        video_files = self._video_files()
        if self.preload_to_memory:
            total_size = sum(path.stat().st_size for path in video_files)
            available_memory = self._available_memory()
            if available_memory is None:
                print(
                    "Skipping RAM video preloading: could not determine available "
                    "system memory.",
                    file=sys.stderr,
                    flush=True,
                )
                return
            if total_size + MEMORY_RESERVE_BYTES > available_memory:
                print(
                    "Skipping RAM video preloading: videos require "
                    f"{total_size:,} bytes and only {available_memory:,} bytes "
                    "are available with the safety reserve.",
                    file=sys.stderr,
                    flush=True,
                )
                return

        print(
            f"Preloading {len(video_files)} videos from {self.video_directory}.",
            flush=True,
        )
        for video_path in video_files:
            if self._stop_event.is_set():
                return
            descriptor = None
            try:
                if self.preload_to_memory:
                    descriptor = os.memfd_create(video_path.name)
                with video_path.open("rb") as source:
                    while not self._stop_event.is_set():
                        chunk = source.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        if descriptor is not None:
                            view = memoryview(chunk)
                            while view:
                                written = os.write(descriptor, view)
                                view = view[written:]
                if self._stop_event.is_set():
                    if descriptor is not None:
                        os.close(descriptor)
                    return
                if descriptor is not None:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    with self._lock:
                        self._memory_files[video_path.resolve()] = descriptor
                    descriptor = None
            except OSError as error:
                print(
                    f"Could not preload video {video_path}: {error}",
                    file=sys.stderr,
                    flush=True,
                )
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        print("Video preloading complete.", flush=True)
