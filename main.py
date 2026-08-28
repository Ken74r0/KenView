import sys
from PyQt6.QtWidgets import QApplication

from kenview.store import Store
from kenview.ui.overlay_window import OverlayWindow
from kenview.ui.control_panel import ControlPanel
from kenview.engine import Engine


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running when overlay hidden

    store = Store()

    # Engine first (the pipeline), then UI that drives it
    engine = Engine(store)

    overlay = OverlayWindow(store)
    overlay.move(60, 60)

    panel = ControlPanel(store, overlay, engine)
    panel.show()

    # Wire engine signals -> overlay
    engine.status.connect(overlay.set_status)
    engine.transcript.connect(overlay.set_transcript)
    engine.question.connect(overlay.show_question)
    overlay.dismiss_requested.connect(lambda: None)

    # Auto-start listening on launch
    engine.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
