"""Shared playback state for the two display processes."""

import json
import os
import tempfile
from pathlib import Path


STATE_FILE = Path(
    os.environ.get(
        "TENNA_COSPLAY_STATE_FILE",
        Path(tempfile.gettempdir()) / "tennaclosplay-playback.json",
    )
)
_UNSET = object()


def write_state(
    media_path=None,
    paused=False,
    playback_id=0,
    visual_path=None,
    transition=None,
    stop_at_seconds=_UNSET,
):
    transition_completed_playback_id = None
    previous_state = read_state()
    if previous_state.get("playback_id") == playback_id:
        transition_completed_playback_id = previous_state.get(
            "transition_completed_playback_id"
        )
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary_file.write_text(
        json.dumps(
            {
                "media": media_path,
                "paused": paused,
                "playback_id": playback_id,
                "visual": visual_path,
                "transition": transition,
                "stop_at_seconds": (
                    previous_state.get("stop_at_seconds")
                    if stop_at_seconds is _UNSET
                    else stop_at_seconds
                ),
                "sound": previous_state.get("sound"),
                "sound_started_playback_id": previous_state.get(
                    "sound_started_playback_id"
                ),
                "sound_start_error": previous_state.get("sound_start_error"),
                "voice_output_level": previous_state.get("voice_output_level"),
                "transition_completed_playback_id": (
                    transition_completed_playback_id
                ),
                "finished_playback_id": previous_state.get(
                    "finished_playback_id"
                ),
            }
        ),
        encoding="utf-8",
    )
    temporary_file.replace(STATE_FILE)


def mark_media_finished(playback_id):
    """Signal that the selected media ended so Screen1 can advance a playlist."""
    state = read_state()
    state["finished_playback_id"] = playback_id
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary_file.write_text(json.dumps(state), encoding="utf-8")
    temporary_file.replace(STATE_FILE)


def mark_transition_finished(playback_id):
    """Acknowledge a transition if it still belongs to the current playback."""
    state = read_state()
    if state.get("playback_id") != playback_id:
        return
    state["transition_completed_playback_id"] = playback_id
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary_file.write_text(json.dumps(state), encoding="utf-8")
    temporary_file.replace(STATE_FILE)


def set_sound(media_path):
    """Set or clear an independent audio overlay without replacing media state."""
    state = read_state()
    sound = state.get("sound")
    previous_id = sound.get("playback_id", 0) if isinstance(sound, dict) else 0
    sound_id = previous_id + 1
    state["sound"] = {
        "media": media_path,
        "playback_id": sound_id,
    }
    state["sound_started_playback_id"] = None
    state["sound_start_error"] = None
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary_file.write_text(json.dumps(state), encoding="utf-8")
    temporary_file.replace(STATE_FILE)
    return sound_id


def mark_sound_started(playback_id):
    """Acknowledge that Screen2 accepted an independent audio overlay."""
    state = read_state()
    sound = state.get("sound")
    if not isinstance(sound, dict) or sound.get("playback_id") != playback_id:
        return
    state["sound_started_playback_id"] = playback_id
    state["sound_start_error"] = None
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary_file.write_text(json.dumps(state), encoding="utf-8")
    temporary_file.replace(STATE_FILE)


def mark_sound_start_failed(playback_id, error):
    """Report a failed independent audio overlay start to Screen1."""
    state = read_state()
    sound = state.get("sound")
    if not isinstance(sound, dict) or sound.get("playback_id") != playback_id:
        return
    state["sound_start_error"] = {
        "playback_id": playback_id,
        "message": str(error),
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary_file.write_text(json.dumps(state), encoding="utf-8")
    temporary_file.replace(STATE_FILE)


def set_voice_output_level(level):
    """Set the live microphone monitor output level."""
    state = read_state()
    state["voice_output_level"] = level
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary_file.write_text(json.dumps(state), encoding="utf-8")
    temporary_file.replace(STATE_FILE)


def read_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "media": None,
            "paused": False,
            "playback_id": 0,
            "finished_playback_id": None,
            "transition_completed_playback_id": None,
            "sound": {"media": None, "playback_id": 0},
            "sound_started_playback_id": None,
            "sound_start_error": None,
        }
