# Screen-Recorder-with-Action-Replay
Screen Recorder with Action Replay &amp; PDF Reports (macOS only) A Python-based tool for macOS that records a selected screen area, replays all mouse and keyboard actions, and generates detailed PDF reports with video comparison and optional timeline.  🖱️ Select area → ⏺️ Record actions → 🔁 Replay → 📊 Compare → 📄 Export reports

Project: Screen Recording (via FFmpeg) + Action Playback (pynput) + PDF Reports

This project allows you to:

Select a screen area (2 clicks — top-left and bottom-right corners).

Record the selected area (via FFmpeg) with the first click inside it.

Automatically replay all mouse and keyboard actions for the second recording.

Save results as video files (capture_1.mp4, capture_2.mp4).

Generate PDF reports:

Optionally — a storyboard (timeline) of the second video.

A frame-by-frame PDF report showing differences between frames (highlighting outlines in the second video if discrepancies exist).

Structure
test.py — the main file that launches the GUI (Tkinter). It displays a popup “Retina?” (for macOS) and then shows the main window with two buttons:

Start/Stop Recording

Replay and Compare, with a checkbox: Generate storyboard for second video?

worker_main.py — a “worker” process (via multiprocessing). It receives commands (start/stop, replay, compare) and calls the corresponding functions from worker_impl.

worker_impl.py — contains all the core logic:

macOS-specific method start_ffmpeg_crop(...) that builds FFmpeg arguments using -f avfoundation and the "Capture screen 0" device.

Listeners (via pynput) for mouse/keyboard during both recordings.

PDF report generation and frame-by-frame comparison.

Utility functions (folder creation, area selection, stopping FFmpeg, etc.).

Dependencies
Python 3.7+ (Python 3.9 or higher recommended).

Python modules (install via pip install ...):

pyautogui (mouse/keyboard control during replay)

pynput (to listen to mouse/keyboard events)

opencv-python (cv2 library for frame processing and highlighting differences)

reportlab (for PDF generation)

multiprocessing (part of Python’s standard library)

FFmpeg — must be installed and accessible from the command line.

On macOS: install via Homebrew → brew install ffmpeg

Installation
Example (macOS):

```
python3 -m venv venv
source venv/bin/activate
pip install pyautogui pynput opencv-python reportlab
# + make sure ffmpeg is installed and available in PATH
```

Launch
Run test.py:

```
python test.py
```
At startup, a popup will appear: “Do you have a Retina display?”

If you're on a Retina display — click Yes (Retina). Logical coordinates will be multiplied by 2.0.

If not — click No (Regular).

The main window appears:

Start/Stop Recording button:

On first press, select an area with 2 clicks.

Then, clicking inside the area will begin recording to capture_1.mp4.

Pressing the button again stops the first recording.

Replay and Compare button:

Clicking inside the area will start capture_2.mp4, replay all recorded mouse/keyboard actions, then stop the recording.

If the checkbox Generate storyboard for second video? is checked, a PDF timeline_2nd_video.pdf will be created.

A frame-by-frame PDF differences_detailed.pdf will also be generated.

In the folder test/session_YYYYmmdd_HHMMSS, you’ll find:

capture_1.mp4 and capture_2.mp4

(optionally) timeline_2nd_video.pdf

differences_detailed.pdf (main report)

macOS Notes
Uses -f avfoundation, device "Capture screen 0".

To allow screen recording and input listening, grant permissions via System Preferences → Security & Privacy.

If FFmpeg prints a warning like Add NSCameraUseContinuityCameraDeviceType ..., it relates to Continuity Camera and can be safely ignored or addressed via Info.plist when packaging the app.

Troubleshooting (macOS)
Ensure FFmpeg is installed and working:

```
ffmpeg -version
```
Make sure the app has screen recording permissions.

Check the console logs (stdout/stderr) — the script prints FFmpeg’s shutdown message.

If you see something like Unrecognized option 'video_size=...', your FFmpeg build might not support that format.

If issues persist, try removing the crop argument or adjust offsets manually.

Additional Notes
Audio recording can be added by extending the FFmpeg arguments in start_ffmpeg_crop (e.g., -f avfoundation:...).

Merging the two recordings is a separate task (e.g., using montage, concat, etc.).

To tweak delays or FPS, adjust fps=10 or time.sleep(...) in the code.

Good luck using it!
