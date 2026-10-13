# -*- coding: utf-8 -*-
"""Regression tests for the shared Persian Sky application theme."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui import theme


def test_palette_uses_persian_sky_primary():
    assert theme.PRIMARY == "#0F9D9A"
    assert theme.SKY == "#54C5E8"
    assert theme.BG == "#EAF4F6"
    assert theme.SURFACE == "#FFFFFF"


def test_theme_applies_shared_stylesheet():
    app = QApplication.instance() or QApplication([])
    theme.apply_persian_sky(app)

    stylesheet = app.styleSheet()
    assert app.style().objectName().lower() == "fusion"
    assert "#0F9D9A" in stylesheet
    assert "#EAF4F6" in stylesheet
    assert "QPushButton" in stylesheet
    assert "QLineEdit" in stylesheet


def test_splash_uses_the_shared_light_palette():
    from ui.splash import StartupSplash

    assert StartupSplash.BG_DEEP == theme.BG
    assert StartupSplash.BG_PANEL == theme.SURFACE
    assert StartupSplash.PRIMARY == theme.PRIMARY
