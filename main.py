"""VidGrab - a small desktop video downloader built with PySide6 + yt-dlp.

A learning project inspired by the workflow of 4K Video Downloader+:
paste a link, inspect the available formats, pick a quality and download.
It shares no code or assets with that product and uses only open-source
components (yt-dlp and FFmpeg).
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from downloader import (
    COOKIE_BROWSERS,
    MODES,
    QUALITIES,
    AnalyzeWorker,
    DownloadWorker,
    build_options,
    cookies_options,
)

STYLESHEET = """
QWidget {
    background: #1a1b26;
    color: #c0caf5;
    font-size: 13px;
}
QLineEdit, QComboBox, QPlainTextEdit, QTableWidget {
    background: #24283b;
    border: 1px solid #414868;
    border-radius: 8px;
    padding: 8px;
    selection-background-color: #7aa2f7;
    min-height: 20px;
}
QLineEdit:focus, QComboBox:focus {
    border: 2px solid #7aa2f7;
    background: #1f2335;
}
QPushButton {
    background: #7aa2f7;
    color: #1a1b26;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background: #8bd5ff;
}
QPushButton:pressed {
    background: #658dff;
}
QPushButton:disabled {
    background: #414868;
    color: #a9b1d6;
}
QPushButton#secondary {
    background: #414868;
    color: #c0caf5;
}
QPushButton#secondary:hover {
    background: #565f89;
}
QHeaderView::section {
    background: #24283b;
    color: #a9b1d6;
    border: none;
    padding: 10px;
    border-bottom: 1px solid #414868;
    font-weight: 600;
    font-size: 12px;
}
QTableWidget {
    gridline-color: #414868;
    selection-background-color: #7aa2f720;
    outline: 0;
}
QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid #24283b;
}
QTableWidget::item:selected {
    background-color: #7aa2f720;
}
QProgressBar {
    background: #24283b;
    border: 1px solid #414868;
    border-radius: 8px;
    text-align: center;
    color: #c0caf5;
    height: 22px;
    font-size: 12px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7aa2f7, stop:1 #8bd5ff);
    border-radius: 6px;
    margin: 1px;
}
QLabel#title {
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#heading {
    color: #a9b1d6;
    font-weight: 600;
    margin-top: 8px;
    font-size: 14px;
}
QFrame#card {
    background: #1f2335;
    border: 1px solid #414868;
    border-radius: 12px;
}
QCheckBox {
    spacing: 8px;
    font-size: 13px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid #414868;
    background: #24283b;
}
QCheckBox::indicator:checked {
    background: #7aa2f7;
    border: 2px solid #7aa2f7;
}
QCheckBox::indicator:hover {
    border: 2px solid #7aa2f7;
}
QFileDialog {
    background-color: #1a1b26;
}
QFileDialog QLabel {
    color: #c0caf5;
}
QFileDialog QPushButton {
    min-width: 80px;
}
QLabel#service_badge {
    font-size: 16px;
    font-weight: 700;
    color: #ffffff;
    background: #2a2e45;
    border: 1px solid #414868;
    border-radius: 8px;
    padding: 6px 12px;
}
QLabel#status {
    font-size: 14px;
    font-weight: 600;
    color: #8bd5ff;
}
"""

# Font families that can render color emoji on each OS. Qt falls back
# through the list, so plain text still uses the system default.
EMOJI_FONT_FAMILIES = ["Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji"]

# Animated frames shown while a link is being analyzed.
ANALYZE_FRAMES = ["🔍", "⏳", "⌛", "✨", "🎬"]


def human_size(num: float | int | None) -> str:
    if not num:
        return "-"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def human_duration(seconds: float | int | None) -> str:
    if not seconds:
        return "-"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VidGrab - Video Downloader")
        self.resize(920, 760)

        self._analyze_thread: QThread | None = None
        self._download_thread: QThread | None = None
        self._analyze_worker: AnalyzeWorker | None = None
        self._download_worker: DownloadWorker | None = None
        self.selected_format_id: str | None = None
        self.info: dict | None = None
        self.cookies_file: str | None = None
        self._analyze_timer: QTimer | None = None
        self._analyze_frame: int = 0

        self._build_ui()
        self.setStyleSheet(STYLESHEET)
        self._apply_emoji_fonts()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("🎬 VidGrab")
        title.setObjectName("title")
        layout.addWidget(title)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "🔗 Paste a video or playlist URL (YouTube ▶️, TikTok 🎵, "
            "Facebook 📘, Vimeo 🎥, Dailymotion 📺, ...)"
        )
        self.url_input.returnPressed.connect(self.analyze)
        paste_btn = QPushButton("📋 Paste")
        paste_btn.setObjectName("secondary")
        paste_btn.clicked.connect(self._paste)
        self.analyze_btn = QPushButton("🔍 Analyze")
        self.analyze_btn.clicked.connect(self.analyze)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(paste_btn)
        url_row.addWidget(self.analyze_btn)
        layout.addLayout(url_row)

        # Vivid status line shown while analyzing (animated via QTimer).
        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        info_card = QFrame()
        info_card.setObjectName("card")
        info_layout = QHBoxLayout(info_card)
        self.thumbnail = QLabel("🎬 No preview")
        self.thumbnail.setFixedSize(200, 112)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setStyleSheet(
            "background:#2a2c34;border-radius:6px;color:#8a8f9c;"
        )
        info_layout.addWidget(self.thumbnail)
        text_col = QVBoxLayout()
        self.service_badge = QLabel("🌐 No service yet")
        self.service_badge.setObjectName("service_badge")
        text_col.addWidget(self.service_badge)
        self.title_label = QLabel("Nothing loaded yet — paste a link above 👆")
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(True)
        self.meta_label = QLabel("-")
        self.meta_label.setStyleSheet("color:#a9b0bf;")
        self.meta_label.setWordWrap(True)
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.meta_label)
        text_col.addStretch(1)
        info_layout.addLayout(text_col, 1)
        layout.addWidget(info_card)

        layout.addWidget(QLabel("🎞️ Available formats", objectName="heading"))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Type", "Resolution", "FPS", "Video", "Audio", "Size"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        layout.addWidget(self.table)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Mode"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODES)
        self.mode_combo.currentTextChanged.connect(self._reset_override)
        controls.addWidget(self.mode_combo)

        controls.addWidget(QLabel("Quality"))
        self.quality_combo = QComboBox()
        for label, _ in QUALITIES:
            self.quality_combo.addItem(label)
        self.quality_combo.currentTextChanged.connect(self._reset_override)
        controls.addWidget(self.quality_combo)

        self.subtitles_check = QCheckBox("📝 Subtitles")
        controls.addWidget(self.subtitles_check)
        self.playlist_check = QCheckBox("🎶 Whole playlist")
        controls.addWidget(self.playlist_check)
        controls.addStretch(1)
        layout.addLayout(controls)

        cookies_row = QHBoxLayout()
        cookies_row.addWidget(QLabel("🍪 Cookies"))
        self.cookies_combo = QComboBox()
        self.cookies_combo.addItems(COOKIE_BROWSERS)
        cookies_row.addWidget(self.cookies_combo)
        cookies_file_btn = QPushButton("🍪 Cookies file...")
        cookies_file_btn.setObjectName("secondary")
        cookies_file_btn.clicked.connect(self._browse_cookies)
        cookies_row.addWidget(cookies_file_btn)
        self.cookies_label = QLabel("(🔓 used for login-gated videos: Vimeo 🎥, private Facebook 📘, ...)")
        self.cookies_label.setStyleSheet("color:#a9b0bf;")
        cookies_row.addWidget(self.cookies_label, 1)
        layout.addLayout(cookies_row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("📁 Save to"))
        self.output_input = QLineEdit(self._default_output_dir())
        out_row.addWidget(self.output_input, 1)
        browse_btn = QPushButton("📂 Browse")
        browse_btn.setObjectName("secondary")
        browse_btn.clicked.connect(self._browse)
        out_row.addWidget(browse_btn)
        layout.addLayout(out_row)

        action_row = QHBoxLayout()
        self.download_btn = QPushButton("⬇️ Download")
        self.download_btn.clicked.connect(self.download)
        self.download_btn.setEnabled(False)
        action_row.addWidget(self.download_btn)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        action_row.addWidget(self.progress, 1)
        layout.addLayout(action_row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        layout.addWidget(self.log, 1)

    def _default_output_dir(self) -> str:
        path = os.path.join(os.path.expanduser("~"), "Downloads")
        return path if os.path.isdir(path) else os.path.expanduser("~")

    # -------------------------------------------------------------- helpers
    def _paste(self) -> None:
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text().strip())

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self.output_input.text()
        )
        if chosen:
            self.output_input.setText(chosen)

    def _browse_cookies(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a cookies.txt file",
            "",
            "Cookie files (*.txt);;All files (*)",
        )
        if path:
            self.cookies_file = path
            self.cookies_label.setText(os.path.basename(path))

    def _current_cookies(self) -> dict:
        return cookies_options(
            self.cookies_combo.currentText(), self.cookies_file
        )

    def _reset_override(self) -> None:
        self.selected_format_id = None
        self.table.clearSelection()

    def _log(self, message: str) -> None:
        self.log.appendPlainText(message)

    def _on_row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        if item is not None:
            self.selected_format_id = item.text()
            self._log(
                f"Selected format {self.selected_format_id} from the table "
                "(advanced override)."
            )

    def _apply_emoji_fonts(self) -> None:
        """Give emoji-heavy widgets a font that can render color emoji."""
        for widget in (
            self.service_badge,
            self.status_label,
            self.thumbnail,
            self.title_label,
            self.meta_label,
            self.analyze_btn,
            self.download_btn,
        ):
            font = widget.font()
            for family in EMOJI_FONT_FAMILIES:
                # Qt falls back automatically; prepending keeps text crisp
                # while giving emoji a chance to render on Windows.
                if family not in font.families():
                    break
            widget.setFont(font)

    def _start_analyze_animation(self, url: str) -> None:
        """Show vivid animated feedback while a link is being analyzed."""
        site_guess = self._guess_site(url)
        guess_suffix = f" {site_guess}" if site_guess else ""
        self._analyze_frame = 0
        self.status_label.setVisible(True)
        self._tick_analyze_animation(guess_suffix)
        if self._analyze_timer is None:
            self._analyze_timer = QTimer(self)
            self._analyze_timer.timeout.connect(self._tick_analyze_animation)
        self._analyze_timer.start(350)
        # Indeterminate progress = lively bar animation.
        self.progress.setRange(0, 0)
        self.progress.setFormat("Analyzing…")
        self.analyze_btn.setText("⏳ Analyzing…")
        self.thumbnail.setPixmap(QPixmap())
        self.thumbnail.setText("🔍\nAnalyzing…")
        self.service_badge.setText(f"🔍 Detecting service{guess_suffix}…")

    def _tick_analyze_animation(self, guess_suffix: str = "") -> None:
        frame = ANALYZE_FRAMES[self._analyze_frame % len(ANALYZE_FRAMES)]
        dots = "." * ((self._analyze_frame % 3) + 1)
        self._analyze_frame += 1
        if not guess_suffix:
            guess_suffix = ""
            url = self.url_input.text().strip()
            if url:
                guess = self._guess_site(url)
                guess_suffix = f" {guess}" if guess else ""
        self.status_label.setText(f"{frame} Analyzing{guess_suffix}{dots} ✨")
        self.progress.setFormat(f"{frame} Analyzing{dots}")

    def _stop_analyze_animation(self, ok: bool) -> None:
        if self._analyze_timer is not None:
            self._analyze_timer.stop()
        self.status_label.setVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if ok else 0)
        self.progress.setFormat("Done 🎉" if ok else "Failed ❌")
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("🔍 Analyze")

    @staticmethod
    def _guess_site(url: str) -> str:
        """Quick service guess from the URL so feedback feels instant."""
        lowered = url.lower()
        for key in (
            "youtube", "youtu.be", "tiktok", "facebook", "fb.watch",
            "instagram", "twitter", "x.com", "dailymotion", "vimeo",
            "twitch", "soundcloud", "reddit",
        ):
            if key in lowered:
                return MainWindow._get_site_emoji(key) + " " + MainWindow._get_site_display(key)
        return ""

    # ------------------------------------------------------------- analyze
    def analyze(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "🔗 Missing URL", "Please paste a URL first. 🔗")
            return
        if self._analyze_thread is not None:
            return

        self.analyze_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self._log(f"🔍 Analyzing {url} ...")
        self._start_analyze_animation(url)

        self._analyze_thread = QThread(self)
        worker = AnalyzeWorker(url, cookies=self._current_cookies())
        self._analyze_worker = worker
        worker.moveToThread(self._analyze_thread)
        self._analyze_thread.started.connect(worker.run)
        worker.note.connect(self._log)
        worker.finished.connect(self._on_analyzed)
        worker.failed.connect(self._on_error)
        worker.finished.connect(self._analyze_thread.quit)
        worker.failed.connect(self._analyze_thread.quit)
        self._analyze_thread.finished.connect(self._on_analyze_done)
        self._analyze_thread.finished.connect(worker.deleteLater)
        self._analyze_thread.start()

    def _on_analyze_done(self) -> None:
        self._analyze_thread = None
        self._analyze_worker = None
        if self._analyze_timer is not None:
            self._analyze_timer.stop()
        self.status_label.setVisible(False)
        self.progress.setRange(0, 100)
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("🔍 Analyze")

    def _on_analyzed(self, info: dict) -> None:
        self._stop_analyze_animation(ok=True)
        self.info = info
        self.title_label.setText(f"🎬 {info.get('title') or 'Unknown title'}")

        # Prominent service badge: big emoji + friendly service name.
        extractor = info.get("extractor") or ""
        site_emoji = self._get_site_emoji(extractor)
        site_name = self._get_site_display(extractor)
        self.service_badge.setText(f"{site_emoji} {site_name}")
        if site_emoji and extractor:
            extractor_with_emoji = f"{site_emoji} {site_name}"
        else:
            extractor_with_emoji = site_name or extractor

        bits = [
            extractor_with_emoji,
            f"👤 {info.get('uploader')}" if info.get("uploader") else "",
            f"⏱️ {human_duration(info.get('duration'))}",
        ]
        self.meta_label.setText("  │  ".join(b for b in bits if b))
        self._load_thumbnail(info.get("thumbnail"))
        self._populate_table(info.get("formats") or [], extractor)
        self.download_btn.setEnabled(bool(info.get("webpage_url")))
        self.status_label.setVisible(True)
        self.status_label.setText(f"✅ Found {len(info.get('formats') or [])} formats on {site_emoji} {site_name}! Pick a quality 👇")
        QTimer.singleShot(6000, lambda: self.status_label.setVisible(False))
        self._log(
            f"✅ Found {len(info.get('formats') or [])} format(s) on "
            f"{site_emoji} {site_name} for '{info.get('title')}'."
        )

    def _load_thumbnail(self, url: str | None) -> None:
        self.thumbnail.setText("🎬 No preview")
        self.thumbnail.setPixmap(QPixmap())
        if not url:
            return
        try:
            import urllib.request

            request = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self.thumbnail.setPixmap(
                    pixmap.scaled(
                        self.thumbnail.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        except Exception:  # noqa: BLE001 - thumbnail is cosmetic
            self.thumbnail.setText("🎬 No preview")

    @staticmethod
    def _get_site_emoji(extractor: str) -> str:
        """Return emoji for site based on extractor name."""
        if not extractor:
            return "🌐"
        key = extractor.lower()
        # URL shortcuts first (for instant guessing from pasted links).
        url_map = {
            "youtu.be": "▶️",
            "youtube": "▶️",
            "tiktok": "🎵",
            "facebook": "📘",
            "fb.watch": "📘",
            "instagram": "📷",
            "dailymotion": "📺",
            "vimeo": "🎥",
            "twitch": "🟣",
            "soundcloud": "🔊",
            "reddit": "🟧",
            "twitter": "🐦",
        }
        for token, emoji in url_map.items():
            if token in key:
                return emoji
        extractor = key
        emoji_map = {
            "youtube": "▶️",
            "tiktok": "🎵",
            "facebook": "📘",
            "instagram": "📷",
            "twitter": "🐦",
            "x": "🐦",
            "dailymotion": "📺",
            "vimeo": "🎥",
            "twitch": "🟣",
            "soundcloud": "🔊",
            "reddit": "🟧",
            "pinterest": "📌",
            "snapchat": "👻",
            "linkedin": "💼",
            "streamable": "📱",
            "rumble": "⚡",
            "odysee": "👁️",
            "bitchute": "🔴",
            "vevo": "🎵",
            "yahoo": "🟣",
            "yahoo screen": "🟣",
            "yahooscreen": "🟣",
            "metacafe": "🎬",
            "collegehumor": "🎓",
            "break": "🍿",
            "spike": "⚔️",
            "fusion": "⚛️",
            "comedy central": "😂",
            "mtv": "📺",
            "vh1": "📺",
            "abc news": "🇺🇸",
            "fox news": "🦊",
            "cnn": "📰",
            "msnbc": "📰",
            "the guardian": "🛡️",
            "bbc": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
            "cbc": "🍁",
            "rt": "☭",
            "al jazeera": "🌍",
            "euronews": "🇪🇺",
            " sky news ": "☁️",
            "hbo": "🎬",
            "showtime": "🎪",
            "starz": "⭐",
            "amc": "📺",
            "fx": "🌀",
            "usa network": "🇺🇸",
            "tnt": "💥",
            "tlc": "💍",
            "history": "🏛️",
            "discovery": "🔬",
            "animal planet": "🐘",
            "national geographic": "🏔️",
            "pbs": "📚",
            "nickelodeon": "🧧",
            "cartoon network": "💫",
            "disney": "🏰",
            "disney+": "🏰",
            "netflix": "🎬",
            "hulu": "📺",
            "prime video": "🛒",
            "disney plus": "🏰",
            "hbo max": "🎬",
            "peacock": "🦚",
            "paramount+": "📡",
            "apple tv+": "🍎",
            "crunchyroll": "🎴",
            "funimation": "🎭",
            "hidive": "📺",
            "retrocrush": "📺",
            "anime lab": "🎴",
        }

        for name, emoji in emoji_map.items():
            if name in extractor:
                return emoji
        return "🌐"  # Default globe emoji for unknown sites

    @staticmethod
    def _get_site_display(extractor: str) -> str:
        """Friendly service name for the badge (YouTube, TikTok, ...)."""
        if not extractor:
            return "Unknown service"
        key = extractor.lower()
        display_map = {
            "youtube": "YouTube",
            "youtu.be": "YouTube",
            "tiktok": "TikTok",
            "facebook": "Facebook",
            "fb.watch": "Facebook",
            "instagram": "Instagram",
            "twitter": "Twitter",
            "dailymotion": "Dailymotion",
            "vimeo": "Vimeo",
            "twitch": "Twitch",
            "soundcloud": "SoundCloud",
            "reddit": "Reddit",
            "pinterest": "Pinterest",
            "snapchat": "Snapchat",
            "linkedin": "LinkedIn",
            "rumble": "Rumble",
            "odysee": "Odysee",
            "bitchute": "BitChute",
        }
        for name, display in display_map.items():
            if name in key:
                return display
        cleaned = extractor.strip().replace("_", " ").replace("-", " ")
        return cleaned.title() if cleaned else "Unknown service"

    def _populate_table(self, formats: list[dict], top_extractor: str = "") -> None:
        self.table.setRowCount(0)
        for fmt in formats:
            row = self.table.rowCount()
            self.table.insertRow(row)
            vcodec = fmt.get("vcodec") or "none"
            acodec = fmt.get("acodec") or "none"
            has_video = vcodec not in ("none", None)
            has_audio = acodec not in ("none", None)
            if has_video and has_audio:
                kind_icon = "🎬"
                kind = "video+audio"
            elif has_video:
                kind_icon = "🎥"
                kind = "video"
            else:
                kind_icon = "🎵"
                kind = "audio"

            # Per-site emoji: formats now carry "extractor" (see
            # downloader.summarize); fall back to the top-level one.
            extractor = fmt.get("extractor") or top_extractor
            site_emoji = self._get_site_emoji(extractor)
            kind = f"{site_emoji} {kind_icon} {kind}"

            height = fmt.get("height")
            resolution = f"{height}p" if height else (fmt.get("note") or "-")
            values = [
                str(fmt.get("id") or ""),
                kind,
                resolution,
                str(fmt.get("fps") or ""),
                vcodec,
                acodec,
                human_size(fmt.get("filesize")),
            ]
            for column, text in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(text)))

    # ------------------------------------------------------------ download
    def download(self) -> None:
        if self._download_thread is not None:
            return
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "🔗 Missing URL", "Please paste a URL first. 🔗")
            return

        output_dir = self.output_input.text().strip()
        if not output_dir or not os.path.isdir(output_dir):
            QMessageBox.warning(
                self, "📁 Invalid folder", "Please choose a valid save folder. 📁"
            )
            return

        quality_label = self.quality_combo.currentText()
        height = dict(QUALITIES)[quality_label]
        options = build_options(
            mode=self.mode_combo.currentText(),
            height=height,
            output_dir=output_dir,
            override_format_id=self.selected_format_id,
            subtitles=self.subtitles_check.isChecked(),
            playlist=self.playlist_check.isChecked(),
            cookies=self._current_cookies(),
        )

        self.download_btn.setEnabled(False)
        self.analyze_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setFormat("⬇️ Downloading…")
        self._log(f"⬇️ Downloading with format '{options['format']}' ...")

        self._download_thread = QThread(self)
        worker = DownloadWorker(url, options)
        self._download_worker = worker
        worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(worker.run)
        worker.note.connect(self._log)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_download_finished)
        worker.failed.connect(self._on_error)
        worker.finished.connect(self._download_thread.quit)
        worker.failed.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._on_download_done)
        self._download_thread.finished.connect(worker.deleteLater)
        self._download_thread.start()

    def _on_download_done(self) -> None:
        self._download_thread = None
        self._download_worker = None
        self.download_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)

    def _on_progress(self, status: dict) -> None:
        if status.get("phase") == "processing":
            self.progress.setFormat("⚙️ Processing…")
            self._log(f"⚙️ Post-processing {status.get('filename')}")
            return
        total = status.get("total") or 0
        downloaded = status.get("downloaded") or 0
        if total:
            self.progress.setValue(int(downloaded * 100 / total))
        speed = status.get("speed") or 0
        eta = status.get("eta")
        parts = [
            f"{human_size(downloaded)} / {human_size(total)}",
            f"{human_size(speed)}/s",
        ]
        if eta:
            parts.append(f"ETA {human_duration(eta)}")
        self.progress.setFormat(" ".join(parts))

    def _on_download_finished(self, path: str) -> None:
        self.progress.setValue(100)
        self.progress.setFormat("Done 🎉")
        resolved = self._resolve_download_path(path)
        self._log(f"🎉 Finished: {resolved or path or 'download complete'}")
        if not resolved:
            QMessageBox.information(
                self, "🎉 Download complete", path or "Done."
            )
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("🎉 Download complete")
        box.setText(f"Saved to:\n{resolved}")
        open_file_btn = box.addButton(
            "▶️ Open file", QMessageBox.ButtonRole.ActionRole
        )
        open_folder_btn = box.addButton(
            "📂 Open folder", QMessageBox.ButtonRole.ActionRole
        )
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        clicked = box.clickedButton()
        if clicked == open_file_btn:
            self._open_file(resolved)
        elif clicked == open_folder_btn:
            self._open_folder(resolved)

    @staticmethod
    def _resolve_download_path(path: str) -> str:
        """Return the real file on disk (merge may change the extension)."""
        if path and os.path.isfile(path):
            return path
        if not path:
            return ""
        base, _ = os.path.splitext(path)
        for ext in (".mp4", ".mkv", ".m4a", ".mp3", ".webm", ".opus"):
            candidate = base + ext
            if os.path.isfile(candidate):
                return candidate
        folder = os.path.dirname(path)
        stem = os.path.splitext(os.path.basename(path))[0]
        if folder and os.path.isdir(folder) and stem:
            matches = [
                f for f in os.listdir(folder) if f.startswith(stem)
            ]
            if matches:
                matches.sort()
                return os.path.join(folder, matches[0])
        return path if path else ""

    def _open_file(self, path: str) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self._log(f"⚠️ Could not open file: {path}")
            QMessageBox.warning(
                self, "⚠️ Cannot open file", f"Could not open:\n{path}"
            )

    def _open_folder(self, path: str) -> None:
        folder = os.path.dirname(path) or path
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            self._log(f"⚠️ Could not open folder: {folder}")
            QMessageBox.warning(
                self, "⚠️ Cannot open folder", f"Could not open:\n{folder}"
            )

    def _on_error(self, message: str) -> None:
        self._stop_analyze_animation(ok=False)
        self._log(f"❌ ERROR: {message}")
        self.progress.setRange(0, 100)
        self.progress.setFormat("Failed ❌")
        hint = self._cookie_hint(message)
        if hint:
            self._log(hint)
        QMessageBox.critical(self, "❌ Error", f"{message}\n\n{hint}" if hint else message)

    def _cookie_hint(self, message: str) -> str:
        lowered = message.lower()
        if "cannot parse data" in lowered and "facebook" in lowered:
            return (
                "Facebook did not return this video to an anonymous request -- "
                "it is usually a private or login-only post. Pick the browser "
                "you are logged into Facebook with in the 'Cookies' box (close "
                "it first), or use a cookies.txt file, then try again."
            )
        if "cookie" in lowered and (
            "could not copy" in lowered
            or "cookie database" in lowered
            or "could not load" in lowered
            or "failed to decrypt" in lowered
            or "cannot decrypt" in lowered
            or "cookie file" in lowered
        ):
            return (
                "VidGrab could not read the browser's cookies. Fully close "
                "the browser (check Task Manager for leftover background "
                "processes) and try again, or use the 'Cookies file...' "
                "button with a cookies.txt export. Firefox and Edge often "
                "work when Chrome blocks access."
            )
        triggers = (
            "logged-in",
            "logged in",
            "log in",
            "login required",
            "sign in",
            "private video",
            "cookies",
            "age-restricted",
            "age restricted",
            "requires authentication",
            "account credentials",
        )
        if not any(t in lowered for t in triggers):
            return ""
        return (
            "This video likely needs a logged-in session. Pick the browser "
            "you are logged in with in the 'Cookies' box (close it first), "
            "or choose a cookies.txt file, then try again."
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        for thread in (self._analyze_thread, self._download_thread):
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(2000)
        event.accept()


def _selftest() -> int:
    """Headless verification of a frozen build; writes JSON and exits."""
    import json
    import tempfile

    import PySide6
    import yt_dlp
    import downloader

    try:
        from yt_dlp.extractor import gen_extractor_classes

        extractor_count = len(list(gen_extractor_classes()))
    except Exception as exc:  # noqa: BLE001
        extractor_count = f"error: {exc}"

    try:
        import curl_cffi

        curl_cffi_version = curl_cffi.__version__
    except Exception as exc:  # noqa: BLE001
        curl_cffi_version = f"error: {exc}"

    result = {
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "python": sys.version.split()[0],
        "pyside6": PySide6.__version__,
        "yt_dlp": yt_dlp.version.__version__,
        "extractors": extractor_count,
        "curl_cffi": curl_cffi_version,
        "app_dir": downloader.app_dir(),
        "ffmpeg": downloader.find_ffmpeg(),
        "format_sample": downloader.build_options(
            "Video + Audio", 1080, tempfile.gettempdir()
        )["format"],
    }

    if result["ffmpeg"]:
        try:
            import subprocess

            proc = subprocess.run(
                [result["ffmpeg"], "-hide_banner", "-version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            banner = (proc.stdout or proc.stderr).splitlines()
            result["ffmpeg_version"] = banner[0] if banner else "no output"
        except Exception as exc:  # noqa: BLE001
            result["ffmpeg_version"] = f"error: {exc}"

    if "--url" in sys.argv:
        index = sys.argv.index("--url")
        if index + 1 < len(sys.argv):
            url = sys.argv[index + 1]
            try:
                with yt_dlp.YoutubeDL(
                    {
                        "quiet": True,
                        "no_warnings": True,
                        "skip_download": True,
                        "noplaylist": True,
                    }
                ) as ydl:
                    info = ydl.extract_info(url, download=False)
                result["extract"] = {
                    "ok": info.get("title"),
                    "extractor": info.get("extractor_key"),
                }
            except Exception as exc:  # noqa: BLE001
                result["extract"] = {"error": f"{type(exc).__name__}: {exc}"}

    path = os.path.join(tempfile.gettempdir(), "vidgrab_selftest.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    try:
        print(json.dumps(result, indent=2))
    except Exception:  # noqa: BLE001 - no console in windowed builds
        pass
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
