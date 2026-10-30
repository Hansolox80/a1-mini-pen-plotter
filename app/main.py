"""Main entry point for the A1 Mini Pen Plotter desktop application."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

# Ensure project root is on sys.path when launched directly or via PyInstaller
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from app import __app_name__, __version__
from app.core.platform_utils import get_user_app_data_dir, is_macos
from app.ui.main_window import MainWindow


def configure_logging() -> None:
    log_dir = get_user_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "a1_mini_pen_plotter.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{__app_name__} v{__version__}")
    parser.add_argument("--svg", type=str, default="", help="Optional SVG file path to open at startup.")
    parser.add_argument("--screenshot", type=str, default="", help="Capture UI screenshot to path and exit.")
    args = parser.parse_args(argv)

    configure_logging()

    # Enable High-DPI PassThrough and Retina scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv[:1])
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SoloDev")

    if is_macos():
        # Clean macOS menu integration
        app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    window = MainWindow(check_recovery=not bool(args.screenshot))
    if args.svg and Path(args.svg).exists():
        window.load_svg_file(args.svg, mark_dirty=False)

    window.show()

    if args.screenshot:
        out_path = Path(args.screenshot)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        def capture_and_quit() -> None:
            window.canvas.fit_plate_to_view()
            app.processEvents()
            pix = window.grab()
            pix.save(str(out_path), "PNG")
            app.quit()

        QTimer.singleShot(600, capture_and_quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
