"""Camera screen template for a Raspberry Pi cosplay display."""

import math
import sys
import time
import tkinter as tk
from pathlib import Path

import PlaybackState
from MediaTypes import (
    is_playlist_file,
    is_talk_animation,
    load_playlist,
    load_startup_playlist,
    media_entries,
    media_kind,
)
from VideoSettings import display_geometry, load_settings, media_loops



CAMERA_SIZE = (1920,1080)
FRAME_DELAY_MS = 50
CAMERA_MODE = "emulator"  # Use "picamera" on Raspberry Pi with a camera attached.
MEDIA_DIR = Path(__file__).resolve().parent / "media"
LEGACY_VIDEO_DIR = Path(__file__).resolve().parent / "videos"
DEFAULT_VIDEO_NAME = "default.mp4"

MEDIA_LIST_BUTTON = 0
PAUSE_BUTTON = 1
STOP_AUDIO_BUTTON = 2
NEXT_BUTTON = 3
VOLUME_DOWN_BUTTON = 4
VOLUME_UP_BUTTON = 6
UP_BUTTON = 13
DOWN_BUTTON = 14
VOICE_VOLUME_STEP = 0.05
MEDIA_TYPE_COLORS = {
    "talk": "#ff79c6",
    "playlist": "#bd93f9",
    "video": "#8be9fd",
    "music": "#50fa7b",
    "default": "white",
}


def draw_emulator_frame(canvas, elapsed, show_labels=True):
    """Draw a moving test scene without needing a camera or extra packages."""
    canvas.delete("all")
    width = max(canvas.winfo_width(), 1)
    height = max(canvas.winfo_height(), 1)
    horizon = height * 0.43
    vanishing_x = width / 2

    canvas.create_rectangle(0, 0, width, horizon, fill="#607d8b", outline="")
    canvas.create_rectangle(0, horizon, width, height, fill="#304638", outline="")
    canvas.create_polygon(
        vanishing_x - width * 0.06,
        horizon,
        vanishing_x + width * 0.06,
        horizon,
        width * 0.96,
        height,
        width * 0.04,
        height,
        fill="#34383a",
        outline="",
    )

    canvas.create_line(
        vanishing_x - width * 0.06,
        horizon,
        width * 0.04,
        height,
        fill="#d5d4c8",
        width=3,
    )
    canvas.create_line(
        vanishing_x + width * 0.06,
        horizon,
        width * 0.96,
        height,
        fill="#d5d4c8",
        width=3,
    )

    dash_offset = (elapsed * 0.45) % 1
    for index in range(6):
        depth = ((index / 6) + dash_offset) % 1
        y = horizon + (height - horizon) * depth**2
        dash_height = max(3, depth * height * 0.055)
        dash_width = max(2, depth * width * 0.012)
        canvas.create_rectangle(
            vanishing_x - dash_width / 2,
            y,
            vanishing_x + dash_width / 2,
            y + dash_height,
            fill="#f2f0df",
            outline="",
        )

    obstacle_x = width * (0.28 + 0.05 * math.sin(elapsed * 0.7))
    obstacle_y = horizon + (height - horizon) * 0.42
    obstacle_size = max(24, width * 0.055)
    canvas.create_rectangle(
        obstacle_x - obstacle_size / 2,
        obstacle_y - obstacle_size,
        obstacle_x + obstacle_size / 2,
        obstacle_y,
        fill="#c75b45",
        outline="white",
        width=2,
    )
    if show_labels:
        canvas.create_text(
            obstacle_x,
            obstacle_y - obstacle_size / 2,
            fill="white",
            font=("TkDefaultFont", 9, "bold"),
            text="TEST",
        )
        canvas.create_text(
            16,
            16,
            anchor="nw",
            fill="white",
            font=("TkDefaultFont", 12, "bold"),
            text="SIMULATED CAMERA - NO LIVE VIDEO",
        )
    canvas.create_line(
        vanishing_x - 10,
        height * 0.56,
        vanishing_x + 10,
        height * 0.56,
        fill="#70e1c1",
        width=2,
    )
    canvas.create_line(
        vanishing_x,
        height * 0.56 - 10,
        vanishing_x,
        height * 0.56 + 10,
        fill="#70e1c1",
        width=2,
    )
    if show_labels:
        canvas.create_text(
            16,
            height - 16,
            anchor="sw",
            fill="white",
            font=("TkDefaultFont", 12, "bold"),
            text="EMULATOR  |  Esc to exit",
        )


