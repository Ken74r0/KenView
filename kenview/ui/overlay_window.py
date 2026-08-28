from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from kenview.native.display_affinity import set_exclude_from_capture


class OverlayWindow(QWidget):
    """Capture-excluded floating panel showing live transcript + drafted
    answers. Supports drag, resize, opacity and monitor selection."""

    dismiss_requested = pyqtSignal()

    def __init__(self, store):
        super().__init__()
        self.store = store

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._pinned = False
        self._old_pos = None
        self._resize_edge = 0

        self._init_ui()
        # Apply capture exclusion once the window has a native handle
        self.show()
        QApplication.processEvents()
        self.apply_affinity()

    # ---- UI ----------------------------------------------------------------

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        body = QWidget()
        body.setObjectName("body")
        body.setStyleSheet("""
            QWidget#body {
                background-color: rgba(25, 25, 30, 210);
                border: 1px solid #4a4a55;
                border-radius: 10px;
            }
            QLabel { color: #e0e0e0; background: transparent; border: none; }
            QLabel#head { color: #9aa0b0; font-size: 10px; }
            QLabel#q   { color: #ffd479; font-size: 14px; font-weight: bold; }
            QLabel#a   { color: #9fe3ff; font-size: 13px; }
            QPushButton {
                background: #33333d; color: #ccc; border: 1px solid #4a4a55;
                border-radius: 5px; padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { background: #41414d; }
            QPushButton#pin { color: #ffd479; }
            QPushButton#pin:checked { border-color: #ffd479; }
        """)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        # Header: status badge + pin
        head = QHBoxLayout()
        self.status_badge = QLabel("starting…")
        self.status_badge.setObjectName("head")
        head.addWidget(self.status_badge)
        head.addStretch(1)
        self.btn_pin = QPushButton("📌 pin")
        self.btn_pin.setObjectName("pin")
        self.btn_pin.setCheckable(True)
        self.btn_pin.clicked.connect(self.toggle_pin)
        head.addWidget(self.btn_pin)
        lay.addLayout(head)

        # Separator
        sep = QLabel("—" * 40)
        sep.setObjectName("head")
        lay.addWidget(sep)

        # Drafted question + answer
        self.question_label = QLabel("Waiting for a question…")
        self.question_label.setObjectName("q")
        self.question_label.setWordWrap(True)
        lay.addWidget(self.question_label)

        self.answer_label = QLabel("")
        self.answer_label.setObjectName("a")
        self.answer_label.setWordWrap(True)
        lay.addWidget(self.answer_label)

        # Buttons for the current drafted answer
        btns = QHBoxLayout()
        self.btn_dismiss = QPushButton("✕ dismiss")
        self.btn_dismiss.setEnabled(False)
        self.btn_dismiss.clicked.connect(self.dismiss_answer)
        btns.addWidget(self.btn_dismiss)
        btns.addStretch(1)
        lay.addLayout(btns)

        outer.addWidget(body)

        self._body = body
        self.setMinimumSize(300, 140)
        self.resize(420, 260)

    # ---- API for the UI to feed --------------------------------------------

    def set_transcript(self, text: str):
        """Live transcript (shown as a compact rolling line for context)."""
        t = " ".join(text.split())
        # Keep header usable; only update if short enough to be useful
        if len(t) > 220:
            t = t[:220] + "…"
        self.status_badge.setText(t)

    def show_question(self, q: dict):
        """Show a drafted answer; pin keeps it on screen."""
        self.question_label.setText("💬 Incoming question detected")
        self.answer_label.setText(q.get("answer", ""))
        self.btn_dismiss.setEnabled(True)
        if not self.isVisible():
            self.show()

    def set_status(self, text: str):
        self.status_badge.setText(text)

    def apply_affinity(self):
        hwnd = int(self.winId())
        ok = set_exclude_from_capture(hwnd, True)
        if not ok:
            self.status_badge.setText("⚠ capture exclusion unavailable")
        elif not self._pinned:
            pass

    # ---- Pin / dismiss -----------------------------------------------------

    def toggle_pin(self):
        self._pinned = self.btn_pin.isChecked()
        self.btn_pin.setText("📌 pinned" if self._pinned else "📌 pin")

    def dismiss_answer(self):
        self.answer_label.setText("")
        self.question_label.setText("Waiting for a question…")
        self.btn_dismiss.setEnabled(False)
        self.dismiss_requested.emit()

    # ---- Dragging -----------------------------------------------------------

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._old_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._old_pos is not None:
            delta = e.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._old_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self._old_pos = None

    # ---- Resize / hide ------------------------------------------------------

    def set_opacity(self, value: float):
        self.setWindowOpacity(max(0.1, min(1.0, value)))

    def move_to_monitor(self, index: int):
        screens = QApplication.screens()
        if 0 <= index < len(screens):
            geo = screens[index].availableGeometry()
            self.move(geo.center().x() - self.width() // 2,
                      geo.center().y() - self.height() // 2)

    # On close, remember we're hidden, not quit
    def hideEvent(self, e):
        super().hideEvent(e)
