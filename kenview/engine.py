"""
KenView engine: wires audio capture -> Deepgram websocket -> LLM question
detection together on a background QThread. Emits Qt signals the UI overlays
subscribe to.
"""
import asyncio
import json
import queue
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from kenview.audio.capture import AudioCaptureThread, RingBuffer, SAMPLE_RATE
from kenview.transcription.deepgram_client import DeepgramClient
from kenview.transcription.llm_client import QuestionDetector


class Engine(QThread):
    """Background pipeline thread.

    Signals:
        transcript(str)      - every finalized transcript chunk
        question(q: dict)    - question detected: {"answer": str}
        status(str)          - status line for the badge
    """

    transcript = pyqtSignal(str)
    question = pyqtSignal(object)
    status = pyqtSignal(str)

    # Detect a question after this much remote audio (cumulative)
    DETECT_EVERY_SECONDS = 6.0
    # Keep the last N transcript strings for the LLM window
    WINDOW_SIZE = 12

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._running = False
        self._stop = threading.Event()

        # Audio buffers (filled by capture thread, drained by us)
        self.loopback_buf = RingBuffer()
        self.mic_buf = RingBuffer()
        self.capture = None

        # Deepgram client + its event loop
        self.dg = None
        self.dg_loop = None
        self.audio_q = None

        # LLM detector
        self.detector = None

        # Recent transcript window
        self.history = []

    # ---- QThread entry point ----------------------------------------------

    def run(self):
        self._running = True
        self.status.emit("Starting audio capture...")

        # 1. Capture thread (WASAPI loopback + mic)
        self.capture = AudioCaptureThread(self.loopback_buf, self.mic_buf)
        self.capture.start()

        # 2. Transcription loop (Deepgram websocket)
        self.audio_q = queue.Queue()
        self.dg = DeepgramClient(
            api_key=self.store.get("deepgram_api_key"),
            on_final=self._on_final_text
        )
        self.dg_loop = threading.Thread(target=self.dg.run, args=(self.audio_q,), daemon=True)
        self.dg_loop.start()

        # 3. LLM detector
        self.detector = QuestionDetector(
            base_url=self.store.get("base_url"),
            api_key=self.store.get_api_key(),
            model=self.store.get("llm_model")
        )

        self.status.emit("Listening...")
        last_detect = time.monotonic()

        try:
            while not self._stop.is_set():
                # Drain captured audio -> send to Deepgram
                data = self.loopback_buf.drain()
                if data:
                    self.audio_q.put_nowait(data)
                if time.monotonic() - last_detect >= self.DETECT_EVERY_SECONDS:
                    # Natural pause: check if recent audio contains a question
                    window = self._window_text()
                    if window.strip():
                        out = self._analyze_async(window)
                        if out.get("is_question"):
                            self.question.emit(out)
                            self.history.append(("[answer]", out.get("answer", "")))
                    last_detect = time.monotonic()
                self.msleep(120)
        finally:
            self._running = False
            self.status.emit("Engine stopped.")

    # ---- Callbacks ----------------------------------------------------------

    def _on_final_text(self, text: str):
        """Called from the Deepgram recv loop (on the asyncio thread)."""
        self.history.append(text)
        if len(self.history) > self.WINDOW_SIZE:
            del self.history[: len(self.history) - self.WINDOW_SIZE]
        self.transcript.emit(text)

    def _window_text(self) -> str:
        return "\n".join(self.history[-self.WINDOW_SIZE:])

    def _analyze_async(self, window: str) -> dict:
        """Run the LLM call on a worker thread so the pump never blocks."""
        result = {}

        def worker():
            result.update(self.detector.analyze(window))

        worker_t = threading.Thread(target=worker, daemon=True)
        worker_t.start()
        worker_t.join(timeout=25)
        return result

    # ---- Lifecycle control ---------------------------------------------------

    def stop(self):
        self._stop.set()
        if self.capture:
            self.capture.stop()
            self.capture.wait()
        if self.dg_loop:
            self.audio_q.put_nowait(None) # Signal Deepgram to stop
            self.dg_loop.join()

    @pyqtSlot(str, str, str)
    def restart(self, base_url, api_key, llm_model):
        """Stop and restart the pipeline (e.g. after settings change)."""
        self.stop()
        self.wait(3000)
        
        # Re-init LLM detector with new params
        self.detector = QuestionDetector(
            base_url=base_url,
            api_key=api_key,
            model=llm_model
        )
        self.start()