def main():
    settings = load_settings()
    debug_settings = settings["debug"]
    video_preview_enabled = settings["video_preview"]
    root = tk.Tk()
    root.title("Screen 1 - Camera")
    root.geometry(display_geometry(settings, "screen1"))
    root.overrideredirect(True)
    root.configure(bg="black")

    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    media_root = MEDIA_DIR
    if (
        not media_entries(MEDIA_DIR)
        and LEGACY_VIDEO_DIR.is_dir()
    ):
        media_root = LEGACY_VIDEO_DIR

    camera = None
    preview_image = None
    preview_item = None
    status_item = None
    selected_index = 0
    current_folder = media_root
    entries = []
    video_instance = None
    video_player = None
    pygame = None
    joystick = None
    current_video = None
    current_visual = None
    paused = False
    ended_video = False
    playback_id = 0
    active_playlist = ()
    playlist_index = -1
    finished_playback_seen = None
    pending_transition_video_id = None
    pending_transition_deadline = 0.0
    pending_playlist_sound_id = None

    def close_screen(_event=None):
        PlaybackState.write_state()
        if video_player is not None:
            video_player.stop()
            video_player.release()
        if video_instance is not None:
            video_instance.release()
        if pygame is not None:
            pygame.quit()
        if camera is not None:
            camera.stop()
            camera.close()
        root.destroy()

    root.bind("<Escape>", close_screen)
    root.protocol("WM_DELETE_WINDOW", close_screen)

    picker = tk.Frame(root, bg="#101820", highlightbackground="#70e1c1", highlightthickness=2)
    tk.Label(
        picker,
        bg="#101820",
        fg="#70e1c1",
        font=("TkDefaultFont", 16, "bold"),
        text="CHOOSE MEDIA",
    ).pack(fill="x", padx=12, pady=(12, 6))
    color_legend = tk.Frame(picker, bg="#101820")
    color_legend.pack(fill="x", padx=12, pady=(0, 4))
    for label, category in (
        ("TALK", "talk"),
        ("LIST", "playlist"),
        ("VIDEO", "video"),
        ("MUSIC", "music"),
    ):
        tk.Label(
            color_legend,
            bg="#101820",
            fg=MEDIA_TYPE_COLORS[category],
            font=("TkDefaultFont", 8, "bold"),
            text=label,
        ).pack(side="left", expand=True)
    video_list = tk.Listbox(
        picker,
        bg="#17232d",
        fg="white",
        selectbackground="#287b69",
        selectforeground="white",
        font=("TkDefaultFont", 12),
        activestyle="none",
        highlightthickness=0,
        exportselection=False,
    )
    video_list.pack(fill="both", expand=True, padx=12, pady=6)
    status_label = tk.Label(
        picker,
        bg="#101820",
        fg="#b8c2cc",
        font=("TkDefaultFont", 9),
        justify="left",
        text=(
            "Up/Down: choose   Enter: open/play\n"
            "A: media list   B/Space: pause   Esc: exit"
            if debug_settings["show_picker_instructions"]
            else ""
        ),
    )
    status_label.pack(fill="x", padx=12, pady=(4, 6))
    play_button = tk.Button(
        picker,
        bg="#287b69",
        fg="white",
        activebackground="#359a83",
        activeforeground="white",
        font=("TkDefaultFont", 11, "bold"),
        text="Play selected",
    )
    play_button.pack(fill="x", padx=12, pady=(0, 12))
    picker.place(relx=1.0, x=-24, y=48, width=320, height=400, anchor="ne")

    video_surface = tk.Frame(
        root,
        bg="black",
        highlightbackground="#70e1c1",
        highlightthickness=3,
    )

    def update_selection(_event=None):
        nonlocal selected_index
        selection = video_list.curselection()
        if selection:
            selected_index = selection[0]

    def picker_is_visible():
        return picker.winfo_manager() == "place"

    def media_entry_color(entry):
        if is_talk_animation(entry):
            return MEDIA_TYPE_COLORS["talk"]
        if is_playlist_file(entry):
            return MEDIA_TYPE_COLORS["playlist"]
        kind = media_kind(entry)
        if kind == "video":
            return MEDIA_TYPE_COLORS["video"]
        if kind == "audio":
            return MEDIA_TYPE_COLORS["music"]
        return MEDIA_TYPE_COLORS["default"]

    def refresh_media_list():
        nonlocal entries, selected_index
        entries = media_entries(current_folder)
        if (
            current_folder == media_root
            and media_root != LEGACY_VIDEO_DIR
            and LEGACY_VIDEO_DIR.is_dir()
        ):
            entries.extend(
                path
                for path in media_entries(LEGACY_VIDEO_DIR)
                if path.is_file()
            )
        video_list.delete(0, "end")
        if current_folder != media_root:
            entries.insert(0, current_folder.parent)
            video_list.insert("end", "[..]")
        for entry in entries:
            if entry == current_folder.parent and current_folder != media_root:
                continue
            if entry.is_dir():
                label = f"[talk] {entry.name}" if is_talk_animation(entry) else f"[folder] {entry.name}"
            elif entry.parent == LEGACY_VIDEO_DIR and media_root != LEGACY_VIDEO_DIR:
                label = f"[videos] {entry.name}"
            elif is_playlist_file(entry):
                label = f"[playlist] {entry.name}"
            else:
                label = entry.name
            video_list.insert("end", label)
            video_list.itemconfigure(
                video_list.size() - 1,
                foreground=media_entry_color(entry),
            )

        selected_index = 0
        if entries:
            video_list.selection_set(0)
            video_list.activate(0)
            video_list.see(0)
            play_button.configure(state="normal")
            status_label.configure(
                text=(
                    f"{current_folder.relative_to(media_root.parent)}\n"
                    "Up/Down: browse   Right: open folder   A/Enter: play\n"
                    "B/Space: pause   X: stop MP3"
                )
            )
        else:
            play_button.configure(state="disabled")
            status_label.configure(
                text=(
                    "No supported media or folders here.\n"
                    "A: open picker   B/Space: pause   X: stop MP3"
                )
            )

    def select_relative(offset):
        nonlocal selected_index
        if active_playlist and not picker_is_visible():
            advance_playlist(offset)
            return
        if not entries:
            return
        selected_index = (selected_index + offset) % len(entries)
        video_list.selection_clear(0, "end")
        video_list.selection_set(selected_index)
        video_list.activate(selected_index)
        video_list.see(selected_index)

    def navigate_list(offset):
        select_relative(offset)
        return "break"

    def navigate_when_picker_hidden(offset):
        if not picker_is_visible():
            select_relative(offset)
        return "break"

    def show_picker(message=None):
        picker.place(relx=1.0, x=-24, y=48, width=320, height=400, anchor="ne")
        picker.lift()
        video_list.focus_set()
        if message:
            status_label.configure(text=message)

    def read_playback_state():
        try:
            return PlaybackState.read_state()
        except (OSError, ValueError) as error:
            status_label.configure(text=f"Could not read playback state: {error}")
            return None

    def enter_folder(folder):
        nonlocal current_folder
        current_folder = folder
        refresh_media_list()

    def open_selected_folder(_event=None):
        update_selection()
        if entries:
            selected_media = entries[selected_index]
            if selected_media.is_dir():
                enter_folder(selected_media)
            elif selected_media == current_folder.parent and current_folder != media_root:
                enter_folder(selected_media)
        return "break"

    def play_media(
        selected_media,
        transition=None,
        playlist_item=False,
        stop_at_seconds=None,
    ):
        nonlocal video_instance, video_player, current_video, current_visual, paused, ended_video
        nonlocal playback_id, pending_transition_video_id, pending_transition_deadline
        nonlocal active_playlist, playlist_index, pending_playlist_sound_id
        has_talk_visual = any(
            is_talk_animation(parent) for parent in selected_media.parents
        )
        if (
            media_kind(selected_media) == "audio"
            and not playlist_item
            and not has_talk_visual
        ):
            PlaybackState.set_sound(str(selected_media))
            picker.place_forget()
            return
        pending_transition_video_id = None
        pending_transition_deadline = 0.0
        if is_talk_animation(selected_media) or media_kind(selected_media) != "video":
            if video_player is not None:
                video_player.stop()
            current_video = selected_media
            paused = False
            ended_video = False
            playback_id += 1
            visual_path = None
            if media_kind(selected_media) == "audio":
                visual_path = next(
                    (
                        parent
                        for parent in selected_media.parents
                        if is_talk_animation(parent)
                    ),
                    None,
                )
            current_visual = str(visual_path) if visual_path is not None else None
            PlaybackState.write_state(
                str(current_video),
                paused,
                playback_id,
                current_visual,
                transition,
                stop_at_seconds,
            )
            video_surface.place_forget()
            picker.place_forget()
            return
        vlc = None
        if video_preview_enabled:
            try:
                import vlc as vlc_module
            except ImportError as error:
                show_picker(f"Could not import VLC: {error}")
                return
            vlc = vlc_module

        current_video = selected_media
        current_visual = None
        paused = False
        ended_video = False
        playback_id += 1
        vlc_exception = vlc.VLCException if vlc is not None else RuntimeError
        try:
            if video_preview_enabled:
                if video_instance is None:
                    video_instance = vlc.Instance(
                        "--avcodec-hw=none",
                        "--avcodec-threads=2",
                        "--no-audio",
                        "--no-video-title-show",
                    )
                    if video_instance is None:
                        raise RuntimeError("VLC could not start")
                    video_player = video_instance.media_player_new()

                video_surface.place(
                    relx=1.0,
                    x=-24,
                    y=24,
                    width=320,
                    height=180,
                    anchor="ne",
                )
                video_surface.lift()
                video_surface.update_idletasks()
                root.update_idletasks()
                if sys.platform.startswith("win"):
                    video_player.set_hwnd(video_surface.winfo_id())
                elif sys.platform == "darwin":
                    video_player.set_nsobject(video_surface.winfo_id())
                else:
                    video_player.set_xwindow(video_surface.winfo_id())

                video_player.stop()
                video_media = video_instance.media_new(str(current_video))
                if media_loops(settings, current_video):
                    video_media.add_option(":input-repeat=65535")
                video_player.set_media(video_media)
                video_player.audio_set_mute(True)
                video_player.audio_set_volume(0)
                if transition is None:
                    if video_player.play() == -1:
                        raise RuntimeError("VLC could not start this video")
                else:
                    pending_transition_video_id = playback_id
                    pending_transition_deadline = (
                        time.monotonic() + transition["duration"] + 2.0
                    )
                video_surface.lift()
            else:
                if video_player is not None:
                    video_player.stop()
                video_surface.place_forget()

            PlaybackState.write_state(
                str(current_video),
                paused,
                playback_id,
                transition=transition,
                stop_at_seconds=stop_at_seconds,
            )
            picker.place_forget()
        except (
            OSError,
            RuntimeError,
            AttributeError,
            tk.TclError,
            vlc_exception,
        ) as error:
            if video_player is not None:
                video_player.stop()
            current_video = None
            paused = False
            video_surface.place_forget()
            if playlist_item:
                active_playlist = ()
                playlist_index = -1
                pending_playlist_sound_id = None
            show_picker(f"Could not start VLC for {selected_media.name}: {error}")

    def play_default_video():
        nonlocal selected_index
        candidate_paths = list(media_root.rglob("*"))
        if media_root != LEGACY_VIDEO_DIR and LEGACY_VIDEO_DIR.is_dir():
            candidate_paths.extend(LEGACY_VIDEO_DIR.rglob("*"))
        default_video = next(
            (
                media_file
                for media_file in candidate_paths
                if media_file.is_file()
                and media_kind(media_file) == "video"
                and media_file.name.casefold() == DEFAULT_VIDEO_NAME.casefold()
            ),
            None,
        )
        if default_video is None:
            show_picker(
                f"Add {DEFAULT_VIDEO_NAME} to the media folder for "
                "automatic playback after media ends."
            )
            return
        if default_video.parent == LEGACY_VIDEO_DIR and media_root != LEGACY_VIDEO_DIR:
            enter_folder(media_root)
        else:
            enter_folder(default_video.parent)
        selected_index = entries.index(default_video)
        video_list.selection_clear(0, "end")
        video_list.selection_set(selected_index)
        video_list.activate(selected_index)
        video_list.see(selected_index)
        play_media(default_video)

    def play_playlist_item(index):
        nonlocal active_playlist, playlist_index, finished_playback_seen
        nonlocal current_video, current_visual, paused, playback_id
        nonlocal pending_playlist_sound_id
        if index < 0:
            index = 0
        if index >= len(active_playlist):
            active_playlist = ()
            playlist_index = -1
            if video_player is not None:
                video_player.stop()
            video_surface.place_forget()
            current_video = None
            current_visual = None
            paused = False
            playback_id += 1
            PlaybackState.write_state(None, False, playback_id)
            show_picker("Playlist finished.")
            return
        playlist_index = index
        finished_playback_seen = None
        item = active_playlist[playlist_index]
        if media_kind(item.path) == "audio":
            pending_playlist_sound_id = PlaybackState.set_sound(str(item.path))
            return
        pending_playlist_sound_id = None
        transition = (
            {
                "effect": item.transition,
                "duration": item.transition_duration,
            }
            if item.transition is not None
            else None
        )
        play_media(
            item.path,
            transition,
            playlist_item=True,
            stop_at_seconds=item.stop_at_seconds,
        )

    def advance_playlist(offset=1):
        if active_playlist:
            play_playlist_item(playlist_index + offset)

    def play_selected(_event=None):
        nonlocal active_playlist, playlist_index
        update_selection()
        if not entries:
            return "break"
        selected_media = entries[selected_index]
        if selected_media == current_folder.parent and current_folder != media_root:
            enter_folder(selected_media)
        elif selected_media.is_dir() and not is_talk_animation(selected_media):
            enter_folder(selected_media)
        elif is_playlist_file(selected_media):
            try:
                active_playlist = load_playlist(selected_media)
            except (OSError, ValueError) as error:
                show_picker(f"Could not load playlist: {error}")
            else:
                playlist_index = -1
                advance_playlist()
        else:
            has_talk_visual = any(
                is_talk_animation(parent) for parent in selected_media.parents
            )
            if media_kind(selected_media) != "audio" or has_talk_visual:
                active_playlist = ()
                playlist_index = -1
            play_media(selected_media)
        return "break"

    def media_button_action(_event=None):
        if (
            current_video is not None
            and is_talk_animation(current_video)
            and not picker_is_visible()
        ):
            show_picker()
            return "break"
        if picker_is_visible():
            return play_selected()
        show_picker()
        return "break"

    def stop_audio(_event=None):
        nonlocal current_video, current_visual, paused, ended_video, playback_id
        nonlocal active_playlist, playlist_index
        nonlocal pending_transition_video_id, pending_transition_deadline
        PlaybackState.set_sound(None)
        if current_video is None or media_kind(current_video) != "audio":
            show_picker("Audio stopped.")
            return "break"
        if video_player is not None:
            video_player.stop()
        current_video = None
        current_visual = None
        paused = False
        ended_video = False
        active_playlist = ()
        playlist_index = -1
        pending_transition_video_id = None
        pending_transition_deadline = 0.0
        playback_id += 1
        PlaybackState.write_state(None, False, playback_id)
        show_picker("Audio stopped.")
        return "break"

    def toggle_pause(_event=None):
        nonlocal paused
        if current_video is None:
            return "break"
        paused = not paused
        if video_player is not None and media_kind(current_video) == "video":
            if paused:
                video_player.set_pause(1)
            else:
                video_player.play()
        PlaybackState.write_state(
            str(current_video),
            paused,
            playback_id,
            current_visual,
        )
        return "break"

    def adjust_voice_volume(change):
        state = read_playback_state()
        if state is None:
            return "break"
        current_level = state.get("voice_output_level")
        if not isinstance(current_level, (int, float)) or isinstance(
            current_level, bool
        ):
            current_level = settings["voice_changer"]["output_level"]
        updated_level = min(1.0, max(0.0, current_level + change))
        PlaybackState.set_voice_output_level(updated_level)
        status_label.configure(
            text=f"Voice volume: {round(updated_level * 100)}%"
        )

    def on_video_list_select(event):
        update_selection(event)
        return "break"

    video_list.bind("<<ListboxSelect>>", on_video_list_select)
    video_list.bind("<Double-Button-1>", play_selected)
    play_button.configure(command=play_selected)
    video_list.bind("<Up>", lambda _event: navigate_list(-1))
    video_list.bind("<Down>", lambda _event: navigate_list(1))
    root.bind("<Up>", lambda _event: navigate_when_picker_hidden(-1))
    root.bind("<Down>", lambda _event: navigate_when_picker_hidden(1))
    root.bind("<Right>", lambda _event: open_selected_folder())
    root.bind("<Return>", play_selected)
    root.bind("<space>", toggle_pause)
    root.bind("<BackSpace>", lambda _event: (show_picker(), "break")[1])
    root.bind("<a>", media_button_action)
    root.bind("<b>", toggle_pause)
    root.bind("<x>", stop_audio)

    refresh_media_list()
    video_list.focus_set()

    try:
        import pygame as pygame_module

        pygame_module.init()
        pygame_module.joystick.init()
        pygame = pygame_module
        if pygame.joystick.get_count():
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
    except ImportError:
        status_label.configure(text="Gamepad unavailable; use keyboard or click to choose.")

    if CAMERA_MODE == "picamera":
        try:
            from picamera2 import Picamera2
            from PIL import Image, ImageTk

            camera = Picamera2()
            camera.configure(
                camera.create_preview_configuration(
                    main={"size": CAMERA_SIZE, "format": "RGB888"}
                )
            )
            camera.start()
        except Exception as error:
            canvas.create_text(
                24,
                24,
                anchor="nw",
                fill="white",
                font=("TkDefaultFont", 18, "bold"),
                text="Camera preview unavailable",
            )
            canvas.create_text(
                24,
                58,
                anchor="nw",
                fill="#b8c2cc",
                font=("TkDefaultFont", 12),
                text=f"Install Picamera2 and Pillow, then check the camera.\n{error}",
            )
            root.mainloop()
            return
    elif CAMERA_MODE != "emulator":
        canvas.create_text(
            24,
            24,
            anchor="nw",
            fill="white",
            font=("TkDefaultFont", 14),
            text='Set CAMERA_MODE to "emulator" or "picamera".',
        )
        root.mainloop()
        return

    def update_preview():
        nonlocal preview_image, preview_item, status_item

        if CAMERA_MODE == "emulator":
            draw_emulator_frame(
                canvas,
                time.monotonic(),
                debug_settings["show_camera_simulation_labels"],
            )
            root.after(FRAME_DELAY_MS, update_preview)
            return

        try:
            frame = camera.capture_array()
            image = Image.fromarray(frame)
            preview_image = ImageTk.PhotoImage(image)

            width = canvas.winfo_width()
            height = canvas.winfo_height()
            x = (width - image.width) // 2
            y = (height - image.height) // 2

            if preview_item is None:
                preview_item = canvas.create_image(x, y, anchor="nw", image=preview_image)
                if debug_settings["show_camera_status_label"]:
                    status_item = canvas.create_text(
                        16,
                        height - 16,
                        anchor="sw",
                        fill="white",
                        font=("TkDefaultFont", 12, "bold"),
                        text="CAMERA VIEW  |  Esc to exit",
                    )
            else:
                canvas.coords(preview_item, x, y)
                canvas.itemconfigure(preview_item, image=preview_image)
                if status_item is not None:
                    canvas.coords(status_item, 16, height - 16)
        except Exception as error:
            canvas.delete("camera_error")
            canvas.create_text(
                16,
                16,
                anchor="nw",
                fill="white",
                font=("TkDefaultFont", 14),
                text=f"Camera stopped: {error}",
                tags="camera_error",
            )
            return

        root.after(FRAME_DELAY_MS, update_preview)

    def poll_gamepad():
        nonlocal joystick, selected_index, ended_video, current_folder
        nonlocal finished_playback_seen
        nonlocal pending_transition_video_id
        nonlocal active_playlist, playlist_index, pending_playlist_sound_id
        if pygame is not None:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED and joystick is None:
                    joystick = pygame.joystick.Joystick(event.device_index)
                    joystick.init()
                elif event.type == pygame.JOYDEVICEREMOVED:
                    joystick = None
                elif event.type == pygame.JOYBUTTONDOWN:
                    if event.button == MEDIA_LIST_BUTTON:
                        media_button_action()
                    elif event.button == PAUSE_BUTTON:
                        toggle_pause()
                    elif event.button == STOP_AUDIO_BUTTON:
                        stop_audio()
                    elif event.button == NEXT_BUTTON:
                        select_relative(1)
                    elif event.button == UP_BUTTON:
                        select_relative(-1)
                    elif event.button == DOWN_BUTTON:
                        select_relative(1)
                    elif event.button == VOLUME_UP_BUTTON:
                        adjust_voice_volume(VOICE_VOLUME_STEP)
                    elif event.button == VOLUME_DOWN_BUTTON:
                        adjust_voice_volume(-VOICE_VOLUME_STEP)
                elif event.type == pygame.JOYHATMOTION:
                    horizontal, vertical = event.value
                    if vertical > 0 or horizontal < 0:
                        select_relative(-1)
                    elif vertical < 0 or horizontal > 0:
                        select_relative(1)

        if video_preview_enabled and pending_transition_video_id is not None:
            state = read_playback_state()
            if state is None:
                root.after(200, poll_gamepad)
                return
            transition_finished = (
                state.get("transition_completed_playback_id")
                == pending_transition_video_id
            )
            timed_out = time.monotonic() >= pending_transition_deadline
            if transition_finished or timed_out:
                pending_transition_video_id = None
                if video_player is not None:
                    try:
                        import vlc
                    except ImportError as error:
                        show_picker(f"Could not import VLC: {error}")
                    else:
                        try:
                            play_result = video_player.play()
                            if play_result == -1:
                                raise RuntimeError(
                                    "VLC rejected the video playback request"
                                )
                            if paused:
                                video_player.set_pause(1)
                        except (RuntimeError, vlc.VLCException) as error:
                            show_picker(
                                f"Could not start VLC for "
                                f"{current_video.name}: {error}"
                            )

        if (
            video_preview_enabled
            and pending_transition_video_id is None
            and current_video is not None
            and media_kind(current_video) == "video"
            and not active_playlist
        ):
            import vlc

            try:
                state = video_player.get_state()
            except vlc.VLCException as error:
                show_picker(
                    f"Could not check VLC playback for "
                    f"{current_video.name}: {error}"
                )
                state = vlc.State.Error
            if state == vlc.State.Error:
                show_picker(f"VLC could not decode: {current_video.name}")
            elif state == vlc.State.Ended and not ended_video:
                ended_video = True
                play_default_video()
            elif state != vlc.State.Ended:
                ended_video = False
        elif (
            not video_preview_enabled
            and current_video is not None
            and media_kind(current_video) == "video"
            and not active_playlist
        ):
            state = read_playback_state()
            if state is None:
                root.after(200, poll_gamepad)
                return
            if (
                state.get("finished_playback_id") == playback_id
                and not ended_video
            ):
                ended_video = True
                play_default_video()
        elif (
            active_playlist
            and pending_transition_video_id is None
            and pending_playlist_sound_id is not None
        ):
            state = read_playback_state()
            if state is None:
                root.after(200, poll_gamepad)
                return
            if state.get("sound_started_playback_id") == pending_playlist_sound_id:
                pending_playlist_sound_id = None
                advance_playlist()
            else:
                sound_error = state.get("sound_start_error")
                if (
                    isinstance(sound_error, dict)
                    and sound_error.get("playback_id") == pending_playlist_sound_id
                ):
                    pending_playlist_sound_id = None
                    active_playlist = ()
                    playlist_index = -1
                    PlaybackState.set_sound(None)
                    show_picker(
                        f"Could not start playlist audio: "
                        f"{sound_error.get('message', 'unknown VLC error')}"
                    )
        elif active_playlist and pending_transition_video_id is None:
            state = read_playback_state()
            if state is None:
                root.after(200, poll_gamepad)
                return
            finished_playback_id = state.get("finished_playback_id")
            if (
                finished_playback_id == playback_id
                and finished_playback_seen != finished_playback_id
            ):
                finished_playback_seen = finished_playback_id
                advance_playlist()
        root.after(25, poll_gamepad)

    root.after(0, update_preview)
    PlaybackState.set_sound(None)
    PlaybackState.write_state(stop_at_seconds=None)
    if settings["startup_playlist"]:
        try:
            active_playlist = load_startup_playlist(
                settings["startup_playlist"],
                Path(__file__).resolve().parent,
            )
        except (OSError, ValueError) as error:
            show_picker(f"Could not load startup playlist: {error}")
        else:
            playlist_index = -1
            advance_playlist()
    root.after(25, poll_gamepad)
    root.mainloop()


if __name__ == "__main__":
    main()
