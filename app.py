# -*- coding: utf-8 -*-
# app.py — PipeAgent Application Entry Point
"""
PipeAgent — Piping Execution Operating System
═══════════════════════════════════════════════════════════
Startup Orchestrator
Version : 5.2.3 (Production)
Engine  : PyQt6

Startup Contract
────────────────
1. QApplication is created first — nothing heavy runs before it.
2. The splash screen is shown and given a chance to paint one frame.
3. All heavy work (database, license, auth) runs in staged callbacks
   AFTER the Qt event loop is alive, so splash animations stay smooth.
4. MainWindow is constructed only after successful authentication and
   defers its own 31 execution modules to the event loop.
5. Strong references are retained to prevent premature garbage collection.
"""

from __future__ import annotations

import sys
import logging
import traceback
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QObject
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog

from core.logging_config import setup_logger
from config import APP_NAME, APP_VERSION, ORG_NAME

from db.manager import DatabaseManager
from security.session import SessionManager
from services.auth.service import AuthService
from services.license import init_trial, check_license

from ui.splash import StartupSplash
from ui.main_window import MainWindow
from ui.dialogs.login_dialog import LoginDialog
from ui.dialogs.license_dialog import LicenseDialog

logger = setup_logger(__name__)


# ═══════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════

SPLASH_DURATION_MS = 6000       # حداکثر مدت انیمیشن اسپلش
FIRST_FRAME_DELAY_MS = 60       # فرصت رسم اولین فریم اسپلش
STAGE_DELAY_MS = 30             # فاصله بین مراحل راه‌اندازی
WATCHDOG_TIMEOUT_MS = 25_000    # نگهبان ضدقفل‌شدگی راه‌اندازی

LOGO_PATH = "assets/logo.png"


# ═══════════════════════════════════════════════════════════
#  EXIT CODES
# ═══════════════════════════════════════════════════════════

EXIT_OK = 0
EXIT_DB_FAILURE = 1
EXIT_LICENSE_DECLINED = 2
EXIT_LOGIN_CANCELLED = 3
EXIT_FATAL = 4


# ═══════════════════════════════════════════════════════════
#  BOOTSTRAPPER
# ═══════════════════════════════════════════════════════════

