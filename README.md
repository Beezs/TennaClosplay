# Cosplay display template

Launch both screens together with `Launch.py`. The launcher waits until two physical displays are connected and initialized before starting either screen:

```bash
python3 Launch.py
```

The launcher starts both screens and closes the other screen when either one exits. You can also run either screen by itself.

This template has two coordinated Python programs:

- `Screen1.py` displays the camera view with a folder-aware media picker over it. Choosing a video keeps the camera full-screen and plays the selected video in a small top-right inset.
- `Screen2.py` displays selected images or plays selected video, MP3, and WAV files with audio.

## Run on Windows

Windows is useful for testing the interface and media playback. `Screen1.py` uses its built-in camera emulator by default; a Raspberry Pi camera cannot be used directly from Windows.

1. Install Python 3 for Windows from [python.org](https://www.python.org/downloads/). Make sure the Python launcher (`py`) is installed. Tkinter is included with the standard installer; verify it by running this in PowerShell:

```powershell
py -3 -m tkinter
```

Close the small test window. In PowerShell, change to the project folder (replace the example path with where you saved it), then install the Python packages:

```powershell
cd "C:\path\to\TennaClosplay"
py -3 -m pip install pygame python-vlc pillow numpy sounddevice
```

Install the VLC desktop application too. `python-vlc` is only the Python binding; VLC supplies the native playback libraries and codecs. Pillow is used for images, NumPy and sounddevice for microphone input/output, and pygame for gamepads. Keyboard and mouse controls still work without a gamepad.

Connect two displays and arrange them side by side in Windows **Settings > System > Display** for the paired layout. The app opens Screen1 at the left edge and Screen2 immediately to its right; their window sizes and positions are controlled by `videoSettings.json` (see [Configuration](#configuration)). Then start both screens from the project folder:

```powershell
py -3 Launch.py
```

The emulator draws a moving test scene behind the media picker; it is not a live camera feed. Press `Esc` in either window to close both. Put media in the project `media` folder. You can also use the existing top-level files in `videos`. See [Controls and media](#controls-and-media) below for browsing and playback controls.

To inspect the raw button, axis, and D-pad values reported by a controller, run:

```powershell
py -3 show_controller_inputs.py
```

The viewer labels buttons by their numeric Pygame index, which is useful for checking a controller with an unusual mapping. Press `Esc` or close the window to exit.

Video playback uses software H.264 decoding with two decoder threads to reduce frame-buffer allocation failures. On lower-powered systems such as a Raspberry Pi, setting `video_preview` to `false` avoids decoding the same video a second time for Screen1's small inset; Screen2 continues full-screen playback with audio. If playback fails, check the message in Screen1's picker or Screen2; a VLC decoder error can indicate a missing codec or an unsupported/corrupt file. Organize media in any number of nested folders. Screen1 lists supported video (`.mp4`, `.mkv`, `.mov`, `.avi`, `.mpeg`, or `.webm`), image (`.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, or `.webp`), MP3, and WAV files. Existing top-level files in `videos` remain available under a `[videos]` label; if `media` contains no selectable media, Screen1 opens the legacy `videos` folder directly.

## Controls and media

On Screen1, use Up/Down and Enter to play the selected item; use Right to enter a folder, including a `.talk` folder, to browse its contents. The picker color-codes `.talk` folders in pink, playlists in purple, videos in cyan, and MP3/WAV music in green; its legend shows the colors. Double-click or use the Play button with a mouse or touch screen. Gamepad A (button 0) or the A key opens the picker when hidden; while it is visible, A/Enter plays the selected item or opens a regular folder. Gamepad B (button 1), the B key, or Space pauses/resumes the current media. Gamepad X (button 2) or the X key stops the current audio file. On the mapped controller, Up/Down are buttons 13/14, Y (button 3) advances playlist entries, and +/− (buttons 6/4) adjust live voice-monitor volume by 5% per press. The controller's D-pad hat also browses, and Backspace shows the picker. While a playlist is playing and the picker is hidden, Y or Up/Down step through playlist entries. Videos play full-screen with audio on Screen2; the small muted top-right inset on Screen1 is controlled by `video_preview`. Images display fitted to Screen2. MP3 and WAV files play with audio on Screen2 while Screen1 keeps showing the camera. Add a `default.mp4` file anywhere under `media` to play it automatically when a standalone video finishes. If your controller uses different buttons, adjust the constants near the top of `Screen1.py`. Press `Esc` in either screen to close both.

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

## Configuration

Edit `videoSettings.json` in the project root (next to `Launch.py`) and restart the app for changes to take effect. It must be valid JSON: use double quotes and do not add comments or trailing commas. You can include only the settings you want to change; omitted settings use the defaults in `VideoSettings.py`. Nested settings can be partially specified. Unknown setting names, malformed JSON, or values outside the allowed ranges stop startup with a clear error.

Example for two different display sizes and a playlist that starts automatically:

```json
{
  "display_resolution": {
    "screen1": { "width": 1920, "height": 1080 },
    "screen2": { "width": 1024, "height": 768 }
  },
  "startup_playlist": ["videos/introduction.list.json"]
}
```

| Setting | What it does |
| --- | --- |
| `volume` | VLC media volume, integer from `0` to `100` (default `85`). |
| `video_preview` | Show the muted video inset on Screen1 in addition to Screen2 playback (default `true`). Set to `false` on a Raspberry Pi to avoid decoding each video twice. |
| `display_resolution.screen1` / `.screen2` | Each screen's `width` and `height` in pixels; positive integers up to `16384`. Screen1 opens at `+0+0`; Screen2 opens at `+screen1-width+0`. Arrange the displays side by side in Windows or Raspberry Pi OS. The older `{"width": ..., "height": ...}` form applies one size to both screens. |
| `startup_playlist` | Ordered array of paths relative to the project folder. Entries can be video, MP3, WAV, or `.list.json` playlist files; paths inside a playlist are relative to that playlist. Use `[]` to disable startup playback. |
| `microphone_device` | `null` selects the system default, a string selects an input device whose name contains that text, or an integer selects a device index. Windows prefers a matching WASAPI input endpoint when available; an integer overrides that selection. |
| `talk_threshold` | Global microphone sensitivity for `.talk` animations, from `0` to `1`; higher values require louder input. Default is `0.01`. |
| `voice_changer` | Filtered microphone monitor settings: `enabled` (`true`/`false`), `gain` (`0`–`8`), `output_level` (`0`–`1`), `bit_depth` (integer `2`–`16`), and `sample_rate_reduction` (integer `1`–`64`). The monitor chooses a sample rate supported by both audio devices and retries if an audio stream stops. Set `enabled` to `false` to disable monitor audio while retaining talk detection. |
| `debug` | Boolean switches: `show_currently_playing`, `show_playback_status`, `show_picker_instructions`, `show_camera_simulation_labels`, `show_camera_status_label`, `show_camera_metrics`, `show_microphone_status`, and `show_talk_detection_status`. `show_camera_metrics` displays camera capture FPS and system CPU temperature on Screen1; temperature displays as `N/A` when the system thermal sensor is unavailable. The first five existing display options default to `true`; camera metrics and microphone diagnostics default to `false`. Errors remain visible. |
| Top-level media filename | Add `"Static.mp4": {"Loop": true}` or `"TennaTalk.wav": {"Loop": true}` to repeat that video or audio. Use `"Static.mp4": {"Loop": false}` or omit the filename entry for one-shot playback. Matching is case-insensitive by filename. A playlist `StopAt` directive still stops a looping video. |

Screen1's video inset is muted; media audio plays on Screen2. Selecting an MP3 or WAV outside a `.talk` folder plays it over the current screen content. Audio inside a `.talk` folder retains its associated animation image. Talk-animation hold time and frame speed are fixed in `Screen2.py`.

To play music with a talk image, use Right to enter the `.talk` folder and select an MP3 or WAV stored directly inside it. Screen2 then holds on that folder's A image while the audio plays; pause/resume still works with B or Space. Regular audio files outside `.talk` folders continue to play without a custom image.

## Raspberry Pi setup (Python 3.13)

### First-time setup

1. Install a Raspberry Pi OS desktop release that provides Python 3.13. Connect the displays side by side and the camera to the Pi, then power it on and log in to the desktop. Copy the project folder to the Pi (for example, using a USB drive or network share). The app opens graphical windows, so start it from the desktop rather than a text-only console.
2. Open Terminal and change to the folder containing this project. For example, if the folder is `TennaClosplay` in your home directory:

```bash
cd ~/TennaClosplay
```

If you put it elsewhere, use that folder's path instead. Confirm the Python version:

```bash
python3.13 --version
```

It should report Python 3.13. Install the system packages once:

```bash
sudo apt update
sudo apt install python3-tk python3-picamera2 python3-pil python3-numpy vlc python3-vlc python3-pygame python3-sounddevice
```

On a Raspberry Pi 4, set `"video_preview": false` in `videoSettings.json` to avoid software-decoding the same video on both screens. Screen2 still plays the video full-screen with audio; Screen1 continues showing the camera.

The default `CAMERA_MODE = "emulator"` in `Screen1.py` draws a test scene and does not use the camera. To use a supported camera connected to the Pi, edit `Screen1.py` and change that line to:

```python
CAMERA_MODE = "picamera"
```

Save the file. Leave it as `"emulator"` if you want to test without camera hardware.

### Start the screens

```bash
cd ~/TennaClosplay
python3.13 Launch.py
```

Run the command after logging into the desktop whenever you want to start the display; this README does not set up automatic launch at boot. It starts both borderless windows together. Press `Esc` in either window to close both. Set each window size in `videoSettings.json`; Screen1 is placed at `+0+0` and Screen2 at `+screen1-width+0`. Images use Pillow; video and audio playback use VLC. Playback selection, talk-image association, and pause state are synchronized between screens; audio plays from Screen2 only.
