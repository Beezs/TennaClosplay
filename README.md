# Cosplay display template

Launch both screens together with `Launch.py`:

```bash
python3 Launch.py
```

The launcher starts both screens and closes the other screen when either one exits. You can also run either screen by itself.

This template has two coordinated Python programs:

- `Screen1.py` displays the camera view with a folder-aware media picker over it. Choosing a video keeps the camera full-screen and plays the selected video in a small top-right inset.
- `Screen2.py` displays selected images or plays selected video, MP3, and WAV files with audio.

## Windows camera emulator

Install Python 3 for Windows and make sure the Python launcher (`py`) is available. The standard Python installer includes Tkinter. You can check Tkinter by running:

```powershell
py -3 -m tkinter
```

Close the small test window, open PowerShell in this project folder, and launch both screens:

```powershell
py -3 Launch.py
```

`Screen1.py` starts in emulator mode by default and draws a moving test scene behind the video picker. No Raspberry Pi or camera is needed to try the interface. Press `Esc` in either screen to close both. To use a real Pi camera later, change `CAMERA_MODE` in `Screen1.py` to `"picamera"` and run the program on Raspberry Pi OS.

To play videos and use the filtered microphone on Windows, install the Python gamepad, VLC, Pillow, NumPy, and audio-input packages:

```powershell
py -3 -m pip install pygame python-vlc pillow numpy sounddevice
```

To see the raw button, axis, and D-pad values reported by a controller, run `py -3 show_controller_inputs.py`. The viewer labels buttons by their numeric Pygame index, which is useful for checking a controller with an unusual mapping. Press `Esc` or close the window to exit.

