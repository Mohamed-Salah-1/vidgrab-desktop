# VidGrab

A small Windows desktop app for downloading videos and audio from YouTube,
TikTok, Facebook, Dailymotion, Vimeo, Twitch and many other sites. It is a
friendly front-end for the [yt-dlp](https://github.com/yt-dlp/yt-dlp) engine,
with a native Qt interface (PySide6).

## Features

- Paste a URL, **Analyze** to see every available format (resolution, fps,
  codecs, size), then download.
- Modes: **Video + Audio**, **Video only**, **Audio only (MP3)**,
  **Audio only (M4A)**.
- Quality cap (Best, 4K, 2K, 1080p, 720p, 480p, 360p, 240p).
- Optional **subtitles** (Arabic + English) and **playlist** support.
- Live progress with speed and ETA.
- **Cookies support** for videos that require a logged-in session
  (Vimeo, private Facebook, age-restricted YouTube, ...).
- **FFmpeg is bundled**, so merging high-resolution video with audio and
  converting to MP3/M4A works with no extra setup.

## Quick start

1. Download `VidGrab.exe` (single file), or unzip
   `VidGrab-windows-x64.zip` and run `VidGrab\VidGrab.exe` (faster startup).
2. Double-click it (no installation required).
3. Paste a video URL and click **Analyze**.
4. Choose a format/mode/quality, pick a folder, and click **Download**.

If Windows SmartScreen shows a warning (the app is not code-signed), click
**More info -> Run anyway**.

## FFmpeg

High-resolution video (1080p, 4K) is usually served by sites as *separate*
video and audio streams. FFmpeg combines (`muxes`) them into one file and also
performs the MP3/M4A conversion.

- The release build already **embeds FFmpeg**; nothing to install.
- When running from source, VidGrab looks for FFmpeg in this order:
  1. the `VIDGRAB_FFMPEG` environment variable,
  2. `ffmpeg.exe` next to the app,
  3. `ffmpeg` on your `PATH`.
- If FFmpeg is missing, high-resolution merges and audio conversion will fail.

## Cookies (for videos that require login)

### The idea, in plain words

When you log in to a website (Vimeo, Facebook, YouTube, ...), the site gives
your browser a small file called a **cookie** that acts like a wristband: it
tells the site "this visitor is logged in." Your browser wears that wristband
on every request.

VidGrab (through yt-dlp) is a separate program with **no wristband**. For
public videos that is fine. But for login-only content such as Vimeo, private
Facebook videos, or age-restricted YouTube, the site sees no wristband and
refuses to serve the video -- which is why you may see an error like
*"The web client only works when logged-in."*

The **Cookies** controls let you lend VidGrab *your* browser's wristband, so
the site treats the download like a normal logged-in view.

> A cookie is effectively a session key. Treat it like a password and never
> share your `cookies.txt` with anyone.

### How to use it in VidGrab

You have two options (the **Cookies** row under the main controls):

1. **From your browser** -- open the **Cookies** dropdown and pick the browser
   you are logged into the site with (Chrome, Edge, Firefox, Brave, Opera,
   Vivaldi, Chromium).
   - On Windows, **close that browser first**: while it is running it locks
     the cookie database, so VidGrab cannot read it.
   - Recent Chrome/Edge versions encrypt cookies in a way that can block
     reading. If the browser option fails, use a cookies file instead.

2. **From a cookies file** -- click **Cookies file...** and select a
   `cookies.txt` in Netscape format. You can export one with a browser
   extension such as *"Get cookies.txt LOCALLY"*. This is the most reliable
   method.

Steps:

1. Log in to the site in your browser.
2. In VidGrab, choose your browser in **Cookies**, or select a `cookies.txt`.
3. Paste the URL, click **Analyze**, then **Download**.

A cookies file always takes priority over the browser dropdown.

### When do I need cookies?

- **Usually needed:** Vimeo, private / friends-only Facebook videos,
  age-restricted or member-only YouTube, some Instagram content.
- **Usually not needed:** public YouTube, public TikTok, Dailymotion,
  Twitch VODs.

If a download fails because a login is required, VidGrab shows a hint telling
you to pick a browser or a cookies file.

## Supported platforms

Anything yt-dlp supports -- several thousand sites -- including ▶️ YouTube,
🎵 TikTok, 📘 Facebook, 📺 Dailymotion, 🎥 Vimeo, 🟣 Twitch, 📷 Instagram and more. 
Some sites require cookies (see above). Extractor behavior can change when sites update;
keeping yt-dlp current is the best fix.

## Run from source

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Build the executable

First put a static `ffmpeg.exe` in `.\vendor\ffmpeg.exe` (a Gyan "essentials"
Windows 64-bit build works well and includes the MP3 encoder). Then choose a
layout:

```powershell
# Single file (portable, easy to share; ~90 MB; startup ~4-7s)
.\build.ps1
# Output: .\dist\VidGrab.exe

# Folder (fast startup ~1s; share the generated zip)
.\build.ps1 -Onedir
# Output: .\dist\VidGrab\VidGrab.exe  +  .\dist\VidGrab-windows-x64.zip
```

`vendor\ffmpeg.exe` is embedded in both layouts; at runtime the app finds it
in its extraction folder and falls back to an `ffmpeg.exe` next to the EXE,
then to `PATH`.

**Which to ship?** The single file is the simplest to hand out. The folder
build starts almost instantly (no per-launch extraction) and zips to about
the same download size, so it is nicer for a live demo.

## Troubleshooting

- **"Analyze" does nothing / no formats** -- the site may require login
  (use Cookies), the URL may be unsupported, or the extractor may be outdated
  (update yt-dlp).
- **High-res download fails or ends up silent** -- FFmpeg was not found.
  Use the bundled build, or install FFmpeg and put it on `PATH`.
- **Subtitles fail with "HTTP Error 429: Too Many Requests"** -- YouTube
  rate-limits subtitle downloads. VidGrab automatically retries without the
  subtitles so the video still downloads (the log shows a note). To get
  subtitles reliably, wait a little and retry, or add cookies (logged-in
  requests are rate-limited less).
- **"Could not copy Chrome cookie database"** -- Chrome and Edge lock and
  encrypt their cookie store while the browser is running, so VidGrab cannot
  read it. Fully close the browser (check Task Manager for leftover
  background processes) and retry, or use the **Cookies file...** button with
  a `cookies.txt` export. VidGrab automatically retries without cookies, so
  public videos still download; only login-gated videos are affected.
- **TikTok fails with "no impersonate target"** -- the browser-impersonation
  library is missing. In the packaged app it ships with the app; from source
  install `yt-dlp[default,curl-cffi]`.

## Legal

This tool is intended for downloading content you are allowed to save (your
own uploads, public-domain or openly licensed material, or content whose
terms permit it). Downloading may violate a site's Terms of Service and local
law; you are responsible for how you use it. Do not use it to circumvent DRM
or licenses.

## Credits and licenses

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) -- Unlicense.
- [Qt for Python (PySide6)](https://www.qt.io/qt-for-python) -- LGPLv3.
- [FFmpeg](https://ffmpeg.org/) -- the bundled build is **GPL**; FFmpeg and
  its source are available from the FFmpeg project. Redistributing an
  FFmpeg-linked application must comply with the GPL.