class PipeAgentBootstrapper(QObject):
    """
    Staged startup controller.

    Every stage is scheduled through the Qt event loop so that the splash
    screen keeps animating and Windows never marks the process as
    "Not Responding" during startup.
    """

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app

        # Strong references — these MUST stay alive for the whole session.
        self.splash: Optional[StartupSplash] = None
        self.db: Optional[DatabaseManager] = None
        self.session_manager: Optional[SessionManager] = None
        self.auth_service: Optional[AuthService] = None
        self.main_window: Optional[MainWindow] = None

        # Flow guards
        self._login_started = False
        self._startup_complete = False
        self._exit_code = EXIT_OK

        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog_timeout)

    # ───────────────────────────────────────────────────────
    #  ENTRY
    # ───────────────────────────────────────────────────────

    def start(self):
        """Show the splash and schedule the first startup stage."""
        self.splash = StartupSplash(
            logo_path=LOGO_PATH,
            duration_ms=SPLASH_DURATION_MS,
        )
        self.splash.animation_finished.connect(self._open_login)
        self.splash.show()

        # Retain on the application object as an extra safety net.
        self.app._splash = self.splash

        self._watchdog.start(WATCHDOG_TIMEOUT_MS)

        # Let the splash paint its first frame before doing any work.
        QTimer.singleShot(FIRST_FRAME_DELAY_MS, self._stage_database)

    # ───────────────────────────────────────────────────────
    #  STAGE 1 — DATABASE
    # ───────────────────────────────────────────────────────

    def _stage_database(self):
        self._splash_message("[DB]       Initializing piping project database…")

        try:
            self.db = DatabaseManager()
            initialized = self.db.initialize()
        except Exception as exc:
            logger.exception("Database initialization raised an exception")
            self._fatal(
                "Database Error",
                "PipeAgent could not initialize its database.\n\n"
                f"{type(exc).__name__}: {exc}",
                EXIT_DB_FAILURE,
            )
            return

        if not initialized:
            logger.error("DatabaseManager.initialize() returned False")
            self._fatal(
                "Database Error",
                "PipeAgent could not initialize its database.\n\n"
                "Please verify the data folder permissions and try again.",
                EXIT_DB_FAILURE,
            )
            return

        logger.info("Database initialized successfully")
        QTimer.singleShot(STAGE_DELAY_MS, self._stage_license)

    # ───────────────────────────────────────────────────────
    #  STAGE 2 — LICENSE
    # ───────────────────────────────────────────────────────

    def _stage_license(self):
        self._splash_message("[SEC]      Verifying license and security policy…")

        try:
            init_trial(self.db)
            license_valid = check_license(self.db)
        except Exception:
            logger.exception("License validation failed")
            license_valid = False

        if license_valid:
            QTimer.singleShot(STAGE_DELAY_MS, self._stage_auth)
            return

        # A modal dialog must never appear behind the always-on-top splash.
        logger.warning("License invalid or expired — prompting user")
        self.splash.suspend()

        try:
            dialog = LicenseDialog(self.db)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        except Exception as exc:
            logger.exception("License dialog failed")
            self._fatal(
                "License Error",
                f"The license dialog could not be opened.\n\n"
                f"{type(exc).__name__}: {exc}",
                EXIT_FATAL,
            )
            return

        if not accepted:
            logger.info("License activation declined by user")
            self._shutdown(EXIT_LICENSE_DECLINED)
            return

        self.splash.resume()
        QTimer.singleShot(STAGE_DELAY_MS, self._stage_auth)

    # ───────────────────────────────────────────────────────
    #  STAGE 3 — AUTH SERVICES
    # ───────────────────────────────────────────────────────

    def _stage_auth(self):
        self._splash_message("[AUTH]     Preparing secure authentication layer…")

        try:
            self.auth_service = AuthService(self.db)
            self.session_manager = SessionManager()
        except Exception as exc:
            logger.exception("Authentication layer failed to initialize")
            self._fatal(
                "Security Error",
                f"The authentication layer could not be prepared.\n\n"
                f"{type(exc).__name__}: {exc}",
                EXIT_FATAL,
            )
            return

        QTimer.singleShot(STAGE_DELAY_MS, self._stage_finish_splash)

    # ───────────────────────────────────────────────────────
    #  STAGE 4 — HAND OVER TO SPLASH
    # ───────────────────────────────────────────────────────

    def _stage_finish_splash(self):
        """
        Core services are ready. Ask the splash to fast-forward.
        `animation_finished` will trigger `_open_login`.
        """
        self._splash_message("[SYS]      Core ready — opening secure login…")
        self.splash.finish_startup()

    # ───────────────────────────────────────────────────────
    #  LOGIN
    # ───────────────────────────────────────────────────────

    def _open_login(self):
        """Triggered by StartupSplash.animation_finished (exactly once)."""
        if self._login_started:
            return

        # Guard: the watchdog may fire before services are ready.
        if self.auth_service is None or self.session_manager is None:
            logger.warning("Login requested before services were ready — ignoring")
            return

        self._login_started = True
        self._watchdog.stop()

        # Detach the splash cleanly before showing a modal dialog.
        try:
            if self.splash is not None:
                self.splash.close()
                self.splash.deleteLater()
        except Exception:
            logger.debug("Splash close skipped", exc_info=True)
        finally:
            self.splash = None
            self.app._splash = None

        # Give Qt one clean turn between closing the splash and the dialog.
        QTimer.singleShot(0, self._show_login_dialog)

    def _show_login_dialog(self):
        logger.info("Opening login dialog")

        try:
            login = LoginDialog(self.auth_service)
            accepted = login.exec() == QDialog.DialogCode.Accepted
        except Exception as exc:
            logger.exception("Login dialog failed")
            self._fatal(
                "Login Error",
                f"The login window could not be opened.\n\n"
                f"{type(exc).__name__}: {exc}",
                EXIT_FATAL,
            )
            return

        if not accepted:
            logger.info("Login cancelled by user")
            self._shutdown(EXIT_LOGIN_CANCELLED)
            return

        user = login.get_authenticated_user()
        if user is None:
            logger.error("Login accepted but no user object was returned")
            QMessageBox.critical(
                None,
                "Login Error",
                "Authentication failed. No user profile was returned.",
            )
            self._shutdown(EXIT_FATAL)
            return

        self.session_manager.start_session(user)
        logger.info("Session started for user '%s'", self.session_manager.username)

        self._launch_main_window()

    # ───────────────────────────────────────────────────────
    #  MAIN WINDOW
    # ───────────────────────────────────────────────────────

    def _launch_main_window(self):
        """
        Build and display the workspace shell.

        MainWindow constructs only its shell here; the 31 execution modules
        are loaded incrementally by its own deferred loader.
        """
        try:
            window = MainWindow(self.db, self.session_manager)
        except Exception as exc:
            logger.exception("Main window construction failed")
            QMessageBox.critical(
                None,
                "PipeAgent Startup Error",
                "The main workspace could not be started.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                "See logs/pipeagent.log for details.",
            )
            try:
                self.session_manager.end_session()
            except Exception:
                logger.debug("Session cleanup skipped", exc_info=True)
            self._shutdown(EXIT_FATAL)
            return

        # Strong references (window + application attribute).
        self.main_window = window
        self.app._main_window = window

        window.show()
        window.raise_()
        window.activateWindow()
        window.setWindowState(
            (window.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )

        # Some window managers need a second nudge after the first paint.
        QTimer.singleShot(120, lambda: (window.raise_(), window.activateWindow()))

        # From now on, closing the main window must terminate the application.
        self.app.setQuitOnLastWindowClosed(True)

        self._startup_complete = True
        logger.info(
            "PipeAgent v%s workspace launched (user=%s)",
            APP_VERSION,
            self.session_manager.username,
        )

    # ───────────────────────────────────────────────────────
    #  HELPERS
    # ───────────────────────────────────────────────────────

    def _splash_message(self, text: str):
        if self.splash is not None:
            try:
                self.splash.message(text)
            except RuntimeError:
                # Splash was already destroyed.
                self.splash = None

    def _on_watchdog_timeout(self):
        """Recover if a startup stage silently stalled."""
        if self._startup_complete or self._login_started:
            return

        logger.error("Startup watchdog fired — startup appears to be stalled")

        if self.auth_service is not None and self.session_manager is not None:
            # Services are ready, only the splash signal was lost.
            self._open_login()
            return

        self._fatal(
            "Startup Timeout",
            "PipeAgent could not complete its startup sequence.\n\n"
            "Please restart the application. If the problem persists, "
            "see logs/pipeagent.log.",
            EXIT_FATAL,
        )

    def _fatal(self, title: str, message: str, exit_code: int):
        """Show a blocking error and terminate the startup sequence."""
        self._watchdog.stop()

        try:
            if self.splash is not None:
                self.splash.close()
                self.splash = None
        except Exception:
            logger.debug("Splash close skipped during fatal handling", exc_info=True)

        QMessageBox.critical(None, title, message)
        self._shutdown(exit_code)

    def _shutdown(self, exit_code: int):
        """Close everything and quit the event loop with a defined code."""
        self._exit_code = exit_code
        self._watchdog.stop()

        try:
            if self.splash is not None:
                self.splash.close()
                self.splash = None
        except Exception:
            logger.debug("Splash cleanup skipped", exc_info=True)

        try:
            if self.db is not None and hasattr(self.db, "close"):
                self.db.close()
        except Exception:
            logger.debug("Database cleanup skipped", exc_info=True)

        logger.info("Shutting down with exit code %d", exit_code)
        self.app.exit(exit_code)

    @property
    def exit_code(self) -> int:
        return self._exit_code


# ═══════════════════════════════════════════════════════════
#  GLOBAL EXCEPTION HOOK
# ═══════════════════════════════════════════════════════════

def _install_excepthook():
    """Log unhandled exceptions instead of letting Qt swallow them."""

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        logger.critical(
            "Unhandled exception:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )

        try:
            QMessageBox.critical(
                None,
                "PipeAgent — Unexpected Error",
                f"An unexpected error occurred:\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                "See logs/pipeagent.log for the full trace.",
            )
        except Exception:
            pass

    sys.excepthook = _hook


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main() -> int:
    # High-DPI policy must be set before QApplication is constructed.
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except AttributeError:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)

    # During startup only dialogs exist; closing one must not quit the app.
    app.setQuitOnLastWindowClosed(False)

    _install_excepthook()

    logger.info("═" * 60)
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)
    logger.info("═" * 60)

    bootstrapper = PipeAgentBootstrapper(app)
    app._bootstrapper = bootstrapper      # strong reference
    bootstrapper.start()

    result = app.exec()
    logger.info("Qt event loop finished with code %d", result)
    return result or bootstrapper.exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C)")
        sys.exit(EXIT_OK)
    except Exception:
        logger.exception("Fatal error in application entry point")
        sys.exit(EXIT_FATAL)