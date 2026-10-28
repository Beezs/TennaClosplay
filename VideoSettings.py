"""Load and validate shared media playback settings."""

import json
from pathlib import Path

from MediaTypes import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

SETTINGS_FILE = Path(__file__).resolve().parent / "videoSettings.json"
DEFAULT_SETTINGS = {
    "volume": 85,
    "display_resolution": {
        "screen1": {
            "width": 800,
            "height": 480,
        },
        "screen2": {
            "width": 800,
            "height": 480,
        },
    },
    "startup_playlist": [],
    "video_preview": True,
    "microphone_device": None,
    "talk_threshold": 0.01,
    "voice_changer": {
        "enabled": True,
        "gain": 2.2,
        "output_level": 0.35,
        "bit_depth": 6,
        "sample_rate_reduction": 6,
    },
    "debug": {
        "show_microphone_status": False,
        "show_talk_detection_status": False,
        "show_currently_playing": True,
        "show_playback_status": True,
        "show_picker_instructions": True,
        "show_camera_simulation_labels": True,
        "show_camera_status_label": True,
        "show_camera_metrics": False,
    },
}


def _require_number(section, key, minimum, maximum, integer=False):
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    if integer and not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")


def _require_boolean(section, key):
    if not isinstance(section[key], bool):
        raise ValueError(f"{key} must be true or false")


def _require_microphone_device(value):
    if value is not None and not isinstance(value, (str, int)):
        raise ValueError("microphone_device must be a device name, index, or null")
    if isinstance(value, bool):
        raise ValueError("microphone_device must be a device name, index, or null")


def _is_loop_setting(key):
    return Path(key).suffix.lower() in AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def _validate_loop_setting(key, value):
    if not isinstance(value, dict) or set(value) != {"Loop"}:
        raise ValueError(f"{key} must contain only a Loop setting")
    _require_boolean(value, "Loop")


def media_loops(settings, media_path):
    """Return whether a configured video or audio filename should loop."""
    filename = Path(media_path).name.casefold()
    return any(
        key.casefold() == filename and value.get("Loop", False)
        for key, value in settings.items()
        if _is_loop_setting(key)
    )


def _validate_settings(settings):
    _require_number(settings, "volume", 0, 100, integer=True)
    _require_boolean(settings, "video_preview")
    for screen_name in ("screen1", "screen2"):
        resolution = settings["display_resolution"][screen_name]
        _require_number(resolution, "width", 1, 16384, integer=True)
        _require_number(resolution, "height", 1, 16384, integer=True)
    startup_playlist = settings["startup_playlist"]
    if not isinstance(startup_playlist, list) or any(
        not isinstance(path, str) or not path.strip()
        for path in startup_playlist
    ):
        raise ValueError("startup_playlist must be an array of non-empty file paths")
    _require_microphone_device(settings["microphone_device"])
    _require_number(settings, "talk_threshold", 0, 1)
    _require_boolean(settings["voice_changer"], "enabled")
    _require_number(settings["voice_changer"], "gain", 0, 8)
    _require_number(settings["voice_changer"], "output_level", 0, 1)
    _require_number(settings["voice_changer"], "bit_depth", 2, 16, integer=True)
    _require_number(
        settings["voice_changer"], "sample_rate_reduction", 1, 64, integer=True
    )


def display_geometry(settings, screen_name):
    """Return the configured window geometry for one screen."""
    resolutions = settings["display_resolution"]
    resolution = resolutions[screen_name]
    x_position = resolutions["screen1"]["width"] if screen_name == "screen2" else 0
    return f"{resolution['width']}x{resolution['height']}+{x_position}+0"


def load_settings(path=SETTINGS_FILE):
    """Load settings, filling omitted options from their documented defaults."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return json.loads(json.dumps(DEFAULT_SETTINGS))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} contains invalid JSON: {error}") from error

    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")

    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    for key, value in raw.items():
        if _is_loop_setting(key):
            _validate_loop_setting(key, value)
            settings[key] = value
            continue
        if key not in settings:
            raise ValueError(f"Unknown setting: {key}")
        if isinstance(settings[key], dict):
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be an object")
            if key == "display_resolution" and {"width", "height"} & value.keys():
                if set(value) != {"width", "height"}:
                    raise ValueError(
                        "display_resolution must define both screen1 and screen2, "
                        "or use the legacy width and height settings"
                    )
                settings[key] = {
                    "screen1": dict(value),
                    "screen2": dict(value),
                }
                continue
            for nested_key, nested_value in value.items():
                if nested_key not in settings[key]:
                    raise ValueError(f"Unknown setting: {key}.{nested_key}")
                if isinstance(settings[key][nested_key], dict):
                    if not isinstance(nested_value, dict):
                        raise ValueError(f"{key}.{nested_key} must be an object")
                    settings[key][nested_key].update(nested_value)
                else:
                    settings[key][nested_key] = nested_value
        else:
            settings[key] = value

    try:
        _validate_settings(settings)
        for key in settings["debug"]:
            _require_boolean(settings["debug"], key)
    except (KeyError, TypeError) as error:
        raise ValueError(f"{path} is missing a required setting") from error
    return settings
