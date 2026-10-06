"""Start one rqt plugin with a readable initial window size."""
from rqt_gui.main import Main
from python_qt_binding.QtCore import QTimer
from python_qt_binding.QtWidgets import QMainWindow


class NativeWindow(Main):
    def create_application(self, argv):
        app = super().create_application(argv)

        def resize():
            screen = app.primaryScreen().availableGeometry()
            for window in app.topLevelWidgets():
                if isinstance(window, QMainWindow) and window.isVisible():
                    window.resize(min(1100, screen.width()), min(720, screen.height()))

        QTimer.singleShot(500, resize)
        return app


if __name__ == "__main__":
    raise SystemExit(NativeWindow().main())
