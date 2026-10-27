"""Full-screen media playback coordinated with the camera view on Screen1."""

import queue
import random
import sys
import threading
import time
import tkinter as tk
import wave
from pathlib import Path

import PlaybackState
from MediaTypes import (
    is_talk_animation,
    media_kind,
    talk_animation_frame_groups,
    talk_animation_images,
)
from VideoSettings import display_geometry, load_settings, media_loops


BACKGROUND = "#101820"
TALKING_HOLD_SECONDS = 0.45
TALK_FRAME_DELAY_SECONDS = 0.125
TALK_SOUND_PATH = Path(__file__).resolve().parent / "media" / "TennaTalk.wav"
TALK_SOUND_LEVEL = 0.12


def main():
    settings = load_settings()
    voice_settings = settings["voice_changer"]
    voice_output_level = voice_settings["output_level"]
    debug_settings = settings["debug"]
    talk_threshold = settings["talk_threshold"]

    root = tk.Tk()
    root.title("Screen 2 - Media Playback")
    window_geometry = display_geometry(settings, "screen2")
    root.geometry(window_geometry)
    root.overrideredirect(True)
    root.configure(bg=BACKGROUND)

    preview = tk.Frame(root, bg="black")
    preview.place(x=0, y=0, relwidth=1, relheight=1)
    image_label = tk.Label(preview, bg="black")
    microphone_status = tk.Label(
        root,
        bg="#101820",
        fg="#70e1c1",
        font=("TkDefaultFont", 9),
        padx=8,
        pady=4,
        text="Starting microphone...",
    )
    if debug_settings["show_microphone_status"]:
        microphone_status.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor="se")
    status_label = tk.Label(
        root,
        bg=BACKGROUND,
        fg="white",
        font=("TkDefaultFont", 12),
        text="Select media on Screen1 to display or play it here.",
    )
    if debug_settings["show_playback_status"]:
        status_label.place(relx=0.5, rely=0.5, anchor="center")
    title_label = tk.Label(
        root,
        bg=BACKGROUND,
        fg="#70e1c1",
        font=("TkDefaultFont", 14, "bold"),
        padx=10,
        pady=6,
    )

    def show_playback_status(text, relx=0.5, rely=0.5, anchor="center"):
        status_label.configure(text=text)
        if debug_settings["show_playback_status"]:
            status_label.place(relx=relx, rely=rely, anchor=anchor)
        else:
            status_label.place_forget()

    def show_currently_playing(text):
        title_label.configure(text=text)
        if debug_settings["show_currently_playing"]:
            title_label.place(x=16, y=16, anchor="nw")
        else:
            title_label.place_forget()

    current_media = None
    current_visual = None
    current_paused = None
    current_playback_id = None
    current_stop_at_seconds = None
    image_photo = None
    current_image_path = None
    transition_overlay = None
    transition_phase = None
    transition_started = 0.0
    transition_duration = 0.0
    transition_playback_id = None
    transition_video_waiting = False
    transition_video_ready = False
    animation_frames = ()
    animation_photos = ()
    animation_index = 0
    next_animation_frame = 0.0
    talking_until = 0.0
    talk_sound_samples = None
    talk_sound_position = None
    talk_sound_active = False
    talk_sound_loop = False
    talk_sound_lock = threading.Lock()
    talk_sound_error = None
    media_finished = False
    instance = None
    player = None
    sound_instance = None
    sound_player = None
    current_sound_id = None
    pending_sound_start_id = None
    pending_sound_start_deadline = 0.0
    microphone_stream = None
    microphone_output_stream = None
    microphone_audio_queue = queue.Queue(maxsize=8)
    microphone_error = None
    microphone_input_label = "Microphone starting..."
    microphone_metrics = {"peak": 0.0, "callbacks": 0, "channel": 0}
    microphone_lock = threading.Lock()
    held_sample = None
    sample_counter = 0

    def load_image_photo(media_path):
        from PIL import Image, ImageOps, ImageTk

        width = max(preview.winfo_width(), 1)
        height = max(preview.winfo_height(), 1)
        with Image.open(media_path) as source:
            source.seek(0)
            fitted = ImageOps.contain(
                source.convert("RGB"),
                (width, height),
                method=Image.Resampling.LANCZOS,
            )
        return ImageTk.PhotoImage(fitted)

    def sound_loops(media_path):
        return media_loops(settings, media_path)

    def display_image(media_path):
        nonlocal image_photo, current_image_path
        current_image_path = Path(media_path)
        image_photo = load_image_photo(current_image_path)
        image_label.configure(image=image_photo)
        image_label.image = image_photo
        image_label.place(x=0, y=0, relwidth=1, relheight=1)
        image_label.lift()

    def display_talk_frame(index):
        nonlocal image_photo, current_image_path
        frame_index = random.randrange(len(animation_frames[index]))
        image_photo = animation_photos[index][frame_index]
        current_image_path = Path(animation_frames[index][frame_index])
        image_label.configure(image=image_photo)
        image_label.image = image_photo
        image_label.place(x=0, y=0, relwidth=1, relheight=1)
        image_label.lift()

    def stop_microphone():
        nonlocal microphone_stream, microphone_output_stream
        if microphone_output_stream is not None:
            microphone_output_stream.stop()
            microphone_output_stream.close()
            microphone_output_stream = None
        if microphone_stream is not None:
            microphone_stream.stop()
            microphone_stream.close()
            microphone_stream = None
        while not microphone_audio_queue.empty():
            try:
                microphone_audio_queue.get_nowait()
            except queue.Empty:
                break

    def start_microphone():
        nonlocal microphone_stream, microphone_output_stream, microphone_error
        nonlocal microphone_input_label
        nonlocal held_sample, sample_counter
        nonlocal talk_sound_samples, talk_sound_position, talk_sound_error
        nonlocal talk_sound_loop, talk_sound_active
        try:
            import sounddevice
            import numpy as np
        except ImportError as error:
            microphone_error = str(error)
            microphone_input_label = (
                "Mic filter unavailable: install sounddevice and numpy"
            )
            if debug_settings["show_microphone_status"]:
                microphone_status.configure(
                    text=microphone_input_label,
                    fg="#ff8a80",
                )
            return f"Microphone filter unavailable: {error}"

        def measure_level(indata):
            channel_levels = np.max(np.abs(indata), axis=0)
            channel_index = int(np.argmax(channel_levels))
            peak_level = float(channel_levels[channel_index])
            with microphone_lock:
                microphone_metrics["peak"] = max(
                    microphone_metrics["peak"], peak_level
                )
                microphone_metrics["callbacks"] += 1
                microphone_metrics["channel"] = channel_index
            return indata[
                :, channel_index : channel_index + 1
            ]

        def detect_microphone(indata, _frames, _time_info, _status):
            measure_level(indata)

        def filter_microphone(indata, _frames, _time_info, _status):
            nonlocal held_sample, sample_counter
            mono_input = measure_level(indata)
            if voice_settings["enabled"]:
                frame_count = len(mono_input)
                if held_sample is None:
                    held_sample = np.zeros(mono_input.shape[1], dtype=np.float32)
                update_frames = np.flatnonzero(
                    (sample_counter + np.arange(frame_count))
                    % voice_settings["sample_rate_reduction"]
                    == 0
                )
                held = np.broadcast_to(held_sample, mono_input.shape).copy()
                if update_frames.size:
                    frame_indices = (
                        np.searchsorted(
                            update_frames,
                            np.arange(frame_count),
                            side="right",
                        )
                        - 1
                    )
                    updated_frames = frame_indices >= 0
                    held[updated_frames] = mono_input[
                        update_frames[frame_indices[updated_frames]]
                    ]
                    held_sample[:] = mono_input[update_frames[-1]]
                sample_counter = (
                    sample_counter + frame_count
                ) % voice_settings["sample_rate_reduction"]
                levels = 2 ** (voice_settings["bit_depth"] - 1)
                amplified = np.clip(held * voice_settings["gain"], -1.0, 1.0)
                quantized = np.round(amplified * levels) / levels
                filtered = np.clip(
                    quantized * voice_output_level,
                    -1.0,
                    1.0,
                )
            else:
                filtered = np.zeros_like(mono_input)

            try:
                microphone_audio_queue.put_nowait(filtered)
            except queue.Full:
                try:
                    microphone_audio_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    microphone_audio_queue.put_nowait(filtered)
                except queue.Full:
                    pass

        output_pending = None

        def play_filtered_voice(outdata, frames, _time_info, _status):
            nonlocal output_pending, talk_sound_position
            nonlocal talk_sound_active, talk_sound_loop
            outdata.fill(0)
            written = 0
            while written < frames:
                if output_pending is None or len(output_pending) == 0:
                    try:
                        output_pending = microphone_audio_queue.get_nowait()
                    except queue.Empty:
                        break

                count = min(frames - written, len(output_pending))
                mono_chunk = output_pending[:count]
                outdata[written : written + count] = mono_chunk
                if outdata.shape[1] > 1:
                    outdata[written : written + count, 1:] = mono_chunk
                output_pending = output_pending[count:]
                written += count
            with talk_sound_lock:
                if (
                    talk_sound_samples is not None
                    and talk_sound_position is not None
                    and talk_sound_active
                ):
                    written_sound = 0
                    while written_sound < frames:
                        count = min(
                            frames - written_sound,
                            len(talk_sound_samples) - talk_sound_position,
                        )
                        sample_chunk = talk_sound_samples[
                            talk_sound_position : talk_sound_position + count
                        ]
                        outdata[written_sound : written_sound + count] = np.clip(
                            outdata[written_sound : written_sound + count]
                            + sample_chunk * TALK_SOUND_LEVEL,
                            -1.0,
                            1.0,
                        )
                        written_sound += count
                        talk_sound_position += count
                        if talk_sound_position >= len(talk_sound_samples):
                            if talk_sound_loop and talk_sound_active:
                                talk_sound_position = 0
                            else:
                                talk_sound_position = None
                                break

        try:
            device_setting = settings["microphone_device"]
            input_device = None
            devices = sounddevice.query_devices()
            if device_setting is not None:
                if isinstance(device_setting, int):
                    device_index = device_setting
                    if (
                        device_index < 0
                        or device_index >= len(devices)
                        or devices[device_index]["max_input_channels"] < 1
                    ):
                        raise ValueError(
                            f"Microphone device index {device_index} is unavailable "
                            "or has no input channels"
                        )
                    input_device = device_index
                else:
                    matching_devices = [
                        index
                        for index, device in enumerate(devices)
                        if device["max_input_channels"] > 0
                        and device_setting.casefold() in device["name"].casefold()
                    ]
                    if not matching_devices:
                        available_devices = ", ".join(
                            f"{index}: {device['name']}"
                            for index, device in enumerate(devices)
                            if device["max_input_channels"] > 0
                        )
                        raise ValueError(
                            f"No microphone matches {device_setting!r}. "
                            f"Available inputs: {available_devices or 'none'}"
                        )
                    host_apis = sounddevice.query_hostapis()
                    wasapi_devices = [
                        index
                        for index in matching_devices
                        if "wasapi"
                        in host_apis[devices[index]["hostapi"]]["name"].casefold()
                    ]
                    input_device = (
                        wasapi_devices[0]
                        if wasapi_devices
                        else matching_devices[0]
                    )
            selected_input = input_device
            if selected_input is None:
                default_input = sounddevice.default.device[0]
                if default_input is not None and 0 <= default_input < len(devices):
                    selected_input = default_input
            microphone_name = (
                devices[selected_input]["name"]
                if selected_input is not None
                else "system default"
            )
            input_channels = (
                min(2, devices[selected_input]["max_input_channels"])
                if selected_input is not None
                else 1
            )

            output_device = sounddevice.default.device[1]
            if output_device is not None and output_device < 0:
                output_device = None
            output_info = sounddevice.query_devices(output_device, "output")
            output_channels = min(2, output_info["max_output_channels"])
            if output_channels < 1:
                raise ValueError("The default audio output has no output channels")
            output_sample_rate = int(output_info["default_samplerate"])
            talk_sound_samples = None
            talk_sound_error = None
            talk_sound_loop = sound_loops(TALK_SOUND_PATH)
            if TALK_SOUND_PATH.is_file():
                try:
                    with wave.open(str(TALK_SOUND_PATH), "rb") as source:
                        if source.getcomptype() != "NONE" or source.getsampwidth() != 2:
                            raise ValueError(
                                "TennaTalk.wav must be uncompressed 16-bit PCM audio"
                            )
                        source_channels = source.getnchannels()
                        source_rate = source.getframerate()
                        raw_samples = np.frombuffer(
                            source.readframes(source.getnframes()),
                            dtype="<i2",
                        ).reshape(-1, source_channels)
                    talk_sound_samples = raw_samples.astype(np.float32) / 32768.0
                    if source_rate != output_sample_rate:
                        source_positions = np.arange(len(talk_sound_samples))
                        target_positions = np.arange(
                            0,
                            len(talk_sound_samples),
                            source_rate / output_sample_rate,
                        )
                        talk_sound_samples = np.column_stack(
                            [
                                np.interp(
                                    target_positions,
                                    source_positions,
                                    talk_sound_samples[:, channel],
                                )
                                for channel in range(source_channels)
                            ]
                        ).astype(np.float32)
                    if output_channels == 1 and source_channels > 1:
                        talk_sound_samples = talk_sound_samples.mean(
                            axis=1,
                            keepdims=True,
                        )
                    elif output_channels > 1 and source_channels == 1:
                        talk_sound_samples = np.repeat(
                            talk_sound_samples,
                            output_channels,
                            axis=1,
                        )
                    elif source_channels != output_channels:
                        talk_sound_samples = talk_sound_samples[:, :output_channels]
                except (OSError, ValueError, wave.Error) as error:
                    talk_sound_error = str(error)
                    talk_sound_samples = None

            needs_output = voice_settings["enabled"] or talk_sound_samples is not None
            microphone_stream = sounddevice.InputStream(
                device=input_device,
                channels=input_channels,
                blocksize=1024,
                callback=filter_microphone if needs_output else detect_microphone,
            )
            if needs_output:
                microphone_output_stream = sounddevice.OutputStream(
                    device=output_device,
                    channels=output_channels,
                    samplerate=output_sample_rate,
                    blocksize=1024,
                    callback=play_filtered_voice,
                )
            with microphone_lock:
                microphone_metrics["peak"] = 0.0
            microphone_stream.start()
            if microphone_output_stream is not None:
                microphone_output_stream.start()
            microphone_error = None
            if debug_settings["show_microphone_status"]:
                host_api = sounddevice.query_hostapis(
                    devices[selected_input]["hostapi"]
                )["name"] if selected_input is not None else "default"
                microphone_input_label = (
                    f"{'RETRO MIC' if voice_settings['enabled'] else 'MIC'}: "
                    f"{microphone_name} (input {selected_input}, {host_api})"
                )
                microphone_status.configure(
                    text=microphone_input_label, fg="#70e1c1"
                )
            if talk_sound_error is not None:
                status_label.configure(
                    text=f"Could not load {TALK_SOUND_PATH.name}: {talk_sound_error}"
                )
                status_label.place(relx=0.5, rely=0.5, anchor="center")
            return "Listening for sound..."
        except (sounddevice.PortAudioError, OSError, RuntimeError, ValueError) as error:
            if microphone_output_stream is not None:
                microphone_output_stream.close()
                microphone_output_stream = None
            if microphone_stream is not None:
                microphone_stream.close()
            microphone_stream = None
            microphone_error = str(error)
            microphone_input_label = f"Mic filter unavailable: {error}"
            if debug_settings["show_microphone_status"]:
                microphone_status.configure(
                    text=microphone_input_label,
                    fg="#ff8a80",
                )
            return f"Microphone unavailable: {error}"

    def stop_preview():
        nonlocal current_media, current_visual, current_paused, image_photo, current_image_path
        nonlocal animation_frames, animation_photos
        if player is not None and current_media is not None:
            if media_kind(current_media) in {"video", "audio"}:
                player.stop()
        current_media = None
        current_visual = None
        current_paused = None
        image_label.place_forget()
        image_label.configure(image="")
        image_label.image = None
        image_photo = None
        current_image_path = None
        animation_frames = ()
        animation_photos = ()
        title_label.place_forget()
        show_playback_status("Select media on Screen1 to display or play it here.")

    def sync_preview():
        nonlocal voice_output_level
        nonlocal current_media, current_visual, current_paused, current_playback_id
        nonlocal current_stop_at_seconds
        nonlocal image_photo, current_image_path, media_finished, instance, player
        nonlocal animation_frames, animation_photos, animation_index
        nonlocal next_animation_frame, talking_until
        nonlocal transition_overlay, transition_phase
        nonlocal transition_started, transition_duration, transition_playback_id
        nonlocal transition_video_waiting, transition_video_ready
        nonlocal sound_instance, sound_player, current_sound_id
        nonlocal pending_sound_start_id, pending_sound_start_deadline
        try:
            state = PlaybackState.read_state()
        except (OSError, ValueError) as error:
            status_label.configure(text=f"Could not read playback state: {error}")
            root.after(200, sync_preview)
            return
        updated_voice_output_level = state.get("voice_output_level")
        if isinstance(updated_voice_output_level, (int, float)) and not isinstance(
            updated_voice_output_level, bool
        ):
            voice_output_level = min(1.0, max(0.0, updated_voice_output_level))

        media_path = state.get("media", state.get("video"))
        visual_path = state.get("visual")
        paused = bool(state.get("paused", False))
        playback_id = state.get("playback_id", 0)
        transition = state.get("transition")
        stop_at_seconds = state.get("stop_at_seconds")
        sound_state = state.get("sound") or {}
        sound_id = sound_state.get("playback_id", 0)
        if sound_id != current_sound_id:
            if sound_player is not None:
                sound_player.stop()
            current_sound_id = sound_id
            pending_sound_start_id = None
            sound_path = sound_state.get("media")
            if sound_path:
                try:
                    import vlc as vlc_module
                except ImportError as error:
                    PlaybackState.mark_sound_start_failed(sound_id, error)
                    status_label.configure(
                        text=f"Could not play audio overlay: {error}"
                    )
                    status_label.place(relx=0.5, rely=0.5, anchor="center")
                else:
                    try:
                        if sound_instance is None:
                            sound_instance = vlc_module.Instance(
                                "--no-video-title-show"
                            )
                            if sound_instance is None:
                                raise RuntimeError(
                                    "VLC could not start audio playback"
                                )
                        if sound_player is None:
                            sound_player = sound_instance.media_player_new()
                        sound_media = sound_instance.media_new(sound_path)
                        if sound_loops(sound_path):
                            sound_media.add_option(":input-repeat=65535")
                        sound_player.set_media(sound_media)
                        sound_player.audio_set_volume(settings["volume"])
                        if sound_player.play() == -1:
                            raise RuntimeError(
                                "VLC could not start the selected sound"
                            )
                        pending_sound_start_id = sound_id
                        pending_sound_start_deadline = time.monotonic() + 5
                    except (
                        OSError,
                        RuntimeError,
                        AttributeError,
                        vlc_module.VLCException,
                    ) as error:
                        PlaybackState.mark_sound_start_failed(sound_id, error)
                        status_label.configure(
                            text=f"Could not play audio overlay: {error}"
                        )
                        status_label.place(relx=0.5, rely=0.5, anchor="center")

        if pending_sound_start_id is not None and sound_player is not None:
            try:
                import vlc as vlc_module
            except ImportError as error:
                PlaybackState.mark_sound_start_failed(
                    pending_sound_start_id, error
                )
                pending_sound_start_id = None
                status_label.configure(
                    text=f"Could not play audio overlay: {error}"
                )
                status_label.place(relx=0.5, rely=0.5, anchor="center")
            else:
                try:
                    sound_player_state = sound_player.get_state()
                    if sound_player_state == vlc_module.State.Playing:
                        PlaybackState.mark_sound_started(pending_sound_start_id)
                        pending_sound_start_id = None
                    elif sound_player_state == vlc_module.State.Error:
                        raise RuntimeError("VLC reported an audio playback error")
                    elif time.monotonic() >= pending_sound_start_deadline:
                        raise RuntimeError(
                            "VLC timed out while starting playlist audio"
                        )
                except (
                    OSError,
                    RuntimeError,
                    AttributeError,
                    vlc_module.VLCException,
                ) as error:
                    PlaybackState.mark_sound_start_failed(
                        pending_sound_start_id, error
                    )
                    pending_sound_start_id = None
                    status_label.configure(
                        text=f"Could not play audio overlay: {error}"
                    )
                    status_label.place(relx=0.5, rely=0.5, anchor="center")

        if (
            transition_phase is None
            and current_media is not None
            and playback_id != current_playback_id
            and isinstance(transition, dict)
            and transition.get("effect") == "fade"
        ):
            duration = transition.get("duration")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                try:
                    transition_overlay = tk.Toplevel(root)
                    transition_overlay.overrideredirect(True)
                    transition_overlay.configure(bg="black")
                    transition_overlay.geometry(window_geometry)
                    transition_overlay.attributes("-topmost", True)
                    transition_overlay.attributes("-alpha", 0.0)
                    transition_overlay.lift()
                    transition_phase = "out"
                    transition_started = time.monotonic()
                    transition_duration = float(duration)
                    transition_playback_id = playback_id
                    transition_video_ready = False
                except tk.TclError as error:
                    if transition_overlay is not None:
                        transition_overlay.destroy()
                    transition_overlay = None
                    status_label.configure(
                        text=f"Could not start fade transition: {error}"
                    )
                    status_label.place(relx=0.5, rely=0.5, anchor="center")
                    PlaybackState.mark_transition_finished(playback_id)
        elif (
            current_media is None
            and playback_id != current_playback_id
            and isinstance(transition, dict)
            and transition.get("effect") == "fade"
        ):
            PlaybackState.mark_transition_finished(playback_id)

        if transition_phase == "out":
            elapsed = time.monotonic() - transition_started
            half_duration = transition_duration / 2
            progress = min(1.0, elapsed / half_duration)
            transition_overlay.attributes("-alpha", progress)
            if progress < 1:
                root.after(20, sync_preview)
                return
            transition_phase = "prepare"
            transition_started = time.monotonic()

        if transition_phase == "prepare" and transition_video_waiting:
            import vlc as vlc_module

            if player.get_state() == vlc_module.State.Playing:
                player.set_pause(1)
                player.set_time(0)
                player.audio_set_mute(True)
                transition_video_waiting = False
                transition_video_ready = True
                transition_phase = "in"
                transition_started = time.monotonic()
            elif time.monotonic() - transition_started > 5:
                status_label.configure(
                    text="VLC did not prepare the incoming video frame"
                )
                status_label.place(relx=0.5, rely=0.5, anchor="center")
                transition_video_waiting = False
                player.stop()
                transition_phase = "in"
                transition_started = time.monotonic()

        if transition_phase == "in":
            elapsed = time.monotonic() - transition_started
            half_duration = transition_duration / 2
            progress = min(1.0, elapsed / half_duration)
            transition_overlay.attributes("-alpha", 1.0 - progress)
            if progress >= 1:
                transition_overlay.destroy()
                transition_overlay = None
                transition_phase = None
                if transition_video_ready:
                    player.audio_set_mute(False)
                    player.set_pause(1 if paused else 0)
                transition_video_ready = False
                PlaybackState.mark_transition_finished(transition_playback_id)
                transition_playback_id = None
        if not media_path:
            if current_media is not None:
                stop_preview()
        elif (
            media_path != current_media
            or visual_path != current_visual
            or playback_id != current_playback_id
        ):
            kind = media_kind(media_path)
            if player is not None:
                player.stop()
            image_label.place_forget()
            current_image_path = None
            title_label.place_forget()
            animation_frames = ()
            animation_photos = ()

            try:
                if is_talk_animation(media_path):
                    animation_frames = talk_animation_frame_groups(media_path)
                    if len(animation_frames) != 2 or not all(animation_frames):
                        raise ValueError(
                            "A .talk folder must contain an image in both A and B folders"
                        )
                    animation_photos = tuple(
                        tuple(load_image_photo(frame) for frame in frames)
                        for frames in animation_frames
                    )
                    animation_index = 0
                    talking_until = 0.0
                    next_animation_frame = time.monotonic()
                    display_talk_frame(animation_index)
                    if microphone_error:
                        status_label.configure(
                            text=f"Microphone unavailable: {microphone_error}"
                        )
                        status_label.place(relx=0.02, rely=0.98, anchor="sw")
                    elif debug_settings["show_talk_detection_status"]:
                        status_label.configure(text="Listening for sound...")
                        status_label.place(relx=0.02, rely=0.98, anchor="sw")
                    else:
                        status_label.place_forget()
                    show_currently_playing(
                        f"TALK ANIMATION  |  {Path(media_path).name}"
                    )
                elif kind == "image":
                    display_image(media_path)
                    status_label.place_forget()
                    animation_frames = ()
                    animation_photos = ()
                elif kind in {"video", "audio"}:
                    if visual_path is not None:
                        if kind != "audio" or not is_talk_animation(visual_path):
                            raise ValueError(
                                "Music visuals must point to a .talk folder"
                            )
                        frames = talk_animation_images(visual_path)
                        if len(frames) != 2:
                            raise ValueError(
                                "The music .talk folder must contain an image in both A and B"
                            )
                        display_image(frames[0])
                        show_currently_playing(
                            f"MUSIC  |  {Path(media_path).name}"
                        )
                        show_playback_status(
                            "Playing music", relx=0.02, rely=0.98, anchor="sw"
                        )
                    elif kind == "video":
                        animation_frames = ()
                        animation_photos = ()
                    else:
                        animation_frames = ()
                        animation_photos = ()

                    import vlc as vlc_module

                    if instance is None:
                        instance = vlc_module.Instance(
                            "--avcodec-hw=none",
                            "--avcodec-threads=2",
                            "--no-video-title-show",
                        )
                        if instance is None:
                            raise RuntimeError("VLC could not start")
                        player = instance.media_player_new()

                    if kind == "video":
                        root.update_idletasks()
                        if sys.platform.startswith("win"):
                            player.set_hwnd(preview.winfo_id())
                        elif sys.platform == "darwin":
                            player.set_nsobject(preview.winfo_id())
                        else:
                            player.set_xwindow(preview.winfo_id())
                        status_label.place_forget()
                        show_currently_playing(
                            f"SCREEN 2  |  {Path(media_path).name}"
                        )
                    elif visual_path is None:
                        show_playback_status(
                            f"Playing audio\n{Path(media_path).name}"
                        )

                    media = instance.media_new(media_path)
                    if sound_loops(media_path):
                        media.add_option(":input-repeat=65535")
                    player.set_media(media)
                    transitioning_video = (
                        transition_phase == "prepare"
                        and kind == "video"
                    )
                    player.audio_set_volume(settings["volume"])
                    player.audio_set_mute(transitioning_video)
                    if player.play() == -1:
                        raise RuntimeError("VLC could not start this media")
                    if transitioning_video:
                        transition_video_waiting = True
                    else:
                        player.audio_set_mute(False)
                    if paused:
                        player.set_pause(1)
                else:
                    status_label.configure(text=f"Unsupported media type: {Path(media_path).name}")
                    status_label.place(relx=0.5, rely=0.5, anchor="center")
                    animation_frames = ()
                    animation_photos = ()
                if transition_phase == "prepare" and not transition_video_waiting:
                    transition_phase = "in"
                    transition_started = time.monotonic()
            except Exception as error:
                image_label.place_forget()
                title_label.place_forget()
                status_label.configure(text=f"Could not display or play media: {error}")
                status_label.place(relx=0.5, rely=0.5, anchor="center")
                PlaybackState.mark_media_finished(playback_id)
                animation_frames = ()
                animation_photos = ()

            current_media = media_path
            current_visual = visual_path
            current_paused = paused
            current_playback_id = playback_id
            current_stop_at_seconds = stop_at_seconds
            media_finished = False
        elif paused != current_paused:
            if player is not None and media_kind(media_path) in {"video", "audio"}:
                player.set_pause(1 if paused else 0)
            current_paused = paused

        if (
            current_media is not None
            and media_kind(current_media) in {"audio", "video"}
            and player is not None
        ):
            try:
                import vlc as vlc_module

                player_state = player.get_state()
                if (
                    current_stop_at_seconds is not None
                    and not media_finished
                    and media_kind(current_media) == "video"
                    and player.get_time() >= current_stop_at_seconds * 1000
                ):
                    player.stop()
                    media_finished = True
                    PlaybackState.mark_media_finished(current_playback_id)
                if (
                    player_state == vlc_module.State.Error
                    and not media_finished
                ):
                    media_finished = True
                    status_label.configure(
                        text=f"VLC could not decode: {Path(current_media).name}"
                    )
                    status_label.place(relx=0.5, rely=0.5, anchor="center")
                    PlaybackState.mark_media_finished(current_playback_id)
                elif (
                    player_state == vlc_module.State.Ended
                    and not media_finished
                ):
                    media_finished = True
                    PlaybackState.mark_media_finished(current_playback_id)
                    if media_kind(current_media) == "audio":
                        show_playback_status(
                            f"Finished audio\n{Path(current_media).name}"
                        )
            except Exception as error:
                status_label.configure(
                    text=f"Could not update playback status: {error}"
                )
                status_label.place(relx=0.5, rely=0.5, anchor="center")

        root.after(
            20 if transition_phase in {"prepare", "in"} else 200,
            sync_preview,
        )

    def update_talk_animation():
        nonlocal animation_index
        nonlocal next_animation_frame, talking_until, talk_sound_position
        nonlocal talk_sound_active
        nonlocal animation_frames, animation_photos
        with microphone_lock:
            peak = microphone_metrics["peak"]
            microphone_metrics["peak"] = 0.0
            callback_count = microphone_metrics["callbacks"]
            channel_index = microphone_metrics["channel"]
        level = peak * voice_settings["gain"]
        now = time.monotonic()
        if level > talk_threshold:
            if now >= talking_until and talk_sound_samples is not None:
                with talk_sound_lock:
                    talk_sound_position = 0
                    talk_sound_active = True
            talking_until = now + TALKING_HOLD_SECONDS

        is_talking = now < talking_until
        if not is_talking and talk_sound_active:
            with talk_sound_lock:
                talk_sound_active = False
                talk_sound_position = None

        if animation_frames and current_media is not None and not current_paused:
            if is_talking:
                if now >= next_animation_frame:
                    animation_index = 1 - animation_index
                    try:
                        display_talk_frame(animation_index)
                    except (OSError, ValueError, tk.TclError) as error:
                        animation_index = 0
                        animation_frames = ()
                        animation_photos = ()
                        status_label.configure(
                            text=f"Could not display talk frame: {error}"
                        )
                        status_label.place(relx=0.02, rely=0.98, anchor="sw")
                    else:
                        next_animation_frame = now + TALK_FRAME_DELAY_SECONDS
                if (
                    debug_settings["show_talk_detection_status"]
                    and microphone_error is None
                ):
                    status_label.configure(
                        text=(
                            f"Sound detected ({level:.3e}; raw {peak:.3e}; "
                            f"threshold {talk_threshold:.3e}) | "
                            f"frame {'B' if animation_index else 'A'} | "
                            f"ch {channel_index} | callbacks {callback_count}"
                        )
                    )
            else:
                if animation_index != 0:
                    animation_index = 0
                    display_talk_frame(animation_index)
                next_animation_frame = now
                if (
                    debug_settings["show_talk_detection_status"]
                    and microphone_error is None
                ):
                    status_label.configure(
                        text=(
                            f"Listening ({level:.3e}; raw {peak:.3e}; "
                            f"threshold {talk_threshold:.3e}) | "
                            f"frame A | ch {channel_index} | "
                            f"callbacks {callback_count}"
                        )
                    )
        root.after(50, update_talk_animation)

    def update_microphone_status():
        if debug_settings["show_microphone_status"]:
            with microphone_lock:
                callback_count = microphone_metrics["callbacks"]
            if microphone_error is not None:
                stream_status = f"error: {microphone_error}"
                status_color = "#ff8a80"
            else:
                stream_status = (
                    "active"
                    if microphone_stream is not None and microphone_stream.active
                    else "inactive"
                )
                status_color = (
                    "#70e1c1" if stream_status == "active" else "#ff8a80"
                )
            microphone_status.configure(
                text=(
                    f"{microphone_input_label} | {stream_status} | "
                    f"callbacks {callback_count}"
                ),
                fg=status_color,
            )
        root.after(500, update_microphone_status)

    def resize_image(_event=None):
        nonlocal animation_photos
        if current_image_path is not None:
            try:
                if animation_frames:
                    animation_photos = tuple(
                        tuple(load_image_photo(frame) for frame in frames)
                        for frames in animation_frames
                    )
                    display_talk_frame(animation_index)
                else:
                    display_image(current_image_path)
            except Exception as error:
                status_label.configure(text=f"Could not display image: {error}")
                status_label.place(relx=0.5, rely=0.5, anchor="center")

    def close_screen(_event=None):
        stop_microphone()
        if player is not None:
            player.stop()
            player.release()
        if sound_player is not None:
            sound_player.stop()
            sound_player.release()
        if instance is not None:
            instance.release()
        if sound_instance is not None:
            sound_instance.release()
        root.destroy()

    preview.bind("<Configure>", resize_image)
    root.bind("<Escape>", close_screen)
    root.protocol("WM_DELETE_WINDOW", close_screen)
    start_microphone()
    root.after(100, sync_preview)
    root.after(50, update_talk_animation)
    root.after(500, update_microphone_status)
    root.mainloop()


if __name__ == "__main__":
    main()
