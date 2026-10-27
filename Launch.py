"""Launch both cosplay screens and keep them running together."""

import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


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