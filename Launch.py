"""Launch both cosplay screens and keep them running together."""

import ctypes
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


DISPLAY_COUNT = 2
DISPLAY_CHECK_INTERVAL_SECONDS = 1
ACTIVE_DISPLAY_GEOMETRY = re.compile(r"\b\d+x\d+[+-]\d+[+-]\d+\b")


def linux_drm_display_count(drm_directory=Path("/sys/class/drm")):
    status_paths = tuple(drm_directory.glob("card*-*/status"))
    if not status_paths:
        return None

    active_displays = 0
    checked_connectors = 0
    for status_path in status_paths:
        try:
            status = status_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        try:
            enabled = status_path.with_name("enabled").read_text(
                encoding="utf-8"
            ).strip()
        except FileNotFoundError:
            return None

        checked_connectors += 1
        if status == "connected" and enabled == "enabled":
            active_displays += 1

    return active_displays if checked_connectors else None


def connected_display_count():
    if platform.system() == "Windows":
        return ctypes.windll.user32.GetSystemMetrics(80)

    if platform.system() == "Linux":
        drm_display_count = linux_drm_display_count()
        if drm_display_count is not None:
            return drm_display_count

        try:
            result = subprocess.run(
                ["xrandr", "--query"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "xrandr is required to detect connected displays on Linux."
            ) from error
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() or str(error)
            raise RuntimeError(f"xrandr could not detect displays: {detail}") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Timed out while detecting connected displays.") from error

        return sum(
            " connected" in line
            and ACTIVE_DISPLAY_GEOMETRY.search(line) is not None
            for line in result.stdout.splitlines()
        )

    raise RuntimeError(f"Display detection is not supported on {sys.platform}.")


def wait_for_displays():
    last_count = None
    while True:
        count = connected_display_count()
        if count >= DISPLAY_COUNT:
            print(
                f"Detected {count} connected and initialized displays. Starting screens.",
                flush=True,
            )
            return

        if count != last_count:
            print(
                f"Waiting for {DISPLAY_COUNT} connected and initialized displays; "
                f"detected {count}.",
                flush=True,
            )
            last_count = count
        time.sleep(DISPLAY_CHECK_INTERVAL_SECONDS)


def stop_processes(processes):
    for process in processes:
        if process.poll() is None:
            process.terminate()

    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    project_dir = Path(__file__).resolve().parent
    screen_paths = [project_dir / "Screen1.py", project_dir / "Screen2.py"]
    missing = [path.name for path in screen_paths if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing screen file(s): {', '.join(missing)}")

    processes = []
    state_file = Path(tempfile.gettempdir()) / f"tennaclosplay-{uuid.uuid4().hex}.json"
    environment = os.environ.copy()
    environment["TENNA_COSPLAY_STATE_FILE"] = str(state_file)
    try:
        wait_for_displays()
        for screen_path in screen_paths:
            processes.append(
                subprocess.Popen(
                    [sys.executable, str(screen_path)],
                    cwd=project_dir,
                    env=environment,
                )
            )

        while all(process.poll() is None for process in processes):
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_processes(processes)
        try:
            state_file.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()