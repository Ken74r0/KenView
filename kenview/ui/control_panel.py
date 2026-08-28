from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QLabel, QFileDialog, QSlider, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSlot

class ControlPanel(QWidget):
    def __init__(self, store, overlay, engine):
        super().__init__()
        self.store = store
        self.overlay = overlay
        self.engine = engine
        self.setWindowTitle("KenView Control Panel")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # --- LLM Settings ---
        layout.addWidget(QLabel("LLM Base URL (OpenAI-compatible /chat/completions):"))
        self.url_input = QLineEdit(self.store.get("base_url", ""))
        layout.addWidget(self.url_input)

        layout.addWidget(QLabel("LLM Model:"))
        self.model_input = QLineEdit(self.store.get("llm_model", "gpt-4o-mini"))
        layout.addWidget(self.model_input)

        layout.addWidget(QLabel("LLM API Key (Bearer):"))
        self.key_input = QLineEdit(self.store.get_api_key())
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.key_input)

        # --- Audio/Transcription Settings ---
        layout.addWidget(QLabel("Deepgram API Key:"))
        self.dg_input = QLineEdit(self.store.get("deepgram_api_key", ""))
        self.dg_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.dg_input)
        
        # --- Actions ---
        btn_save = QPushButton("Apply & Save Settings")
        btn_save.clicked.connect(self.apply_settings)
        layout.addWidget(btn_save)

        self.btn_engine = QPushButton("▶ Start listening")
        self.btn_engine.clicked.connect(self.toggle_engine)
        layout.addWidget(self.btn_engine)
        
        self.btn_hide = QPushButton("Hide overlay")
        self.btn_hide.clicked.connect(self.toggle_overlay)
        layout.addWidget(self.btn_hide)

    def apply_settings(self):
        self.store.set("base_url", self.url_input.text().strip())
        self.store.set("llm_model", self.model_input.text().strip())
        self.store.set_api_key(self.key_input.text().strip())
        self.store.set("deepgram_api_key", self.dg_input.text().strip())
        # If engine is running, restart so new creds take effect
        if self.engine.isRunning():
            self.engine.restart(
                self.url_input.text().strip(),
                self.key_input.text().strip(),
                self.model_input.text().strip()
            )

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