Install the VLC desktop application as well; `python-vlc` requires VLC's native libraries. Video playback uses software H.264 decoding with two decoder threads to reduce frame-buffer allocation failures when both screens play video. If video playback still fails, check the message in Screen1's picker or Screen2; a VLC decoder error can indicate a missing codec or an unsupported/corrupt file. Put media in the `media` folder and organize it in as many nested folders as you like. Screen1 lists folders and supported video (`.mp4`, `.mkv`, `.mov`, `.avi`, `.mpeg`, or `.webm`), image (`.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, or `.webp`), MP3, and WAV files. Existing top-level files in `videos` remain available under a `[videos]` label; if `media` contains no selectable media, Screen1 opens the legacy `videos` folder directly.

On Screen1, use Up/Down and Enter to play the selected item; use Right to enter a folder, including a `.talk` folder, to browse its contents. The picker color-codes `.talk` folders in pink, playlists in purple, videos in cyan, and MP3/WAV music in green; its legend shows the colors. Double-click or use the Play button with a mouse or touch screen. Gamepad A (button 0) or the A key opens the picker when hidden; while it is visible, A/Enter plays the selected item or opens a regular folder. Gamepad B (button 1), the B key, or Space pauses/resumes the current media. Gamepad X (button 2) or the X key stops the current audio file. On the mapped controller, Up/Down are buttons 13/14, Y (button 3) advances playlist entries, and +/− (buttons 6/4) adjust live voice-monitor volume by 5% per press. The controller's D-pad hat also browses, and Backspace shows the picker. While a playlist is playing and the picker is hidden, Y or Up/Down step through playlist entries. Videos play in a small muted top-right inset on Screen1 and full-screen with audio on Screen2. Images display fitted to Screen2. MP3 and WAV files play with audio on Screen2 while Screen1 keeps showing the camera. Add a `default.mp4` file anywhere under `media` to play it automatically when a standalone video finishes. If your controller uses different buttons, adjust the constants near the top of `Screen1.py`. Press `Esc` in either screen to close both.

Playlist files use the `.list.json` suffix and contain a JSON array of paths and optional transition directives. Paths are resolved relative to the playlist file, and media plays in the order listed. Supported entries are video, image, MP3, WAV, and `.talk` folder paths. Playlist MP3/WAV entries start as independent audio overlays; the playlist advances to the next entry as soon as Screen2 accepts the audio, so following video plays underneath it while the sound continues. Add `["Effect", "Fade", seconds]` between media entries to fade Screen2 to black and back as it changes to the following entry; duration must be greater than 0 and no more than 10 seconds. Add `["StopAt", "Video", seconds]` before a video entry to stop that video at the specified playback time and advance to the next item. Both directives can be used before the same video. The transition starts only after the current video or standalone audio has finished: Screen2 fades the outgoing frame to black, prepares the next item, then fades in. A new video remains paused on its first frame until fade-in completes, then resumes with audio. Images and `.talk` animations change while the screen is black and fade in. Videos and standalone audio files advance automatically when playback ends; images and `.talk` animations remain displayed until you press Next. Screen1's inset video preview has audio disabled; media audio plays on Screen2 only. For example, `videos\introduction.list.json` can contain:

```json
[
  "TennaIntro.mp4",
  ["Effect", "Fade", 0.5],
  ["StopAt", "Video", 30],
  "ItsTVTime.mp4",
  "Wispher.talk"
]
```

At the end of a playlist, playback stops and the picker reopens. Invalid JSON, missing paths, and unsupported entries show an error in the picker.

To create a talking animation, make a folder whose name ends in `.talk` (for example, `media\expressions\mad.talk`). Add an `A` folder and a `B` folder inside it, each containing at least one supported image. Screen2 randomly selects an image from the corresponding A or B folder whenever it changes frames: it shows a random A image while quiet and alternates between random A and B images while sound is detected. If `media\TennaTalk.wav` exists, Screen2 also plays it quietly when each new talking burst is detected, mixed through the microphone output. The effect stops when the talk detector returns to quiet (after its short hold interval); the dedicated `TennaTalk.wav` file is not shown in the media picker. Other WAV files can be selected or used in playlists like MP3s. All `.talk` folders use the same `talk_threshold` from `videoSettings.json` and fixed hold time/frame speed defined by constants near the top of `Screen2.py`; thresholds are global, not configurable per animation. Detection uses gain-adjusted microphone peak level, not speech recognition. `talk_threshold` defaults to `0.01`; raise it to reduce sensitivity and lower it to increase sensitivity. The optional debug readout shows the measured peak, gain-adjusted level, and threshold in scientific notation. Screen2 captures the mic and plays the processed signal through separate input/output streams, and automatically checks both input channels when the device provides stereo capture. If the readout stays at `0.00e+00` while Windows' input meter moves, restart Screen2 with the latest changes and check `microphone_device`; if only Windows reports activity but the app still reads zero, reselect the device in Windows Sound settings. Screen2 routes the microphone to the default audio output through a retro bitcrusher effect: reduced bit depth and sample rate, with no added static. Headphones are strongly recommended to prevent speaker feedback.

Playback and voice effects are configured in the root `videoSettings.json`; restart the app after changing it. Set `display_resolution.screen1.width` and `.height` and `display_resolution.screen2.width` and `.height` to the respective window pixel dimensions; each may differ. For example, Screen1 can be `800` by `480` while Screen2 is `1920` by `1080`. Screen1 opens at the left edge and Screen2 opens immediately to its right, using Screen1's width as its horizontal offset, so position the displays beside each other in the operating system's display layout. Dimensions must be positive integers no greater than `16384`; omitted values use the defaults. A previous single-resolution `display_resolution` object with `width` and `height` remains supported and applies to both screens. `startup_playlist` is an ordered array of paths relative to the project root. Entries can be individual video/MP3/WAV files or `.list.json` files; referenced lists are expanded in order, with their paths resolved relative to each list and their fade directives preserved for Screen2. Screen1 starts the resulting sequence automatically and advances when each item ends. Leave the array empty to disable startup playback. Example: `"startup_playlist": ["videos/introduction.list.json"]`. `volume` controls VLC playback volume, `microphone_device` selects a microphone by a unique part of its device name (or `null` for the default), `talk_threshold` controls the global talk-animation sensitivity, and `voice_changer` controls the filtered mic monitor. Add a top-level filename setting such as `"Static.mp4": {"Loop": true}` or `"TennaTalk.wav": {"Loop": true}` to loop that video or audio whenever it plays; use `false` or omit the setting for normal one-shot playback. Matching is by filename, case-insensitively. When a video loops, both screen players repeat it; a playlist `StopAt` directive still stops it at the configured time. Selecting an MP3 or WAV outside a `.talk` folder plays it as a sound overlay without replacing the current video, image, or animation. Audio files stored inside a `.talk` folder retain their talk-image association. On Windows, a name match prefers the WASAPI input endpoint when available; set `microphone_device` to a numeric device index to override endpoint selection. The `debug` options toggle UI overlays: `show_currently_playing` controls the Screen2 media title; `show_playback_status` controls informational Screen2 messages such as the idle/playing status; `show_picker_instructions` hides or shows the keyboard-help text in Screen1's media picker; `show_camera_simulation_labels` controls the emulator's TEST, simulation, and emulator labels; `show_camera_status_label` toggles the live-camera footer; `show_microphone_status` and `show_talk_detection_status` control microphone diagnostics. These options default to true except the microphone diagnostics, which default to false. Playback and camera errors remain visible regardless of these options. Set `voice_changer.enabled` to `false` to disable filtered mic output while keeping microphone detection active. Adjust bit depth and sample-rate reduction for a stronger or subtler bitcrusher. Talk animation hold time and frame speed are fixed in `Screen2.py`. Missing settings use defaults; invalid JSON or out-of-range values stop startup with a clear error.

To play music with a talk image, use Right to enter the `.talk` folder and select an MP3 or WAV stored directly inside it. Screen2 then holds on that folder's A image while the audio plays; pause/resume still works with B or Space. Regular audio files outside `.talk` folders continue to play without a custom image.

## Raspberry Pi setup

Run these in a terminal on Raspberry Pi OS:

```bash
sudo apt update
sudo apt install python3-tk python3-picamera2 python3-pil python3-numpy vlc python3-vlc python3-pygame python3-sounddevice
```

Run the launcher while logged into the graphical desktop:

```bash
python3 Launch.py
```

Press `Esc` in either screen to close both. Both windows open without window borders. Configure each window's dimensions with its `display_resolution.screen1` or `.screen2` width and height in `videoSettings.json`; Screen1 is placed at `+0+0` and Screen2 at `+screen1-width+0`.

`Screen1.py` defaults to `CAMERA_MODE = "emulator"`, which draws an animated test scene and needs no camera or extra Python packages. This lets you try the picker before your hardware arrives; it is not live video. On Raspberry Pi, install the packages above and change the setting to `CAMERA_MODE = "picamera"` to use the attached camera. Images require Pillow; videos, MP3s, and WAVs use VLC. Playback selection, talk-image association, and pause state are synchronized between screens; audio plays from Screen2 only.
