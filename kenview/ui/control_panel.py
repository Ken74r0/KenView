from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QFileDialog, QSlider, QComboBox
)
from PyQt6.QtCore import Qt

from kenview.context.document_loader import extract_text


class ControlPanel(QWidget):
    """Settings form. Also acts as the engine controller (start/stop)."""

    def __init__(self, store, overlay, engine):
        super().__init__()
        self.store = store
        self.overlay = overlay
        self.engine = engine
        self.setWindowTitle("KenView Control Panel")
        self._init_ui()
        self._on_engine_status = None

    def _init_ui(self):
        lay = QVBoxLayout(self)

        # --- LLM endpoint (OpenAI-compatible) ---
        lay.addWidget(QLabel("LLM Base URL (OpenAI-compatible /chat/completions):"))
        self.url_input = QLineEdit(self.store.get("base_url", ""))
        lay.addWidget(self.url_input)

        lay.addWidget(QLabel("LLM API Key (Bearer):"))
        self.key_input = QLineEdit(self.store.get_api_key())
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self.key_input)

        lay.addWidget(QLabel("Deepgram API Key:"))
        self.dg_input = QLineEdit(self.store.get("deepgram_api_key", ""))
        self.dg_input.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self.dg_input)

        # --- Reference document ---
        lay.addWidget(QLabel("Reference document:"))
        row = QHBoxLayout()
        self.file_label = QLabel(self.store.get("reference_filename") or "none loaded")
        row.addWidget(self.file_label, 1)
        b = QPushButton("Upload")
        b.clicked.connect(self.upload_file)
        row.addWidget(b)
        lay.addLayout(row)

        # --- Polishing: opacity + monitor ---
        lay.addWidget(QLabel("Overlay opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(95)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.overlay.set_opacity(v / 100.0)
        )
        lay.addWidget(self.opacity_slider)

        lay.addWidget(QLabel("Monitor:"))
        self.monitor_combo = QComboBox()
        self.refresh_monitors()
        self.monitor_combo.currentIndexChanged.connect(self.change_monitor)
        lay.addWidget(self.monitor_combo)

        # --- Controls ---
        ctrl = QHBoxLayout()
        self.btn_apply = QPushButton("Apply & Save")
        self.btn_apply.clicked.connect(self.apply_settings)
        ctrl.addWidget(self.btn_apply)

        self.btn_engine = QPushButton("▶ Start listening")
        self.btn_engine.clicked.connect(self.toggle_engine)
        ctrl.addWidget(self.btn_engine)

        self.btn_hide = QPushButton("Hide overlay")
        self.btn_hide.clicked.connect(self.toggle_overlay)
        ctrl.addWidget(self.btn_hide)
        lay.addLayout(ctrl)

    def refresh_monitors(self):
        try:
            screens = QApplication.screens()
        except Exception:
            screens = []
        self.monitor_combo.clear()
        for i, s in enumerate(screens):
            self.monitor_combo.addItem(f"Monitor {i + 1} — {s.size().width()}×{s.size().height()}")
        if not screens:
            self.monitor_combo.addItem("Monitor 1")

    def change_monitor(self, idx):
        self.overlay.move_to_monitor(idx)

    def upload_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Open reference", "", "Documents (*.txt *.md *.pdf *.docx *.doc)"
        )
        if f:
            text = extract_text(f)
            self.store.set("reference_filename", f)
            self.store.set("reference_text", text)
            self.file_label.setText(f)

    # ---- Persist settings -------------------------------------------------

    def apply_settings(self):
        self.store.set("base_url", self.url_input.text().strip())
        self.store.set_api_key(self.key_input.text().strip())
        self.store.set("deepgram_api_key", self.dg_input.text().strip())
        # If engine is running, restart so new creds take effect
        if self.engine.isRunning():
            self.engine.restart()

    def toggle_engine(self):
        if self.engine.isRunning():
            self.engine.stop()
            self.btn_engine.setText("▶ Start listening")
        else:
            self.engine.start()
            self.btn_engine.setText("⏹ Stop listening")

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
            self.btn_hide.setText("Show overlay")
        else:
            self.overlay.show()
            self.btn_hide.setText("Hide overlay")

    def set_status(self, text):
        if hasattr(self, "status_label"):
            self.status_label.setText(text)
