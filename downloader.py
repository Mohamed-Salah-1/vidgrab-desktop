"""yt-dlp backed download engine for VidGrab.

This module contains no UI code. It exposes:

* :func:`build_options` - translate the user's choices into yt-dlp options.
* :class:`AnalyzeWorker` - fetch media metadata without downloading.
* :class:`DownloadWorker` - run a download with live progress callbacks.

The workers are :class:`QObject` subclasses so they can be moved onto a
``QThread`` and emit signals back to the GUI thread.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from typing import Any

import yt_dlp
from PySide6.QtCore import QObject, Signal

MODES = (
    "Video + Audio",
    "Video only",
    "Audio only (MP3)",
    "Audio only (M4A)",
)

QUALITIES = (
    ("Best available", None),
    ("2160p (4K)", 2160),
    ("1440p (2K)", 1440),
    ("1080p (Full HD)", 1080),
    ("720p (HD)", 720),
    ("480p", 480),
    ("360p", 360),
    ("240p", 240),
)

COOKIE_BROWSERS = (
    "No cookies",
    "Chrome",
    "Edge",
    "Firefox",
    "Brave",
    "Opera",
    "Vivaldi",
    "Chromium",
)


def cookies_options(
    browser: str | None,
    cookie_file: str | None = None,
) -> dict[str, Any]:
    """Map UI choices to yt-dlp cookie options.

    A cookies.txt file wins over a browser when both are provided.
    """
    if cookie_file and os.path.exists(cookie_file):
        return {"cookiefile": cookie_file}
    if browser and browser != "No cookies":
        return {"cookiesfrombrowser": (browser.lower(), None, None, None)}
    return {}


_COOKIE_ERROR_MARKERS = (
    "cookie database",
    "could not copy",
    "could not load cookies",
    "failed to decrypt",
    "cannot decrypt",
    "cookie file",
    "does not look like a netscape",
    "cookiesfrombrowser",
)


def is_cookie_error(exc: BaseException | str) -> bool:
    """True when the failure is about reading a browser's cookies.

    Sites keep these cookies locked (Chrome/Edge) or encrypted, so loading
    them can fail even when the video itself is fine. Callers use this to
    retry without cookies instead of aborting the whole operation.
    """
    text = str(exc).lower()
    return any(marker in text for marker in _COOKIE_ERROR_MARKERS)


_SUBTITLE_ERROR_MARKERS = (
    "unable to download video subtitles",
    "unable to download subtitles",
    "some subtitles could not be",
)


_TRANSIENT_HTTP_MARKERS = (
    "http error 403",
    "http error 429",
    "403 forbidden",
    "429 too many requests",
)


def is_transient_http_error(exc: BaseException | str) -> bool:
    """True for HTTP 403/429 failures that are usually transient.

    YouTube's media servers hand out expiring, throttled URLs; a 403 in
    the middle of (or at the start of) a download often clears up when
    the URLs are re-requested a few seconds later. Callers use this to
    retry the whole download with freshly extracted URLs.
    """
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_HTTP_MARKERS)


def is_subtitle_error(exc: BaseException | str) -> bool:
    """True when the failure is about downloading subtitles.

    yt-dlp treats subtitle download errors as fatal (they abort the whole
    job), so callers use this to retry the video without subtitles instead
    of losing an otherwise successful download.
    """
    text = str(exc).lower()
    return any(marker in text for marker in _SUBTITLE_ERROR_MARKERS)


def app_dir() -> str:
    """Directory the app runs from (the EXE's folder when frozen)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg() -> str | None:
    """Locate FFmpeg.

    Search order: ``VIDGRAB_FFMPEG`` env var, the binary embedded by
    PyInstaller, ``ffmpeg.exe`` next to the EXE, then PATH.
    """
    override = os.environ.get("VIDGRAB_FFMPEG")
    if override and os.path.exists(override):
        return override

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        embedded = os.path.join(meipass, "ffmpeg.exe")
        if os.path.exists(embedded):
            return embedded

    bundled = os.path.join(app_dir(), "ffmpeg.exe")
    if os.path.exists(bundled):
        return bundled

    return shutil.which("ffmpeg")


def format_selector(
    mode: str,
    height: int | None,
    override_format_id: str | None = None,
) -> str:
    """Return a yt-dlp ``format`` expression for the chosen controls."""
    if override_format_id:
        if mode == "Video + Audio":
            return f"{override_format_id}+bestaudio/{override_format_id}/best"
        if mode == "Video only":
            return f"{override_format_id}/best"
        return "bestaudio/best"

    cap = f"[height<={height}]" if height else ""
    if mode == "Video + Audio":
        return f"bestvideo{cap}+bestaudio/best{cap}/best"
    if mode == "Video only":
        return f"bestvideo{cap}/best{cap}/best"
    if mode == "Audio only (M4A)":
        return "bestaudio[ext=m4a]/bestaudio/best"
    if mode == "Audio only (MP3)":
        return "bestaudio/best"
    return "best"


def build_options(
    mode: str,
    height: int | None,
    output_dir: str,
    override_format_id: str | None = None,
    subtitles: bool = False,
    playlist: bool = False,
    cookies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a yt-dlp options dictionary for a download request."""
    options: dict[str, Any] = {
        "format": format_selector(mode, height, override_format_id),
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "noplaylist": not playlist,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "overwrites": True,
        "ignoreerrors": False,
        "retries": 3,
        "progress_hooks": [],
        "postprocessor_hooks": [],
    }

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg

    postprocessors: list[dict[str, Any]] = []
    if mode == "Video + Audio":
        options["merge_output_format"] = "mp4"
    elif mode == "Audio only (MP3)":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        )
    elif mode == "Audio only (M4A)":
        postprocessors.append(
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}
        )

    if subtitles:
        options["writesubtitles"] = True
        options["writeautomaticsub"] = True
        options["subtitleslangs"] = ["en", "ar"]
        options["subtitlesformat"] = "srt/best"
        # Pause between subtitle requests; YouTube rate-limits (429) these.
        options["sleep_interval_subtitles"] = 1
        postprocessors.append({"key": "FFmpegEmbedSubtitle"})

    if postprocessors:
        options["postprocessors"] = postprocessors

    if cookies:
        options.update(cookies)

    return options


def summarize(info: dict[str, Any]) -> dict[str, Any]:
    """Reduce a raw yt-dlp info dict to the fields the GUI needs."""
    extractor_key = info.get("extractor_key") or ""
    formats = []
    for fmt in info.get("formats") or []:
        formats.append(
            {
                "id": fmt.get("format_id"),
                "ext": fmt.get("ext"),
                "height": fmt.get("height"),
                "fps": fmt.get("fps"),
                "vcodec": fmt.get("vcodec"),
                "acodec": fmt.get("acodec"),
                "filesize": fmt.get("filesize")
                or fmt.get("filesize_approx"),
                "note": fmt.get("format_note") or "",
                # Per-format dicts from yt-dlp carry no extractor of their
                # own, so propagate the top-level one for the GUI's emoji.
                "extractor": fmt.get("extractor_key") or extractor_key,
            }
        )
    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url"),
        "extractor": extractor_key,
        "is_playlist": info.get("_type") == "playlist",
        "formats": formats,
    }


class AnalyzeWorker(QObject):
    """Fetch metadata for a URL on a background thread."""

    finished = Signal(dict)
    failed = Signal(str)
    note = Signal(str)

    def __init__(
        self, url: str, cookies: dict[str, Any] | None = None
    ) -> None:
        super().__init__()
        self.url = url
        self.cookies = cookies or {}

    def _extract(self, options: dict[str, Any]) -> dict[str, Any]:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(self.url, download=False)

    def run(self) -> None:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "skip_download": True,
            "noplaylist": True,
        }
        options.update(self.cookies)
        try:
            info = self._extract(options)
        except Exception as exc:  # noqa: BLE001 - surface any yt-dlp error
            if self.cookies and is_cookie_error(exc):
                self.note.emit(
                    "Could not read the browser's cookies; retrying "
                    "without them."
                )
                options.pop("cookiefile", None)
                options.pop("cookiesfrombrowser", None)
                try:
                    info = self._extract(options)
                except Exception as exc2:  # noqa: BLE001
                    self.failed.emit(f"{type(exc2).__name__}: {exc2}")
                    return
            else:
                self.failed.emit(f"{type(exc).__name__}: {exc}")
                return
        self.finished.emit(summarize(info))


class DownloadWorker(QObject):
    """Run a single download and stream progress back to the GUI."""

    progress = Signal(dict)
    finished = Signal(str)
    failed = Signal(str)
    note = Signal(str)

    def __init__(self, url: str, options: dict[str, Any]) -> None:
        super().__init__()
        self.url = url
        self.options = dict(options)
        self._has_cookies = bool(
            self.options.get("cookiefile")
            or self.options.get("cookiesfrombrowser")
        )
        self._has_subtitles = bool(
            self.options.get("writesubtitles")
            or self.options.get("writeautomaticsub")
        )

    def _download(self) -> str:
        with yt_dlp.YoutubeDL(self.options) as ydl:
            info = ydl.extract_info(self.url, download=True)
            try:
                return ydl.prepare_filename(info)
            except Exception:  # noqa: BLE001 - fall back to reported path
                return info.get("_filename") or ""

    def _strip_subtitles(self) -> None:
        for key in (
            "writesubtitles",
            "writeautomaticsub",
            "subtitleslangs",
            "subtitlesformat",
            "sleep_interval_subtitles",
        ):
            self.options.pop(key, None)
        postprocessors = self.options.get("postprocessors")
        if postprocessors:
            self.options["postprocessors"] = [
                pp
                for pp in postprocessors
                if pp.get("key") != "FFmpegEmbedSubtitle"
            ]

    def _recover(self, exc: Exception) -> str | None:
        """Retry once after dropping the feature that caused the failure."""
        if self._has_subtitles and is_subtitle_error(exc):
            self.note.emit(
                "Subtitles could not be downloaded (the site rate-limits "
                "these requests); retrying the video without subtitles."
            )
            self._has_subtitles = False
            self._strip_subtitles()
        elif self._has_cookies and is_cookie_error(exc):
            self.note.emit(
                "Could not read the browser's cookies; retrying without them."
            )
            self._has_cookies = False
            self.options.pop("cookiefile", None)
            self.options.pop("cookiesfrombrowser", None)
        else:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return None

        try:
            return self._download()
        except Exception as exc2:  # noqa: BLE001
            self.failed.emit(f"{type(exc2).__name__}: {exc2}")
            return None

    def run(self) -> None:
        def hook(status: dict[str, Any]) -> None:
            if status.get("status") == "downloading":
                self.progress.emit(
                    {
                        "phase": "downloading",
                        "downloaded": status.get("downloaded_bytes") or 0,
                        "total": status.get("total_bytes")
                        or status.get("total_bytes_estimate")
                        or 0,
                        "speed": status.get("speed") or 0,
                        "eta": status.get("eta") or 0,
                        "filename": os.path.basename(
                            status.get("filename") or ""
                        ),
                    }
                )
            elif status.get("status") == "finished":
                self.progress.emit(
                    {
                        "phase": "processing",
                        "filename": os.path.basename(
                            status.get("filename") or ""
                        ),
                    }
                )

        self.options.setdefault("progress_hooks", []).append(hook)
        attempts = 3
        path: str | None = None
        for attempt in range(1, attempts + 1):
            try:
                path = self._download()
                break
            except Exception as exc:  # noqa: BLE001 - retry or recover below
                if is_transient_http_error(exc) and attempt < attempts:
                    wait = attempt * 3
                    short = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                    self.note.emit(
                        f"⚠️ Transient server error ({short}); fetching "
                        f"fresh links and retrying in {wait}s "
                        f"(attempt {attempt + 1}/{attempts}) ..."
                    )
                    time.sleep(wait)
                    continue
                path = self._recover(exc)
                break
        if path is None:
            return
        self.finished.emit(path)
