import os
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTimer, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .gui import branding
from .gui.main_window import MainWindow

SPLASH_MS = 2500  # tempo mínimo da janela de abertura


def main() -> int:
    QLocale.setDefault(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    branding.load_fonts()
    app.setWindowIcon(QIcon(branding.mark_pixmap(256, 2)))
    tr = QTranslator(app)
    if tr.load("qtbase_pt_BR", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(tr)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_splash = "--sem-abertura" not in sys.argv and not os.environ.get("IDEFSIM_NO_SPLASH")

    splash = None
    if show_splash:
        splash = branding.SplashScreen(app.primaryScreen().devicePixelRatio())
        splash.show()
        app.processEvents()

    win = MainWindow(args[0] if args else None)

    if splash is None:
        win.show()
    else:
        def reveal():
            if splash.isVisible():
                win.show()
                splash.finish(win)
        splash.clicked.connect(reveal)
        QTimer.singleShot(SPLASH_MS, reveal)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
